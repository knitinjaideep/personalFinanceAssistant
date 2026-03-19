"""
Document upload and management API endpoints.
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.db.engine import get_session
from app.db import repositories as repo
from app.db.fts import delete_fts_for_document
from app.domain.entities import DocumentSummary, DocumentUploadResponse
from app.domain.errors import DocumentIngestionError, UnsupportedFileTypeError
from app.services.ingestion import ingest_document

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """Upload a financial statement PDF for processing."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.storage.allowed_extensions:
        raise HTTPException(400, f"File type '{ext}' not supported. Allowed: {settings.storage.allowed_extensions}")

    # Validate size
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.storage.max_file_size_mb:
        raise HTTPException(400, f"File too large ({size_mb:.1f}MB). Max: {settings.storage.max_file_size_mb}MB")

    # Save file
    uploads_dir = settings.get_uploads_dir()
    stored_name = f"{uuid.uuid4()}{ext}"
    file_path = uploads_dir / stored_name

    with open(file_path, "wb") as f:
        f.write(contents)

    # Ingest in background
    async def _ingest():
        try:
            await ingest_document(file_path, file.filename)
        except Exception as exc:
            logger.error("upload.ingest_failed", filename=file.filename, error=str(exc))

    asyncio.create_task(_ingest())

    return DocumentUploadResponse(
        document_id=stored_name.replace(ext, ""),
        filename=file.filename,
        status="processing",
    )


@router.get("/", response_model=list[DocumentSummary])
async def list_documents():
    """List all uploaded documents with status."""
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
    """Get details for a specific document."""
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
    """Delete a document and all related data."""
    async with get_session() as session:
        try:
            doc = await repo.get_document(session, doc_id)
        except Exception:
            raise HTTPException(404, f"Document {doc_id} not found")

        # Delete file from disk
        file_path = Path(doc.file_path)
        if file_path.exists():
            file_path.unlink()

        # Delete FTS entries
        await delete_fts_for_document(doc_id)

        # Delete DB records
        await repo.delete_document_cascade(session, doc_id)

    return {"status": "deleted", "document_id": doc_id}
