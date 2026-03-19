"""
Bucket endpoints.

Routes:
  GET    /api/v1/buckets/                         List all active buckets
  POST   /api/v1/buckets/                         Create a bucket
  GET    /api/v1/buckets/grouped                  Buckets with their documents nested
  GET    /api/v1/buckets/{id}                     Get a single bucket
  DELETE /api/v1/buckets/{id}                     Soft-delete a bucket
  POST   /api/v1/buckets/{id}/documents/{doc_id}  Assign document to bucket
  DELETE /api/v1/buckets/{id}/documents/{doc_id}  Unassign document from bucket
  GET    /api/v1/buckets/{id}/documents           List documents in bucket

  GET    /api/v1/buckets/events/stream            SSE stream of processing events
  POST   /api/v1/buckets/events                   Internal: emit a processing event
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import AsyncGenerator

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.domain.entities import BucketCreateRequest
from app.services.bucket_service import BucketService

logger = structlog.get_logger(__name__)
router = APIRouter()

# ── In-memory SSE event bus ───────────────────────────────────────────────────
# Keyed by session_id. Each value is an asyncio.Queue of event dicts.
# This is intentionally simple — no Redis, no DB. Events are ephemeral.
# For production scale this would be replaced with a pub/sub system.
_event_queues: dict[str, asyncio.Queue] = {}

# Sentinel to signal stream end
_STREAM_DONE = object()


def _get_or_create_queue(session_id: str) -> asyncio.Queue:
    if session_id not in _event_queues:
        _event_queues[session_id] = asyncio.Queue(maxsize=500)
    return _event_queues[session_id]


async def emit_event(session_id: str, event: dict) -> None:
    """
    Emit a processing event to a session's SSE queue.

    Called by ingestion and chat services to stream agent activity.
    """
    queue = _get_or_create_queue(session_id)
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning("event_queue.full", session_id=session_id)


async def emit_done(session_id: str) -> None:
    """Signal that a session's event stream is complete."""
    queue = _get_or_create_queue(session_id)
    try:
        queue.put_nowait(_STREAM_DONE)
    except asyncio.QueueFull:
        pass


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse_format(data: dict) -> str:
    """Format a dict as an SSE message."""
    return f"data: {json.dumps(data)}\n\n"


async def _event_generator(
    session_id: str, request: Request
) -> AsyncGenerator[str, None]:
    """
    Yield SSE messages for a session until the client disconnects or the
    stream is explicitly closed.
    """
    queue = _get_or_create_queue(session_id)
    try:
        while True:
            # Check client disconnect
            if await request.is_disconnected():
                break

            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send keepalive comment
                yield ": keepalive\n\n"
                continue

            if event is _STREAM_DONE:
                yield _sse_format({"type": "stream_done", "session_id": session_id})
                break

            yield _sse_format(event)
    finally:
        _event_queues.pop(session_id, None)


# ── Bucket CRUD ───────────────────────────────────────────────────────────────

@router.get("/", summary="List all active buckets")
async def list_buckets() -> JSONResponse:
    """Return all non-deleted buckets."""
    service = BucketService()
    buckets = await service.list_buckets()
    return JSONResponse(content=buckets)


@router.get("/grouped", summary="Buckets with their documents nested")
async def list_buckets_grouped() -> JSONResponse:
    """
    Return all active buckets, each containing their assigned documents.
    Used by the upload screen.
    """
    service = BucketService()
    grouped = await service.get_buckets_grouped_with_docs()
    return JSONResponse(content=grouped)


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a new bucket")
async def create_bucket(request: BucketCreateRequest) -> JSONResponse:
    """Create a new bucket. Returns 409 if the name already exists."""
    service = BucketService()
    try:
        bucket = await service.create_bucket(request)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return JSONResponse(content=bucket, status_code=status.HTTP_201_CREATED)


@router.get("/{bucket_id}", summary="Get a single bucket")
async def get_bucket(bucket_id: uuid.UUID) -> JSONResponse:
    service = BucketService()
    bucket = await service.get_bucket(bucket_id)
    if not bucket:
        raise HTTPException(status_code=404, detail=f"Bucket {bucket_id} not found.")
    return JSONResponse(content=bucket)


@router.delete("/{bucket_id}", summary="Delete a bucket")
async def delete_bucket(bucket_id: uuid.UUID) -> JSONResponse:
    """
    Soft-delete a bucket.  Documents are NOT deleted — only the bucket record.
    """
    service = BucketService()
    deleted = await service.delete_bucket(bucket_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Bucket {bucket_id} not found.")
    return JSONResponse(content={"deleted": True, "bucket_id": str(bucket_id)})


# ── Document assignment ───────────────────────────────────────────────────────

@router.post(
    "/{bucket_id}/documents/{document_id}",
    summary="Assign a document to a bucket",
)
async def assign_document(
    bucket_id: uuid.UUID, document_id: uuid.UUID
) -> JSONResponse:
    service = BucketService()
    try:
        bucket = await service.assign_document(bucket_id, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return JSONResponse(content=bucket)


@router.delete(
    "/{bucket_id}/documents/{document_id}",
    summary="Remove a document from a bucket",
)
async def unassign_document(
    bucket_id: uuid.UUID, document_id: uuid.UUID
) -> JSONResponse:
    service = BucketService()
    removed = await service.unassign_document(bucket_id, document_id)
    if not removed:
        raise HTTPException(
            status_code=404, detail="Assignment not found."
        )
    return JSONResponse(
        content={
            "removed": True,
            "bucket_id": str(bucket_id),
            "document_id": str(document_id),
        }
    )


@router.get("/{bucket_id}/documents", summary="List documents in a bucket")
async def list_bucket_documents(bucket_id: uuid.UUID) -> JSONResponse:
    service = BucketService()
    docs = await service.list_documents_in_bucket(bucket_id)
    return JSONResponse(content=docs)


# ── SSE event stream ──────────────────────────────────────────────────────────

@router.get(
    "/events/stream",
    summary="Stream processing events via SSE",
    response_class=StreamingResponse,
)
async def stream_events(session_id: str, request: Request) -> StreamingResponse:
    """
    Server-Sent Events stream for agent activity.

    Connect with:
      GET /api/v1/buckets/events/stream?session_id=<id>
      Accept: text/event-stream

    Events are pushed here by ingestion and chat pipelines.
    The stream closes when the session is done or the client disconnects.
    """
    return StreamingResponse(
        _event_generator(session_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering
        },
    )


class EventPayload(BaseModel):
    session_id: str
    event_type: str
    status: str
    agent_name: str
    step_name: str
    message: str
    bucket_id: str | None = None
    bucket_name: str | None = None
    document_id: str | None = None
    document_name: str | None = None
    progress: float | None = None
    metadata: dict = {}


@router.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Emit a processing event (internal use)",
)
async def emit_processing_event(payload: EventPayload) -> JSONResponse:
    """
    Push a processing event to an active SSE stream.

    Used by background tasks and agents to emit structured activity events.
    """
    event = {
        **payload.model_dump(),
        "timestamp": datetime.utcnow().isoformat(),
    }
    await emit_event(payload.session_id, event)
    return JSONResponse(content={"queued": True}, status_code=status.HTTP_202_ACCEPTED)
