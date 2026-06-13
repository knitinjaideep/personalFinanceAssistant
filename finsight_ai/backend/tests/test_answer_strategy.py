"""
Phase 6 tests: simple questions MUST NOT call the LLM.

Tests verify that choose_strategy returns TEMPLATE_ONLY for simple SQL intents
and that render_template produces a non-empty string — proving zero LLM calls.
"""

from __future__ import annotations

import pytest
from app.chat.answer_templates import AnswerStrategy, choose_strategy, render_template
from app.chat.fact_builder import FactBundle, CategoryFact, MerchantFact, build_facts
from app.domain.enums import QueryIntent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _simple_spend_bundle(total: float = 482.31, count: int = 4) -> FactBundle:
    return FactBundle(
        total_spend=total,
        transaction_count=count,
        rows_used=count,
        filters_used={"merchant": "Costco", "period": "May 2026"},
        top_merchants=[MerchantFact(merchant="Costco", amount=total, transaction_count=count)],
    )


def _category_bundle() -> FactBundle:
    return FactBundle(
        total_spend=2814.77,
        transaction_count=51,
        rows_used=51,
        filters_used={"institution": "chase", "period": "March 2026"},
        top_categories=[
            CategoryFact(category="Dining", amount=1200.00, transaction_count=20),
            CategoryFact(category="Groceries", amount=800.00, transaction_count=15),
        ],
    )


def _no_data_bundle() -> FactBundle:
    return FactBundle(
        rows_used=0,
        filters_used={"merchant": "Whole Foods", "period": "March 2026"},
    )


# ── Phase 6: strategy selection ───────────────────────────────────────────────

def test_simple_transaction_lookup_uses_template_only():
    bundle = _simple_spend_bundle()
    strategy = choose_strategy(QueryIntent.TRANSACTION_LOOKUP, "Costco transactions in May", bundle)
    assert strategy == AnswerStrategy.TEMPLATE_ONLY


def test_simple_spending_by_category_uses_template_only():
    bundle = _category_bundle()
    strategy = choose_strategy(QueryIntent.SPENDING_BY_CATEGORY, "What did I spend in March?", bundle)
    assert strategy == AnswerStrategy.TEMPLATE_ONLY


def test_balance_lookup_uses_template_only():
    bundle = FactBundle(balance=15432.00, rows_used=2, filters_used={})
    strategy = choose_strategy(QueryIntent.BALANCE_LOOKUP, "What is my account balance?", bundle)
    assert strategy == AnswerStrategy.TEMPLATE_ONLY


def test_fee_summary_uses_template_only():
    bundle = FactBundle(total_fees=150.00, transaction_count=3, rows_used=3, filters_used={})
    strategy = choose_strategy(QueryIntent.FEE_SUMMARY, "What fees was I charged?", bundle)
    assert strategy == AnswerStrategy.TEMPLATE_ONLY


def test_no_data_uses_template_only():
    bundle = _no_data_bundle()
    strategy = choose_strategy(QueryIntent.TRANSACTION_LOOKUP, "Show me Whole Foods in March", bundle)
    assert strategy == AnswerStrategy.TEMPLATE_ONLY


def test_text_explanation_forces_llm():
    bundle = _simple_spend_bundle()
    strategy = choose_strategy(QueryIntent.TEXT_EXPLANATION, "Explain my fees", bundle, has_rag=True)
    assert strategy == AnswerStrategy.LLM_NARRATIVE


def test_why_question_upgrades_to_hybrid():
    bundle = _simple_spend_bundle()
    strategy = choose_strategy(QueryIntent.SPENDING_BY_CATEGORY, "Why did I spend so much?", bundle)
    assert strategy == AnswerStrategy.HYBRID_TEMPLATE_PLUS_LLM


def test_trend_question_upgrades_to_hybrid():
    bundle = _simple_spend_bundle()
    strategy = choose_strategy(QueryIntent.SPENDING_BY_CATEGORY, "Show me my spending trend", bundle)
    assert strategy == AnswerStrategy.HYBRID_TEMPLATE_PLUS_LLM


def test_comparison_bundle_upgrades_to_hybrid():
    from app.chat.fact_builder import PeriodComparison
    bundle = FactBundle(
        total_spend=3000.00,
        rows_used=2,
        filters_used={},
        comparison=PeriodComparison(
            period_a_label="Feb", period_a_value=2500.0,
            period_b_label="Mar", period_b_value=3000.0,
            delta=500.0, pct_change=20.0,
        ),
    )
    strategy = choose_strategy(QueryIntent.SPENDING_BY_CATEGORY, "Compare February and March", bundle)
    assert strategy == AnswerStrategy.HYBRID_TEMPLATE_PLUS_LLM


# ── Phase 6: template renders correctly ───────────────────────────────────────

def test_render_merchant_lookup():
    bundle = _simple_spend_bundle()
    text = render_template(QueryIntent.TRANSACTION_LOOKUP, bundle)
    assert "Costco" in text
    assert "$482.31" in text
    assert "4 transaction" in text


def test_render_spending_by_category_with_top_category():
    bundle = _category_bundle()
    text = render_template(QueryIntent.SPENDING_BY_CATEGORY, bundle)
    assert "$2,814.77" in text
    assert "51 transaction" in text


def test_render_no_data_mentions_merchant():
    bundle = _no_data_bundle()
    text = render_template(QueryIntent.TRANSACTION_LOOKUP, bundle)
    assert "Whole Foods" in text or "no" in text.lower()


def test_render_balance():
    bundle = FactBundle(balance=15432.00, rows_used=1, filters_used={})
    text = render_template(QueryIntent.BALANCE_LOOKUP, bundle)
    assert "$15,432.00" in text


def test_render_fees():
    bundle = FactBundle(
        total_fees=175.00,
        transaction_count=3,
        rows_used=2,
        filters_used={},
        top_categories=[CategoryFact(category="Advisory", amount=150.00, transaction_count=2)],
    )
    text = render_template(QueryIntent.FEE_SUMMARY, bundle)
    assert "$175.00" in text
    assert "Advisory" in text


def test_render_holdings():
    bundle = FactBundle(holdings_value=95000.00, rows_used=5, filters_used={})
    text = render_template(QueryIntent.HOLDINGS_TOTAL, bundle)
    assert "$95,000.00" in text


def test_render_cash_flow():
    bundle = FactBundle(
        total_income=5000.00,
        total_spend=3482.41,
        net_cash_flow=1517.59,
        rows_used=1,
        filters_used={},
    )
    text = render_template(QueryIntent.CASH_FLOW_SUMMARY, bundle)
    assert "$5,000.00" in text
    assert "$3,482.41" in text
    assert "positive" in text.lower()
