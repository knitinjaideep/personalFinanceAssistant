"""
Scan API — local folder scanner endpoints.

GET  /api/v1/scan/status  — scan all configured folders, return counts (no ingestion).
POST /api/v1/scan/ingest  — scan then ingest all pending (not-yet-ingested) files.

The scanner reads from STATEMENT_SOURCES in config/statement_sources.py.
Files are deduped via SHA-256 so re-scanning never re-ingests the same file.
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.db.engine import get_session
from app.services.local_scanner import IngestStatus, ScanResult, scan_all_sources
from app.services.ingestion import ingest_document

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/scan", tags=["scan"])


# ── Response schemas ──────────────────────────────────────────────────────────

class SourceSummaryResponse(BaseModel):
    source_id: str
    institution_type: str
    account_product: str
    bucket: str
    root_path: str
    total_files: int
    ingested: int
    pending: int
    failed: int
    no_parser: int
    latest_file_date: str | None


class ScanStatusResponse(BaseModel):
    sources: list[SourceSummaryResponse]
    total_discovered: int
    total_ingested: int
    total_pending: int
    total_failed: int
    total_no_parser: int
    scanned_at: str


class IngestResultResponse(BaseModel):
    ingested: int
    skipped: int     # already ingested
    failed: int
    no_parser: int
    errors: list[str]
    scan: ScanStatusResponse


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scan_to_response(result: ScanResult) -> ScanStatusResponse:
    return ScanStatusResponse(
        sources=[
            SourceSummaryResponse(
                source_id=s.source_id,
                institution_type=s.institution_type,
                account_product=s.account_product,
                bucket=s.bucket,
                root_path=s.root_path,
                total_files=s.total_files,
                ingested=s.ingested,
                pending=s.pending,
                failed=s.failed,
                no_parser=s.no_parser,
                latest_file_date=s.latest_file_date,
            )
            for s in result.sources
        ],
        total_discovered=result.total_discovered,
        total_ingested=result.total_ingested,
        total_pending=result.total_pending,
        total_failed=result.total_failed,
        total_no_parser=result.total_no_parser,
        scanned_at=result.scanned_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status", response_model=ScanStatusResponse)
async def get_scan_status():
    """
    Scan all configured local folders and return per-source counts.

    This is a read-only operation — no files are ingested.
    Used by the Home page to show "X files found, Y ingested, Z pending".
    """
    async with get_session() as session:
        result = await scan_all_sources(session)
    return _scan_to_response(result)


@router.post("/ingest", response_model=IngestResultResponse)
async def ingest_pending_files():
    """
    Scan all configured local folders then ingest every pending file.

    - Files already in the DB (by SHA-256 hash) are skipped.
    - Files from institutions without a parser are counted as no_parser.
    - Each file is ingested sequentially to avoid overloading Ollama.
    - Returns a summary of what was ingested, skipped, or failed.
    """
    async with get_session() as session:
        scan = await scan_all_sources(session)

    ingested = 0
    failed = 0
    errors: list[str] = []

    pending = scan.pending_files  # PENDING + FAILED from prior attempts

    logger.info("scan.ingest_start", pending=len(pending))

    for df in pending:
        try:
            await ingest_document(
                file_path=df.absolute_path,
                original_filename=df.filename,
                file_hash=df.file_hash,
                source_file_path=str(df.absolute_path),
                account_product=df.account_product,
                source_id=df.source_id,
            )
            ingested += 1
            logger.info("scan.ingested", file=df.filename, source=df.source_id)
        except Exception as exc:
            failed += 1
            msg = f"{df.filename}: {exc}"
            errors.append(msg)
            logger.warning("scan.ingest_failed", file=df.filename, error=str(exc))

    # Re-scan to get fresh counts after ingestion
    async with get_session() as session:
        updated_scan = await scan_all_sources(session)

    logger.info("scan.ingest_complete", ingested=ingested, failed=failed)

    return IngestResultResponse(
        ingested=ingested,
        skipped=scan.total_ingested,   # was already ingested before this run
        failed=failed,
        no_parser=scan.total_no_parser,
        errors=errors,
        scan=_scan_to_response(updated_scan),
    )
