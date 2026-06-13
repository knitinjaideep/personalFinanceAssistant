"""
Structured query planner for Coral's chat pipeline.

Sits between the intent classifier / route-decision layer and the SQL execution
layer.  Instead of passing loose intent + entity fields into sql_query, the
planner emits a typed ``QueryPlan`` that captures *what to compute*, *what to
filter on*, and *how to present the result*.

Two planning paths:
  1. Deterministic (route_risk == SAFE, route_type == SIMPLE_SQL):
     Pure rule-based translation, ~0 ms, no LLM.
  2. LLM-assisted (route_risk == NEEDS_LLM_PLANNER):
     Sends a tight JSON schema prompt to the local model; validates the
     response strictly through Pydantic before use.

If the LLM path fails for any reason the planner falls back to the
deterministic path rather than crashing.

Usage inside chat_router.route():

    from app.chat.query_planner import plan

    query_plan = await plan(classification, decision, question=question)
    # query_plan.to_query_context() replaces the old _build_context() call
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.logger import get_logger
from app.domain.classification import (
    ChatIntent,
    ExtractedEntities,
    IntentClassificationResult,
    RouteDecision,
    RouteRisk,
    RouteType,
)
from app.domain.entities import QueryContext

logger = get_logger(__name__)

# ── Task type taxonomy ────────────────────────────────────────────────────────

PlanTaskType = Literal[
    "aggregate_transactions",   # SUM / total spend for a filter set
    "list_transactions",        # list individual transactions
    "top_merchants",            # ranked merchant breakdown
    "top_categories",           # ranked category breakdown
    "compare_spending",         # period-over-period or institution comparison
    "balance_lookup",           # account balance / cash snapshot
    "investment_summary",       # portfolio / holdings total
    "document_search",          # FTS / RAG text retrieval
    "hybrid_analysis",          # SQL + document evidence combined
    "clarification",            # too vague to plan; ask user
]

# Metrics that the SQL layer can actually compute.  Others fail safely to
# clarification rather than producing wrong answers.
_SUPPORTED_METRICS: frozenset[str] = frozenset({
    "total_spent", "total_income", "total_fees",
    "transaction_count", "average_transaction",
    "balance", "net_worth",
    "holdings_value", "holdings_count",
})


# ── Sub-models ────────────────────────────────────────────────────────────────

class QueryFilters(BaseModel):
    """Normalized filter set applied to the primary SQL query."""

    date_from: date | None = None
    date_to: date | None = None
    timeframe_label: str = ""

    category: str | None = None
    merchant: str | None = None
    institution: str | None = None
    account_name: str | None = None

    amount_min: float | None = None
    amount_max: float | None = None

    is_recurring_only: bool = False
    limit: int = Field(default=50, ge=1, le=500)

    @field_validator("limit", mode="before")
    @classmethod
    def _clamp_limit(cls, v: object) -> int:
        try:
            n = int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 50
        return max(1, min(500, n))

    def to_query_context(self) -> QueryContext:
        """Convert to the QueryContext the existing SQL layer accepts."""
        return QueryContext(
            date_from=self.date_from,
            date_to=self.date_to,
            timeframe_label=self.timeframe_label,
            category=self.category,
            merchant=self.merchant,
            institution=self.institution,
            account_type=None,
            account_name=self.account_name,
            amount_min=self.amount_min,
            amount_max=self.amount_max,
            is_recurring_only=self.is_recurring_only,
            limit=self.limit,
        )


class MetricRequest(BaseModel):
    """Which aggregate metric the user is asking for."""

    name: str = "total_spent"       # one of _SUPPORTED_METRICS
    aggregation: str = "sum"        # sum | count | avg | min | max
    field: str = "amount"           # DB field to aggregate
    group_by: str | None = None     # "category" | "merchant" | "month" | None
    top_n: int | None = None        # return only top-N groups

    @field_validator("name", mode="before")
    @classmethod
    def _validate_metric(cls, v: object) -> str:
        if not isinstance(v, str):
            return "total_spent"
        clean = v.strip().lower()
        return clean if clean in _SUPPORTED_METRICS else "total_spent"

    @field_validator("aggregation", mode="before")
    @classmethod
    def _coerce_aggregation(cls, v: object) -> str:
        valid = {"sum", "count", "avg", "min", "max"}
        s = str(v).strip().lower() if v else "sum"
        return s if s in valid else "sum"


class ComparisonSpec(BaseModel):
    """Describes a period-over-period or side-by-side comparison."""

    period_a_label: str = ""        # e.g. "March 2025"
    period_b_label: str = ""        # e.g. "April 2025"
    filters_a: QueryFilters = Field(default_factory=QueryFilters)
    filters_b: QueryFilters = Field(default_factory=QueryFilters)
    compare_on: str = "total_spent" # metric to compare


class RetrievalSpec(BaseModel):
    """Parameters for FTS / vector text retrieval."""

    query_text: str = ""            # search text (may differ from raw question)
    institution: str | None = None  # narrow to a specific institution's docs
    top_k: int = Field(default=5, ge=1, le=20)


class ChartSpec(BaseModel):
    """Hints for frontend chart rendering (optional; planner fills when useful)."""

    chart_type: Literal["bar", "line", "pie", "table", "none"] = "none"
    x: str = ""         # field / label for the x-axis
    y: str = ""         # field / label for the y-axis
    title: str = ""


# ── Main output model ─────────────────────────────────────────────────────────

class QueryPlan(BaseModel):
    """Structured plan produced before any SQL / RAG execution.

    Shape mirrors the spec:
        task_type      — what to compute
        data_sources   — which retrieval paths to use
        metrics        — list of metric requests (aggregations)
        filters        — normalized filter set
        group_by       — optional grouping dimensions
        comparison     — period-over-period or side-by-side spec
        retrieval      — FTS / vector search spec
        chart          — frontend rendering hints
        clarification_needed — true when the question cannot be answered
        clarifying_question  — question to ask the user if needed

    The downstream SQL layer and answer builder consume this instead of raw
    (intent, entities) pairs.  ``to_query_context()`` converts the primary
    filters into the legacy QueryContext the SQL handlers still use.
    """

    # Core classification carried through
    task_type: PlanTaskType = "aggregate_transactions"
    intent: ChatIntent = ChatIntent.UNKNOWN

    # Explicit data-source list (e.g. ["sql"] or ["sql", "rag"])
    data_sources: list[str] = Field(default_factory=lambda: ["sql"])

    # Primary query parameters
    filters: QueryFilters = Field(default_factory=QueryFilters)

    # One or more metrics to compute (most questions need just one)
    metrics: list[MetricRequest] = Field(default_factory=lambda: [MetricRequest()])

    # Top-level grouping dimensions (mirrors MetricRequest.group_by for multi-metric cases)
    group_by: list[str] | None = None

    # Optional structured extensions
    comparison: ComparisonSpec | None = None
    retrieval: RetrievalSpec | None = None
    chart: ChartSpec | None = None

    # Clarification
    clarification_needed: bool = False
    clarifying_question: str | None = None

    # Planning metadata (not part of LLM contract, set by planner internally)
    plan_source: Literal["deterministic", "llm", "llm_fallback"] = "deterministic"
    plan_confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("plan_confidence", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> float:
        try:
            f = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.5
        return max(0.0, min(1.0, f))

    @field_validator("metrics", mode="before")
    @classmethod
    def _ensure_metrics_list(cls, v: object) -> object:
        # Accept a single MetricRequest dict from LLM output that forgot the list wrapper
        if isinstance(v, dict):
            return [v]
        return v

    def primary_metric(self) -> MetricRequest:
        """Convenience accessor for the first (usually only) metric."""
        return self.metrics[0] if self.metrics else MetricRequest()

    def to_query_context(self) -> QueryContext:
        """Convenience bridge so callers only need a QueryPlan."""
        return self.filters.to_query_context()

    def requires_clarification(self) -> bool:
        return self.clarification_needed or self.task_type == "clarification"


# ── Intent → task_type mapping ────────────────────────────────────────────────

_INTENT_TO_TASK: dict[ChatIntent, PlanTaskType] = {
    ChatIntent.SPENDING_SUMMARY: "aggregate_transactions",
    ChatIntent.TRANSACTION_SEARCH: "list_transactions",
    ChatIntent.INCOME_SUMMARY: "aggregate_transactions",
    ChatIntent.BALANCE_SUMMARY: "balance_lookup",
    ChatIntent.INVESTMENT_SUMMARY: "investment_summary",
    ChatIntent.FEES_SUMMARY: "aggregate_transactions",
    ChatIntent.DOCUMENT_LOOKUP: "document_search",
    ChatIntent.ACCOUNT_SUMMARY: "balance_lookup",
    ChatIntent.COMPARISON: "compare_spending",
    ChatIntent.RECURRING_TRANSACTIONS: "list_transactions",
    ChatIntent.UNKNOWN: "clarification",
}

# Intents whose default metric name/aggregation/field differs from total_spent/sum/amount
# maps intent → (name, aggregation, field)
_INTENT_TO_METRIC: dict[ChatIntent, tuple[str, str, str]] = {
    ChatIntent.INCOME_SUMMARY: ("total_income", "sum", "amount"),
    ChatIntent.FEES_SUMMARY: ("total_fees", "sum", "amount"),
    ChatIntent.BALANCE_SUMMARY: ("balance", "sum", "total_value"),
    ChatIntent.INVESTMENT_SUMMARY: ("holdings_value", "sum", "market_value"),
    ChatIntent.ACCOUNT_SUMMARY: ("balance", "sum", "total_value"),
    ChatIntent.TRANSACTION_SEARCH: ("transaction_count", "count", "id"),
    ChatIntent.RECURRING_TRANSACTIONS: ("transaction_count", "count", "id"),
}

# Intents that use document retrieval
_DOCUMENT_DATA_SOURCES: frozenset[ChatIntent] = frozenset({
    ChatIntent.DOCUMENT_LOOKUP,
})
_HYBRID_DATA_SOURCES: frozenset[ChatIntent] = frozenset({
    ChatIntent.INVESTMENT_SUMMARY,
    ChatIntent.FEES_SUMMARY,
})

# Intents that benefit from a chart even without LLM help
# maps intent → (chart_type, x, y)
_AUTO_CHART_INTENTS: dict[ChatIntent, tuple[str, str, str]] = {
    ChatIntent.SPENDING_SUMMARY: ("bar", "category", "amount"),
    ChatIntent.INCOME_SUMMARY: ("bar", "month", "amount"),
}


# ── Deterministic planner ─────────────────────────────────────────────────────

def _build_filters_from_entities(ents: ExtractedEntities, ctx: QueryContext) -> QueryFilters:
    """Combine already-normalized QueryContext with raw entities for completeness."""
    return QueryFilters(
        date_from=ctx.date_from,
        date_to=ctx.date_to,
        timeframe_label=ctx.timeframe_label,
        category=ctx.category,
        merchant=ctx.merchant,
        institution=ctx.institution,
        account_name=ctx.account_name,
        amount_min=ctx.amount_min,
        amount_max=ctx.amount_max,
        is_recurring_only=ctx.is_recurring_only,
        limit=ctx.limit,
    )


def _detect_top_n(question: str) -> int | None:
    """Extract 'top N' from questions like 'top 5 categories'."""
    m = re.search(r"\btop\s+(\d+)\b", question, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        return max(1, min(50, n))
    return None


def _detect_group_by(question: str, intent: ChatIntent) -> str | None:
    q = question.lower()
    if "by category" in q or "per category" in q or intent == ChatIntent.SPENDING_SUMMARY:
        return "category"
    if "by merchant" in q or "per merchant" in q or "top merchant" in q:
        return "merchant"
    if "by month" in q or "per month" in q or "monthly" in q:
        return "month"
    return None


def _make_comparison_spec(
    ents: ExtractedEntities,
    ctx: QueryContext,
    question: str,
) -> ComparisonSpec:
    """Rough period extraction for compare_spending plans.

    The question text already has time extracted into ctx.  For comparison we
    try to build two filter sets; if we can't distinguish them we leave both
    copies identical (the LLM path should handle this better).
    """
    base = QueryFilters(
        date_from=ctx.date_from,
        date_to=ctx.date_to,
        timeframe_label=ctx.timeframe_label,
        category=ctx.category,
        institution=ctx.institution,
        amount_min=ctx.amount_min,
        amount_max=ctx.amount_max,
    )
    period_a = ctx.timeframe_label or "period A"
    period_b = ents.compare_to or "period B"
    return ComparisonSpec(
        period_a_label=period_a,
        period_b_label=period_b,
        filters_a=base,
        filters_b=QueryFilters(institution=ctx.institution, category=ctx.category),
        compare_on="total_spent",
    )


def plan_deterministic(
    classification: IntentClassificationResult,
    ctx: QueryContext,
    question: str,
) -> QueryPlan:
    """Build a QueryPlan using only rule-based logic. Zero LLM latency."""
    intent = classification.intent
    ents = classification.entities

    task = _INTENT_TO_TASK.get(intent, "clarification")
    metric_tuple = _INTENT_TO_METRIC.get(intent, ("total_spent", "sum", "amount"))
    metric_name, aggregation, field = metric_tuple
    top_n = _detect_top_n(question)
    group_by_str = _detect_group_by(question, intent)

    filters = _build_filters_from_entities(ents, ctx)

    # Top-N questions → narrow the list and adjust task type
    if top_n and task == "aggregate_transactions":
        task = "top_categories" if group_by_str == "category" else "top_merchants"
        filters.limit = top_n

    # Mark recurring-only flag
    if intent == ChatIntent.RECURRING_TRANSACTIONS:
        filters.is_recurring_only = True

    metrics = [MetricRequest(
        name=metric_name,
        aggregation=aggregation,
        field=field,
        group_by=group_by_str,
        top_n=top_n,
    )]

    # Data sources
    if intent in _DOCUMENT_DATA_SOURCES:
        data_sources = ["rag"]
    elif intent in _HYBRID_DATA_SOURCES:
        data_sources = ["sql", "rag"]
    else:
        data_sources = ["sql"]

    # group_by list (mirrors primary metric's group_by for easy access)
    group_by_list: list[str] | None = [group_by_str] if group_by_str else None

    # Comparison spec
    comparison: ComparisonSpec | None = None
    if task == "compare_spending":
        comparison = _make_comparison_spec(ents, ctx, question)

    # Retrieval spec (document / hybrid)
    retrieval: RetrievalSpec | None = None
    if task in ("document_search", "hybrid_analysis") or "rag" in data_sources:
        retrieval = RetrievalSpec(
            query_text=question,
            institution=ctx.institution,
        )

    # Chart hint
    auto_chart = _AUTO_CHART_INTENTS.get(intent)
    chart: ChartSpec | None = None
    if auto_chart:
        chart_type, x, y = auto_chart
        chart = ChartSpec(chart_type=chart_type, x=x, y=y)

    # Clarification when genuinely unknown
    needs_clarification = task == "clarification"
    clarifying_q: str | None = None
    if needs_clarification:
        clarifying_q = (
            classification.clarifying_question
            or "Could you tell me which account, institution, or time period you mean?"
        )

    return QueryPlan(
        task_type=task,
        intent=intent,
        data_sources=data_sources,
        filters=filters,
        metrics=metrics,
        group_by=group_by_list,
        comparison=comparison,
        retrieval=retrieval,
        chart=chart,
        clarification_needed=needs_clarification,
        clarifying_question=clarifying_q,
        plan_source="deterministic",
        plan_confidence=classification.confidence,
    )


# ── LLM planner prompt + validation ──────────────────────────────────────────

_LLM_SYSTEM_PROMPT = """\
You are a query planner for a personal-finance assistant.
Given a user question and its pre-classified intent, output a SINGLE JSON object
that describes exactly how to query the data.

You MUST use one of these task_type values:
  aggregate_transactions | list_transactions | top_merchants | top_categories
  compare_spending | balance_lookup | investment_summary | document_search
  hybrid_analysis | clarification

Supported metric names (use exactly as written):
  total_spent | total_income | total_fees | transaction_count
  average_transaction | balance | net_worth | holdings_value | holdings_count

Output ONLY this JSON shape — no prose, no markdown fences:
{
  "task_type": "<task_type>",
  "data_sources": ["sql"],
  "filters": {
    "date_from": "<YYYY-MM-DD or null>",
    "date_to":   "<YYYY-MM-DD or null>",
    "timeframe_label": "<string>",
    "category": "<string or null>",
    "merchant": "<string or null>",
    "institution": "<string or null>",
    "account_name": "<string or null>",
    "amount_min": <float or null>,
    "amount_max": <float or null>,
    "is_recurring_only": <bool>,
    "limit": <int 1-500>
  },
  "metrics": [
    {
      "name": "<metric_name>",
      "aggregation": "sum",
      "field": "amount",
      "group_by": "<category|merchant|month or null>",
      "top_n": <int or null>
    }
  ],
  "group_by": ["<category|merchant|month>"] or null,
  "comparison": null,
  "retrieval": null,
  "chart": {
    "chart_type": "<bar|line|pie|table|none>",
    "x": "<field or label>",
    "y": "<field or label>",
    "title": "<string>"
  },
  "clarification_needed": false,
  "clarifying_question": "<string or null>",
  "plan_confidence": <float 0.0-1.0>
}

Rules:
- Set task_type="clarification" and clarification_needed=true only when unanswerable.
- For compare_spending, populate the comparison object with filters_a and filters_b.
- Prefer concrete filters over clarification.
- Leave date_from/date_to null when dates cannot be resolved.
- Never invent account balances or transaction amounts.
- data_sources must be a JSON array: ["sql"], ["rag"], or ["sql","rag"].
"""


def _extract_json_block(raw: str) -> str:
    """Pull the first {...} block out of a possibly-noisy LLM response."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


def _validate_plan(raw: str, fallback: QueryPlan) -> QueryPlan:
    """Parse + validate raw LLM text into a QueryPlan. Returns fallback on error."""
    try:
        data: dict[str, Any] = json.loads(_extract_json_block(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("query_planner.llm_json_parse_failed", extra={"error": str(exc), "raw": raw[:200]})
        return fallback

    # Coerce: LLM may return a single metric dict instead of a list
    if "metric" in data and "metrics" not in data:
        data["metrics"] = [data.pop("metric")]
    elif "metrics" in data and isinstance(data["metrics"], dict):
        data["metrics"] = [data["metrics"]]

    # Coerce: ensure data_sources is a list
    if "data_sources" in data and isinstance(data["data_sources"], str):
        data["data_sources"] = [data["data_sources"]]

    # Coerce comparison sub-object if present
    if "comparison" in data and data["comparison"] is not None:
        comp = data["comparison"]
        if isinstance(comp, dict):
            for key in ("filters_a", "filters_b"):
                if key not in comp:
                    comp[key] = {}

    try:
        plan = QueryPlan.model_validate(data)
        plan.plan_source = "llm"
        return plan
    except Exception as exc:  # noqa: BLE001
        logger.warning("query_planner.llm_plan_invalid", extra={"error": str(exc), "raw": raw[:200]})
        return fallback


async def _plan_with_llm(
    classification: IntentClassificationResult,
    fallback: QueryPlan,
    question: str,
) -> QueryPlan:
    """Call the local LLM to build a richer QueryPlan. Falls back on any error."""
    from app.config import settings
    from app.services import llm as llm_service

    model = settings.ollama.classification_model
    user_prompt = (
        f'Intent: {classification.intent.value}\n'
        f'Entities: {classification.entities.model_dump_json()}\n'
        f'Question: "{question}"'
    )
    try:
        raw = await llm_service.generate(
            user_prompt,
            model=model,
            system=_LLM_SYSTEM_PROMPT,
            temperature=0.0,
            format_json=True,
            num_ctx=settings.ollama.classification_num_ctx,
        )
        plan = _validate_plan(raw, fallback)
        plan.plan_source = "llm"
        pm = plan.primary_metric()
        logger.info(
            "query_planner.llm_plan_produced",
            extra={
                "task_type": plan.task_type,
                "metric": pm.name,
                "group_by": pm.group_by,
                "data_sources": plan.data_sources,
                "plan_confidence": plan.plan_confidence,
            },
        )
        return plan
    except Exception as exc:  # noqa: BLE001
        logger.warning("query_planner.llm_failed", extra={"error": str(exc)})
        fallback_copy = fallback.model_copy(update={"plan_source": "llm_fallback"})
        return fallback_copy


# ── Validation helpers ────────────────────────────────────────────────────────

def _validate_required_filters(plan: QueryPlan) -> QueryPlan:
    """Demote to clarification when critical filters are missing for specific tasks."""
    if plan.task_type == "compare_spending" and plan.comparison is None:
        return plan.model_copy(update={
            "task_type": "clarification",
            "clarification_needed": True,
            "clarifying_question": (
                "I can see you want to compare spending, but I need two time periods "
                "to compare (e.g. 'March vs April'). Could you clarify?"
            ),
        })
    return plan


# ── Public entry point ────────────────────────────────────────────────────────

async def plan(
    classification: IntentClassificationResult,
    decision: RouteDecision,
    *,
    question: str = "",
    ctx: QueryContext | None = None,
) -> QueryPlan:
    """Produce a QueryPlan from a classification result and routing decision.

    Args:
        classification: Validated output of the intent classifier.
        decision:       Routing decision from the complexity gate.
        question:       Raw user question (used for top-N detection, etc.).
        ctx:            Pre-built QueryContext from _build_context(); if None,
                        it is rebuilt from classification.entities directly.

    Returns:
        A validated QueryPlan ready for consumption by the SQL layer.
    """
    # Build a QueryContext from entities if caller didn't provide one.
    if ctx is None:
        from app.services.chat_router import _build_context
        ctx = _build_context(classification)

    # Deterministic plan is always built first (fast path and LLM fallback).
    det_plan = plan_deterministic(classification, ctx, question)

    # Choose planning path based on route_risk.
    if decision.route_risk == RouteRisk.NEEDS_LLM_PLANNER:
        final_plan = await _plan_with_llm(classification, det_plan, question)
    else:
        final_plan = det_plan

    # Post-planning validation (required-filter checks, etc.)
    final_plan = _validate_required_filters(final_plan)

    pm = final_plan.primary_metric()
    logger.info(
        "query_planner.plan_produced",
        extra={
            "task_type": final_plan.task_type,
            "intent": final_plan.intent.value,
            "data_sources": final_plan.data_sources,
            "metric": pm.name,
            "aggregation": pm.aggregation,
            "group_by": pm.group_by,
            "top_n": pm.top_n,
            "clarification_needed": final_plan.clarification_needed,
            "institution": final_plan.filters.institution,
            "category": final_plan.filters.category,
            "merchant": final_plan.filters.merchant,
            "timeframe": final_plan.filters.timeframe_label or None,
            "date_from": str(final_plan.filters.date_from) if final_plan.filters.date_from else None,
            "date_to": str(final_plan.filters.date_to) if final_plan.filters.date_to else None,
            "is_recurring_only": final_plan.filters.is_recurring_only,
            "plan_source": final_plan.plan_source,
            "plan_confidence": round(final_plan.plan_confidence, 3),
            "route_type": decision.route_type.value,
            "route_risk": decision.route_risk.value,
        },
    )

    return final_plan
