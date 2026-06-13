"""
Chat router — the robust pipeline that replaces the old "classify → maybe no data" flow.

    user question
      → intent classifier (LLM, validated)
      → entity + time-range extraction / normalization
      → route to SQL / RAG / hybrid
      → confidence check
      → fallback chain (relax SQL → date fallback → RAG → helpful response)
      → final structured answer + debug metadata

It reuses the existing SQL handlers (``sql_query``), text/vector search, and the
``answer_builder`` narrative generator. It never short-circuits straight to
"no data" — the fallback chain always produces *something* useful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.chat.query_planner import QueryPlan, plan as build_query_plan
from app.chat.services.conversation_context import conversation_context
from app.config import settings
from app.core.logger import get_logger, get_request_id
from app.domain.classification import (
    ChatIntent,
    DataSource,
    IntentClassificationResult,
    RouteDecision,
)
from app.domain.entities import QueryContext, StructuredAnswer
from app.domain.enums import QueryIntent, QueryPath
from app.services import availability, sql_query, text_search, vector_search
from app.services.answer_builder import build_answer
from app.services.intent_classifier import classify
from app.services.intent_mapping import build_route_decision, to_query_intent
from app.services.normalization import (
    category_display_name,
    institution_display_name,
    normalize_account,
    normalize_category,
    normalize_institution,
    normalize_timerange,
)

logger = get_logger(__name__)

# Confidence below this triggers a clarification consideration / broad fallback.
_LOW_CONFIDENCE = 0.35

# final_answer_status values
ANSWERED = "answered"
PARTIAL = "partial"
CLARIFICATION_NEEDED = "clarification_needed"
NO_DATA_AFTER_FALLBACK = "no_data_after_fallback"


@dataclass
class RoutingOutcome:
    """Everything the chat API needs, plus internal debug metadata."""

    answer: StructuredAnswer
    classification: IntentClassificationResult
    query_intent: QueryIntent
    route: str
    final_answer_status: str
    fallback_steps: list[str] = field(default_factory=list)
    sql_rows: int = 0
    rag_chunks: int = 0
    route_decision: RouteDecision | None = None
    query_plan: QueryPlan | None = None


# ── Context construction ──────────────────────────────────────────────────────

def _build_context(result: IntentClassificationResult, today: date | None = None) -> QueryContext:
    """Translate a validated classification into the QueryContext the SQL layer uses."""
    ents = result.entities

    inst_slug, _ = normalize_institution(ents.institution)
    category = normalize_category(ents.category)
    account_name = normalize_account(ents.account)

    tr = ents.time_range
    date_from = date_to = None
    label = ""
    if tr.start_date or tr.end_date:
        date_from = _parse_iso(tr.start_date)
        date_to = _parse_iso(tr.end_date)
        label = tr.value or ""
    elif tr.value:
        date_from, date_to, label = normalize_timerange(tr.value, today=today)

    # When the user names a specific card (e.g. "amazon prime card") the merchant
    # field sometimes captures it instead of `account`. If we resolved an account
    # name, don't also treat that same token as a spending merchant.
    merchant = ents.merchant.lower() if ents.merchant else None
    if account_name and merchant and account_name in merchant:
        merchant = None

    return QueryContext(
        date_from=date_from,
        date_to=date_to,
        timeframe_label=label,
        category=category,
        merchant=merchant,
        institution=inst_slug,
        account_type=None,
        account_name=account_name,
        amount_min=ents.amount_min,
        amount_max=ents.amount_max,
    )


def _parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


# ── Main entry point ──────────────────────────────────────────────────────────

async def route(
    question: str,
    *,
    req_id: str = "",
    conversation_id: str = "",
) -> RoutingOutcome:
    """Run the full pipeline for a question and return a RoutingOutcome."""
    req_id = req_id or get_request_id()
    steps: list[str] = []

    logger.info(
        "chat_router.start",
        extra={
            "stage": "chat_router_start",
            "request_id": req_id,
            "conversation_id": conversation_id or "none",
            "user_question": question[:200],
            "selected_model": settings.ollama.model,
        },
    )

    # ── 1. Classify ──────────────────────────────────────────────────────────
    classification = await classify(question)

    # ── 1b. Merge prior conversation context for follow-up resolution ────────
    if conversation_id:
        classification = await conversation_context.resolve_followup(
            conversation_id, classification
        )

    # ── 1c. Build routing decision (complexity gate) ──────────────────────────
    decision = build_route_decision(classification, question=question)
    decision.llm_called = classification.source == "llm"

    query_intent = to_query_intent(classification.intent)
    ctx = _build_context(classification)

    # ── 1d. Query planner — structured plan from classification + decision ────
    query_plan = await build_query_plan(
        classification, decision, question=question, ctx=ctx
    )

    # When the planner says clarification is needed and the classifier agrees,
    # honour that immediately (avoids a wasted SQL round-trip).
    if query_plan.requires_clarification() and classification.intent == ChatIntent.UNKNOWN:
        steps.append("planner_requested_clarification")
        return _finalize(
            _clarification_answer(question, classification, query_intent),
            classification, query_intent, "clarification", CLARIFICATION_NEEDED,
            steps, 0, 0, req_id, decision, query_plan,
        )

    # Use the planner's resolved context for downstream SQL (preferred path).
    ctx = query_plan.to_query_context()
    # Embed route_risk into ctx so answer_builder can read it without an extra kwarg.
    ctx.route_risk = decision.route_risk.value if decision else "safe"

    logger.info(
        "chat_router.classified",
        extra={
            "stage": "chat_router_classified",
            "request_id": req_id,
            "classifier_intent": classification.intent.value,
            "classifier_source": classification.source,
            "data_source": classification.data_source.value,
            "confidence": round(classification.confidence, 3),
            "query_intent": query_intent.value,
            "route_type": decision.route_type.value,
            "route_risk": decision.route_risk.value,
            "complexity_signals": decision.complexity_signals,
            "llm_called": decision.llm_called,
            "category": ctx.category,
            "institution": ctx.institution,
            "merchant": ctx.merchant,
            "timeframe": ctx.timeframe_label or None,
        },
    )

    # ── 2. Explicit clarification request from the classifier ────────────────
    if classification.needs_clarification and classification.intent == ChatIntent.UNKNOWN:
        steps.append("classifier_requested_clarification")
        return _finalize(
            _clarification_answer(question, classification, query_intent),
            classification, query_intent, "clarification", CLARIFICATION_NEEDED,
            steps, 0, 0, req_id, decision, query_plan,
        )

    # ── 3. Resolve route ─────────────────────────────────────────────────────
    path = _resolve_path(classification.data_source, query_intent)

    # ── 4. SQL exact execution — no silent filter relaxation ─────────────────
    sql_result: dict[str, Any] | None = None
    if path in (QueryPath.SQL, QueryPath.HYBRID):
        sql_result, sql_steps = await _sql_exact(query_intent, question, ctx, req_id)
        steps.extend(sql_steps)

    sql_rows = len(sql_result["rows"]) if sql_result and sql_result.get("rows") else 0
    has_sql = sql_rows > 0

    # ── 5. RAG (for rag/hybrid, or as a fallback when SQL came back empty) ────
    rag_chunks = 0
    force_rag = path in (QueryPath.FTS, QueryPath.VECTOR, QueryPath.HYBRID)
    rag_fallback = (not has_sql) and path == QueryPath.SQL
    if force_rag or rag_fallback:
        if rag_fallback:
            steps.append("rag_fallback")
        rag_chunks = await _count_rag(question)

    # ── 6. If we have data (or suggestions), let answer_builder compose the answer
    sql_was_relaxed = bool(sql_result and sql_result.get("_relaxed"))
    has_suggestions = bool(sql_result and sql_result.get("suggestions"))
    if has_sql or rag_chunks > 0 or has_suggestions:
        effective_path = path
        if rag_fallback and rag_chunks > 0:
            effective_path = QueryPath.HYBRID  # blend whatever SQL we have + chunks
        answer = await build_answer(
            question, query_intent, effective_path,
            classification.confidence, ctx, req_id=req_id,
        )
        # Labeled relaxation — attach a visible caveat so the user knows we broadened.
        if sql_was_relaxed:
            answer.caveats = list(answer.caveats or [])
            answer.caveats.append(
                "Search broadened: category/merchant filters were dropped because no exact "
                "match was found. Results may include other categories."
            )
        status = PARTIAL if (not has_sql or sql_was_relaxed) else ANSWERED

        # Record resolved context for follow-up resolution
        if conversation_id:
            await _record_turn(conversation_id, classification, ctx, answer.summary)

        return _finalize(answer, classification, query_intent, effective_path.value,
                         status, steps, sql_rows, rag_chunks, req_id, decision, query_plan)

    # ── 7. Helpful fallback — never a bare "no data" ─────────────────────────
    steps.append("helpful_fallback")
    answer = await _helpful_answer(question, classification, query_intent, ctx, req_id)
    return _finalize(answer, classification, query_intent, "fallback",
                     NO_DATA_AFTER_FALLBACK, steps, 0, 0, req_id, decision, query_plan)


# ── Conversation context recording ────────────────────────────────────────────

async def _record_turn(
    conversation_id: str,
    classification: IntentClassificationResult,
    ctx: QueryContext,
    answer_summary: str,
) -> None:
    try:
        await conversation_context.record_turn(
            conversation_id,
            classification=classification,
            institution=ctx.institution,
            account_name=ctx.account_name,
            category=ctx.category,
            merchant=ctx.merchant,
            date_from=ctx.date_from.isoformat() if ctx.date_from else None,
            date_to=ctx.date_to.isoformat() if ctx.date_to else None,
            timeframe_label=ctx.timeframe_label,
            amount_min=ctx.amount_min,
            amount_max=ctx.amount_max,
            answer_summary=answer_summary[:200],
        )
    except Exception as exc:
        logger.warning("chat_router.record_turn_failed", extra={"error": str(exc)})


# ── Route resolution ──────────────────────────────────────────────────────────

def _resolve_path(data_source: DataSource, query_intent: QueryIntent) -> QueryPath:
    if data_source == DataSource.SQL:
        return QueryPath.SQL
    if data_source == DataSource.RAG:
        return QueryPath.FTS
    if data_source == DataSource.HYBRID:
        return QueryPath.HYBRID
    # unknown → broad hybrid fallback
    return QueryPath.HYBRID


# ── SQL execution with labeled relaxation fallback ────────────────────────────

async def _sql_exact(
    query_intent: QueryIntent,
    question: str,
    ctx: QueryContext,
    req_id: str,
) -> tuple[dict[str, Any], list[str]]:
    """Execute SQL with the user's exact filters first.

    If exact query returns nothing AND category/merchant filters were applied,
    retries once with those filters dropped (broadened search). The relaxation
    is always labeled — it is stored in result['_relaxed'] so callers can mark
    the answer as PARTIAL with a visible caveat. No silent widening.
    """
    steps: list[str] = ["sql_exact"]
    result = await sql_query.execute_for_intent(query_intent, question, ctx)
    if result.get("rows"):
        logger.info(
            "chat_router.sql_exact_hit",
            extra={"stage": "sql_exact", "request_id": req_id, "rows": len(result["rows"])},
        )
        return result, steps

    sug_count = len(result.get("suggestions", []))
    logger.info(
        "chat_router.sql_exact_miss",
        extra={
            "stage": "sql_exact_miss",
            "request_id": req_id,
            "searched_filters": result.get("searched_filters", {}),
            "suggestion_count": sug_count,
        },
    )

    # Labeled relaxation: drop category + merchant filters and retry once.
    # Only attempt when at least one of those filters was set (otherwise same query).
    if ctx.category is not None or ctx.merchant is not None:
        relaxed_ctx = ctx.model_copy(update={"category": None, "merchant": None})
        relaxed_result = await sql_query.execute_for_intent(query_intent, question, relaxed_ctx)
        if relaxed_result.get("rows"):
            steps.append("sql_relaxed_filters")
            relaxed_result["_relaxed"] = True
            logger.info(
                "chat_router.sql_relaxed_hit",
                extra={
                    "stage": "sql_relaxed_filters",
                    "request_id": req_id,
                    "rows": len(relaxed_result["rows"]),
                },
            )
            return relaxed_result, steps

    return result, steps


# ── RAG counting ──────────────────────────────────────────────────────────────

async def _count_rag(question: str) -> int:
    try:
        return len(await text_search.search(question))
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_router.fts_failed", extra={"error": str(exc)})
        return 0


# ── Helpful / clarification answers ───────────────────────────────────────────

async def _helpful_answer(
    question: str,
    classification: IntentClassificationResult,
    query_intent: QueryIntent,
    ctx: QueryContext,
    req_id: str,
) -> StructuredAnswer:
    """Explain what was searched and surface what data DOES exist."""
    inst_display = institution_display_name(ctx.institution)
    cat_display = category_display_name(ctx.category)

    searched_bits: list[str] = []
    if cat_display:
        searched_bits.append(f"{cat_display} transactions")
    if inst_display:
        searched_bits.append(f"at {inst_display}")
    if ctx.timeframe_label:
        searched_bits.append(f"for {ctx.timeframe_label}")
    searched = " ".join(searched_bits) if searched_bits else "your statements"

    cats = await availability.available_categories(ctx.institution)
    insts = await availability.available_institutions()
    earliest, latest = await availability.transaction_date_bounds(ctx.institution)

    lines = [f"I couldn't find {searched}."]
    if cats:
        pretty = ", ".join(category_display_name(c) or c for c in cats[:8])
        lines.append(f"Categories I do have: {pretty}.")
    if insts:
        lines.append(f"Institutions with data: {', '.join(insts[:8])}.")
    if earliest and latest:
        lines.append(f"Available date range: {earliest} to {latest}.")

    # One clarifying question as the final fallback.
    clarify = classification.clarifying_question
    if not clarify:
        if cat_display:
            clarify = (
                f"Want me to broaden the search beyond {cat_display} "
                "(e.g. related categories like supermarkets or food delivery)?"
            )
        else:
            clarify = "Could you tell me which account, institution, or time period you mean?"
    lines.append(clarify)

    answer = StructuredAnswer(
        answer_type="prose",
        title="I need a bit more to answer that",
        summary=" ".join(lines),
        intent=query_intent.value,
        query_path="fallback",
        confidence=classification.confidence,
        caveats=[f"Searched: {searched}."],
        suggested_followups=_followups_from_availability(cats, insts),
        request_id=req_id,
    )
    return answer


def _followups_from_availability(cats: list[str], insts: list[str]) -> list[str]:
    out: list[str] = []
    if cats:
        first = category_display_name(cats[0]) or cats[0]
        out.append(f"How much did I spend on {first}?")
    if insts:
        out.append(f"Show me {insts[0]} transactions")
    out.append("What documents have been uploaded?")
    out.append("What institutions are covered?")
    return out[:4]


def _clarification_answer(
    question: str,
    classification: IntentClassificationResult,
    query_intent: QueryIntent,
) -> StructuredAnswer:
    q = classification.clarifying_question or (
        "I'm not sure what you're asking about. Could you mention an account, "
        "institution, category, or time period?"
    )
    return StructuredAnswer(
        answer_type="prose",
        title="Could you clarify?",
        summary=q,
        intent=query_intent.value,
        query_path="clarification",
        confidence=classification.confidence,
        suggested_followups=[
            "How much did I spend on groceries last month?",
            "What fees did Morgan Stanley charge me?",
            "Show me my account balances",
        ],
    )


# ── Finalization + logging ────────────────────────────────────────────────────

def _finalize(
    answer: StructuredAnswer,
    classification: IntentClassificationResult,
    query_intent: QueryIntent,
    route: str,
    status: str,
    steps: list[str],
    sql_rows: int,
    rag_chunks: int,
    req_id: str,
    decision: RouteDecision | None = None,
    query_plan: QueryPlan | None = None,
) -> RoutingOutcome:
    logger.info(
        "chat_router.done",
        extra={
            "stage": "chat_router_done",
            "request_id": req_id,
            "selected_model": settings.ollama.model,
            "classifier_intent": classification.intent.value,
            "query_intent": query_intent.value,
            "selected_route": route,
            "route_type": decision.route_type.value if decision else "unknown",
            "route_risk": decision.route_risk.value if decision else "unknown",
            "complexity_signals": decision.complexity_signals if decision else [],
            "llm_called": decision.llm_called if decision else False,
            "plan_task_type": query_plan.task_type if query_plan else "unknown",
            "plan_source": query_plan.plan_source if query_plan else "unknown",
            "sql_rows": sql_rows,
            "rag_chunks": rag_chunks,
            "fallback_steps": steps,
            "final_answer_status": status,
            "answer_strategy": getattr(answer, "answer_strategy", "unknown"),
            "answer_llm_called": getattr(answer, "llm_called", True),
        },
    )
    return RoutingOutcome(
        answer=answer,
        classification=classification,
        query_intent=query_intent,
        route=route,
        final_answer_status=status,
        fallback_steps=steps,
        sql_rows=sql_rows,
        rag_chunks=rag_chunks,
        route_decision=decision,
        query_plan=query_plan,
    )
