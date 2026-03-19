"""
Chat endpoint — RAG-powered financial question answering (Phase 4 reliability).

Routes:
  POST /api/v1/chat/query    Answer a question (request/response)
  POST /api/v1/chat/stream   Answer a question with streaming SSE events

Phase 4 changes:
  - Uses ChatPipeline instead of ChatService for all streaming requests.
  - New SSE event types: chat_retrieve_started, chat_retrieve_done,
    chat_generate_started, chat_generate_progress, chat_generate_done,
    chat_fallback_triggered, chat_answer_ready.
  - Fallback answers (retrieval-only or safe error) are clearly labelled.
  - Hard 30s generation timeout + stall watchdog via OllamaClient.
  - /query endpoint keeps ChatService for non-streaming backward-compat.
"""

from __future__ import annotations

import json
import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat_service
from app.api.schemas.answer_schemas import StructuredResponseCompletePayload
from app.api.schemas.sse_schemas import StreamDoneEvent
from app.domain.entities import BucketScopedChatRequest, ChatRequest, ChatResponse
from app.domain.enums import BUCKET_INSTITUTIONS, BucketType
from app.services.chat.pipeline import ChatPipeline, PipelineResult, _event
from app.services.chat_service import ChatService

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post(
    "/query",
    response_model=ChatResponse,
    summary="Ask a financial question",
)
async def query(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """
    Answer a natural language question about your financial statements.

    Returns a single JSON response (no streaming).  Use ``/stream`` for
    a richer, trace-annotated experience.

    Examples:
    - "How much did I pay in fees in the last 6 months?"
    - "What is my current Morgan Stanley account balance?"
    - "Compare my balances month over month."
    - "What recurring charges do I have?"
    """
    try:
        return await chat_service.answer(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat error: {exc}")


@router.post(
    "/stream",
    summary="Ask a financial question with streaming SSE events (Phase 4)",
    response_class=StreamingResponse,
)
async def stream_query(
    request: BucketScopedChatRequest,
) -> StreamingResponse:
    """
    Answer a question and stream structured agent trace events via SSE.

    Phase 4 event sequence::

        chat_retrieve_started   → { query }
        chat_retrieve_done      → { chunks_found, sql_rows, has_sql }
        chat_generate_started   → { model }
        chat_generate_progress  → { elapsed_ms }  (every ~2s)
        chat_generate_done      → { elapsed_ms }
        chat_fallback_triggered → { reason, error }   (only on LLM failure/stall)
        chat_answer_ready       → { answer_type, confidence, fallback, pipeline_stage }
        response_complete       → full answer payload
        [stream_done]

    Fallbacks:
    - Timeout (>30s) or stall → retrieval-only answer, labelled clearly.
    - Retrieval-only fails     → safe error message.
    """
    session_id = request.session_id or str(uuid.uuid4())
    pipeline_start = time.monotonic()
    pipeline = ChatPipeline()

    async def _generate():
        try:
            # Derive human-readable bucket context for grounded no-data messages.
            # bucket_type ("banking", "investments") maps to a display label and
            # the list of institutions the user would expect to be searched.
            bucket_label: str | None = None
            institution_labels: list[str] = []
            if request.bucket_type is not None:
                bucket_label = request.bucket_type.value.title()  # e.g. "Banking"
                inst_types = BUCKET_INSTITUTIONS.get(request.bucket_type, [])
                institution_labels = [
                    it.value.replace("_", " ").title() for it in inst_types
                ]

            async for item in pipeline.stream(
                question=request.question,
                conversation_history=[
                    {"role": m.role, "content": m.content}
                    for m in request.conversation_history
                ],
                bucket_ids=[str(b) for b in (request.bucket_ids or [])],
                session_id=session_id,
                bucket_label=bucket_label,
                institution_labels=institution_labels,
            ):
                if isinstance(item, PipelineResult):
                    result: PipelineResult = item
                    source_list = [
                        {
                            "id": s.id,
                            "document_id": str(s.document_id),
                            "chunk_text": s.chunk_text,
                            "page_number": s.page_number,
                            "section": s.section,
                            "institution_type": (
                                s.institution_type.value if s.institution_type else None
                            ),
                            "statement_period": s.statement_period,
                        }
                        for s in result.sources
                    ]
                    complete_payload = StructuredResponseCompletePayload(
                        session_id=session_id,
                        answer=result.answer_text,
                        answer_type=result.structured.answer_type,
                        structured_answer=result.structured.model_dump(),
                        sources=source_list,
                        sql_query_used=result.sql_query_used,
                        confidence=getattr(result.structured, "confidence", None),
                        caveats=getattr(result.structured, "caveats", []),
                        processing_time_seconds=result.processing_time_seconds,
                        pipeline_meta=result.pipeline_meta,
                    )
                    total_ms = int((time.monotonic() - pipeline_start) * 1000)
                    # response_complete is the single terminal SSE event.
                    # pipeline_meta carries fallback/warning context in one place.
                    ev = _event(
                        session_id=session_id,
                        event_type="response_complete",
                        stage="finalize",
                        message="Answer ready",
                        status="complete",
                        progress=1.0,
                        payload=complete_payload.model_dump(),
                    )
                    yield _to_sse(ev)
                else:
                    yield _to_sse(item)

            elapsed_ms = int((time.monotonic() - pipeline_start) * 1000)
            yield StreamDoneEvent(
                session_id=session_id,
                total_duration_ms=elapsed_ms,
                error=None,
            ).to_sse()

        except Exception as exc:
            logger.exception("chat.stream_error", session_id=session_id, error=str(exc))
            err_ev = _event(
                session_id=session_id,
                event_type="error",
                stage="stream_error",
                message=f"Unexpected stream error: {exc}",
                status="failed",
            )
            yield _to_sse(err_ev)
            elapsed_ms = int((time.monotonic() - pipeline_start) * 1000)
            yield StreamDoneEvent(
                session_id=session_id,
                total_duration_ms=elapsed_ms,
                error=str(exc),
            ).to_sse()

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_sse(event: dict) -> str:
    """Serialise a pipeline event dict to an SSE ``data:`` frame."""
    return f"data: {json.dumps(event, default=str)}\n\n"
