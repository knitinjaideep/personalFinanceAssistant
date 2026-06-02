"""
Chat API endpoint — robust intent pipeline (classifier → router → fallback).

The heavy lifting lives in ``app.services.chat_router``. This endpoint owns
request-level timing/logging and translates routing outcomes to the API schema.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.core.logger import get_logger, get_request_id
from app.domain.entities import AnswerTimings, ChatRequest, ChatResponse
from app.domain.errors import CoralError
from app.services.chat_router import route

logger = get_logger("coral.chat")
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/query", response_model=ChatResponse)
async def chat_query(request: Request, body: ChatRequest) -> ChatResponse:
    """Answer a financial question via the intent classification + routing pipeline."""
    if not body.question.strip():
        raise HTTPException(400, "Question cannot be empty")

    req_id = getattr(request.state, "request_id", "") or get_request_id()
    total_start = time.perf_counter()

    logger.info(
        "chat_request_received",
        extra={
            "stage": "chat_request_received",
            "request_id": req_id,
            "selected_model": settings.ollama.model,
            "user_question": body.question[:200],
        },
    )

    try:
        outcome = await route(body.question, req_id=req_id)

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
                "sql_rows": outcome.sql_rows,
                "rag_chunks": outcome.rag_chunks,
                "fallback_steps": outcome.fallback_steps,
                "final_answer_status": outcome.final_answer_status,
                "duration_ms": total_ms,
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
        raise HTTPException(
            500,
            {"detail": "An unexpected error occurred processing your question", "request_id": req_id},
        )
