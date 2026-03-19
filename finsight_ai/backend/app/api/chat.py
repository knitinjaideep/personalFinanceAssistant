"""
Chat API endpoint — query router + answer builder.
"""

from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, HTTPException

from app.domain.entities import ChatRequest, ChatResponse
from app.domain.errors import CoralError
from app.services.answer_builder import build_answer
from app.services.query_router import route_question

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/query", response_model=ChatResponse)
async def chat_query(request: ChatRequest):
    """Answer a financial question using SQL-first routing."""
    if not request.question.strip():
        raise HTTPException(400, "Question cannot be empty")

    start = time.time()

    try:
        # Step 1: Route the question
        intent, path, confidence = await route_question(request.question)

        # Step 2: Build structured answer
        answer = await build_answer(request.question, intent, path, confidence)

        elapsed = time.time() - start
        logger.info("chat.answered", question=request.question[:80],
                   intent=intent.value, path=path.value, elapsed=f"{elapsed:.2f}s")

        return ChatResponse(answer=answer, raw_text=answer.summary)

    except CoralError as exc:
        logger.error("chat.error", question=request.question[:80], error=str(exc))
        raise HTTPException(500, f"Query failed: {exc.message}")
    except Exception as exc:
        logger.error("chat.unexpected", question=request.question[:80], error=str(exc))
        raise HTTPException(500, "An unexpected error occurred processing your question")
