"""
Ingestion service — upload → parse → detect → extract → persist → index.

Simple, reliable, sequential pipeline. No LangGraph, no MCP.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

import structlog

from app.config import settings
from app.db.engine import get_session
from app.db import repositories as repo
from app.db.fts import index_chunk
from app.domain.entities import ParsedStatement
from app.domain.errors import (
    ClassificationError,
    DocumentIngestionError,
    DocumentParseError,
    ExtractionError,
    UnsupportedFileTypeError,
)
from app.parsers.base import get_parser_registry
from app.parsers.pdf import parse_pdf

logger = structlog.get_logger(__name__)

_RECURRING_KEYWORDS = [
    "netflix", "spotify", "hulu", "apple.com", "google *", "amazon prime",
    "youtube", "disney+", "sling", "adobe", "microsoft", "dropbox",
    "icloud", "nytimes", "wsj", "gym", "subscription", "membership",
    "verizon", "t-mobile", "at&t", "comcast", "xfinity",
]


def _is_likely_recurring(description: str) -> bool:
    desc_lower = description.lower()
    return any(kw in desc_lower for kw in _RECURRING_KEYWORDS)

# Chunk size for FTS indexing (characters)
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Institution display names
INSTITUTION_NAMES = {
    "morgan_stanley": "Morgan Stanley",
    "chase": "Chase",
    "etrade": "E*TRADE",
    "amex": "American Express",
    "discover": "Discover",
}


async def ingest_document(
    file_path: Path,
    original_filename: str,
    file_hash: str | None = None,
    source_file_path: str | None = None,
    account_product: str | None = None,
    source_id: str | None = None,
    institution_slug: str | None = None,
    account_slug: str | None = None,
    statement_year: int | None = None,
    statement_month: int | None = None,
    bucket: str | None = None,
    document_id: str | None = None,
) -> str:
    """Full ingestion pipeline for a single document.

    Steps:
    1. Register document in DB
    2. Parse PDF → raw text + tables
    3. Detect institution (parser registry)
    4. Extract structured data (parser.extract)
    5. Persist canonical records
    6. Save bank-specific details
    7. Chunk text and index in FTS5
    8. Optionally generate embeddings

    Extra keyword args are populated when the file originates from the local scanner
    (file_hash for dedup, source_file_path for provenance, account_product for UI labels).
    Pass document_id to pre-assign the ID (used by bulk upload).

    Returns:
        document_id
    """
    doc_id = document_id or str(uuid.uuid4())

    async with get_session() as session:
        # Step 1: Register document
        doc = await repo.create_document(
            session,
            id=doc_id,
            original_filename=original_filename,
            stored_filename=file_path.name,
            file_path=str(file_path),
            file_size_bytes=file_path.stat().st_size,
            mime_type="application/pdf",
            status="processing",
            file_hash=file_hash,
            source_file_path=source_file_path,
            account_product=account_product,
            source_id=source_id,
        )
        logger.info("ingest.registered", doc_id=doc_id, filename=original_filename)

    try:
        log = logger.bind(
            doc_id=doc_id,
            filename=original_filename,
            statement_year=statement_year,
            statement_month=statement_month,
            account_slug=account_slug,
            status_before="processing",
        )

        # Step 2: Parse PDF
        parsed_doc = await parse_pdf(file_path)
        log.info("ingest.parsed", pages=parsed_doc.page_count)

        async with get_session() as session:
            await repo.update_document(session, doc_id, page_count=parsed_doc.page_count)

        # Step 3: Detect institution
        registry = get_parser_registry()
        sample_text = parsed_doc.full_text[:3000]
        parser, confidence = registry.detect_institution(sample_text)

        if parser is None:
            async with get_session() as session:
                await repo.update_document(session, doc_id,
                    status="failed", error_message="Could not identify institution")
            log.warning("ingest.classify_failed", status_after="failed")
            raise ClassificationError("No parser matched the document")

        institution_type = parser.institution_type
        log = log.bind(institution=institution_type, parser=type(parser).__name__)
        log.info("ingest.classified", confidence=confidence)

        async with get_session() as session:
            await repo.update_document(session, doc_id, institution_type=institution_type)

        # Step 4: Extract structured data
        parsed_stmt = await parser.extract(parsed_doc)
        log.info("ingest.extracted",
                 account_type=parsed_stmt.account_type,
                 account_masked=parsed_stmt.account_number_masked,
                 period_start=str(parsed_stmt.period_start) if parsed_stmt.period_start else None,
                 period_end=str(parsed_stmt.period_end) if parsed_stmt.period_end else None,
                 transactions=len(parsed_stmt.transactions),
                 fees=len(parsed_stmt.fees),
                 holdings=len(parsed_stmt.holdings),
                 balances=len(parsed_stmt.balances))

        # Step 5: Persist canonical records
        await persist_canonical(doc_id, institution_type, parsed_stmt)
        log.info("ingest.persisted_canonical",
                 transactions=len(parsed_stmt.transactions),
                 fees=len(parsed_stmt.fees),
                 balances=len(parsed_stmt.balances),
                 holdings=len(parsed_stmt.holdings))

        # Step 6: Chunk and index text
        chunk_count = await chunk_and_index(doc_id, institution_type, parsed_doc)
        log.info("ingest.chunked", chunks=chunk_count)

        # Mark complete
        async with get_session() as session:
            await repo.update_document(session, doc_id,
                status="parsed", processed_time=datetime.utcnow())

        log.info("ingest.complete", status_after="parsed",
                 transactions=len(parsed_stmt.transactions),
                 fees=len(parsed_stmt.fees),
                 balances=len(parsed_stmt.balances),
                 holdings=len(parsed_stmt.holdings),
                 chunks=chunk_count)
        return doc_id

    except (DocumentParseError, ClassificationError, ExtractionError) as exc:
        async with get_session() as session:
            await repo.update_document(session, doc_id,
                status="failed", error_message=str(exc))
        raise
    except Exception as exc:
        logger.error("ingest.unexpected_error", doc_id=doc_id, error=str(exc))
        async with get_session() as session:
            await repo.update_document(session, doc_id,
                status="failed", error_message=f"Unexpected error: {exc}")
        raise DocumentIngestionError(f"Ingestion failed: {exc}") from exc


def _account_name_from_product(account_product: str | None) -> str | None:
    """Derive a card/account name from a document's account_product label.

    "Chase — Prime Visa" → "Prime Visa"; "American Express — Blue Cash" → "Blue Cash".
    Returns None when there's nothing usable.
    """
    if not account_product:
        return None
    # Split on em/en dash or hyphen-with-spaces; take the trailing product segment.
    parts = re.split(r"\s*[—–]\s*|\s+-\s+", account_product)
    tail = parts[-1].strip() if parts else account_product.strip()
    return tail or None


async def persist_canonical(doc_id: str, institution_type: str, stmt: ParsedStatement) -> None:
    """Persist extracted data into canonical tables."""
    async with get_session() as session:
        # Get or create institution
        inst = await repo.get_or_create_institution(
            session, institution_type,
            INSTITUTION_NAMES.get(institution_type, institution_type.title())
        )

        # Resolve a stable account name. The parser rarely reads a masked card
        # number for credit cards, so fall back to the document's account_product
        # (set at upload time) — this keeps Prime / Freedom / Sapphire as distinct
        # accounts instead of collapsing into one "unknown" Chase account.
        doc = await repo.get_document(session, doc_id)
        account_name = stmt.account_name or _account_name_from_product(doc.account_product)

        # Get or create account
        acct = await repo.get_or_create_account(
            session,
            institution_id=inst.id,
            institution_type=institution_type,
            account_number_masked=stmt.account_number_masked or "unknown",
            account_type=stmt.account_type,
            account_name=account_name,
        )

        # Create statement
        from datetime import date as date_type
        statement = await repo.create_statement(
            session,
            document_id=doc_id,
            institution_id=inst.id,
            institution_type=institution_type,
            account_id=acct.id,
            account_type=stmt.account_type,
            statement_type=stmt.statement_type,
            period_start=stmt.period_start or date_type.today(),
            period_end=stmt.period_end or date_type.today(),
            extraction_status="success" if stmt.transactions or stmt.holdings else "partial",
            overall_confidence=stmt.confidence,
            warnings=json.dumps(stmt.warnings),
        )

        # Transactions
        if stmt.transactions:
            await repo.bulk_create_transactions(session, [
                {
                    "account_id": acct.id,
                    "statement_id": statement.id,
                    "transaction_date": t.transaction_date,
                    "settlement_date": t.settlement_date,
                    "description": t.description,
                    "merchant_name": t.merchant_name,
                    "transaction_type": t.transaction_type,
                    "category": t.category,
                    "amount": str(t.amount),
                    "quantity": str(t.quantity) if t.quantity else None,
                    "price_per_unit": str(t.price_per_unit) if t.price_per_unit else None,
                    "symbol": t.symbol,
                    "is_recurring": _is_likely_recurring(t.description or ""),
                    "confidence": t.confidence,
                    "source_page": t.source_page,
                }
                for t in stmt.transactions
            ])

        # Fees
        if stmt.fees:
            await repo.bulk_create_fees(session, [
                {
                    "account_id": acct.id,
                    "statement_id": statement.id,
                    "fee_date": f.fee_date,
                    "description": f.description,
                    "amount": str(f.amount),
                    "fee_category": f.fee_category,
                    "annualized_rate": str(f.annualized_rate) if f.annualized_rate else None,
                    "confidence": f.confidence,
                    "source_page": f.source_page,
                }
                for f in stmt.fees
            ])

        # Holdings
        if stmt.holdings:
            await repo.bulk_create_holdings(session, [
                {
                    "account_id": acct.id,
                    "statement_id": statement.id,
                    "symbol": h.symbol,
                    "description": h.description,
                    "quantity": str(h.quantity) if h.quantity else None,
                    "price": str(h.price) if h.price else None,
                    "market_value": str(h.market_value),
                    "cost_basis": str(h.cost_basis) if h.cost_basis else None,
                    "unrealized_gain_loss": str(h.unrealized_gain_loss) if h.unrealized_gain_loss else None,
                    "percent_of_portfolio": str(h.percent_of_portfolio) if h.percent_of_portfolio else None,
                    "asset_class": h.asset_class,
                    "confidence": h.confidence,
                    "source_page": h.source_page,
                }
                for h in stmt.holdings
            ])

        # Balance snapshots
        if stmt.balances:
            await repo.bulk_create_balance_snapshots(session, [
                {
                    "account_id": acct.id,
                    "statement_id": statement.id,
                    "snapshot_date": b.snapshot_date,
                    "total_value": str(b.total_value),
                    "cash_value": str(b.cash_value) if b.cash_value else None,
                    "invested_value": str(b.invested_value) if b.invested_value else None,
                    "unrealized_gain_loss": str(b.unrealized_gain_loss) if b.unrealized_gain_loss else None,
                    "confidence": b.confidence,
                    "source_page": b.source_page,
                }
                for b in stmt.balances
            ])

        # Bank-specific details
        if stmt.institution_details:
            await repo.create_institution_detail(
                session, institution_type, statement.id, stmt.institution_details
            )

        logger.info("ingest.persisted", doc_id=doc_id, statement_id=statement.id)


async def chunk_and_index(doc_id: str, institution_type: str, parsed_doc) -> int:
    """Chunk document text and index in FTS5. Returns number of chunks created."""
    chunks = []
    for page in parsed_doc.pages:
        text = page.raw_text
        if not text.strip():
            continue

        # Simple overlapping chunking
        start = 0
        chunk_idx = len(chunks)
        while start < len(text):
            end = min(start + CHUNK_SIZE, len(text))
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({
                    "document_id": doc_id,
                    "chunk_index": chunk_idx,
                    "content": chunk_text,
                    "page_number": page.page_number,
                    "institution_type": institution_type,
                })
                chunk_idx += 1
            start += CHUNK_SIZE - CHUNK_OVERLAP

    if not chunks:
        return 0

    # Save chunks to DB
    async with get_session() as session:
        saved = await repo.bulk_create_text_chunks(session, chunks)

    # Index in FTS5
    for chunk_data, model in zip(chunks, saved):
        await index_chunk(
            chunk_id=model.id,
            content=chunk_data["content"],
            document_id=doc_id,
            institution_type=institution_type,
            page_number=chunk_data.get("page_number"),
        )

    logger.info("ingest.indexed", doc_id=doc_id, chunks=len(chunks))
    return len(chunks)
