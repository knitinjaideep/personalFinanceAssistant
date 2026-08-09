"""
Tests for app.chat.insight_builder.

All tests are pure Python — no database, no Ollama, no network.

Acceptance criteria verified here:
  - InsightBundle created for spending summary (category breakdown)
  - InsightBundle created for category breakdown (dominant category insight)
  - InsightBundle created for balance lookup
  - Caveat included when SQL result used relaxed filters
  - No hallucinated numbers in insight fields (direct_answer only uses FactBundle values)
"""

from __future__ import annotations

import pytest

from app.chat.fact_builder import CategoryFact, FactBundle, MerchantFact, PeriodComparison
from app.chat.insight_builder import InsightBundle, build_insights, build_llm_context_from_insight
from app.domain.enums import QueryIntent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sql(rows: list[dict], *, relaxed: bool = False, **kwargs) -> dict:
    result: dict = {
        "rows": rows,
        "searched_filters": kwargs,
        "exact_match": not relaxed,
        "suggestions": [],
        "sql_used": "SELECT 1",
    }
    if relaxed:
        result["_relaxed"] = True
    return result


def _spending_fact_bundle(total: float, categories: list[tuple[str, float, int]]) -> FactBundle:
    cats = [CategoryFact(category=c, amount=a, transaction_count=n) for c, a, n in categories]
    return FactBundle(
        total_spend=total,
        transaction_count=sum(n for _, _, n in categories),
        top_categories=cats,
        rows_used=sum(n for _, _, n in categories),
        date_range="2026-05-01 to 2026-05-31",
    )


# ── Test 1: InsightBundle for spending summary ────────────────────────────────

def test_insight_bundle_spending_summary():
    """build_insights() produces a valid InsightBundle for SPENDING_BY_CATEGORY."""
    fb = _spending_fact_bundle(
        total=850.00,
        categories=[
            ("Restaurants", 320.00, 12),
            ("Groceries", 280.00, 8),
            ("Shopping", 250.00, 6),
        ],
    )
    sql = _sql([{"category": "Restaurants", "total_spent": "320.00"}])

    bundle = build_insights(
        question="How much did I spend last month?",
        intent_result=None,
        route_decision=None,
        query_plan=None,
        sql_result=sql,
        fact_bundle=fb,
        query_intent=QueryIntent.SPENDING_BY_CATEGORY,
    )

    assert isinstance(bundle, InsightBundle)
    assert bundle.direct_answer is not None
    assert "$850.00" in bundle.direct_answer
    # Top category mentioned
    assert "Restaurants" in bundle.direct_answer
    # Supporting facts include the breakdown
    fact_text = "\n".join(bundle.supporting_facts)
    assert "Restaurants" in fact_text
    assert "Groceries" in fact_text
    # No caveats for a clean, exact result
    assert bundle.confidence == "high"


# ── Test 2: InsightBundle for category breakdown (dominant-category insight) ──

def test_insight_bundle_dominant_category():
    """primary_insight says 'dominates' when top category > 50% of total."""
    fb = _spending_fact_bundle(
        total=1000.00,
        categories=[
            ("Restaurants", 600.00, 20),  # 60% → dominates
            ("Shopping", 400.00, 10),
        ],
    )
    bundle = build_insights(
        question="Show my top spending categories",
        intent_result=None,
        route_decision=None,
        query_plan=None,
        fact_bundle=fb,
        query_intent=QueryIntent.SPENDING_BY_CATEGORY,
    )

    assert bundle.primary_insight is not None
    assert "dominates" in bundle.primary_insight.lower() or "more than half" in bundle.primary_insight.lower()
    # Direct answer references the total and top category
    assert "Restaurants" in (bundle.direct_answer or "")
    # Primary insight must not contain new numbers (no arithmetic)
    import re
    # Allow "$" only if it directly references a pre-computed value already in direct_answer
    # The core rule: primary_insight itself should not contain dollar signs
    assert "$" not in (bundle.primary_insight or ""), (
        f"primary_insight contains a dollar sign (hallucinated number?): {bundle.primary_insight}"
    )


# ── Test 3: InsightBundle for balance lookup ─────────────────────────────────

def test_insight_bundle_balance_lookup():
    """build_insights() for BALANCE_LOOKUP returns balance in direct_answer."""
    fb = FactBundle(
        balance=12_345.67,
        account_name="Chase Checking",
        rows_used=1,
        date_range="2026-05-31 to 2026-05-31",
    )
    sql = _sql([{"total_value": "12345.67", "account_name": "Chase Checking"}])

    bundle = build_insights(
        question="What is my Chase checking balance?",
        intent_result=None,
        route_decision=None,
        query_plan=None,
        sql_result=sql,
        fact_bundle=fb,
        query_intent=QueryIntent.BALANCE_LOOKUP,
    )

    assert bundle.direct_answer is not None
    assert "$12,345.67" in bundle.direct_answer
    assert "Chase Checking" in bundle.direct_answer
    # Balance lookup has no meaningful primary_insight (just a number)
    # — no error if it's None
    assert bundle.confidence == "high"


# ── Test 4: Caveat when SQL used relaxed filters ──────────────────────────────

def test_caveat_when_sql_relaxed():
    """InsightBundle includes a caveat when sql_result has _relaxed=True."""
    fb = _spending_fact_bundle(
        total=500.00,
        categories=[("Other", 500.00, 5)],
    )
    # Simulate the relaxed-filter flag set by chat_router._sql_exact()
    sql = _sql([{"category": "Other", "total_spent": "500.00"}], relaxed=True)

    bundle = build_insights(
        question="How much did I spend on groceries?",
        intent_result=None,
        route_decision=None,
        query_plan=None,
        sql_result=sql,
        fact_bundle=fb,
        query_intent=QueryIntent.SPENDING_BY_CATEGORY,
    )

    assert bundle.confidence == "low"
    relaxed_caveat = [c for c in bundle.caveats if "broadened" in c.lower() or "relaxed" in c.lower()]
    assert relaxed_caveat, f"Expected a relaxed-filter caveat, got: {bundle.caveats}"


# ── Test 5: No hallucinated numbers ──────────────────────────────────────────

def test_no_hallucinated_numbers_in_insight_fields():
    """
    direct_answer and primary_insight must only contain numbers that are
    present in FactBundle. They must never invent or recalculate totals.
    """
    fb = _spending_fact_bundle(
        total=437.50,
        categories=[
            ("Travel", 220.00, 3),
            ("Food", 217.50, 9),
        ],
    )

    bundle = build_insights(
        question="Show my spending breakdown",
        intent_result=None,
        route_decision=None,
        query_plan=None,
        fact_bundle=fb,
        query_intent=QueryIntent.SPENDING_BY_CATEGORY,
    )

    # Every dollar amount appearing in direct_answer must come from FactBundle
    import re

    def extract_dollar_amounts(text: str) -> list[float]:
        # Match $1,234.56 or $1234.56 and strip the leading $
        return [
            float(m.lstrip("$").replace(",", ""))
            for m in re.findall(r"\$[\d,]+(?:\.\d+)?", text)
        ]

    known_values = {
        fb.total_spend,
        *[c.amount for c in fb.top_categories],
    }

    for field_text in [bundle.direct_answer or "", bundle.primary_insight or ""]:
        for amount in extract_dollar_amounts(field_text):
            assert amount in known_values, (
                f"Hallucinated amount ${amount:,.2f} not found in FactBundle "
                f"(known: {known_values}). Text: {field_text!r}"
            )


# ── Test 6: Fee summary InsightBundle ────────────────────────────────────────

def test_insight_bundle_fee_summary():
    """FEE_SUMMARY intent populates total_fees in direct_answer."""
    fb = FactBundle(
        total_fees=125.00,
        transaction_count=3,
        top_categories=[CategoryFact(category="Advisory Fee", amount=125.00, transaction_count=3)],
        rows_used=3,
        date_range="2026-05-01 to 2026-05-31",
    )

    bundle = build_insights(
        question="What fees did Morgan Stanley charge?",
        intent_result=None,
        route_decision=None,
        query_plan=None,
        fact_bundle=fb,
        query_intent=QueryIntent.FEE_SUMMARY,
    )

    assert bundle.direct_answer is not None
    assert "$125.00" in bundle.direct_answer
    assert "Advisory Fee" in (bundle.primary_insight or "") or bundle.primary_insight is not None


# ── Test 7: build_llm_context_from_insight shapes the LLM prompt ─────────────

def test_build_llm_context_from_insight_structure():
    """build_llm_context_from_insight() produces a well-structured context block."""
    fb = _spending_fact_bundle(total=850.00, categories=[("Restaurants", 850.00, 10)])
    bundle = build_insights(
        question="How much did I spend?",
        intent_result=None,
        route_decision=None,
        query_plan=None,
        fact_bundle=fb,
        query_intent=QueryIntent.SPENDING_BY_CATEGORY,
    )

    ctx = build_llm_context_from_insight(bundle, fb, template_summary="You spent $850.00.")

    assert "Direct answer" in ctx
    assert "$850.00" in ctx
    assert "Supporting facts" in ctx
    assert "Answer mode" in ctx
    assert "Confidence" in ctx
    # The LLM context must not contain raw SQL column names
    assert "total_spent" not in ctx
    assert "transaction_count" not in ctx


# ── Test 8: InsightBundle with missing data ───────────────────────────────────

def test_insight_bundle_empty_fact_bundle():
    """Empty FactBundle produces a low-confidence InsightBundle with no direct_answer."""
    bundle = build_insights(
        question="How much did I spend?",
        intent_result=None,
        route_decision=None,
        query_plan=None,
        fact_bundle=FactBundle(),
    )

    assert isinstance(bundle, InsightBundle)
    assert bundle.direct_answer is None
    assert bundle.confidence == "low"
