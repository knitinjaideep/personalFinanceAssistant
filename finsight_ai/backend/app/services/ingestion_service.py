"""
Ingestion service — orchestrates the full document upload → processing pipeline.

Responsibilities:
1. Validate and store the uploaded file.
2. Create a StatementDocument record in the DB.
3. Register a per-document ``EventBus`` so the SSE stream endpoint can subscribe.
4. Emit a ``document_received`` event before launching the background task.
5. Invoke the LangGraph ingestion graph asynchronously (background task).
6. Close the bus (emitting ``stream_done``) when the graph finishes or errors.

Phase 2.4:
  The IngestionService no longer just fires-and-forgets.  It wraps the graph
  invocation in a try/finally that always closes the bus, ensuring the SSE
  client doesn't hang indefinitely on error.

  The graph nodes (supervisor.py) emit the detailed per-stage events.  The
  service emits the bookend events: ``document_received`` and the final
  ``stream_done`` sentinel via ``bus_registry.close()``.
"""

from __future__ import annotations

import asyncio
import time
import shutil
import uuid
from pathlib import Path

import structlog

from app.agents.supervisor import ingestion_graph
from app.agents.state import IngestionState
from app.api.schemas.sse_schemas import DocumentReceivedPayload, StreamDoneEvent
from app.config import settings
from app.database.engine import get_session
from app.database.repositories.statement_repo import StatementDocumentRepository
from app.domain.entities import DocumentUploadResponse, StatementDocument
from app.domain.enums import DocumentStatus
from app.domain.errors import FileTooLargeError, UnsupportedFileTypeError
from app.services.event_bus import bus_registry, make_ingestion_event

logger = structlog.get_logger(__name__)

ALLOWED_EXTENSIONS = {ext.lstrip(".") for ext in settings.storage.allowed_extensions}
MAX_SIZE_BYTES = settings.storage.max_file_size_mb * 1024 * 1024


class IngestionService:
    """
    Handles the document upload lifecycle.

    Design:
    - Upload validation + file storage + DB record creation happen synchronously
      (within the HTTP request handler), so the 202 response is fast.
    - Processing is launched as an ``asyncio`` background task.
    - A per-document ``EventBus`` is registered before the task starts so that
      ``GET /documents/{id}/stream`` can subscribe immediately after upload.
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
            file_content: Raw bytes of the uploaded file.
            original_filename: The user's filename.
            content_type: MIME type from the multipart form.

        Returns:
            ``DocumentUploadResponse`` with ``document_id`` and initial status.

        Raises:
            UnsupportedFileTypeError: For non-PDF/CSV files.
            FileTooLargeError: For files exceeding the size limit.
        """
        # ── Validate ───────────────────────────────────────────────────────────
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

        # ── Store file ─────────────────────────────────────────────────────────
        doc_id = uuid.uuid4()
        doc_id_str = str(doc_id)
        stored_filename = f"{doc_id}.{ext}"
        file_path = self._uploads_dir / stored_filename
        file_path.write_bytes(file_content)

        logger.info(
            "ingestion.file_stored",
            document_id=doc_id_str,
            filename=original_filename,
            size_bytes=len(file_content),
        )

        # ── Create DB record ───────────────────────────────────────────────────
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

        # ── Register EventBus before background task ───────────────────────────
        bus = bus_registry.create(doc_id_str)

        received_payload = DocumentReceivedPayload(
            filename=original_filename,
            file_size_bytes=len(file_content),
            document_id=doc_id_str,
        )
        await bus.emit(
            make_ingestion_event(
                session_id=doc_id_str,
                event_type="document_received",
                stage="accept_upload",
                message=f"Document '{original_filename}' accepted and queued for processing",
                status="complete",
                progress=0.0,
                document_id=doc_id_str,
                payload=received_payload.model_dump(),
            )
        )

        # ── Launch processing graph in background ──────────────────────────────
        asyncio.create_task(
            self._process_document(doc_id_str, str(file_path.resolve()), original_filename),
            name=f"ingest_{doc_id_str}",
        )

        return DocumentUploadResponse(
            document_id=doc_id,
            original_filename=original_filename,
            file_size_bytes=len(file_content),
            status=DocumentStatus.QUEUED,
            message=(
                "Document queued for processing. "
                "Subscribe to /documents/{id}/stream for live progress, "
                "or poll /documents/{id}/status."
            ),
        )

    async def _process_document(
        self,
        document_id: str,
        file_path: str,
        original_filename: str,
    ) -> None:
        """
        Run the LangGraph ingestion pipeline for a document.

        This runs as a background task.  Errors are logged but do not
        propagate since the HTTP response has already been sent.

        The ``EventBus`` is always closed in the ``finally`` block, so the SSE
        consumer is never left waiting indefinitely.
        """
        logger.info("ingestion.processing_start", document_id=document_id)
        pipeline_start = time.monotonic()

        # Update document status to PROCESSING
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

        pipeline_error: str | None = None

        try:
            final_state = await ingestion_graph.ainvoke(initial_state)

            errors = final_state.get("errors", [])
            warnings = final_state.get("warnings", [])

            if errors:
                logger.warning(
                    "ingestion.completed_with_errors",
                    document_id=document_id,
                    errors=errors,
                )
                pipeline_error = "; ".join(errors)
            else:
                logger.info("ingestion.completed", document_id=document_id)

        except Exception as exc:
            pipeline_error = str(exc)
            logger.exception(
                "ingestion.graph_error",
                document_id=document_id,
                error=pipeline_error,
            )
            async with get_session() as session:
                repo = StatementDocumentRepository(session)
                await repo.update_status(
                    uuid.UUID(document_id),
                    DocumentStatus.FAILED,
                    error_message=pipeline_error,
                )

        finally:
            # Always close the bus — sends stream_done to waiting SSE clients.
            duration_ms = int((time.monotonic() - pipeline_start) * 1000)
            done_event = StreamDoneEvent(
                session_id=document_id,
                total_duration_ms=duration_ms,
                error=pipeline_error,
            )
            await bus_registry.close(document_id, done_event=done_event)
            logger.debug(
                "ingestion.bus_closed",
                document_id=document_id,
                duration_ms=duration_ms,
            )
