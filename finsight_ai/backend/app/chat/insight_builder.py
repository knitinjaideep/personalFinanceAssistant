"""
Insight Builder — translates FactBundle facts into interpreted meaning before
the LLM writes the final answer.

Pipeline position:
    SQLResult / RetrievalResult → FactBundle → InsightBundle → AnswerBuilder

Rules:
  - ALL calculations stay in FactBundle (never in InsightBundle).
  - InsightBundle interprets meaning from pre-computed facts.
  - direct_answer and supporting_facts are 100% deterministic (no LLM).
  - primary_insight is deterministic for most cases; only advisory/analytical
    modes produce a one-line characterization that names no new numbers.
  - LLM is NOT called here. This module is pure Python.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from app.chat.answer_style import AnswerMode, ResponseShape
from app.chat.fact_builder import FactBundle
from app.domain.enums import QueryIntent

if TYPE_CHECKING:
    from app.chat.answer_style import AnswerStyleDecision
    from app.chat.query_planner import QueryPlan
    from app.domain.classification import IntentClassificationResult, RouteDecision


# ── Model ─────────────────────────────────────────────────────────────────────

class InsightBundle(BaseModel):
    """Interpreted meaning derived from FactBundle before LLM narration."""

    # A complete, single-sentence factual answer (numbers included, from FactBundle).
    # None when the facts don't resolve to a single clear answer.
    direct_answer: str | None = None

    # A one-sentence characterization of what the number *means* in context.
    # Never contains a new number — only references pre-computed facts.
    primary_insight: str | None = None

    # Key facts in human-readable form (from FactBundle, no new arithmetic).
    supporting_facts: list[str] = Field(default_factory=list)

    # Caveats forwarded from FactBundle + any insight-level caveats.
    caveats: list[str] = Field(default_factory=list)

    # Suggested follow-up questions (forwarded from FactBundle, intent-aware).
    recommended_followups: list[str] = Field(default_factory=list)

    # How reliable the interpretation is given data completeness.
    confidence: Literal["low", "medium", "high"] = "medium"

    # The answer mode and shape decided upstream (forwarded for LLM prompt).
    answer_mode: AnswerMode = AnswerMode.FACTUAL
    response_shape: ResponseShape = ResponseShape.ONE_LINE_ANSWER

    # Provenance summary for the LLM context block.
    source_summary: dict[str, Any] | None = None


# ── Public entry point ─────────────────────────────────────────────────────────

def build_insights(
    question: str,
    intent_result: "IntentClassificationResult | None",
    route_decision: "RouteDecision | None",
    query_plan: "QueryPlan | None",
    sql_result: dict[str, Any] | None = None,
    retrieval_chunks: list[Any] | None = None,
    fact_bundle: FactBundle | None = None,
    answer_style: "AnswerStyleDecision | None" = None,
    *,
    query_intent: QueryIntent | None = None,
) -> InsightBundle:
    """
    Derive an InsightBundle from pre-computed facts.

    Deterministic — no LLM calls. All numbers come from fact_bundle.

    Args:
        query_intent: Pre-resolved QueryIntent (preferred). When None, falls
                      back to resolving from intent_result.
    """
    fb = fact_bundle or FactBundle()
    intent = query_intent if query_intent is not None else _resolve_intent(intent_result)
    answer_mode = answer_style.answer_mode if answer_style else AnswerMode.FACTUAL
    response_shape = answer_style.response_shape if answer_style else ResponseShape.ONE_LINE_ANSWER

    # ── Direct answer ──────────────────────────────────────────────────────────
    direct_answer = _build_direct_answer(intent, fb, sql_result, retrieval_chunks)

    # ── Primary insight (interpretation, no new numbers) ──────────────────────
    primary_insight = _build_primary_insight(intent, fb, answer_mode, question)

    # ── Supporting facts ───────────────────────────────────────────────────────
    supporting_facts = _build_supporting_facts(intent, fb, sql_result)

    # ── Caveats ────────────────────────────────────────────────────────────────
    caveats = list(fb.caveats)
    relaxed = bool(sql_result and sql_result.get("_relaxed"))
    if relaxed:
        caveats.append(
            "Search was broadened: category or merchant filters were relaxed "
            "because no exact match was found."
        )
    if fb.missing_data_notes:
        caveats.extend(fb.missing_data_notes)

    # ── Confidence ────────────────────────────────────────────────────────────
    confidence = _derive_confidence(fb, sql_result, retrieval_chunks, relaxed)

    # ── Source summary ────────────────────────────────────────────────────────
    source_summary = _build_source_summary(fb, sql_result, retrieval_chunks)

    return InsightBundle(
        direct_answer=direct_answer,
        primary_insight=primary_insight,
        supporting_facts=supporting_facts,
        caveats=caveats,
        recommended_followups=fb.suggested_followups,
        confidence=confidence,
        answer_mode=answer_mode,
        response_shape=response_shape,
        source_summary=source_summary,
    )


# ── Direct answer builders (one sentence, uses only FactBundle numbers) ────────

def _build_direct_answer(
    intent: QueryIntent,
    fb: FactBundle,
    sql_result: dict[str, Any] | None,
    retrieval_chunks: list[Any] | None,
) -> str | None:
    period = fb.filters_used.get("period") or fb.date_range or ""
    period_clause = f" {period}" if period else ""

    if intent == QueryIntent.SPENDING_BY_CATEGORY:
        if fb.total_spend is not None:
            top = fb.top_categories[0].category if fb.top_categories else None
            if top:
                return (
                    f"You spent ${fb.total_spend:,.2f}{period_clause}, "
                    f"with {top} as your largest category."
                )
            return f"You spent ${fb.total_spend:,.2f}{period_clause}."

    if intent == QueryIntent.TRANSACTION_LOOKUP:
        if fb.total_spend is not None and fb.transaction_count:
            return (
                f"Found {fb.transaction_count} transaction"
                f"{'s' if fb.transaction_count != 1 else ''} "
                f"totaling ${fb.total_spend:,.2f}{period_clause}."
            )

    if intent == QueryIntent.SUBSCRIPTION_LOOKUP:
        if fb.total_spend is not None and fb.transaction_count:
            return (
                f"Found {fb.transaction_count} recurring charge"
                f"{'s' if fb.transaction_count != 1 else ''} "
                f"totaling ${fb.total_spend:,.2f}{period_clause}."
            )

    if intent == QueryIntent.FEE_SUMMARY:
        if fb.total_fees is not None:
            return f"Total fees charged{period_clause}: ${fb.total_fees:,.2f}."

    if intent == QueryIntent.BALANCE_LOOKUP:
        if fb.balance is not None:
            acct = f" ({fb.account_name})" if fb.account_name else ""
            return f"Your account balance{acct} is ${fb.balance:,.2f}."

    if intent == QueryIntent.HOLDINGS_TOTAL:
        if fb.holdings_value is not None:
            return f"Total portfolio value: ${fb.holdings_value:,.2f}."

    if intent == QueryIntent.HOLDINGS_LOOKUP:
        if fb.holdings_value is not None and fb.transaction_count:
            return (
                f"Found {fb.transaction_count} holding"
                f"{'s' if fb.transaction_count != 1 else ''} "
                f"with total market value ${fb.holdings_value:,.2f}."
            )

    if intent == QueryIntent.CASH_FLOW_SUMMARY:
        if fb.net_cash_flow is not None:
            direction = "positive" if fb.net_cash_flow >= 0 else "negative"
            return (
                f"Net cash flow{period_clause}: ${fb.net_cash_flow:,.2f} ({direction})."
            )

    # Generic fallback when some spend total was computed
    if fb.total_spend is not None:
        return f"Total: ${fb.total_spend:,.2f}{period_clause}."

    # RAG-only path — no single number to anchor on
    if retrieval_chunks:
        return None

    return None


# ── Primary insight (interpretation, references no new numbers) ────────────────

def _build_primary_insight(
    intent: QueryIntent,
    fb: FactBundle,
    answer_mode: AnswerMode,
    question: str,
) -> str | None:
    # Spending by category — characterize the distribution
    if intent == QueryIntent.SPENDING_BY_CATEGORY and fb.top_categories:
        total = fb.total_spend or 0.0
        top = fb.top_categories[0]
        if total > 0:
            share = top.amount / total
            if share >= 0.5:
                return (
                    f"{top.category} accounts for more than half of your total spending "
                    f"— it dominates this period."
                )
            elif share >= 0.3:
                return (
                    f"{top.category} is your largest category and represents "
                    f"a significant share of total spending."
                )
            elif len(fb.top_categories) >= 3:
                return (
                    "Spending is spread across multiple categories "
                    "rather than concentrated in one area."
                )

    # Transaction lookup — characterize volume
    if intent == QueryIntent.TRANSACTION_LOOKUP:
        if fb.transaction_count and fb.average_transaction is not None:
            if fb.average_transaction > 200:
                return "These are predominantly large transactions."
            elif fb.transaction_count > 30:
                return "This is a high volume of transactions for the period."

    # Fee summary — characterize relative to what's expected
    if intent == QueryIntent.FEE_SUMMARY and fb.total_fees is not None:
        if fb.total_fees == 0:
            return "No fees were charged during this period."
        if fb.top_categories:
            top_fee_cat = fb.top_categories[0].category
            return f"The majority of fees fall under {top_fee_cat}."

    # Balance lookup — no additional characterization beyond the number
    if intent == QueryIntent.BALANCE_LOOKUP:
        return None

    # Holdings — characterize concentration
    if intent in (QueryIntent.HOLDINGS_LOOKUP, QueryIntent.HOLDINGS_TOTAL):
        if fb.transaction_count and fb.transaction_count <= 3:
            return "Your portfolio is concentrated in a small number of positions."
        elif fb.transaction_count and fb.transaction_count > 10:
            return "Your portfolio is diversified across many positions."

    # Cash flow — characterize the direction
    if intent == QueryIntent.CASH_FLOW_SUMMARY and fb.net_cash_flow is not None:
        if fb.net_cash_flow > 0:
            if fb.total_income and fb.total_spend:
                return "You spent less than you earned during this period."
        elif fb.net_cash_flow < 0:
            return "Outflows exceeded inflows during this period."

    # Analytical mode — add an interpretation when we have comparison data
    if answer_mode == AnswerMode.ANALYTICAL and fb.comparison is not None:
        c = fb.comparison
        if c.delta > 0:
            return (
                f"Spending increased from {c.period_a_label} to {c.period_b_label} "
                f"— the increase appears in the figures above."
            )
        elif c.delta < 0:
            return (
                f"Spending decreased from {c.period_a_label} to {c.period_b_label}."
            )

    return None


# ── Supporting facts (from FactBundle, no arithmetic) ─────────────────────────

def _build_supporting_facts(
    intent: QueryIntent,
    fb: FactBundle,
    sql_result: dict[str, Any] | None,
) -> list[str]:
    facts: list[str] = []

    if fb.date_range:
        facts.append(f"Period: {fb.date_range}")

    if fb.institution:
        facts.append(f"Institution: {fb.institution.replace('_', ' ').title()}")

    if fb.account_name:
        facts.append(f"Account: {fb.account_name}")

    # Category breakdown (top 5)
    if fb.top_categories:
        for cat in fb.top_categories[:5]:
            facts.append(f"  {cat.category}: ${cat.amount:,.2f} ({cat.transaction_count} txns)")

    # Merchant breakdown (top 5, only for transaction/spending intents)
    if intent in (QueryIntent.TRANSACTION_LOOKUP, QueryIntent.SUBSCRIPTION_LOOKUP):
        for merch in fb.top_merchants[:5]:
            facts.append(f"  {merch.merchant}: ${merch.amount:,.2f}")

    # Cash flow components
    if intent == QueryIntent.CASH_FLOW_SUMMARY:
        if fb.total_income is not None:
            facts.append(f"Total inflow: ${fb.total_income:,.2f}")
        if fb.total_spend is not None:
            facts.append(f"Total outflow: ${fb.total_spend:,.2f}")

    # Holdings / balance metrics
    if intent in (QueryIntent.HOLDINGS_LOOKUP, QueryIntent.HOLDINGS_TOTAL):
        if fb.holdings_value is not None:
            facts.append(f"Total market value: ${fb.holdings_value:,.2f}")

    # Comparison delta
    if fb.comparison is not None:
        c = fb.comparison
        direction = "up" if c.delta >= 0 else "down"
        pct_str = f" ({abs(c.pct_change):.1f}%)" if c.pct_change is not None else ""
        facts.append(
            f"{c.period_a_label} → {c.period_b_label}: "
            f"${abs(c.delta):,.2f} {direction}{pct_str}"
        )

    # Row count
    if fb.rows_used:
        facts.append(f"Source rows: {fb.rows_used}")

    return facts


# ── Confidence derivation ──────────────────────────────────────────────────────

def _derive_confidence(
    fb: FactBundle,
    sql_result: dict[str, Any] | None,
    retrieval_chunks: list[Any] | None,
    relaxed: bool,
) -> Literal["low", "medium", "high"]:
    if relaxed:
        return "low"
    if fb.missing_data_notes:
        return "low"

    has_sql = bool(sql_result and sql_result.get("rows"))
    exact_match = bool(sql_result.get("exact_match", True)) if sql_result else True

    if has_sql and exact_match and fb.rows_used > 0:
        return "high"
    if has_sql and fb.rows_used > 0:
        return "medium"
    if retrieval_chunks:
        return "medium"

    return "low"


# ── Source summary ─────────────────────────────────────────────────────────────

def _build_source_summary(
    fb: FactBundle,
    sql_result: dict[str, Any] | None,
    retrieval_chunks: list[Any] | None,
) -> dict[str, Any] | None:
    summary: dict[str, Any] = {}

    if fb.institution:
        summary["institution"] = fb.institution
    if fb.account_name:
        summary["account"] = fb.account_name
    if fb.date_range:
        summary["date_range"] = fb.date_range
    if fb.rows_used:
        summary["sql_rows"] = fb.rows_used
    if retrieval_chunks:
        summary["rag_chunks"] = len(retrieval_chunks)
    if sql_result and sql_result.get("sql_used"):
        summary["sql_used"] = sql_result["sql_used"]

    return summary or None


# ── Intent resolver ────────────────────────────────────────────────────────────

def _resolve_intent(intent_result: "IntentClassificationResult | None") -> QueryIntent:
    if intent_result is None:
        return QueryIntent.HYBRID_FINANCIAL_QUESTION
    from app.services.intent_mapping import to_query_intent
    return to_query_intent(intent_result.intent)


# ── LLM context builder (called by answer_builder to compose the LLM prompt) ──

def build_llm_context_from_insight(
    insight: InsightBundle,
    fact_bundle: FactBundle,
    template_summary: str = "",
) -> str:
    """
    Compose the context block the LLM receives.

    Instead of raw facts, the LLM receives interpreted meaning:
      - direct_answer: pre-computed single-sentence answer
      - primary_insight: what the number means
      - supporting_facts: breakdown items
      - caveats: data quality notes
    """
    lines: list[str] = []

    if template_summary:
        lines.append(f"Template summary: {template_summary}")
        lines.append("")

    if insight.direct_answer:
        lines.append(f"Direct answer: {insight.direct_answer}")

    if insight.primary_insight:
        lines.append(f"Primary insight: {insight.primary_insight}")

    if insight.supporting_facts:
        lines.append("")
        lines.append("Supporting facts (pre-computed, do not recalculate):")
        for f in insight.supporting_facts:
            lines.append(f"  {f}")

    if insight.caveats:
        lines.append("")
        lines.append("Caveats:")
        for c in insight.caveats:
            lines.append(f"  - {c}")

    if insight.source_summary:
        lines.append("")
        lines.append("Data source:")
        for k, v in insight.source_summary.items():
            if k != "sql_used":
                lines.append(f"  {k}: {v}")

    lines.append(f"\nAnswer mode: {insight.answer_mode.value}")
    lines.append(f"Response shape: {insight.response_shape.value}")
    lines.append(f"Confidence: {insight.confidence}")

    return "\n".join(lines)
