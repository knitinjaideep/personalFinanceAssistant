"""
SSE streaming pipeline for chat — delegates to the shared safe chat_router pipeline.

This module wraps ``app.services.chat_router.route()`` with Server-Sent Events so
the UI can show progressive status without duplicating any query planning, SQL
execution, fact building, answer building, or verification logic.

Event protocol:
  status       {"message": str}
  answer_token {"text": str}          — final summary text, emitted once after answer is verified
  chart        {type: str, ...}       — forwarded from StructuredAnswer.chart_payload
  citations    {"chunks": [...]}      — forwarded from StructuredAnswer.citations
  error        {"message": str}
  done         {"request_id": str, "answer": {...}, "duration_ms": float}
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from app.chat.guardrails import safe_error_message
from app.core.logger import get_logger, get_request_id
from app.services.chat_router import route

logger = get_logger(__name__)


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ── Main streaming generator ──────────────────────────────────────────────────

async def stream_chat(
    question: str,
    *,
    req_id: str = "",
    conversation_id: str = "",
) -> AsyncIterator[str]:
    """Async generator that yields SSE-formatted strings for a chat question.

    Delegates all pipeline work (classify, query planning, SQL execution, fact
    building, answer building, verification) to ``chat_router.route()``.  Only
    wraps that call with progress status events so the UI can animate.

    The ``done`` event carries the full verified StructuredAnswer so the client
    gets the same safety guarantees as the batch ``/query`` endpoint.
    """
    req_id = req_id or get_request_id()
    total_start = time.perf_counter()

    logger.info(
        "stream_chat.start",
        extra={
            "stage": "stream_start",
            "request_id": req_id,
            "conversation_id": conversation_id or "none",
            "question": question[:200],
            "pipeline": "shared_safe_route",
        },
    )

    try:
        # ── 1. Let the client know we're working ─────────────────────────────
        yield _sse("status", {"message": "Understanding your question…"})

        # ── 2. Understanding + planning phase ─────────────────────────────────
        # (classify, build_route_decision, query_planner all run inside route())
        yield _sse("status", {"message": "Checking your data…"})

        # ── 3. Run the full safe pipeline ─────────────────────────────────────
        # chat_router.route() runs:
        #   classify → build_route_decision (complexity gate) → build_query_plan
        #   → _sql_exact (labeled relaxation, no silent widening)
        #   → RAG/FTS (when needed)
        #   → build_answer (FactBundle → choose_strategy → LLM narrative)
        #   → verify_answer
        # We never duplicate any of that here.
        outcome = await route(question, req_id=req_id, conversation_id=conversation_id)
        answer = outcome.answer

        total_ms = round((time.perf_counter() - total_start) * 1000, 1)

        logger.info(
            "stream_chat.safe_route_complete",
            extra={
                "stage": "stream_safe_route_done",
                "request_id": req_id,
                "pipeline": "shared_safe_route",
                "answer_strategy": answer.answer_strategy,
                "llm_called": answer.llm_called,
                "verifier_passed": answer.verifier_passed,
                "sql_rows": outcome.sql_rows,
                "rag_chunks": outcome.rag_chunks,
                "final_answer_status": outcome.final_answer_status,
                "total_ms": total_ms,
            },
        )

        yield _sse("status", {"message": "Preparing a verified answer…"})

        # ── 4. Emit citations if answer has them ──────────────────────────────
        if answer.citations:
            yield _sse("citations", {"chunks": answer.citations[:5]})

        # ── 5. Emit chart payload if present ─────────────────────────────────
        if answer.chart_payload:
            yield _sse("chart", answer.chart_payload)

        # ── 6. Emit the verified answer summary as a single token ─────────────
        if answer.summary:
            yield _sse("answer_token", {"text": answer.summary})

        # ── 7. Done — emit full verified StructuredAnswer ─────────────────────
        yield _sse("done", {
            "request_id": req_id,
            "conversation_id": conversation_id or "",
            "duration_ms": total_ms,
            "answer": answer.model_dump(),
        })

    except Exception as exc:
        logger.error(
            "stream_chat.error",
            extra={"stage": "stream_error", "request_id": req_id, "error": str(exc)},
            exc_info=True,
        )
        yield _sse("error", {"message": safe_error_message(exc)})
        yield _sse("done", {"request_id": req_id})
