"""
SSE streaming pipeline for chat — delegates to the shared safe chat_router pipeline.

This module wraps ``app.services.chat_router.route()`` with Server-Sent Events so
the UI can show progressive status without duplicating any query planning, SQL
execution, fact building, answer building, or verification logic.

Event protocol:
  status       {"message": str}
  intent       {"intent": str, "route_type": str, "answer_mode": str,
                "response_shape": str, "query_plan_task": str,
                "affordability_scenario": str|None, "verification": str,
                "endpoint_type": "stream"}
  answer_token {"text": str}          — final summary text, emitted once after answer is verified
  chart        {type: str, ...}       — forwarded from StructuredAnswer.chart_payload
  citations    {"chunks": [...]}      — forwarded from StructuredAnswer.citations
  error        {"message": str}
  done         {"request_id": str, "answer": {...}, "duration_ms": float,
                "debug": {...}}       — debug present only when pipeline metadata is available
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from app.chat.guardrails import safe_error_message
from app.config import settings
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
            "endpoint_type": "stream",
            "request_id": req_id,
            "conversation_id": conversation_id or "none",
            "question": question[:200],
            "selected_model": settings.ollama.model,
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
        #   → affordability analyzer (when route_type == AFFORDABILITY)
        #   → _sql_exact (labeled relaxation, no silent widening)
        #   → RAG/FTS (when needed)
        #   → build_answer (FactBundle → InsightBundle → choose_strategy → LLM narrative)
        #   → verify_answer
        # We never duplicate any of that here.
        outcome = await route(question, req_id=req_id, conversation_id=conversation_id)
        answer = outcome.answer

        total_ms = round((time.perf_counter() - total_start) * 1000, 1)

        # ── 3a. Derive affordability scenario label (if applicable) ───────────
        affordability_scenario: str | None = None
        if outcome.query_plan and outcome.query_plan.affordability:
            aff = outcome.query_plan.affordability
            affordability_scenario = getattr(aff, "semantic_scenario_type", None)

        # ── 3b. Derive verification status string ─────────────────────────────
        if answer.verifier_repaired:
            verification_status = "repaired"
        elif answer.verifier_passed:
            verification_status = "passed"
        else:
            verification_status = "failed"

        logger.info(
            "stream_chat.pipeline_complete",
            extra={
                "stage": "stream_pipeline_done",
                "endpoint_type": "stream",
                "request_id": req_id,
                "conversation_id": conversation_id or "none",
                "selected_model": settings.ollama.model,
                "pipeline": "shared_safe_route",
                "classifier_intent": outcome.classification.intent.value,
                "query_intent": outcome.query_intent.value,
                "selected_route": outcome.route,
                "route_type": outcome.route_decision.route_type.value if outcome.route_decision else "unknown",
                "route_risk": outcome.route_decision.route_risk.value if outcome.route_decision else "unknown",
                "answer_mode": answer.answer_mode,
                "response_shape": answer.response_shape,
                "query_plan_task": outcome.query_plan.task_type if outcome.query_plan else "unknown",
                "affordability_scenario": affordability_scenario,
                "answer_strategy": answer.answer_strategy,
                "llm_called": answer.llm_called,
                "verifier_status": verification_status,
                "verifier_passed": answer.verifier_passed,
                "verifier_repaired": answer.verifier_repaired,
                "sql_rows": outcome.sql_rows,
                "rag_chunks": outcome.rag_chunks,
                "fallback_steps": outcome.fallback_steps,
                "final_answer_status": outcome.final_answer_status,
                "duration_ms": total_ms,
            },
        )

        yield _sse("status", {"message": "Preparing a verified answer…"})

        # ── 4. Emit pipeline metadata as a structured intent event ────────────
        # Mirrors the debug_payload fields logged by /query so clients and
        # server logs stay in sync for both endpoints.
        yield _sse("intent", {
            "endpoint_type": "stream",
            "request_id": req_id,
            "intent": outcome.query_intent.value,
            "classifier_intent": outcome.classification.intent.value,
            "route_type": outcome.route_decision.route_type.value if outcome.route_decision else "unknown",
            "route_risk": outcome.route_decision.route_risk.value if outcome.route_decision else "unknown",
            "answer_mode": answer.answer_mode,
            "response_shape": answer.response_shape,
            "answer_style_reason": answer.answer_style_reason,
            "query_plan_task": outcome.query_plan.task_type if outcome.query_plan else "unknown",
            "query_plan_source": outcome.query_plan.plan_source if outcome.query_plan else "unknown",
            "affordability_scenario": affordability_scenario,
            "verification": verification_status,
            "verifier_passed": answer.verifier_passed,
            "verifier_repaired": answer.verifier_repaired,
            "answer_strategy": answer.answer_strategy,
            "llm_called": answer.llm_called,
            "sql_rows": outcome.sql_rows,
            "rag_chunks": outcome.rag_chunks,
            "fallback_steps": outcome.fallback_steps,
            "final_answer_status": outcome.final_answer_status,
        })

        # ── 5. Emit citations if answer has them ──────────────────────────────
        if answer.citations:
            yield _sse("citations", {"chunks": answer.citations[:5]})

        # ── 6. Emit chart payload if present ─────────────────────────────────
        if answer.chart_payload:
            yield _sse("chart", answer.chart_payload)

        # ── 7. Emit the verified answer summary as a single token ─────────────
        if answer.summary:
            yield _sse("answer_token", {"text": answer.summary})

        # ── 8. Done — emit full verified StructuredAnswer + optional debug ─────
        done_payload: dict[str, Any] = {
            "request_id": req_id,
            "conversation_id": conversation_id or "",
            "duration_ms": total_ms,
            "answer": answer.model_dump(),
        }
        if settings.debug_chat:
            insight_dict: dict | None = None
            if answer.insight_bundle is not None:
                try:
                    insight_dict = answer.insight_bundle.model_dump()
                except Exception:
                    insight_dict = None
            done_payload["debug"] = {
                "endpoint_type": "stream",
                "route_type": outcome.route_decision.route_type.value if outcome.route_decision else "",
                "route_risk": outcome.route_decision.route_risk.value if outcome.route_decision else "",
                "query_plan_task": outcome.query_plan.task_type if outcome.query_plan else "",
                "query_plan_source": outcome.query_plan.plan_source if outcome.query_plan else "",
                "sql_queries_executed": list(answer.sql_used),
                "row_count": answer.rows_used,
                "retrieval_count": outcome.rag_chunks,
                "answer_strategy": answer.answer_strategy,
                "llm_called": answer.llm_called,
                "verifier_passed": answer.verifier_passed,
                "verifier_repaired": answer.verifier_repaired,
                "verifier_warnings": list(answer.verifier_warnings),
                "fallback_steps": list(outcome.fallback_steps),
                "answer_mode": answer.answer_mode,
                "response_shape": answer.response_shape,
                "answer_style_reason": answer.answer_style_reason,
                "affordability_scenario": affordability_scenario,
                "insight_bundle": insight_dict,
                "duration_ms": total_ms,
            }
        yield _sse("done", done_payload)

    except Exception as exc:
        logger.error(
            "stream_chat.error",
            extra={
                "stage": "stream_error",
                "endpoint_type": "stream",
                "request_id": req_id,
                "error": str(exc),
            },
            exc_info=True,
        )
        yield _sse("error", {"message": safe_error_message(exc)})
        yield _sse("done", {"request_id": req_id})
