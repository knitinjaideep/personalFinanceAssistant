"""
Deterministic answer templates for simple Coral chatbot responses.

The LLM is NOT called for template_only answers. Templates produce instant,
accurate responses for well-defined question types.

Decision logic:
  template_only       — single-metric SQL answers with no ambiguity
  llm_narrative       — analysis, comparisons, document/RAG answers, "why" questions
  hybrid_template_plus_llm — structured facts + LLM commentary (e.g. month comparisons)

Rule: if a question has a single clear numeric or list answer AND the SQL
returned exact rows, use a template. Otherwise use the LLM.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from app.chat.fact_builder import FactBundle
from app.domain.enums import QueryIntent


# ── Strategy enum ──────────────────────────────────────────────────────────────

class AnswerStrategy(str, Enum):
    TEMPLATE_ONLY = "template_only"
    LLM_NARRATIVE = "llm_narrative"
    HYBRID_TEMPLATE_PLUS_LLM = "hybrid_template_plus_llm"


# ── Strategy decision ──────────────────────────────────────────────────────────

# Intents that are safe for template-only answers when SQL hits exactly.
_TEMPLATE_SAFE_INTENTS: frozenset[QueryIntent] = frozenset({
    QueryIntent.SPENDING_BY_CATEGORY,
    QueryIntent.TRANSACTION_LOOKUP,
    QueryIntent.SUBSCRIPTION_LOOKUP,
    QueryIntent.FEE_SUMMARY,
    QueryIntent.BALANCE_LOOKUP,
    QueryIntent.HOLDINGS_TOTAL,
    QueryIntent.CASH_FLOW_SUMMARY,
    QueryIntent.DOCUMENT_AVAILABILITY,
    QueryIntent.INSTITUTION_COVERAGE,
    QueryIntent.STATEMENT_COVERAGE,
})

# Intents that always need the LLM narrative path.
_LLM_REQUIRED_INTENTS: frozenset[QueryIntent] = frozenset({
    QueryIntent.TEXT_EXPLANATION,
    QueryIntent.HYBRID_FINANCIAL_QUESTION,
})

# Complexity signals that upgrade template → hybrid or LLM.
_COMPLEXITY_KEYWORDS: tuple[str, ...] = (
    "why", "how am i doing", "unusual", "trend", "compare",
    "explain", "tell me about", "what does", "analysis", "insight",
    "projection", "forecast", "best", "worst", "should i",
)


def choose_strategy(
    intent: QueryIntent,
    question: str,
    fact_bundle: FactBundle,
    *,
    has_rag: bool = False,
    route_risk: str = "safe",
) -> AnswerStrategy:
    """
    Decide how to answer: template, LLM, or hybrid.

    Args:
        intent:      Resolved query intent.
        question:    Raw user question (lowercased internally for matching).
        fact_bundle: Pre-computed facts from fact_builder.
        has_rag:     True if text/RAG results are included in this answer.
        route_risk:  RouteRisk value string from the routing decision.

    Returns:
        AnswerStrategy enum value.
    """
    # No data → no template, use a no-data prose answer
    if fact_bundle.rows_used == 0:
        return AnswerStrategy.TEMPLATE_ONLY   # no_data template handles this

    # Always LLM for document/hybrid intents or when RAG is involved
    if intent in _LLM_REQUIRED_INTENTS or has_rag:
        return AnswerStrategy.LLM_NARRATIVE

    # Complexity signals in the question → upgrade to hybrid
    q_lower = question.lower()
    if any(kw in q_lower for kw in _COMPLEXITY_KEYWORDS):
        return AnswerStrategy.HYBRID_TEMPLATE_PLUS_LLM

    # Routing risk upgrade
    if route_risk == "needs_llm_planner":
        return AnswerStrategy.HYBRID_TEMPLATE_PLUS_LLM

    # Comparison bundles → hybrid (needs LLM to phrase the delta)
    if fact_bundle.comparison is not None:
        return AnswerStrategy.HYBRID_TEMPLATE_PLUS_LLM

    # Safe simple intents → template_only
    if intent in _TEMPLATE_SAFE_INTENTS:
        return AnswerStrategy.TEMPLATE_ONLY

    return AnswerStrategy.LLM_NARRATIVE


# ── Template renderer ──────────────────────────────────────────────────────────

def render_template(
    intent: QueryIntent,
    fact_bundle: FactBundle,
    question: str = "",
) -> str:
    """
    Build a human-readable summary string from facts.
    Returns "" when no suitable template applies (caller falls back to LLM).
    """
    if fact_bundle.rows_used == 0:
        return _render_no_data(fact_bundle)

    if intent == QueryIntent.SPENDING_BY_CATEGORY:
        return _render_spending_by_category(fact_bundle)

    if intent in (QueryIntent.TRANSACTION_LOOKUP, QueryIntent.SUBSCRIPTION_LOOKUP):
        return _render_transaction_lookup(fact_bundle, question)

    if intent == QueryIntent.CASH_FLOW_SUMMARY:
        return _render_cash_flow(fact_bundle)

    if intent == QueryIntent.FEE_SUMMARY:
        return _render_fees(fact_bundle)

    if intent == QueryIntent.BALANCE_LOOKUP:
        return _render_balance(fact_bundle)

    if intent == QueryIntent.HOLDINGS_TOTAL:
        return _render_holdings(fact_bundle)

    if intent in (
        QueryIntent.DOCUMENT_AVAILABILITY,
        QueryIntent.INSTITUTION_COVERAGE,
        QueryIntent.STATEMENT_COVERAGE,
    ):
        return _render_coverage(fact_bundle)

    return ""


# ── Individual templates ───────────────────────────────────────────────────────

def _render_spending_by_category(b: FactBundle) -> str:
    parts: list[str] = []

    period = _period_phrase(b)
    inst = _institution_phrase(b)
    qualifier = f"{inst}{period}" if (inst or period) else ""

    if b.top_categories:
        total_str = _fmt_money(b.total_spend)
        count_str = _fmt_count(b.transaction_count)
        top = b.top_categories[0]
        top_str = _fmt_money(top.amount)

        if len(b.top_categories) == 1:
            parts.append(
                f"You spent {total_str} on {top.category}{qualifier}"
                f" across {count_str}."
            )
        else:
            parts.append(
                f"Your total spend{qualifier} was {total_str}"
                f" across {count_str}."
            )
            parts.append(
                f"Top category: {top.category} at {top_str}."
            )
    elif b.total_spend is not None:
        total_str = _fmt_money(b.total_spend)
        count_str = _fmt_count(b.transaction_count)
        parts.append(f"Your total spend{qualifier} was {total_str} across {count_str}.")

    return " ".join(parts) if parts else ""


def _render_transaction_lookup(b: FactBundle, question: str) -> str:
    period = _period_phrase(b)
    inst = _institution_phrase(b)
    qualifier = f"{inst}{period}" if (inst or period) else ""

    count = b.transaction_count
    total = b.total_spend

    # Single merchant lookup (e.g. "Costco transactions")
    if b.filters_used.get("merchant") and b.top_merchants:
        merchant = b.top_merchants[0].merchant
        amt_str = _fmt_money(total)
        count_str = _fmt_count(count)
        return (
            f"You spent {amt_str} at {merchant}{qualifier} across {count_str}."
        )

    # Generic transaction list
    if total is not None and count:
        total_str = _fmt_money(total)
        count_str = _fmt_count(count)
        return f"Found {count_str}{qualifier} totalling {total_str}."

    if count:
        return f"Found {_fmt_count(count)}{qualifier}."

    return ""


def _render_cash_flow(b: FactBundle) -> str:
    period = _period_phrase(b)
    inst = _institution_phrase(b)
    qualifier = f"{inst}{period}" if (inst or period) else ""

    income = _fmt_money(b.total_income)
    spend = _fmt_money(b.total_spend)
    net = b.net_cash_flow

    if b.total_income is not None and b.total_spend is not None:
        net_str = _fmt_money(net)
        direction = "positive" if (net or 0) >= 0 else "negative"
        return (
            f"Your cash flow{qualifier}: {income} in, {spend} out,"
            f" {net_str} net ({direction})."
        )
    if net is not None:
        return f"Your net cash flow{qualifier} was {_fmt_money(net)}."
    return ""


def _render_fees(b: FactBundle) -> str:
    period = _period_phrase(b)
    inst = _institution_phrase(b)
    qualifier = f"{inst}{period}" if (inst or period) else ""

    if b.total_fees is not None:
        fee_str = _fmt_money(b.total_fees)
        count_str = _fmt_count(b.transaction_count)
        if b.top_categories:
            top = b.top_categories[0]
            return (
                f"You were charged {fee_str} in fees{qualifier}"
                f" ({count_str}). Top fee type: {top.category}."
            )
        return f"You were charged {fee_str} in fees{qualifier} ({count_str})."
    return ""


def _render_balance(b: FactBundle) -> str:
    period = _period_phrase(b)
    inst = _institution_phrase(b)
    qualifier = f"{inst}{period}" if (inst or period) else ""

    if b.balance is not None:
        bal_str = _fmt_money(b.balance)
        return f"Your account balance{qualifier} is {bal_str}."
    return ""


def _render_holdings(b: FactBundle) -> str:
    period = _period_phrase(b)
    inst = _institution_phrase(b)
    qualifier = f"{inst}{period}" if (inst or period) else ""

    if b.holdings_value is not None:
        val_str = _fmt_money(b.holdings_value)
        return f"Your total invested amount{qualifier} is {val_str}."
    return ""


def _render_coverage(b: FactBundle) -> str:
    if b.rows_used == 0:
        return "No documents found."
    return f"Found {b.rows_used} document(s) in your library."


def _render_no_data(b: FactBundle) -> str:
    filters = b.filters_used
    parts: list[str] = []

    merchant = filters.get("merchant")
    category = filters.get("category")
    period = filters.get("period") or (
        f"{filters.get('date_from', '')} to {filters.get('date_to', '')}".strip(" to")
    )
    institution = filters.get("institution")

    if merchant:
        parts.append(f"{merchant}")
    elif category:
        parts.append(f"{category}")

    if institution:
        inst = str(institution).replace("_", " ").title()
        parts.append(f"at {inst}")
    if period:
        parts.append(f"in {period}")

    subject = " ".join(parts) if parts else "matching data"
    return f"I found no {subject} transactions."


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _fmt_money(val: float | None) -> str:
    if val is None:
        return "$0.00"
    # Negative values: show as -$X,XXX.XX
    if val < 0:
        return f"-${abs(val):,.2f}"
    return f"${val:,.2f}"


def _fmt_count(n: int | None) -> str:
    if not n:
        return "0 transactions"
    return f"{n} transaction{'s' if n != 1 else ''}"


def _period_phrase(b: FactBundle) -> str:
    period = b.filters_used.get("period")
    if period:
        return f" in {period}"
    if b.date_from and b.date_to:
        from_str = b.date_from.strftime("%b %Y") if b.date_from else ""
        to_str = b.date_to.strftime("%b %Y") if b.date_to else ""
        if from_str == to_str:
            return f" in {from_str}"
        return f" from {from_str} to {to_str}"
    return ""


def _institution_phrase(b: FactBundle) -> str:
    inst = b.institution or b.filters_used.get("institution")
    if not inst:
        return ""
    return f" ({str(inst).replace('_', ' ').title()})"


# ── LLM context builder (for hybrid path) ─────────────────────────────────────

def build_llm_context_from_facts(
    fact_bundle: FactBundle,
    template_summary: str = "",
) -> str:
    """
    Build a compact data context string for the LLM when using hybrid strategy.
    The LLM receives computed facts, not raw rows. It must explain, not calculate.
    """
    lines: list[str] = []

    if template_summary:
        lines.append(f"Summary: {template_summary}")

    if fact_bundle.total_spend is not None:
        lines.append(f"Total spend: ${fact_bundle.total_spend:,.2f}")
    if fact_bundle.total_income is not None:
        lines.append(f"Total income: ${fact_bundle.total_income:,.2f}")
    if fact_bundle.net_cash_flow is not None:
        lines.append(f"Net cash flow: ${fact_bundle.net_cash_flow:,.2f}")
    if fact_bundle.total_fees is not None:
        lines.append(f"Total fees: ${fact_bundle.total_fees:,.2f}")
    if fact_bundle.balance is not None:
        lines.append(f"Balance: ${fact_bundle.balance:,.2f}")
    if fact_bundle.holdings_value is not None:
        lines.append(f"Holdings value: ${fact_bundle.holdings_value:,.2f}")
    if fact_bundle.transaction_count:
        lines.append(f"Transaction count: {fact_bundle.transaction_count}")
    if fact_bundle.average_transaction is not None:
        lines.append(f"Average transaction: ${fact_bundle.average_transaction:,.2f}")
    if fact_bundle.date_range:
        lines.append(f"Date range: {fact_bundle.date_range}")

    if fact_bundle.top_categories:
        lines.append("Top categories:")
        for c in fact_bundle.top_categories[:5]:
            lines.append(f"  - {c.category}: ${c.amount:,.2f} ({c.transaction_count} txn)")

    if fact_bundle.top_merchants:
        lines.append("Top merchants:")
        for m in fact_bundle.top_merchants[:5]:
            lines.append(f"  - {m.merchant}: ${m.amount:,.2f} ({m.transaction_count} txn)")

    if fact_bundle.comparison:
        cmp = fact_bundle.comparison
        lines.append(
            f"Comparison: {cmp.period_a_label} ${cmp.period_a_value:,.2f} vs "
            f"{cmp.period_b_label} ${cmp.period_b_value:,.2f} "
            f"(delta: ${cmp.delta:+,.2f}"
            + (f", {cmp.pct_change:+.1f}%" if cmp.pct_change is not None else "")
            + ")"
        )

    if fact_bundle.institution:
        lines.append(f"Institution: {fact_bundle.institution}")

    if fact_bundle.caveats:
        lines.append("Caveats: " + "; ".join(fact_bundle.caveats))

    return "\n".join(lines)
