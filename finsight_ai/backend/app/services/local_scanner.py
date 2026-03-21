"""
Local filesystem scanner — discovers statement PDFs from configured source folders.

This is the primary data-ingestion front door. The flow is:

  1. Iterate over STATEMENT_SOURCES (config/statement_sources.py).
  2. Glob each source's root_path for PDFs (recurse into YYYY/ subdirs).
  3. Compute SHA-256 for each file.
  4. Check the documents table to see if already ingested (by file_hash).
  5. Classify each file as: INGESTED | PENDING | FAILED.
  6. Return a ScanResult summary + flat list of pending DiscoveredFiles.

The scanner is read-only; it never writes to the DB.
Ingestion is triggered separately via the /scan/ingest endpoint.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.statement_sources import (
    PARSEABLE_INSTITUTION_TYPES,
    STATEMENT_SOURCES,
    StatementSource,
)
from app.db.models import DocumentModel

logger = structlog.get_logger(__name__)


# ── Value types ───────────────────────────────────────────────────────────────

class IngestStatus(str, Enum):
    PENDING   = "pending"    # found on disk, not yet in DB
    INGESTED  = "ingested"   # already in DB with status=parsed
    FAILED    = "failed"     # in DB but with status=failed (will retry)
    NO_PARSER = "no_parser"  # institution has no parser yet (bofa, marcus)


@dataclass
class DiscoveredFile:
    """A single PDF discovered during a scan, enriched with dedup metadata."""
    source_id: str
    institution_type: str
    account_product: str
    bucket: str
    absolute_path: Path
    filename: str
    file_hash: str
    file_size_bytes: int
    last_modified_at: datetime
    year: int | None           # inferred from parent directory name if numeric
    ingest_status: IngestStatus
    # Only set when ingest_status == INGESTED or FAILED
    document_id: str | None = None


@dataclass
class SourceSummary:
    """Per-source aggregated counts returned by a scan."""
    source_id: str
    institution_type: str
    account_product: str
    bucket: str
    root_path: str
    total_files: int = 0
    ingested: int = 0
    pending: int = 0
    failed: int = 0
    no_parser: int = 0
    latest_file_date: str | None = None    # ISO date of newest file mtime
    latest_statement_date: str | None = None  # ISO date from DB period_end


@dataclass
class ScanResult:
    """Top-level result returned by scan_all_sources()."""
    sources: list[SourceSummary] = field(default_factory=list)
    discovered_files: list[DiscoveredFile] = field(default_factory=list)
    pending_files: list[DiscoveredFile] = field(default_factory=list)
    total_discovered: int = 0
    total_ingested: int = 0
    total_pending: int = 0
    total_failed: int = 0
    total_no_parser: int = 0
    scanned_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ── Core scanner ──────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file efficiently."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _infer_year(path: Path) -> int | None:
    """Try to extract a 4-digit year from a parent directory name."""
    for part in path.parts:
        if len(part) == 4 and part.isdigit():
            yr = int(part)
            if 2000 <= yr <= 2100:
                return yr
    return None


async def scan_all_sources(session: AsyncSession) -> ScanResult:
    """
    Scan all configured statement sources and return a ScanResult.

    Hits the filesystem and the DB; does NOT perform any ingestion.
    """
    # Load all existing file_hashes from the DB in one query for fast dedup.
    existing: dict[str, tuple[str, str]] = {}  # hash → (document_id, status)
    rows = await session.execute(
        select(DocumentModel.file_hash, DocumentModel.id, DocumentModel.status)
        .where(DocumentModel.file_hash.isnot(None))
    )
    for file_hash, doc_id, status in rows.fetchall():
        if file_hash:
            existing[file_hash] = (doc_id, status)

    result = ScanResult()

    for source in STATEMENT_SOURCES:
        summary, files = _scan_source(source, existing)
        result.sources.append(summary)
        result.discovered_files.extend(files)

    # Flatten counts
    result.total_discovered = len(result.discovered_files)
    result.total_ingested   = sum(1 for f in result.discovered_files if f.ingest_status == IngestStatus.INGESTED)
    result.total_pending    = sum(1 for f in result.discovered_files if f.ingest_status == IngestStatus.PENDING)
    result.total_failed     = sum(1 for f in result.discovered_files if f.ingest_status == IngestStatus.FAILED)
    result.total_no_parser  = sum(1 for f in result.discovered_files if f.ingest_status == IngestStatus.NO_PARSER)
    result.pending_files    = [f for f in result.discovered_files if f.ingest_status in (IngestStatus.PENDING, IngestStatus.FAILED)]

    logger.info(
        "scanner.complete",
        total=result.total_discovered,
        pending=result.total_pending,
        ingested=result.total_ingested,
    )
    return result


def _scan_source(
    source: StatementSource,
    existing: dict[str, tuple[str, str]],
) -> tuple[SourceSummary, list[DiscoveredFile]]:
    """
    Scan one StatementSource folder. Returns (SourceSummary, list of DiscoveredFile).
    Pure filesystem + existing-hash lookup — no DB writes.
    """
    summary = SourceSummary(
        source_id=source.source_id,
        institution_type=source.institution_type,
        account_product=source.account_product,
        bucket=source.bucket,
        root_path=str(source.root_path),
    )
    files: list[DiscoveredFile] = []

    if not source.root_path.exists():
        logger.debug("scanner.source_missing", source_id=source.source_id, path=str(source.root_path))
        return summary, files

    # Glob PDFs (recurses into YYYY/ subdirs via **)
    pdf_paths = sorted(source.root_path.glob(source.glob_pattern))

    # When multiple sources share the same root_path (Chase products),
    # filter by filename_hints so each source only claims its own files.
    if source.filename_hints:
        pdf_paths = [
            p for p in pdf_paths
            if any(hint.lower() in p.stem.lower() for hint in source.filename_hints)
        ]

    latest_mtime: float | None = None

    for pdf_path in pdf_paths:
        try:
            stat = pdf_path.stat()
            mtime = stat.st_mtime
            if latest_mtime is None or mtime > latest_mtime:
                latest_mtime = mtime

            file_hash = _sha256(pdf_path)
            year = _infer_year(pdf_path)

            # Determine ingest status
            if source.institution_type not in PARSEABLE_INSTITUTION_TYPES:
                status = IngestStatus.NO_PARSER
            elif file_hash in existing:
                doc_id, doc_status = existing[file_hash]
                status = IngestStatus.INGESTED if doc_status == "parsed" else IngestStatus.FAILED
            else:
                status = IngestStatus.PENDING
                doc_id = None

            doc_id_val = existing.get(file_hash, (None,))[0] if file_hash in existing else None

            df = DiscoveredFile(
                source_id=source.source_id,
                institution_type=source.institution_type,
                account_product=source.account_product,
                bucket=source.bucket,
                absolute_path=pdf_path,
                filename=pdf_path.name,
                file_hash=file_hash,
                file_size_bytes=stat.st_size,
                last_modified_at=datetime.fromtimestamp(mtime),
                year=year,
                ingest_status=status,
                document_id=doc_id_val,
            )
            files.append(df)

            # Update summary counts
            if status == IngestStatus.INGESTED:
                summary.ingested += 1
            elif status == IngestStatus.PENDING:
                summary.pending += 1
            elif status == IngestStatus.FAILED:
                summary.failed += 1
            elif status == IngestStatus.NO_PARSER:
                summary.no_parser += 1

        except OSError as exc:
            logger.warning("scanner.file_error", path=str(pdf_path), error=str(exc))

    summary.total_files = len(files)
    if latest_mtime is not None:
        summary.latest_file_date = datetime.fromtimestamp(latest_mtime).date().isoformat()

    return summary, files
