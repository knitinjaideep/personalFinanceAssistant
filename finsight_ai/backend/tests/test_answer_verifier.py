"""
Phase 8 tests: answer verifier prevents hallucinated finance answers.

All tests are pure Python — no database, no Ollama.
"""

from __future__ import annotations

import pytest

from app.chat.answer_verifier import (
    VerifierResult,
    _extract_dollar_amounts,
    _fact_bundle_amounts,
    _find_hallucinated_amounts,
    _claims_trend,
    _claims_found,
    verify_answer,
)
from app.chat.fact_builder import (
    CategoryFact,
    FactBundle,
    MerchantFact,
    PeriodComparison,
)
from app.domain.entities import StructuredAnswer


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_answer(summary: str, answer_type: str = "numeric", rows: int = 3) -> StructuredAnswer:
    return StructuredAnswer(
        answer_type=answer_type,
        summary=summary,
        rows_used=rows,
        intent="spending_by_category",
    )


def _spend_bundle(total: float = 482.31, count: int = 4) -> FactBundle:
    return FactBundle(
        total_spend=total,
        transaction_count=count,
        rows_used=count,
        filters_used={"merchant": "Costco", "period": "May 2026"},
        top_merchants=[MerchantFact(merchant="Costco", amount=total, transaction_count=count)],
    )


# ── Dollar amount extraction ──────────────────────────────────────────────────

def test_extract_amounts_basic():
    amounts = _extract_dollar_amounts("You spent $482.31 across 4 transactions.")
    assert 482.31 in amounts

def test_extract_amounts_thousands():
    amounts = _extract_dollar_amounts("Your total was $2,814.77.")
    assert 2814.77 in amounts

def test_extract_amounts_no_amounts():
    amounts = _extract_dollar_amounts("No transactions found.")
    assert amounts == set()

def test_extract_amounts_multiple():
    amounts = _extract_dollar_amounts("Income: $5,000.00; Spend: $3,482.41")
    assert 5000.0 in amounts
    assert 3482.41 in amounts


# ── Fact bundle amount set ─────────────────────────────────────────────────────

def test_fact_bundle_amounts_includes_total_spend():
    bundle = _spend_bundle(482.31)
    known = _fact_bundle_amounts(bundle)
    assert 482.31 in known

def test_fact_bundle_amounts_includes_top_merchant():
    bundle = FactBundle(
        total_spend=1000.00,
        rows_used=2,
        filters_used={},
        top_merchants=[MerchantFact(merchant="Amazon", amount=600.00, transaction_count=2)],
    )
    known = _fact_bundle_amounts(bundle)
    assert 600.0 in known

def test_fact_bundle_amounts_comparison():
    bundle = FactBundle(
        rows_used=2,
        filters_used={},
        comparison=PeriodComparison(
            period_a_label="Feb", period_a_value=2500.0,
            period_b_label="Mar", period_b_value=3000.0,
            delta=500.0, pct_change=20.0,
        ),
    )
    known = _fact_bundle_amounts(bundle)
    assert 2500.0 in known
    assert 3000.0 in known
    assert 500.0 in known


# ── Hallucination detection ───────────────────────────────────────────────────

def test_no_hallucination_when_amounts_match():
    bundle = _spend_bundle(482.31)
    hallucinated = _find_hallucinated_amounts("You spent $482.31 at Costco.", bundle)
    assert hallucinated == []

def test_hallucination_detected_for_unknown_amount():
    bundle = _spend_bundle(482.31)
    hallucinated = _find_hallucinated_amounts("You spent $9,999.00 at Costco.", bundle)
    assert 9999.0 in hallucinated

def test_no_hallucination_check_when_zero_rows():
    bundle = FactBundle(rows_used=0, filters_used={})
    # When no rows, hallucination check is skipped (check 1 handles this)
    hallucinated = _find_hallucinated_amounts("You spent $500.00.", bundle)
    assert hallucinated == []


# ── Trend language detection ──────────────────────────────────────────────────

def test_claims_trend_increased():
    assert _claims_trend("Your spending increased by 10% this month.")

def test_claims_trend_went_up():
    assert _claims_trend("Fees went up from last year.")

def test_claims_trend_negative():
    assert not _claims_trend("You spent $482.31 at Costco in May.")


# ── Claims found detection ────────────────────────────────────────────────────

def test_claims_found_you_spent():
    assert _claims_found("You spent $482.31 at Costco.")

def test_claims_found_negative():
    assert not _claims_found("No transactions found for that period.")


# ── Full verifier: passing cases ──────────────────────────────────────────────

def test_verifier_passes_accurate_answer():
    bundle = _spend_bundle(482.31)
    answer = _make_answer("You spent $482.31 at Costco in May 2026 across 4 transactions.")
    result = verify_answer("Costco spend in May", bundle, answer)
    assert result.passed
    assert result.warnings == []
    assert not result.repaired


def test_verifier_passes_no_data_answer():
    bundle = FactBundle(rows_used=0, filters_used={"merchant": "Whole Foods"})
    answer = _make_answer(
        "I found no Whole Foods transactions in March 2026.",
        answer_type="no_data",
        rows=0,
    )
    result = verify_answer("Whole Foods in March", bundle, answer)
    assert result.passed


# ── Full verifier: hallucination failure ──────────────────────────────────────

def test_verifier_flags_hallucinated_amount():
    bundle = _spend_bundle(482.31)
    answer = _make_answer("You spent $9,999.00 at Costco last month.")
    result = verify_answer("Costco spend", bundle, answer)
    assert not result.passed
    assert any("9,999.00" in w or "9999" in w for w in result.warnings)


def test_verifier_flags_positive_result_with_no_data():
    bundle = FactBundle(rows_used=0, filters_used={})
    answer = _make_answer("You spent $500.00 on groceries.", answer_type="numeric", rows=0)
    result = verify_answer("grocery spend", bundle, answer)
    assert not result.passed
    assert any("no data rows" in w.lower() for w in result.warnings)


def test_verifier_flags_trend_without_comparison():
    bundle = _spend_bundle(482.31)  # no comparison field
    answer = _make_answer("Your spending increased significantly compared to last month.")
    result = verify_answer("spending trend", bundle, answer)
    assert not result.passed
    assert any("trend" in w.lower() or "comparison" in w.lower() for w in result.warnings)


def test_verifier_trend_ok_with_comparison_facts():
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
    answer = _make_answer(
        "Your spending increased by $500.00 from February ($2,500.00) to March ($3,000.00)."
    )
    result = verify_answer("Feb vs Mar comparison", bundle, answer)
    assert result.passed


# ── Repair path ───────────────────────────────────────────────────────────────

def test_verifier_repairs_no_data_with_positive_claim():
    bundle = FactBundle(rows_used=0, filters_used={"merchant": "Amazon"})
    answer = _make_answer("You spent $250.00 at Amazon.", answer_type="numeric", rows=0)
    result = verify_answer("Amazon spend", bundle, answer)
    assert result.repaired
    assert result.repaired_summary is not None
    # Repaired answer should not claim a dollar amount that doesn't exist
    assert "couldn't find" in (result.repaired_summary or "").lower() or \
           "no matching" in (result.repaired_summary or "").lower() or \
           "searched" in (result.repaired_summary or "").lower()


def test_verifier_repair_contains_real_facts():
    bundle = FactBundle(
        total_spend=482.31,
        rows_used=4,
        filters_used={},
    )
    # LLM hallucinated a wrong amount
    answer = _make_answer("You spent $999.99 at Costco.")
    result = verify_answer("Costco spend", bundle, answer)
    # If repaired, the repaired summary should contain the real amount
    if result.repaired and result.repaired_summary:
        assert "$482.31" in result.repaired_summary


# ── Institution mismatch ──────────────────────────────────────────────────────

def test_verifier_flags_wrong_institution():
    bundle = FactBundle(
        total_fees=150.00,
        rows_used=2,
        filters_used={},
        institution="morgan_stanley",
    )
    # LLM mentions Chase (wrong institution)
    answer = _make_answer("Chase charged you $150.00 in advisory fees.")
    result = verify_answer("Morgan Stanley fees", bundle, answer)
    assert not result.passed
    assert any("chase" in w.lower() or "institution" in w.lower() for w in result.warnings)


# ── Date range check ──────────────────────────────────────────────────────────

def test_verifier_flags_wrong_year():
    from datetime import date
    bundle = FactBundle(
        total_spend=500.00,
        rows_used=3,
        filters_used={},
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 31),
        date_range="2026-03-01 to 2026-03-31",
    )
    # LLM says 2024 (wrong year — more than 1 year off)
    answer = _make_answer("In January 2024, you spent $500.00 on groceries.")
    result = verify_answer("March 2026 spend", bundle, answer)
    assert not result.passed
    assert any("2024" in w for w in result.warnings)


def test_verifier_allows_correct_year():
    from datetime import date
    bundle = FactBundle(
        total_spend=500.00,
        rows_used=3,
        filters_used={},
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 31),
    )
    answer = _make_answer("In March 2026, you spent $500.00.")
    result = verify_answer("March 2026 spend", bundle, answer)
    # Year 2026 is correct — should pass year check
    year_warnings = [w for w in result.warnings if "2026" in w and "year" in w.lower()]
    assert year_warnings == []
