"""
Reprocess / backfill service.

Repairs documents whose downstream tables were never populated (or were populated
partially) by an earlier ingestion run — without re-uploading or deleting the PDF.

Key operations:
  - clear_document_child_records(doc_id)  : safely remove ONLY this document's
        statements/transactions/fees/holdings/balances/chunks/embeddings/FTS rows.
        The document row itself is never touched.
  - reprocess_document(doc_id)            : clear → re-parse → re-extract →
        re-persist → re-chunk → re-embed → set status parsed/failed.
  - find_documents_missing_data()         : detect "parsed but incomplete" docs.
  - ingestion_health()                    : aggregate + per-document issue report.

This deliberately reuses the parser pipeline pieces from app.services.ingestion
(persist_canonical, chunk_and_index, _generate_embeddings) so there is a single
extraction/persistence implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from app.config import settings
from app.db import repositories as repo
from app.db.engine import get_session
from app.db.fts import delete_fts_for_document
from app.db.models import DocumentModel
from app.parsers.base import get_parser_registry
from app.parsers.pdf import parse_pdf
from app.services.ingestion import (
    _generate_embeddings,
    chunk_and_index,
    persist_canonical,
)

logger = structlog.get_logger(__name__)


# ── Incompleteness detection ──────────────────────────────────────────────────

# Issue codes used in the health report.
ISSUE_ZERO_TRANSACTIONS = "zero_transactions"
ISSUE_ZERO_CHUNKS = "zero_chunks"
ISSUE_MISSING_EMBEDDINGS = "missing_embeddings"
ISSUE_MISSING_INSTITUTION = "missing_institution"
ISSUE_MISSING_MONTH = "missing_month"
ISSUE_MISSING_YEAR = "missing_year"
ISSUE_NO_STATEMENT = "no_statement_persisted"
ISSUE_STUCK_PROCESSING = "stuck_processing"
ISSUE_FAILED = "failed"

# A statement that legitimately has no transactions (e.g. brokerage holdings-only
# statements). We still flag zero_transactions but don't treat those institutions
# as "must have transactions" for the complete/incomplete verdict.
_HOLDINGS_INSTITUTIONS = {"morgan_stanley", "etrade"}


@dataclass
class DocIssues:
    document_id: str
    filename: str
    status: str
    issues: list[str] = field(default_factory=list)

    @property
    def recommended_action(self) -> str:
        if not self.issues:
            return "none"
        if self.issues == [ISSUE_FAILED]:
            return "reprocess"
        return "reprocess"

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "status": self.status,
            "issues": self.issues,
            "recommended_action": self.recommended_action,
        }


async def _inspect_document(session, doc: DocumentModel) -> DocIssues:
    """Compute the list of data-completeness issues for one document.

    "Zero transactions" is only treated as a problem for *transaction-style*
    statements (credit cards, checking). Holdings/advisory statements (Morgan
    Stanley, E*TRADE) routinely have no transactions — they carry holdings,
    balances, and/or fees instead — so an empty transactions table there is
    expected, not a defect.
    """
    from app.api.documents import normalize_status  # local import avoids cycle

    status = normalize_status(doc.status)
    issues: list[str] = []

    if status == "failed":
        issues.append(ISSUE_FAILED)
    if status == "processing":
        issues.append(ISSUE_STUCK_PROCESSING)

    stmts = await repo.get_statements_for_document(session, doc.id)
    txn_count = await repo.count_transactions_for_document(session, doc.id)
    chunk_count = await repo.count_chunks_for_document(session, doc.id)
    emb_count = await repo.count_chunks_for_document(session, doc.id, with_embedding=True)
    holdings_count = await repo.count_holdings_for_document(session, doc.id)
    balance_count = await repo.count_balances_for_document(session, doc.id)
    fee_count = await repo.count_fees_for_document(session, doc.id)

    is_holdings_style = (doc.institution_type or "").lower() in _HOLDINGS_INSTITUTIONS
    # Does the document carry any financial signal at all?
    has_any_financial_data = bool(
        txn_count or holdings_count or balance_count or fee_count
    )

    if not stmts:
        issues.append(ISSUE_NO_STATEMENT)

    if txn_count == 0:
        # For holdings-style statements, zero transactions is only a problem when
        # the doc also has no holdings/balances/fees (i.e. nothing was extracted).
        if is_holdings_style:
            if not has_any_financial_data:
                issues.append(ISSUE_ZERO_TRANSACTIONS)
        else:
            issues.append(ISSUE_ZERO_TRANSACTIONS)

    if chunk_count == 0:
        issues.append(ISSUE_ZERO_CHUNKS)
    if settings.search.vector_search_enabled and chunk_count > 0 and emb_count == 0:
        issues.append(ISSUE_MISSING_EMBEDDINGS)
    if not doc.institution_type or doc.institution_type == "unknown":
        issues.append(ISSUE_MISSING_INSTITUTION)

    # Month/year come from the parsed statement period.
    anchor = None
    if stmts:
        ends = [s.period_end for s in stmts if s.period_end]
        anchor = max(ends) if ends else None
    if anchor is None:
        issues.append(ISSUE_MISSING_MONTH)
        issues.append(ISSUE_MISSING_YEAR)

    return DocIssues(document_id=doc.id, filename=doc.original_filename, status=status, issues=issues)


def _is_incomplete(di: DocIssues) -> bool:
    """A parsed document is 'incomplete' if it's missing data it should have.

    _inspect_document already accounts for holdings-style statements (it won't add
    ISSUE_ZERO_TRANSACTIONS for an advisory statement that has balances/fees), so
    here any remaining flagged issue means the document genuinely needs attention.
    """
    if di.status == "failed":
        return True
    return bool(di.issues)


async def find_documents_missing_data() -> list[DocIssues]:
    """Return parsed-but-incomplete (or failed) documents that should be reprocessed."""
    async with get_session() as session:
        docs = await repo.list_documents(session)
        out: list[DocIssues] = []
        for doc in docs:
            di = await _inspect_document(session, doc)
            if _is_incomplete(di):
                out.append(di)
    return out


# ── Ingestion health report ───────────────────────────────────────────────────

async def ingestion_health() -> dict[str, Any]:
    """Aggregate completeness metrics + per-document issues."""
    async with get_session() as session:
        docs = await repo.list_documents(session)
        per_doc: list[DocIssues] = [await _inspect_document(session, doc) for doc in docs]

    summary = {
        "total_documents": len(docs),
        "complete_documents": sum(1 for d in per_doc if not d.issues),
        "missing_transactions": sum(1 for d in per_doc if ISSUE_ZERO_TRANSACTIONS in d.issues),
        "missing_chunks": sum(1 for d in per_doc if ISSUE_ZERO_CHUNKS in d.issues),
        "missing_embeddings": sum(1 for d in per_doc if ISSUE_MISSING_EMBEDDINGS in d.issues),
        "missing_metadata": sum(
            1 for d in per_doc
            if {ISSUE_MISSING_INSTITUTION, ISSUE_MISSING_MONTH, ISSUE_MISSING_YEAR} & set(d.issues)
        ),
        "stuck_processing": sum(1 for d in per_doc if ISSUE_STUCK_PROCESSING in d.issues),
        "failed": sum(1 for d in per_doc if d.status == "failed"),
        "incomplete_documents": sum(1 for d in per_doc if _is_incomplete(d)),
    }
    issues = [d.to_dict() for d in per_doc if d.issues]
    return {"summary": summary, "documents": issues}


# ── Safe per-document cleanup ─────────────────────────────────────────────────

async def clear_document_child_records(doc_id: str) -> dict[str, int]:
    """Delete ONLY this document's downstream rows. Never deletes the document row.

    Removes: statements (+ transactions/fees/holdings/balances/bank-details via the
    existing cascade helper), text chunks (+ stored embeddings), and FTS rows.
    """
    async with get_session() as session:
        txn_before = await repo.count_transactions_for_document(session, doc_id)
        chunk_before = await repo.count_chunks_for_document(session, doc_id)

        # Statements + their child rows (transactions/fees/holdings/balances/details).
        await repo.delete_statements_for_document(session, doc_id)
        # Text chunks + embeddings (embeddings are a column on text_chunks).
        chunks_deleted = await repo.delete_chunks_for_document(session, doc_id)

    # FTS rows live in a virtual table — delete outside the ORM session.
    await delete_fts_for_document(doc_id)

    logger.info(
        "reprocess.cleared_children",
        doc_id=doc_id,
        transactions_removed=txn_before,
        chunks_removed=chunks_deleted or chunk_before,
    )
    return {"transactions_removed": txn_before, "chunks_removed": chunks_deleted}


# ── Reprocess a single document ───────────────────────────────────────────────

@dataclass
class ReprocessResult:
    document_id: str
    filename: str
    status_before: str
    status_after: str
    ok: bool
    transactions: int = 0
    fees: int = 0
    balances: int = 0
    holdings: int = 0
    chunks: int = 0
    embeddings: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


async def reprocess_document(doc_id: str) -> ReprocessResult:
    """Re-run the full extraction pipeline for an existing document.

    Steps: load doc → locate PDF → clear stale child rows → set processing →
    parse → classify → extract → persist → chunk → embed → set parsed/failed.
    The PDF file and the document row are preserved throughout.
    """
    async with get_session() as session:
        doc = await repo.get_document(session, doc_id)
        status_before = doc.status
        filename = doc.original_filename
        file_path = Path(doc.file_path)

    log = logger.bind(doc_id=doc_id, filename=filename, status_before=status_before)

    if not file_path.exists():
        msg = f"Source PDF not found: {file_path}"
        async with get_session() as session:
            await repo.update_document(session, doc_id, status="failed", error_message=msg)
        log.error("reprocess.file_missing", status_after="failed", error=msg)
        return ReprocessResult(doc_id, filename, status_before, "failed", ok=False, error=msg)

    # 1. Clear stale partial rows for THIS document only.
    await clear_document_child_records(doc_id)

    # 2. Mark processing.
    async with get_session() as session:
        await repo.update_document(session, doc_id, status="processing", error_message=None)

    try:
        # 3. Parse.
        parsed_doc = await parse_pdf(file_path)
        async with get_session() as session:
            await repo.update_document(session, doc_id, page_count=parsed_doc.page_count)

        # 4. Classify.
        registry = get_parser_registry()
        parser, confidence = registry.detect_institution(parsed_doc.full_text[:3000])
        if parser is None:
            msg = "Could not identify institution"
            async with get_session() as session:
                await repo.update_document(session, doc_id, status="failed", error_message=msg)
            log.warning("reprocess.classify_failed", status_after="failed")
            return ReprocessResult(doc_id, filename, status_before, "failed", ok=False, error=msg)

        institution_type = parser.institution_type
        log = log.bind(institution=institution_type, parser=type(parser).__name__)
        async with get_session() as session:
            await repo.update_document(session, doc_id, institution_type=institution_type)

        # 5. Extract.
        stmt = await parser.extract(parsed_doc)
        log.info("reprocess.extracted",
                 confidence=confidence,
                 account_type=stmt.account_type,
                 period_start=str(stmt.period_start) if stmt.period_start else None,
                 period_end=str(stmt.period_end) if stmt.period_end else None,
                 transactions=len(stmt.transactions), fees=len(stmt.fees),
                 holdings=len(stmt.holdings), balances=len(stmt.balances))

        # 6. Persist canonical.
        await persist_canonical(doc_id, institution_type, stmt)

        # 7. Chunk + index.
        chunk_count = await chunk_and_index(doc_id, institution_type, parsed_doc)

        # 8. Embeddings (non-fatal).
        embedded = 0
        if settings.search.vector_search_enabled:
            embedded = await _generate_embeddings(doc_id)

        # 9. Mark parsed.
        async with get_session() as session:
            await repo.update_document(session, doc_id, status="parsed",
                                       processed_time=datetime.utcnow())

        log.info("reprocess.complete", status_after="parsed",
                 transactions=len(stmt.transactions), fees=len(stmt.fees),
                 balances=len(stmt.balances), holdings=len(stmt.holdings),
                 chunks=chunk_count, embeddings=embedded)

        return ReprocessResult(
            doc_id, filename, status_before, "parsed", ok=True,
            transactions=len(stmt.transactions), fees=len(stmt.fees),
            balances=len(stmt.balances), holdings=len(stmt.holdings),
            chunks=chunk_count, embeddings=embedded,
        )

    except Exception as exc:  # noqa: BLE001
        async with get_session() as session:
            await repo.update_document(session, doc_id, status="failed", error_message=str(exc))
        log.error("reprocess.failed", status_after="failed", error=str(exc))
        return ReprocessResult(doc_id, filename, status_before, "failed", ok=False, error=str(exc))


# ── Batch helpers ─────────────────────────────────────────────────────────────

async def reprocess_documents(doc_ids: list[str]) -> list[ReprocessResult]:
    """Reprocess a list of documents sequentially (safe for SQLite)."""
    results: list[ReprocessResult] = []
    for doc_id in doc_ids:
        results.append(await reprocess_document(doc_id))
    return results


async def all_document_ids() -> list[str]:
    async with get_session() as session:
        docs = await repo.list_documents(session)
        return [d.id for d in docs]


async def failed_document_ids() -> list[str]:
    from app.api.documents import normalize_status
    async with get_session() as session:
        docs = await repo.list_documents(session)
        return [d.id for d in docs if normalize_status(d.status) == "failed"]


async def missing_data_document_ids() -> list[str]:
    issues = await find_documents_missing_data()
    return [d.document_id for d in issues]
