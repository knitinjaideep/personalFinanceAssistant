"""
Chat API endpoints:
  POST /api/v1/chat/query   — batch response (original)
  POST /api/v1/chat/stream  — SSE streaming response (new)

The heavy lifting lives in ``app.services.chat_router`` (batch) and
``app.chat.streaming`` (SSE). This module owns request-level
timing/logging and translates routing outcomes to the API schema.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.logger import get_logger, get_request_id
from app.domain.entities import AnswerTimings, ChatDebugPayload, ChatRequest, ChatResponse
from app.domain.errors import CoralError
from app.services.chat_router import route
from app.chat.streaming import stream_chat

logger = get_logger("coral.chat")
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """Stream a chat response as Server-Sent Events.

    Each event is: ``event: <type>\\ndata: <json>\\n\\n``
    Event types: status, intent, tool_start, tool_result, answer_token, table, chart, error, done
    """
    if not body.question.strip():
        raise HTTPException(400, "Question cannot be empty")

    req_id = getattr(request.state, "request_id", "") or get_request_id()
    conv_id = body.conversation_id or str(uuid.uuid4())

    async def _generate():
        async for chunk in stream_chat(body.question, req_id=req_id, conversation_id=conv_id):
            yield chunk

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/query", response_model=ChatResponse)
async def chat_query(request: Request, body: ChatRequest) -> ChatResponse:
    """Answer a financial question via the intent classification + routing pipeline."""
    if not body.question.strip():
        raise HTTPException(400, "Question cannot be empty")

    req_id = getattr(request.state, "request_id", "") or get_request_id()
    conv_id = body.conversation_id or str(uuid.uuid4())
    total_start = time.perf_counter()

    logger.info(
        "chat_request_received",
        extra={
            "stage": "chat_request_received",
            "request_id": req_id,
            "conversation_id": conv_id,
            "selected_model": settings.ollama.model,
            "user_question": body.question[:200],
        },
    )

    try:
        outcome = await route(body.question, req_id=req_id, conversation_id=conv_id)

        answer = outcome.answer
        total_ms = round((time.perf_counter() - total_start) * 1000, 1)
        # Preserve any per-stage timings answer_builder populated.
        timings = answer.timings or AnswerTimings()
        timings.total_ms = total_ms
        answer.timings = timings
        answer.request_id = req_id

        logger.info(
            "chat_request_completed",
            extra={
                "stage": "chat_request_completed",
                "request_id": req_id,
                "classifier_intent": outcome.classification.intent.value,
                "query_intent": outcome.query_intent.value,
                "selected_route": outcome.route,
                "route_type": outcome.route_decision.route_type.value if outcome.route_decision else "unknown",
                "route_risk": outcome.route_decision.route_risk.value if outcome.route_decision else "unknown",
                "sql_rows": outcome.sql_rows,
                "rag_chunks": outcome.rag_chunks,
                "fallback_steps": outcome.fallback_steps,
                "final_answer_status": outcome.final_answer_status,
                "answer_strategy": answer.answer_strategy,
                "llm_called": answer.llm_called,
                "verifier_passed": answer.verifier_passed,
                "verifier_repaired": answer.verifier_repaired,
                "duration_ms": total_ms,
            },
        )

        debug_payload: ChatDebugPayload | None = None
        if settings.debug_chat:
            debug_payload = ChatDebugPayload(
                route_type=outcome.route_decision.route_type.value if outcome.route_decision else "",
                route_risk=outcome.route_decision.route_risk.value if outcome.route_decision else "",
                query_plan_task=outcome.query_plan.task_type if outcome.query_plan else "",
                query_plan_source=outcome.query_plan.plan_source if outcome.query_plan else "",
                sql_queries_executed=list(answer.sql_used),
                row_count=answer.rows_used,
                retrieval_count=outcome.rag_chunks,
                answer_strategy=answer.answer_strategy,
                llm_called=answer.llm_called,
                verifier_passed=answer.verifier_passed,
                verifier_repaired=answer.verifier_repaired,
                verifier_warnings=list(answer.verifier_warnings),
                fallback_steps=list(outcome.fallback_steps),
                timings={
                    "intent_ms": timings.intent_ms,
                    "sql_ms": timings.sql_ms,
                    "rag_ms": timings.rag_ms,
                    "llm_ms": timings.llm_ms,
                    "total_ms": timings.total_ms,
                },
            )

        return ChatResponse(answer=answer, raw_text=answer.summary, request_id=req_id, debug=debug_payload)

    except CoralError as exc:
        duration_ms = round((time.perf_counter() - total_start) * 1000, 1)
        logger.error(
            "chat_request_failed",
            extra={
                "stage": "chat_request_failed",
                "request_id": req_id,
                "error": exc.message,
                "duration_ms": duration_ms,
            },
        )
        raise HTTPException(500, {"detail": f"Query failed: {exc.message}", "request_id": req_id})
    except Exception as exc:
        duration_ms = round((time.perf_counter() - total_start) * 1000, 1)
        logger.error(
            "chat_request_failed",
            extra={
                "stage": "chat_request_failed",
                "request_id": req_id,
                "error": str(exc),
                "duration_ms": duration_ms,
            },
            exc_info=True,
        )
        raise HTTPException(
            500,
            {"detail": "An unexpected error occurred processing your question", "request_id": req_id},
        )
