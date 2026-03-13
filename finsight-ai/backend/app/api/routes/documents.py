"""
Document upload and status endpoints.

Routes:
  POST   /api/v1/documents/upload          Upload a financial statement
  GET    /api/v1/documents/                List all documents
  GET    /api/v1/documents/{id}            Get document by ID
  GET    /api/v1/documents/{id}/status     Poll processing status
  GET    /api/v1/documents/{id}/stream     SSE stream of ingestion trace events

Phase 2.4:
  The ``/stream`` endpoint subscribes to the per-document ``EventBus``
  registered by ``IngestionService`` before it launches the background task.
  The client receives typed ``SSEEvent`` messages as each pipeline stage
  completes, followed by a ``StreamDoneEvent`` sentinel.

  If the client connects after the job has already finished (race condition
  or page refresh), the endpoint immediately returns a 200 with the
  ``stream_done`` sentinel so the frontend doesn't hang.
"""

from __future__ import annotations

import asyncio
import uuid

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, get_ingestion_service
from app.api.schemas.sse_schemas import StreamDoneEvent
from app.database.repositories.statement_repo import StatementDocumentRepository
from app.domain.entities import DocumentUploadResponse
from app.domain.errors import FileTooLargeError, UnsupportedFileTypeError
from app.services.deletion_service import DeletionService
from app.services.event_bus import bus_registry
from app.services.ingestion_service import IngestionService

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a financial statement for processing",
)
async def upload_document(
    file: UploadFile = File(..., description="PDF financial statement"),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> DocumentUploadResponse:
    """
    Upload a financial statement PDF.

    The document is queued for background processing. Use the returned
    `document_id` to poll `/documents/{id}/status` for processing progress.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()

    try:
        response = await ingestion_service.ingest_upload(
            file_content=content,
            original_filename=file.filename,
            content_type=file.content_type or "application/pdf",
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except FileTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")

    return response


@router.get(
    "/",
    summary="List all uploaded documents",
)
async def list_documents(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """List all uploaded financial documents with their processing status."""
    repo = StatementDocumentRepository(session)
    docs = await repo.list_all(limit=limit, offset=offset)
    return JSONResponse(
        content=[
            {
                "id": doc.id,
                "original_filename": doc.original_filename,
                "institution_type": doc.institution_type,
                "document_status": doc.document_status,
                "page_count": doc.page_count,
                "upload_timestamp": doc.upload_timestamp.isoformat(),
                "processed_timestamp": (
                    doc.processed_timestamp.isoformat()
                    if doc.processed_timestamp
                    else None
                ),
                "error_message": doc.error_message,
            }
            for doc in docs
        ]
    )


@router.get(
    "/{document_id}/status",
    summary="Poll document processing status",
)
async def get_document_status(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Return the current processing status of a document."""
    repo = StatementDocumentRepository(session)
    try:
        doc = await repo.get_by_id(document_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

    return JSONResponse(
        content={
            "document_id": doc.id,
            "status": doc.document_status,
            "institution_type": doc.institution_type,
            "page_count": doc.page_count,
            "error_message": doc.error_message,
            "upload_timestamp": doc.upload_timestamp.isoformat(),
            "processed_timestamp": (
                doc.processed_timestamp.isoformat()
                if doc.processed_timestamp
                else None
            ),
        }
    )


@router.get(
    "/{document_id}/stream",
    summary="Stream ingestion trace events for a document (SSE)",
    response_class=StreamingResponse,
)
async def stream_document_events(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """
    Subscribe to the real-time ingestion trace for a document.

    Emits typed ``SSEEvent`` messages as each pipeline stage completes:
      document_received → parse_started → text_extracted →
      institution_hypotheses → extraction_started_v2 → fields_detected →
      [fields_needing_review] → [reconciliation_started →
      reconciliation_completed] → persist_started → persist_completed →
      embedding_started_v2 → embedding_completed →
      ingestion_pipeline_complete → [stream_done]

    **Connection timing:**
    - If the job is still running, events arrive in real time.
    - If the job already finished before connection (e.g. page refresh),
      the endpoint responds immediately with a ``stream_done`` sentinel
      so the client doesn't hang.
    - If the document does not exist, returns HTTP 404.
    """
    doc_id_str = str(document_id)

    # Verify the document exists before opening the stream
    repo = StatementDocumentRepository(session)
    try:
        doc = await repo.get_by_id(document_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

    async def _generate():
        bus = bus_registry.get(doc_id_str)

        if bus is None:
            # Job already completed or document was never processed via the
            # streaming path — emit a done sentinel immediately.
            logger.debug(
                "document_stream.no_bus",
                document_id=doc_id_str,
                document_status=doc.document_status,
            )
            done = StreamDoneEvent(
                session_id=doc_id_str,
                total_duration_ms=None,
                error=None,
            )
            yield done.to_sse()
            return

        logger.debug("document_stream.subscribing", document_id=doc_id_str)
        async for event in bus.drain():
            yield event.to_sse()

        logger.debug("document_stream.complete", document_id=doc_id_str)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete(
    "/{document_id}",
    summary="Delete a document from all storage layers",
)
async def delete_document(document_id: uuid.UUID) -> JSONResponse:
    """
    Safely delete a document from:
    - Bucket-document link table
    - Extracted data (fees, transactions, holdings, balance snapshots, statements)
    - Chroma vector store embeddings
    - Soft-delete the document record (status = deleted)

    Returns a summary of what was removed.
    """
    service = DeletionService()
    try:
        summary = await service.delete_document(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Deletion failed: {exc}")
    return JSONResponse(content=summary)
