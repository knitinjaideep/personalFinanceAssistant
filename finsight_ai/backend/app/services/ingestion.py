"""
Ingestion service — upload → parse → detect → extract → persist → index.

Simple, reliable, sequential pipeline. No LangGraph, no MCP.
"""

from __future__ import annotations

import json
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


async def ingest_document(file_path: Path, original_filename: str) -> str:
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

    Returns:
        document_id
    """
    doc_id = str(uuid.uuid4())

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
        )
        logger.info("ingest.registered", doc_id=doc_id, filename=original_filename)

    try:
        # Step 2: Parse PDF
        parsed_doc = await parse_pdf(file_path)

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
            raise ClassificationError("No parser matched the document")

        institution_type = parser.institution_type
        logger.info("ingest.classified", doc_id=doc_id,
                   institution=institution_type, confidence=confidence)

        async with get_session() as session:
            await repo.update_document(session, doc_id, institution_type=institution_type)

        # Step 4: Extract structured data
        parsed_stmt = await parser.extract(parsed_doc)
        logger.info("ingest.extracted", doc_id=doc_id,
                   transactions=len(parsed_stmt.transactions),
                   fees=len(parsed_stmt.fees),
                   holdings=len(parsed_stmt.holdings),
                   balances=len(parsed_stmt.balances))

        # Step 5: Persist canonical records
        await _persist_canonical(doc_id, institution_type, parsed_stmt)

        # Step 6: Chunk and index text
        await _chunk_and_index(doc_id, institution_type, parsed_doc)

        # Step 7: Optionally generate embeddings
        if settings.search.vector_search_enabled:
            await _generate_embeddings(doc_id)

        # Mark complete
        async with get_session() as session:
            await repo.update_document(session, doc_id,
                status="parsed", processed_time=datetime.utcnow())

        logger.info("ingest.complete", doc_id=doc_id)
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


async def _persist_canonical(doc_id: str, institution_type: str, stmt: ParsedStatement) -> None:
    """Persist extracted data into canonical tables."""
    async with get_session() as session:
        # Get or create institution
        inst = await repo.get_or_create_institution(
            session, institution_type,
            INSTITUTION_NAMES.get(institution_type, institution_type.title())
        )

        # Get or create account
        acct = await repo.get_or_create_account(
            session,
            institution_id=inst.id,
            institution_type=institution_type,
            account_number_masked=stmt.account_number_masked or "unknown",
            account_type=stmt.account_type,
            account_name=stmt.account_name,
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


async def _chunk_and_index(doc_id: str, institution_type: str, parsed_doc) -> None:
    """Chunk document text and index in FTS5."""
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
        return

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


async def _generate_embeddings(doc_id: str) -> None:
    """Generate vector embeddings for document chunks (optional)."""
    try:
        from app.services.llm import embed as embed_texts

        async with get_session() as session:
            chunks = await repo.get_chunks_for_document(session, doc_id)

        if not chunks:
            return

        # Batch embed
        texts = [c.content for c in chunks]
        batch_size = 10
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = await embed_texts(batch)
            all_embeddings.extend(embeddings)

        # Store embeddings
        async with get_session() as session:
            for chunk, emb in zip(chunks, all_embeddings):
                chunk.embedding = json.dumps(emb)
                session.add(chunk)
            await session.flush()

        logger.info("ingest.embedded", doc_id=doc_id, chunks=len(chunks))

    except Exception as exc:
        # Embedding failure is non-fatal
        logger.warning("ingest.embedding_failed", doc_id=doc_id, error=str(exc))
