"""
Document upload and management API endpoints.

Upload flow (two modes):
  1. Manual upload to Coral folder:
       POST /upload?source_id=chase_checking&year=2025
       → file is written to the Coral folder (e.g. …/Chase/Checking/2025/filename.pdf)
       → scanner hash is computed and dedup checked
       → ingestion runs in background (same pipeline as the scanner)

  2. Upload to staging area (legacy / no folder selected):
       POST /upload  (no source_id)
       → file is saved to data/uploads/
       → ingestion runs in background without folder metadata
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
from app.db.engine import get_session
from app.db import repositories as repo
from app.db.fts import delete_fts_for_document
from app.db.models import DocumentModel
from app.domain.entities import DocumentSummary, DocumentUploadResponse
from app.services.ingestion import ingest_document
from app.statement_sources import SOURCES_BY_ID

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    source_id: str | None = Form(default=None),
    year: int | None = Form(default=None),
):
    """
    Upload a financial statement PDF.

    When source_id is provided the file is copied into the correct Coral folder
    (creating the YYYY sub-directory if needed), then ingested via the same
    pipeline as the local scanner.

    When source_id is omitted the file is saved to the staging uploads directory
    and ingested without folder metadata.

    Form fields:
        file      — PDF file (required)
        source_id — slug from STATEMENT_SOURCES, e.g. "chase_checking" (optional)
        year      — 4-digit year for the YYYY sub-directory (optional, defaults to current year)
    """
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in settings.storage.allowed_extensions:
        raise HTTPException(
            400,
            f"File type '{ext}' not supported. Allowed: {settings.storage.allowed_extensions}",
        )

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.storage.max_file_size_mb:
        raise HTTPException(
            400,
            f"File too large ({size_mb:.1f} MB). Max: {settings.storage.max_file_size_mb} MB",
        )

    file_hash = _sha256_bytes(contents)

    # ── Dedup check ───────────────────────────────────────────────────────────
    async with get_session() as session:
        existing = await session.execute(
            select(DocumentModel.id, DocumentModel.status)
            .where(DocumentModel.file_hash == file_hash)
        )
        row = existing.fetchone()
        if row:
            return DocumentUploadResponse(
                document_id=row[0],
                filename=file.filename,
                status=row[1],
                message="File already ingested (duplicate SHA-256).",
            )

    # ── Determine destination path ────────────────────────────────────────────
    if source_id:
        source = SOURCES_BY_ID.get(source_id)
        if not source:
            raise HTTPException(400, f"Unknown source_id '{source_id}'. "
                                f"Valid ids: {list(SOURCES_BY_ID.keys())}")

        target_year = year or datetime.now().year
        dest_dir = source.root_path / str(target_year)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / file.filename

        # Avoid overwriting an existing file with a different hash
        if dest_path.exists():
            existing_hash = _sha256_bytes(dest_path.read_bytes())
            if existing_hash != file_hash:
                # Rename to avoid clobber
                stem = Path(file.filename).stem
                dest_path = dest_dir / f"{stem}_{uuid.uuid4().hex[:6]}{ext}"

        dest_path.write_bytes(contents)
        account_product = source.account_product

    else:
        # Staging upload — save to data/uploads/
        uploads_dir = settings.get_uploads_dir()
        stored_name = f"{uuid.uuid4()}{ext}"
        dest_path = uploads_dir / stored_name
        dest_path.write_bytes(contents)
        account_product = None

    doc_id = str(uuid.uuid4())

    # ── Ingest in background ──────────────────────────────────────────────────
    async def _ingest() -> None:
        try:
            await ingest_document(
                file_path=dest_path,
                original_filename=file.filename,
                file_hash=file_hash,
                source_file_path=str(dest_path),
                account_product=account_product,
                source_id=source_id,
            )
        except Exception as exc:
            logger.error("upload.ingest_failed", filename=file.filename, error=str(exc))

    asyncio.create_task(_ingest())

    logger.info(
        "upload.accepted",
        filename=file.filename,
        source_id=source_id,
        dest=str(dest_path),
    )

    return DocumentUploadResponse(
        document_id=doc_id,
        filename=file.filename,
        status="processing",
    )


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
    """
    Re-run ingestion for a document that already exists in the DB.

    Deletes all statements/transactions/fees/holdings/balance_snapshots/text_chunks
    for the document, then re-parses and re-extracts from the original file.
    Useful after parser improvements to backfill existing documents.
    """
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

    # Delete all derived data for this document (keep the document record itself)
    await delete_fts_for_document(doc_id)
    async with get_session() as session:
        await repo.delete_statements_for_document(session, doc_id)

    async def _reingest() -> None:
        try:
            from app.services.ingestion import _persist_canonical, _chunk_and_index
            from app.parsers.pdf import parse_pdf
            from app.parsers.base import get_parser_registry
            from app.domain.errors import ClassificationError
            import json
            from datetime import datetime

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
            await _persist_canonical(doc_id, institution_type, parsed_stmt)
            await _chunk_and_index(doc_id, institution_type, parsed_doc)

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
    """
    Re-run ingestion for all parsed documents.
    Useful after parser improvements to backfill the entire corpus.
    """
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
        from app.services.ingestion import _persist_canonical, _chunk_and_index
        from app.parsers.pdf import parse_pdf
        from app.parsers.base import get_parser_registry
        from datetime import datetime
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
                await _persist_canonical(doc_id, institution_type, parsed_stmt)
                await _chunk_and_index(doc_id, institution_type, parsed_doc)

                async with get_session() as session:
                    await repo.update_document(session, doc_id, status="parsed",
                        processed_time=datetime.utcnow())

                logger.info("reingest_all.doc_done", doc_id=doc_id)
            except Exception as exc:
                logger.error("reingest_all.failed", doc_id=doc_id, error=str(exc))
                async with get_session() as session:
                    await repo.update_document(session, doc_id, status="failed",
                        error_message=str(exc))

    asyncio.create_task(_bulk_reingest())
    return {"status": "reingesting", "count": len(reingesting), "document_ids": reingesting}


@router.get("/sources/list")
async def list_sources():
    """
    Return the list of configured Coral statement sources.

    Used by the upload modal to populate the destination dropdown.
    """
    return [
        {
            "source_id": s.source_id,
            "account_product": s.account_product,
            "bucket": s.bucket,
            "institution_type": s.institution_type,
            "root_path": str(s.root_path),
        }
        for s in SOURCES_BY_ID.values()
    ]
