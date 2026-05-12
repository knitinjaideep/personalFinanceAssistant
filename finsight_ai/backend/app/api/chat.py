"""
Chat API endpoint — query router + answer builder.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from app.core.logger import get_logger, get_request_id
from app.domain.entities import AnswerTimings, ChatRequest, ChatResponse
from app.domain.errors import CoralError
from app.services.answer_builder import build_answer
from app.services.query_router import route_question

logger = get_logger("coral.chat")
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/query", response_model=ChatResponse)
async def chat_query(request: Request, body: ChatRequest) -> ChatResponse:
    """Answer a financial question using SQL-first routing."""
    if not body.question.strip():
        raise HTTPException(400, "Question cannot be empty")

    req_id = getattr(request.state, "request_id", "") or get_request_id()
    total_start = time.perf_counter()

    logger.info(
        "chat_request_received",
        extra={
            "stage": "chat_request_received",
            "request_id": req_id,
            "question_preview": body.question[:80],
        },
    )

    timings = AnswerTimings()

    try:
        # ── Step 1: Route + extract context ──────────────────────────────────
        logger.info(
            "intent_classification_started",
            extra={"stage": "intent_classification_started", "request_id": req_id},
        )
        t0 = time.perf_counter()
        intent, path, confidence, ctx = await route_question(body.question)
        timings.intent_ms = round((time.perf_counter() - t0) * 1000, 1)

        logger.info(
            "intent_classification_completed",
            extra={
                "stage": "intent_classification_completed",
                "request_id": req_id,
                "intent": intent.value,
                "route": path.value,
                "confidence": round(confidence, 3),
                "duration_ms": timings.intent_ms,
            },
        )
        logger.info(
            "query_parsing_completed",
            extra={
                "stage": "query_parsing_completed",
                "request_id": req_id,
                "timeframe": ctx.timeframe_label or None,
                "category": ctx.category,
                "merchant": ctx.merchant,
                "institution": ctx.institution,
                "account_type": ctx.account_type,
            },
        )
        logger.info(
            "route_selected",
            extra={
                "stage": "route_selected",
                "request_id": req_id,
                "route": path.value,
                "intent": intent.value,
            },
        )

        # ── Step 2: Build structured answer ───────────────────────────────────
        t1 = time.perf_counter()
        answer = await build_answer(body.question, intent, path, confidence, ctx, req_id=req_id)
        timings.sql_ms = answer.timings.sql_ms
        timings.rag_ms = answer.timings.rag_ms
        timings.llm_ms = answer.timings.llm_ms

        timings.total_ms = round((time.perf_counter() - total_start) * 1000, 1)
        answer.timings = timings
        answer.request_id = req_id

        logger.info(
            "chat_request_completed",
            extra={
                "stage": "chat_request_completed",
                "request_id": req_id,
                "intent": intent.value,
                "route": path.value,
                "confidence": round(confidence, 3),
                "rows_used": answer.rows_used,
                "answer_type": answer.answer_type,
                "duration_ms": timings.total_ms,
            },
        )

        return ChatResponse(answer=answer, raw_text=answer.summary, request_id=req_id)

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
        raise HTTPException(500, {"detail": "An unexpected error occurred processing your question", "request_id": req_id})
