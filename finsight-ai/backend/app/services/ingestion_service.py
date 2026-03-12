"""
Ingestion service — orchestrates the full document upload → processing pipeline.

Responsibilities:
1. Validate and store the uploaded file
2. Create a StatementDocument record in the DB
3. Invoke the LangGraph ingestion graph asynchronously
4. Return the initial document record for the API to respond immediately

The ingestion graph runs in the background; the API responds with
the document_id immediately so the frontend can poll for status.
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

import structlog

from app.agents.supervisor import ingestion_graph
from app.agents.state import IngestionState
from app.config import settings
from app.database.engine import get_session
from app.database.repositories.statement_repo import StatementDocumentRepository
from app.domain.entities import DocumentUploadResponse, StatementDocument
from app.domain.enums import DocumentStatus
from app.domain.errors import FileTooLargeError, UnsupportedFileTypeError

logger = structlog.get_logger(__name__)

ALLOWED_EXTENSIONS = {ext.lstrip(".") for ext in settings.storage.allowed_extensions}
MAX_SIZE_BYTES = settings.storage.max_file_size_mb * 1024 * 1024


class IngestionService:
    """
    Handles the document upload lifecycle.

    Design: upload is synchronous (file saved, DB record created), then
    processing is kicked off as a background asyncio task so the HTTP
    response returns immediately.
    """

    def __init__(self) -> None:
        self._uploads_dir = settings.get_uploads_dir()

    async def ingest_upload(
        self,
        file_content: bytes,
        original_filename: str,
        content_type: str,
    ) -> DocumentUploadResponse:
        """
        Accept an uploaded file, validate it, store it, and kick off processing.

        Args:
            file_content: Raw bytes of the uploaded file
            original_filename: The user's filename
            content_type: MIME type from the multipart form

        Returns:
            DocumentUploadResponse with document_id and initial status.

        Raises:
            UnsupportedFileTypeError: For non-PDF/CSV files
            FileTooLargeError: For files exceeding the size limit
        """
        # Validate
        ext = Path(original_filename).suffix.lstrip(".").lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                f"File type '.{ext}' is not supported. Allowed: {ALLOWED_EXTENSIONS}"
            )
        if len(file_content) > MAX_SIZE_BYTES:
            raise FileTooLargeError(
                f"File size {len(file_content) / 1_000_000:.1f} MB exceeds "
                f"maximum {settings.storage.max_file_size_mb} MB"
            )

        # Store file with a UUID-based name to prevent collisions and path traversal
        doc_id = uuid.uuid4()
        stored_filename = f"{doc_id}.{ext}"
        file_path = self._uploads_dir / stored_filename
        file_path.write_bytes(file_content)

        logger.info(
            "ingestion.file_stored",
            document_id=str(doc_id),
            filename=original_filename,
            size_bytes=len(file_content),
        )

        # Create DB record
        document = StatementDocument(
            id=doc_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=str(file_path.resolve()),
            file_size_bytes=len(file_content),
            mime_type=content_type or "application/pdf",
            document_status=DocumentStatus.QUEUED,
        )

        async with get_session() as session:
            repo = StatementDocumentRepository(session)
            await repo.create(document)

        # Launch processing graph in background (non-blocking)
        asyncio.create_task(
            self._process_document(str(doc_id), str(file_path.resolve()), original_filename),
            name=f"ingest_{doc_id}",
        )

        return DocumentUploadResponse(
            document_id=doc_id,
            original_filename=original_filename,
            file_size_bytes=len(file_content),
            status=DocumentStatus.QUEUED,
            message="Document queued for processing. Use the document_id to poll for status.",
        )

    async def _process_document(
        self, document_id: str, file_path: str, original_filename: str
    ) -> None:
        """
        Run the LangGraph ingestion pipeline for a document.

        This runs as a background task. Errors are logged but do not
        propagate since the HTTP response has already been sent.
        """
        logger.info("ingestion.processing_start", document_id=document_id)

        # Update status to processing
        async with get_session() as session:
            repo = StatementDocumentRepository(session)
            await repo.update_status(uuid.UUID(document_id), DocumentStatus.PROCESSING)

        initial_state: IngestionState = {
            "document_id": document_id,
            "file_path": file_path,
            "original_filename": original_filename,
            "errors": [],
            "warnings": [],
            "document_status": DocumentStatus.PROCESSING.value,
        }

        try:
            final_state = await ingestion_graph.ainvoke(initial_state)

            errors = final_state.get("errors", [])
            if errors:
                logger.warning(
                    "ingestion.completed_with_errors",
                    document_id=document_id,
                    errors=errors,
                )
            else:
                logger.info("ingestion.completed", document_id=document_id)

        except Exception as exc:
            logger.exception("ingestion.graph_error", document_id=document_id, error=str(exc))
            async with get_session() as session:
                repo = StatementDocumentRepository(session)
                await repo.update_status(
                    uuid.UUID(document_id),
                    DocumentStatus.FAILED,
                    error_message=str(exc),
                )
