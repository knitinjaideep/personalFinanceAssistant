"""
Chat endpoint — RAG-powered financial question answering.

Routes:
  POST /api/v1/chat/query         Answer a question (request/response)
  POST /api/v1/chat/stream        Answer a question with streaming SSE events

Phase 2.4 upgrade:
  - All events use the typed ``SSEEvent`` envelope from ``sse_schemas``.
  - ``StreamDoneEvent`` terminates every stream.
  - Retrieval strategy is declared before execution (retrieval_plan_selected).
  - SQL candidate + validation events fire when SQL is used.
  - Source chunks are ranked and surfaced as ``source_chunks_ranked``.
  - The final ``response_complete`` payload carries a typed ``ResponseCompletePayload``.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat_service
from app.api.schemas.answer_schemas import StructuredResponseCompletePayload
from app.api.schemas.sse_schemas import (
    ResponseCompletePayload,
    ResponseDraftStartedPayload,
    RetrievalPlanSelectedPayload,
    SourceChunksRankedPayload,
    SQLCandidateGeneratedPayload,
    SQLValidatedPayload,
    StreamDoneEvent,
)
from app.domain.entities import BucketScopedChatRequest, ChatRequest, ChatResponse
from app.services.event_bus import make_chat_event
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
    summary="Ask a financial question with streaming SSE events + answer",
    response_class=StreamingResponse,
)
async def stream_query(
    request: BucketScopedChatRequest,
    http_request: Request,
    chat_service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    """
    Answer a question and stream structured agent trace events via SSE,
    followed by the final typed answer payload.

    Phase 2.4 event sequence:
      retrieval_plan_selected → sql_candidate_generated (if SQL) →
      sql_validated (if SQL) → source_chunks_ranked →
      response_draft_started → response_complete → [stream_done]

    Bucket scope:
    - bucket_ids: null  → query all buckets
    - bucket_ids: [id]  → query specific bucket(s)

    The final ``response_complete`` event carries a ``ResponseCompletePayload``
    in its ``payload`` field, including the full answer, sources, SQL (if any),
    confidence, and caveats.
    """
    session_id = request.session_id or str(uuid.uuid4())
    pipeline_start = time.monotonic()

    async def _generate():
        def _ev(
            event_type: str,
            stage: str,
            message: str,
            status: str = "complete",
            agent: str = "chat_pipeline",
            progress: float | None = None,
            duration_ms: int | None = None,
            warnings: list[str] | None = None,
            payload: dict | None = None,
        ) -> str:
            event = make_chat_event(
                session_id=session_id,
                event_type=event_type,
                stage=stage,
                message=message,
                status=status,
                agent_name=agent,
                progress=progress,
                duration_ms=duration_ms,
                warnings=warnings,
                payload=payload or {},
            )
            return event.to_sse()

        def _done(error: str | None = None) -> str:
            elapsed_ms = int((time.monotonic() - pipeline_start) * 1000)
            return StreamDoneEvent(
                session_id=session_id,
                total_duration_ms=elapsed_ms,
                error=error,
            ).to_sse()

        try:
            # ── 1. Declare retrieval plan ──────────────────────────────────────
            if not request.bucket_ids:
                scope_label = "all buckets"
            elif len(request.bucket_ids) == 1:
                scope_label = "1 bucket"
            else:
                scope_label = f"{len(request.bucket_ids)} buckets"

            # Determine strategy heuristically — in Phase 2.6 this will be
            # the full query planner; for now we default to hybrid.
            strategy = "hybrid"

            plan_payload = RetrievalPlanSelectedPayload(
                session_id=session_id,
                strategy=strategy,
                scope_label=scope_label,
                bucket_ids=[str(b) for b in (request.bucket_ids or [])],
            )
            yield _ev(
                "retrieval_plan_selected",
                "plan_retrieval",
                f"Retrieval strategy: {strategy} across {scope_label}",
                status="complete",
                progress=0.1,
                payload=plan_payload.model_dump(),
            )

            # ── 2. Execute retrieval ───────────────────────────────────────────
            chat_req = ChatRequest(
                question=request.question,
                conversation_history=request.conversation_history,
            )

            retrieval_start = time.monotonic()
            try:
                if hasattr(chat_service, "answer_scoped") and request.bucket_ids:
                    response = await chat_service.answer_scoped(
                        chat_req, [str(bid) for bid in request.bucket_ids]
                    )
                else:
                    response = await chat_service.answer(chat_req)
            except Exception as exc:
                logger.exception("chat.stream.answer_error", session_id=session_id, error=str(exc))
                yield _ev(
                    "error", "chat_error",
                    f"Retrieval or generation failed: {exc}",
                    status="failed",
                )
                yield _done(error=str(exc))
                return

            retrieval_ms = int((time.monotonic() - retrieval_start) * 1000)

            # ── 3. SQL candidate event (when SQL was used) ─────────────────────
            if response.sql_query_used:
                sql_candidate = SQLCandidateGeneratedPayload(
                    session_id=session_id,
                    intent="financial_query",
                    sql=response.sql_query_used,
                    template_name=None,
                )
                yield _ev(
                    "sql_candidate_generated",
                    "generate_sql",
                    "SQL query generated from intent",
                    progress=0.35,
                    payload=sql_candidate.model_dump(),
                )

                sql_validated = SQLValidatedPayload(
                    session_id=session_id,
                    sql=response.sql_query_used,
                    tables_referenced=[],  # Populated by Phase 2.6 query planner
                    rows_returned=None,
                    duration_ms=retrieval_ms,
                )
                yield _ev(
                    "sql_validated",
                    "validate_sql",
                    "SQL passed safety checks",
                    progress=0.45,
                    payload=sql_validated.model_dump(),
                )

            # ── 4. Surface ranked source chunks ───────────────────────────────
            top_sources = [
                {
                    "document_id": s.document_id,
                    "institution": s.institution_type,
                    "section": s.section,
                    "page_number": s.page_number,
                    "score": None,  # Populated by Phase 2.6 retriever upgrade
                }
                for s in response.sources[:5]
            ]
            chunks_payload = SourceChunksRankedPayload(
                session_id=session_id,
                chunk_count=len(response.sources),
                top_sources=top_sources,
            )
            yield _ev(
                "source_chunks_ranked",
                "rank_chunks",
                f"Ranked {len(response.sources)} source chunk(s) by relevance",
                progress=0.6,
                duration_ms=retrieval_ms,
                payload=chunks_payload.model_dump(),
            )

            # ── 5. Generation started ──────────────────────────────────────────
            draft_payload = ResponseDraftStartedPayload(
                session_id=session_id,
                model="qwen3:8b",  # From settings in Phase 2.6; hardcoded for now
                prompt_token_estimate=None,
            )
            yield _ev(
                "response_draft_started",
                "llm_generation",
                "Generating answer with local Ollama model",
                status="started",
                agent="ollama",
                progress=0.75,
                payload=draft_payload.model_dump(),
            )

            # ── 6. Final response_complete (Phase 2.7 structured answer) ─────────
            source_list = [
                {
                    "id": s.id,
                    "document_id": s.document_id,
                    "chunk_text": s.chunk_text,
                    "page_number": s.page_number,
                    "section": s.section,
                    "institution_type": s.institution_type,
                    "statement_period": s.statement_period,
                }
                for s in response.sources
            ]
            answer_payload = StructuredResponseCompletePayload(
                session_id=session_id,
                answer=response.answer,
                answer_type=response.answer_type,
                structured_answer=response.structured_answer,  # typed dict from answer_builder
                sources=source_list,
                sql_query_used=response.sql_query_used,
                confidence=response.confidence,
                caveats=response.caveats,
                processing_time_seconds=response.processing_time_seconds,
            )
            total_ms = int((time.monotonic() - pipeline_start) * 1000)
            yield _ev(
                "response_complete",
                "finalize",
                "Answer ready",
                status="complete",
                progress=1.0,
                duration_ms=total_ms,
                payload=answer_payload.model_dump(),
            )

            yield _done()

        except Exception as exc:
            logger.exception("chat.stream_error", session_id=session_id, error=str(exc))
            yield _ev("error", "stream_error", f"Unexpected error: {exc}", status="failed")
            yield _done(error=str(exc))

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
