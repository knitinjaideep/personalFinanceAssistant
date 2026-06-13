"""
Tests for app.chat.fact_builder — verifies all Python calculations are correct.

These tests run without a database or Ollama: just pure function calls.
"""

from __future__ import annotations

import pytest
from datetime import date

from app.chat.fact_builder import (
    FactBundle,
    MerchantFact,
    CategoryFact,
    build_facts,
    _to_decimal,
    _extract_date_range,
)
from app.domain.enums import QueryIntent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sql(rows: list[dict], **kwargs) -> dict:
    """Minimal sql_result dict mirroring what sql_query.execute_for_intent returns."""
    return {
        "rows": rows,
        "searched_filters": kwargs,
        "exact_match": True,
        "suggestions": [],
    }


# ── _to_decimal ───────────────────────────────────────────────────────────────

def test_to_decimal_handles_none():
    from decimal import Decimal
    assert _to_decimal(None) == Decimal("0")

def test_to_decimal_handles_string():
    from decimal import Decimal
    assert _to_decimal("123.45") == Decimal("123.45")

def test_to_decimal_handles_float():
    from decimal import Decimal
    assert _to_decimal(99.99) == Decimal("99.99")

def test_to_decimal_handles_garbage():
    from decimal import Decimal
    assert _to_decimal("bad") == Decimal("0")


# ── _extract_date_range ───────────────────────────────────────────────────────

def test_extract_date_range_from_transaction_date():
    rows = [
        {"transaction_date": "2026-03-05"},
        {"transaction_date": "2026-03-20"},
        {"transaction_date": "2026-03-01"},
    ]
    d_from, d_to = _extract_date_range(rows)
    assert d_from == date(2026, 3, 1)
    assert d_to == date(2026, 3, 20)

def test_extract_date_range_empty():
    d_from, d_to = _extract_date_range([])
    assert d_from is None
    assert d_to is None


# ── SPENDING_BY_CATEGORY ──────────────────────────────────────────────────────

def test_spending_total_is_python_sum():
    rows = [
        {"category": "Groceries", "total_spent": "420.10", "transaction_count": 5},
        {"category": "Dining", "total_spent": "310.88", "transaction_count": 8},
        {"category": "Gas", "total_spent": "89.43", "transaction_count": 3},
    ]
    bundle = build_facts(QueryIntent.SPENDING_BY_CATEGORY, _sql(rows))
    assert bundle.total_spend == pytest.approx(420.10 + 310.88 + 89.43, rel=1e-4)

def test_spending_transaction_count_summed():
    rows = [
        {"category": "Groceries", "total_spent": "420.10", "transaction_count": 5},
        {"category": "Dining", "total_spent": "310.88", "transaction_count": 8},
    ]
    bundle = build_facts(QueryIntent.SPENDING_BY_CATEGORY, _sql(rows))
    assert bundle.transaction_count == 13

def test_spending_categories_sorted_descending():
    rows = [
        {"category": "Gas", "total_spent": "89.00", "transaction_count": 2},
        {"category": "Groceries", "total_spent": "420.00", "transaction_count": 5},
        {"category": "Dining", "total_spent": "310.00", "transaction_count": 8},
    ]
    bundle = build_facts(QueryIntent.SPENDING_BY_CATEGORY, _sql(rows))
    amounts = [c.amount for c in bundle.top_categories]
    assert amounts == sorted(amounts, reverse=True)

def test_spending_average_transaction():
    rows = [
        {"category": "Groceries", "total_spent": "200.00", "transaction_count": 4},
    ]
    bundle = build_facts(QueryIntent.SPENDING_BY_CATEGORY, _sql(rows))
    # 200 / 4 = 50.00
    assert bundle.average_transaction == pytest.approx(50.0)

def test_spending_chart_ready_data_populated():
    rows = [
        {"category": "Groceries", "total_spent": "420.10", "transaction_count": 5},
        {"category": "Dining", "total_spent": "310.88", "transaction_count": 8},
    ]
    bundle = build_facts(QueryIntent.SPENDING_BY_CATEGORY, _sql(rows))
    labels = [d["label"] for d in bundle.chart_ready_data]
    assert "Groceries" in labels
    assert "Dining" in labels


# ── TRANSACTION_LOOKUP ────────────────────────────────────────────────────────

def test_transaction_lookup_total():
    rows = [
        {"amount": "50.00", "merchant_name": "Costco", "transaction_date": "2026-03-01"},
        {"amount": "25.50", "merchant_name": "Costco", "transaction_date": "2026-03-10"},
        {"amount": "100.00", "merchant_name": "Amazon", "transaction_date": "2026-03-15"},
    ]
    bundle = build_facts(QueryIntent.TRANSACTION_LOOKUP, _sql(rows))
    assert bundle.total_spend == pytest.approx(175.50)
    assert bundle.transaction_count == 3

def test_transaction_lookup_top_merchant_is_largest():
    rows = [
        {"amount": "50.00", "merchant_name": "Costco"},
        {"amount": "25.50", "merchant_name": "Costco"},
        {"amount": "200.00", "merchant_name": "Amazon"},
    ]
    bundle = build_facts(QueryIntent.TRANSACTION_LOOKUP, _sql(rows))
    assert bundle.top_merchants[0].merchant == "Amazon"
    assert bundle.top_merchants[0].amount == pytest.approx(200.0)

def test_transaction_lookup_merchant_count():
    rows = [
        {"amount": "50.00", "merchant_name": "Costco"},
        {"amount": "25.50", "merchant_name": "Costco"},
        {"amount": "10.00", "merchant_name": "Costco"},
    ]
    bundle = build_facts(QueryIntent.TRANSACTION_LOOKUP, _sql(rows))
    costco = bundle.top_merchants[0]
    assert costco.merchant == "Costco"
    assert costco.transaction_count == 3


# ── CASH_FLOW_SUMMARY ─────────────────────────────────────────────────────────

def test_cash_flow_net_calculated():
    rows = [{"total_inflow": "5000.00", "total_outflow": "3482.41"}]
    bundle = build_facts(QueryIntent.CASH_FLOW_SUMMARY, _sql(rows))
    assert bundle.total_income == pytest.approx(5000.00)
    assert bundle.total_spend == pytest.approx(3482.41)
    assert bundle.net_cash_flow == pytest.approx(5000.00 - 3482.41)

def test_cash_flow_negative_net():
    rows = [{"total_inflow": "2000.00", "total_outflow": "3000.00"}]
    bundle = build_facts(QueryIntent.CASH_FLOW_SUMMARY, _sql(rows))
    assert bundle.net_cash_flow == pytest.approx(-1000.0)


# ── FEE_SUMMARY ───────────────────────────────────────────────────────────────

def test_fee_total():
    rows = [
        {"fee_category": "Advisory", "total_amount": "150.00", "fee_count": 2},
        {"fee_category": "Transfer", "total_amount": "25.00", "fee_count": 1},
    ]
    bundle = build_facts(QueryIntent.FEE_SUMMARY, _sql(rows))
    assert bundle.total_fees == pytest.approx(175.0)
    assert bundle.transaction_count == 3

def test_fee_categories_sorted():
    rows = [
        {"fee_category": "Advisory", "total_amount": "25.00", "fee_count": 1},
        {"fee_category": "Transfer", "total_amount": "150.00", "fee_count": 2},
    ]
    bundle = build_facts(QueryIntent.FEE_SUMMARY, _sql(rows))
    assert bundle.top_categories[0].category == "Transfer"
    assert bundle.top_categories[0].amount == pytest.approx(150.0)


# ── BALANCE_LOOKUP ────────────────────────────────────────────────────────────

def test_balance_total():
    rows = [
        {"total_value": "10000.00"},
        {"total_value": "5000.00"},
    ]
    bundle = build_facts(QueryIntent.BALANCE_LOOKUP, _sql(rows))
    assert bundle.balance == pytest.approx(15000.0)


# ── HOLDINGS_TOTAL ────────────────────────────────────────────────────────────

def test_holdings_value():
    rows = [
        {"total_value": "25000.00"},
        {"total_value": "10000.00"},
    ]
    bundle = build_facts(QueryIntent.HOLDINGS_TOTAL, _sql(rows))
    assert bundle.holdings_value == pytest.approx(35000.0)


# ── SPENDING_COMPARISON ───────────────────────────────────────────────────────

def test_comparison_delta():
    rows = [
        {"period_label": "Feb 2026", "total_spent": "3000.00"},
        {"period_label": "Mar 2026", "total_spent": "3312.45"},
    ]
    bundle = build_facts(QueryIntent.SPENDING_COMPARISON, _sql(rows))
    assert bundle.comparison is not None
    assert bundle.comparison.delta == pytest.approx(312.45, rel=1e-4)

def test_comparison_pct_change():
    rows = [
        {"period_label": "Feb", "total_spent": "3000.00"},
        {"period_label": "Mar", "total_spent": "3300.00"},
    ]
    bundle = build_facts(QueryIntent.SPENDING_COMPARISON, _sql(rows))
    assert bundle.comparison is not None
    # (300 / 3000) * 100 = 10%
    assert bundle.comparison.pct_change == pytest.approx(10.0)

def test_comparison_pct_none_when_zero_base():
    rows = [
        {"period_label": "Feb", "total_spent": "0.00"},
        {"period_label": "Mar", "total_spent": "100.00"},
    ]
    bundle = build_facts(QueryIntent.SPENDING_COMPARISON, _sql(rows))
    assert bundle.comparison is not None
    assert bundle.comparison.pct_change is None


# ── Empty result ──────────────────────────────────────────────────────────────

def test_empty_rows_returns_bundle_with_missing_note():
    bundle = build_facts(QueryIntent.SPENDING_BY_CATEGORY, _sql([]))
    assert bundle.rows_used == 0
    assert bundle.total_spend is None
    assert any("No rows" in n for n in bundle.missing_data_notes)

def test_none_sql_result():
    bundle = build_facts(QueryIntent.TRANSACTION_LOOKUP, None)
    assert bundle.rows_used == 0


# ── Caveats ───────────────────────────────────────────────────────────────────

def test_caveat_institution_filter():
    rows = [{"category": "Groceries", "total_spent": "100.00", "transaction_count": 1}]
    bundle = build_facts(
        QueryIntent.SPENDING_BY_CATEGORY,
        _sql(rows, institution="chase"),
    )
    assert any("Chase" in c for c in bundle.caveats)

def test_caveat_merchant_filter():
    rows = [{"amount": "50.00", "merchant_name": "Costco"}]
    bundle = build_facts(
        QueryIntent.TRANSACTION_LOOKUP,
        _sql(rows, merchant="costco"),
    )
    assert any("costco" in c.lower() for c in bundle.caveats)

def test_caveat_refunds_included():
    rows = [
        {"amount": "50.00", "merchant_name": "Costco", "transaction_date": "2026-03-01"},
        {"amount": "-25.00", "merchant_name": "Costco", "transaction_date": "2026-03-05"},
    ]
    bundle = build_facts(QueryIntent.TRANSACTION_LOOKUP, _sql(rows))
    assert any("Refund" in c or "refund" in c for c in bundle.caveats)


# ── Follow-up suggestions ─────────────────────────────────────────────────────

def test_followups_not_empty():
    rows = [{"category": "Groceries", "total_spent": "100.00", "transaction_count": 1}]
    bundle = build_facts(QueryIntent.SPENDING_BY_CATEGORY, _sql(rows))
    assert len(bundle.suggested_followups) > 0

def test_followups_personalized_with_institution():
    rows = [{"fee_category": "Advisory", "total_amount": "100.00", "fee_count": 1}]
    bundle = build_facts(
        QueryIntent.FEE_SUMMARY,
        _sql(rows, institution="morgan_stanley"),
    )
    assert any("Morgan Stanley" in f for f in bundle.suggested_followups)
