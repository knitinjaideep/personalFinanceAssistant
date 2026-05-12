"""
Document upload and management API endpoints.

Upload flow:
  POST /api/v1/documents/upload-local
    — structured upload: institution/account/year/month → normalized filename
    — saves into correct Coral folder (creates year sub-dir if needed)
    — SHA-256 dedup, full ingestion pipeline

  POST /api/v1/documents/upload  (legacy / quick drop)
    — accepts source_id + year (old behavior)
    — kept for backward compatibility

  GET /api/v1/documents/{doc_id}/status
    — lightweight status poll for upload progress tracking
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime
from pathlib import Path

import structlog
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import select

from app.config import settings
from app.config.statement_catalog import (
    CATALOG_BY_SLUGS,
    normalize_filename,
    safe_dest_path,
    validate_upload,
)
from app.db.engine import get_session
from app.db import repositories as repo
from app.db.fts import delete_fts_for_document
from app.db.models import DocumentModel
from app.domain.entities import (
    BulkUploadFileResult,
    BulkUploadSummary,
    DocumentSummary,
    DocumentUploadResponse,
)
from app.services.ingestion import ingest_document
from app.statement_sources import SOURCES_BY_ID

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_pdf(file: UploadFile, contents: bytes) -> None:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.storage.allowed_extensions:
        raise HTTPException(
            400,
            f"File type '{ext}' not supported. Only PDF files are accepted.",
        )
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.storage.max_file_size_mb:
        raise HTTPException(
            400,
            f"File too large ({size_mb:.1f} MB). Max: {settings.storage.max_file_size_mb} MB",
        )


async def _dedup_check(file_hash: str) -> DocumentUploadResponse | None:
    """Return a response if the hash already exists in the DB."""
    async with get_session() as session:
        existing = await session.execute(
            select(DocumentModel.id, DocumentModel.status, DocumentModel.original_filename)
            .where(DocumentModel.file_hash == file_hash)
        )
        row = existing.fetchone()
        if row:
            return DocumentUploadResponse(
                document_id=row[0],
                filename=row[2] or "",
                status=row[1],
                message="File already ingested (duplicate SHA-256).",
            )
    return None


# ── Upload-local (structured upload) ─────────────────────────────────────────

@router.post("/upload-local", response_model=DocumentUploadResponse)
async def upload_local(
    file: UploadFile = File(...),
    institution_slug: str = Form(...),
    account_slug: str = Form(...),
    year: int = Form(...),
    month: int = Form(...),
):
    """
    Structured upload: place a PDF into the correct Coral folder.

    Form fields:
        file              — PDF file (required)
        institution_slug  — e.g. "chase"
        account_slug      — e.g. "sapphire_preferred"
        year              — 4-digit year, e.g. 2025
        month             — 1–12

    The file is saved as:
        $CORAL_STATEMENTS_ROOT/<rel_path>/<year>/<account_slug>_<year>_<MM>_<month>.pdf

    If a file with the same SHA-256 already exists, the existing record is returned.
    If a normalized file already exists at the destination with a DIFFERENT hash, a
    collision suffix is appended to avoid clobbering existing data.
    """
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    contents = await file.read()
    _validate_pdf(file, contents)
    file_hash = _sha256_bytes(contents)

    # Dedup check
    duped = await _dedup_check(file_hash)
    if duped:
        return duped

    # Validate catalog params
    try:
        entry = validate_upload(institution_slug, account_slug, year, month)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    # Compute safe destination
    try:
        dest_path = safe_dest_path(institution_slug, account_slug, year, month)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    # Create year folder if needed
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Collision guard: if dest exists with a different hash, append suffix
    if dest_path.exists():
        existing_hash = _sha256_bytes(dest_path.read_bytes())
        if existing_hash != file_hash:
            stem = dest_path.stem
            dest_path = dest_path.parent / f"{stem}_{uuid.uuid4().hex[:6]}.pdf"

    dest_path.write_bytes(contents)

    account_product = f"{entry.institution_label} — {entry.account_label}"
    source_id = f"{institution_slug}__{account_slug}"
    original_filename = file.filename

    async def _ingest() -> None:
        try:
            await ingest_document(
                file_path=dest_path,
                original_filename=original_filename,
                file_hash=file_hash,
                source_file_path=str(dest_path),
                account_product=account_product,
                source_id=source_id,
                institution_slug=institution_slug,
                account_slug=account_slug,
                statement_year=year,
                statement_month=month,
                bucket=entry.bucket,
            )
        except Exception as exc:
            logger.error("upload_local.ingest_failed", filename=original_filename, error=str(exc))

    doc_id = str(uuid.uuid4())
    asyncio.create_task(_ingest())

    logger.info(
        "upload_local.accepted",
        filename=original_filename,
        institution=institution_slug,
        account=account_slug,
        year=year,
        month=month,
        dest=str(dest_path),
    )

    return DocumentUploadResponse(
        document_id=doc_id,
        filename=original_filename,
        status="processing",
        message=f"Saving to {dest_path.name}…",
    )


# ── Bulk upload-local ─────────────────────────────────────────────────────────

@router.post("/bulk-upload-local", response_model=BulkUploadSummary)
async def bulk_upload_local(
    files: list[UploadFile] = File(...),
    institution_slugs: str = Form(...),   # JSON array of strings
    account_slugs: str = Form(...),       # JSON array of strings
    years: str = Form(...),               # JSON array of ints
    months: str = Form(...),              # JSON array of ints
):
    """
    Bulk structured upload: accept multiple PDFs with per-file metadata.

    Form fields:
        files             — list of PDF files
        institution_slugs — JSON array, one entry per file
        account_slugs     — JSON array, one entry per file
        years             — JSON array of ints, one entry per file
        months            — JSON array of ints, one entry per file

    Each file is processed independently. Failures do not abort the batch.
    Returns a BulkUploadSummary with per-file BulkUploadFileResult entries.
    """
    import json

    try:
        inst_list:  list[str] = json.loads(institution_slugs)
        acct_list:  list[str] = json.loads(account_slugs)
        year_list:  list[int] = [int(y) for y in json.loads(years)]
        month_list: list[int] = [int(m) for m in json.loads(months)]
    except Exception as exc:
        raise HTTPException(400, f"Malformed metadata arrays: {exc}")

    if not (len(files) == len(inst_list) == len(acct_list) == len(year_list) == len(month_list)):
        raise HTTPException(
            400,
            f"Length mismatch: {len(files)} files but metadata arrays have "
            f"lengths institution_slugs={len(inst_list)}, account_slugs={len(acct_list)}, "
            f"years={len(year_list)}, months={len(month_list)}"
        )

    results: list[BulkUploadFileResult] = []

    for file, institution_slug, account_slug, year, month in zip(
        files, inst_list, acct_list, year_list, month_list
    ):
        fname = file.filename or "unknown.pdf"

        # Validate PDF
        try:
            contents = await file.read()
            _validate_pdf(file, contents)
        except HTTPException as exc:
            results.append(BulkUploadFileResult(
                filename=fname,
                outcome="failed",
                error_message=exc.detail,
            ))
            continue

        file_hash = _sha256_bytes(contents)

        # Dedup
        duped = await _dedup_check(file_hash)
        if duped:
            results.append(BulkUploadFileResult(
                filename=fname,
                outcome="duplicate_skipped",
                document_id=duped.document_id,
            ))
            continue

        # Validate catalog
        try:
            entry = validate_upload(institution_slug, account_slug, year, month)
        except ValueError as exc:
            results.append(BulkUploadFileResult(
                filename=fname,
                outcome="failed",
                error_message=str(exc),
            ))
            continue

        # Compute safe path
        try:
            dest_path = safe_dest_path(institution_slug, account_slug, year, month)
        except ValueError as exc:
            results.append(BulkUploadFileResult(
                filename=fname,
                outcome="failed",
                error_message=str(exc),
            ))
            continue

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if dest_path.exists():
            existing_hash = _sha256_bytes(dest_path.read_bytes())
            if existing_hash != file_hash:
                stem = dest_path.stem
                dest_path = dest_path.parent / f"{stem}_{uuid.uuid4().hex[:6]}.pdf"

        dest_path.write_bytes(contents)

        account_product = f"{entry.institution_label} — {entry.account_label}"
        source_id = f"{institution_slug}__{account_slug}"
        doc_id = str(uuid.uuid4())

        async def _ingest(
            _dest=dest_path,
            _fname=fname,
            _hash=file_hash,
            _ap=account_product,
            _sid=source_id,
            _inst=institution_slug,
            _acct=account_slug,
            _yr=year,
            _mo=month,
            _bkt=entry.bucket,
            _did=doc_id,
        ) -> None:
            try:
                await ingest_document(
                    file_path=_dest,
                    original_filename=_fname,
                    file_hash=_hash,
                    source_file_path=str(_dest),
                    account_product=_ap,
                    source_id=_sid,
                    institution_slug=_inst,
                    account_slug=_acct,
                    statement_year=_yr,
                    statement_month=_mo,
                    bucket=_bkt,
                    document_id=_did,
                )
            except Exception as exc:
                logger.error("bulk_upload.ingest_failed", filename=_fname, error=str(exc))

        asyncio.create_task(_ingest())

        results.append(BulkUploadFileResult(
            filename=fname,
            outcome="saved",
            document_id=doc_id,
            destination_path=str(dest_path),
        ))

        logger.info(
            "bulk_upload.accepted",
            filename=fname,
            institution=institution_slug,
            account=account_slug,
            year=year,
            month=month,
            dest=str(dest_path),
        )

    summary = BulkUploadSummary(
        uploaded=sum(1 for r in results if r.outcome == "saved"),
        duplicates_skipped=sum(1 for r in results if r.outcome == "duplicate_skipped"),
        successfully_ingested=0,  # async — not known at response time
        failed=sum(1 for r in results if r.outcome == "failed"),
        partial_parses=0,
        results=results,
    )
    return summary


# ── Legacy upload (source_id-based) ──────────────────────────────────────────

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    source_id: str | None = Form(default=None),
    year: int | None = Form(default=None),
):
    """
    Legacy upload: accepts a source_id + year (old statement_sources model).
    New code should use /upload-local instead.
    """
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    contents = await file.read()
    _validate_pdf(file, contents)
    file_hash = _sha256_bytes(contents)

    duped = await _dedup_check(file_hash)
    if duped:
        return duped

    ext = Path(file.filename).suffix.lower()

    if source_id:
        source = SOURCES_BY_ID.get(source_id)
        if not source:
            raise HTTPException(400, f"Unknown source_id '{source_id}'.")

        target_year = year or datetime.now().year
        dest_dir = source.root_path / str(target_year)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / file.filename

        if dest_path.exists():
            existing_hash = _sha256_bytes(dest_path.read_bytes())
            if existing_hash != file_hash:
                stem = Path(file.filename).stem
                dest_path = dest_dir / f"{stem}_{uuid.uuid4().hex[:6]}{ext}"

        dest_path.write_bytes(contents)
        account_product = source.account_product
    else:
        uploads_dir = settings.get_uploads_dir()
        stored_name = f"{uuid.uuid4()}{ext}"
        dest_path = uploads_dir / stored_name
        dest_path.write_bytes(contents)
        account_product = None

    original_filename = file.filename

    async def _ingest() -> None:
        try:
            await ingest_document(
                file_path=dest_path,
                original_filename=original_filename,
                file_hash=file_hash,
                source_file_path=str(dest_path),
                account_product=account_product,
                source_id=source_id,
            )
        except Exception as exc:
            logger.error("upload.ingest_failed", filename=original_filename, error=str(exc))

    asyncio.create_task(_ingest())

    return DocumentUploadResponse(
        document_id=str(uuid.uuid4()),
        filename=original_filename,
        status="processing",
    )


# ── Status poll ───────────────────────────────────────────────────────────────

@router.get("/{doc_id}/status")
async def get_document_status(doc_id: str):
    """Lightweight status poll — used by upload progress tracking."""
    async with get_session() as session:
        existing = await session.execute(
            select(
                DocumentModel.id,
                DocumentModel.status,
                DocumentModel.error_message,
                DocumentModel.institution_type,
                DocumentModel.page_count,
                DocumentModel.original_filename,
            ).where(DocumentModel.id == doc_id)
        )
        row = existing.fetchone()

    if not row:
        raise HTTPException(404, f"Document {doc_id} not found")

    return {
        "document_id": row[0],
        "status": row[1],
        "error": row[2],
        "institution": row[3],
        "page_count": row[4],
        "filename": row[5],
    }


# ── List / get / delete ───────────────────────────────────────────────────────

@router.get("/", response_model=list[DocumentSummary])
async def list_documents():
    """List all documents with status."""
    async with get_session() as session:
        docs = await repo.list_documents(session)
        summaries = []
        for doc in docs:
            stmts = await repo.get_statements_for_document(session, doc.id)
            summaries.append(DocumentSummary(
                id=doc.id,
                filename=doc.original_filename,
                institution=doc.institution_type,
                status=doc.status,
                page_count=doc.page_count,
                statement_count=len(stmts),
                upload_time=doc.upload_time,
                error=doc.error_message,
            ))
        return summaries


@router.get("/{doc_id}", response_model=DocumentSummary)
async def get_document(doc_id: str):
    """Get a specific document by ID."""
    async with get_session() as session:
        try:
            doc = await repo.get_document(session, doc_id)
        except Exception:
            raise HTTPException(404, f"Document {doc_id} not found")
        stmts = await repo.get_statements_for_document(session, doc.id)
        return DocumentSummary(
            id=doc.id,
            filename=doc.original_filename,
            institution=doc.institution_type,
            status=doc.status,
            page_count=doc.page_count,
            statement_count=len(stmts),
            upload_time=doc.upload_time,
            error=doc.error_message,
        )


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and all related records."""
    async with get_session() as session:
        try:
            doc = await repo.get_document(session, doc_id)
        except Exception:
            raise HTTPException(404, f"Document {doc_id} not found")

        file_path = Path(doc.file_path)
        if file_path.exists():
            file_path.unlink()

        await delete_fts_for_document(doc_id)
        await repo.delete_document_cascade(session, doc_id)

    return {"status": "deleted", "document_id": doc_id}


@router.post("/{doc_id}/reingest")
async def reingest_document(doc_id: str):
    """Re-run ingestion for a document that already exists in the DB."""
    async with get_session() as session:
        try:
            doc = await repo.get_document(session, doc_id)
        except Exception:
            raise HTTPException(404, f"Document {doc_id} not found")
        file_path = Path(doc.file_path)
        original_filename = doc.original_filename
        file_hash = doc.file_hash
        source_file_path = doc.source_file_path
        account_product = doc.account_product
        source_id = doc.source_id

    if not file_path.exists():
        raise HTTPException(400, f"Source file not found: {file_path}")

    await delete_fts_for_document(doc_id)
    async with get_session() as session:
        await repo.delete_statements_for_document(session, doc_id)

    async def _reingest() -> None:
        try:
            from app.services.ingestion import persist_canonical, chunk_and_index
            from app.parsers.pdf import parse_pdf
            from app.parsers.base import get_parser_registry

            async with get_session() as session:
                await repo.update_document(session, doc_id, status="processing", error_message=None)

            parsed_doc = await parse_pdf(file_path)
            registry = get_parser_registry()
            parser, confidence = registry.detect_institution(parsed_doc.full_text[:3000])

            if parser is None:
                async with get_session() as session:
                    await repo.update_document(session, doc_id, status="failed",
                        error_message="Could not identify institution")
                return

            institution_type = parser.institution_type
            async with get_session() as session:
                await repo.update_document(session, doc_id, institution_type=institution_type,
                    page_count=parsed_doc.page_count)

            parsed_stmt = await parser.extract(parsed_doc)
            await persist_canonical(doc_id, institution_type, parsed_stmt)
            await chunk_and_index(doc_id, institution_type, parsed_doc)

            async with get_session() as session:
                await repo.update_document(session, doc_id, status="parsed",
                    processed_time=datetime.utcnow())

            logger.info("reingest.complete", doc_id=doc_id)
        except Exception as exc:
            logger.error("reingest.failed", doc_id=doc_id, error=str(exc))
            async with get_session() as session:
                await repo.update_document(session, doc_id, status="failed",
                    error_message=str(exc))

    asyncio.create_task(_reingest())
    return {"status": "reingesting", "document_id": doc_id}


@router.post("/reingest-all")
async def reingest_all_documents():
    """Re-run ingestion for all parsed/failed documents."""
    async with get_session() as session:
        docs = await repo.list_documents(session)

    reingesting = []
    for doc in docs:
        if doc.status in ("parsed", "failed"):
            file_path = Path(doc.file_path)
            if file_path.exists():
                reingesting.append(doc.id)

    for doc_id in reingesting:
        await delete_fts_for_document(doc_id)
        async with get_session() as session:
            await repo.delete_statements_for_document(session, doc_id)

    async def _bulk_reingest() -> None:
        from app.services.ingestion import persist_canonical, chunk_and_index
        from app.parsers.pdf import parse_pdf
        from app.parsers.base import get_parser_registry

        for doc_id in reingesting:
            async with get_session() as session:
                try:
                    doc = await repo.get_document(session, doc_id)
                except Exception:
                    continue
            try:
                async with get_session() as session:
                    await repo.update_document(session, doc_id, status="processing", error_message=None)

                parsed_doc = await parse_pdf(Path(doc.file_path))
                registry = get_parser_registry()
                parser, _ = registry.detect_institution(parsed_doc.full_text[:3000])

                if parser is None:
                    async with get_session() as session:
                        await repo.update_document(session, doc_id, status="failed",
                            error_message="Could not identify institution")
                    continue

                institution_type = parser.institution_type
                async with get_session() as session:
                    await repo.update_document(session, doc_id, institution_type=institution_type,
                        page_count=parsed_doc.page_count)

                parsed_stmt = await parser.extract(parsed_doc)
                await persist_canonical(doc_id, institution_type, parsed_stmt)
                await chunk_and_index(doc_id, institution_type, parsed_doc)

                async with get_session() as session:
                    await repo.update_document(session, doc_id, status="parsed",
                        processed_time=datetime.utcnow())

            except Exception as exc:
                logger.error("reingest_all.failed", doc_id=doc_id, error=str(exc))
                async with get_session() as session:
                    await repo.update_document(session, doc_id, status="failed",
                        error_message=str(exc))

    asyncio.create_task(_bulk_reingest())
    return {"status": "reingesting", "count": len(reingesting), "document_ids": reingesting}


@router.get("/sources/list")
async def list_sources():
    """Return configured statement sources for upload modal."""
    from app.config.statement_catalog import ACCOUNT_CATALOG, CATALOG_BY_INSTITUTION, INSTITUTION_SLUGS
    result = []
    for slug in INSTITUTION_SLUGS:
        accounts = CATALOG_BY_INSTITUTION[slug]
        for a in accounts:
            result.append({
                "institution_slug": a.institution_slug,
                "institution_label": a.institution_label,
                "account_slug": a.account_slug,
                "account_label": a.account_label,
                "bucket": a.bucket,
                "parseable": a.parseable,
                "supported_years": sorted(a.supported_years, reverse=True),
            })
    return result
