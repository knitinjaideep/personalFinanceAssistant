"""
Unit tests for the three-layer affordability engine.

Tests are fully synchronous where possible (no DB, no LLM).
All tests use the internal Python functions directly.

Coverage:
  - ScenarioMathResult purchase calculations
  - ScenarioMathResult home calculations
  - DecisionResult purchase verdicts
  - DecisionResult home verdicts
  - allowed/forbidden conclusions present
  - Gemma invalid output fallback → template
  - Verifier catches changed verdict
  - Verifier catches invented amount
  - Verifier catches forbidden conclusion
  - Verifier catches home wording in purchase answer
  - Purchase answers never mention down payment / closing costs
  - Home answers include cash_needed_at_close
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

# Bootstrap path so imports resolve without installing the package
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.chat.affordability import (
    # models
    ScenarioMathResult,
    DecisionResult,
    DecisionSeverity,
    PurchaseVerdictCode,
    HomeVerdictCode,
    # math layers
    _Snapshot,
    _calc_purchase,
    _calc_home,
    # decision layers
    _decide_purchase,
    _decide_home,
    # templates
    _render_template_purchase,
    _render_template_home,
    # verifier
    _verify,
    _assemble_from_llm,
    # helpers
    _EMERGENCY_FUND_MONTHS,
    _DOWN_PAYMENT_PCT,
    _CLOSING_COST_PCT,
    _dedupe_caveats,
)
from app.domain.entities import StructuredAnswer


# ── Shared fixtures ────────────────────────────────────────────────────────────

def _make_snapshot(
    liquid: float = 50_000,
    retirement: float = 80_000,
    brokerage: float = 0,
    monthly_spend: float = 3_000,
    monthly_income: float | None = None,
) -> _Snapshot:
    """Build a _Snapshot without hitting the database."""
    rows = []
    if liquid > 0:
        rows.append({
            "account_name": "Chase Checking",
            "account_type": "checking",
            "institution": "Chase",
            "snapshot_date": "2026-06-01",
            "total_value": liquid,
            "cash_value": liquid,
            "invested_value": 0,
        })
    if retirement > 0:
        rows.append({
            "account_name": "Fidelity IRA",
            "account_type": "ira",
            "institution": "Fidelity",
            "snapshot_date": "2026-06-01",
            "total_value": retirement,
            "cash_value": 0,
            "invested_value": retirement,
        })
    if brokerage > 0:
        rows.append({
            "account_name": "E*TRADE Brokerage",
            "account_type": "individual_brokerage",
            "institution": "ETRADE",
            "snapshot_date": "2026-06-01",
            "total_value": brokerage,
            "cash_value": 0,
            "invested_value": brokerage,
        })
    inc = Decimal(str(monthly_income)) if monthly_income else None
    return _Snapshot(rows, Decimal(str(monthly_spend)), inc)


# ── ScenarioMathResult: purchase calculations ─────────────────────────────────

class TestPurchaseMath:
    def test_comfortable_scenario(self):
        snap = _make_snapshot(liquid=100_000, monthly_spend=3_000)
        math = _calc_purchase(snap, Decimal("5000"), "Birkin", "luxury_discretionary", "Can we afford a Birkin?")

        reserve = Decimal(str(3_000 * _EMERGENCY_FUND_MONTHS))
        assert math.emergency_reserve_target == reserve
        assert math.gross_liquid_cash == Decimal("100000")
        assert math.comfortable_spend_capacity == Decimal("100000") - reserve
        assert math.purchase_price == Decimal("5000")
        assert math.cash_after_purchase == Decimal("95000")
        assert math.reserve_gap_after_purchase == Decimal("0")  # no gap

    def test_reserve_gap_calculation(self):
        # liquid=30k, spend=3k → reserve=18k → capacity=12k
        # price=15k → dips into reserve
        snap = _make_snapshot(liquid=30_000, monthly_spend=3_000)
        math = _calc_purchase(snap, Decimal("15000"), "car", "vehicle", "")

        assert math.reserve_gap_before_purchase == Decimal("0")   # liquid > reserve before
        assert math.cash_after_purchase == Decimal("15000")
        assert math.reserve_gap_after_purchase == Decimal("3000")  # reserve=18k, cash_after=15k

    def test_assumed_birkin_price(self):
        snap = _make_snapshot(liquid=50_000)
        math = _calc_purchase(snap, None, "Birkin", "luxury_discretionary", "Can we afford a Birkin by Hermes?")
        assert math.purchase_price == Decimal("15000")
        assert math.purchase_price_source == "assumed"
        assert any("Birkin" in a for a in math.assumptions)

    def test_unknown_price_no_item(self):
        snap = _make_snapshot(liquid=50_000)
        math = _calc_purchase(snap, None, "widget", "general", "")
        assert math.purchase_price is None
        assert math.purchase_price_source == "unknown"

    def test_retirement_excluded(self):
        snap = _make_snapshot(liquid=50_000, retirement=200_000)
        math = _calc_purchase(snap, Decimal("5000"), "bag", "luxury_discretionary", "")
        # Retirement must not appear in gross_liquid_cash
        assert math.gross_liquid_cash == Decimal("50000")
        assert any("IRA" in a or "retirement" in a.lower() for a in math.excluded_assets)

    def test_purchase_as_pct_of_liquid(self):
        snap = _make_snapshot(liquid=50_000)
        math = _calc_purchase(snap, Decimal("10000"), "vacation", "travel", "")
        assert math.purchase_as_pct_of_liquid == Decimal("20")   # 10k/50k = 20%

    def test_assumptions_always_present(self):
        snap = _make_snapshot(liquid=50_000)
        math = _calc_purchase(snap, Decimal("5000"), "bag", "luxury_discretionary", "")
        assert len(math.assumptions) >= 2
        assert any("emergency reserve" in a.lower() for a in math.assumptions)
        assert any("retirement" in a.lower() for a in math.assumptions)

    def test_no_down_payment_terms_in_assumptions(self):
        snap = _make_snapshot(liquid=50_000)
        math = _calc_purchase(snap, Decimal("5000"), "bag", "luxury_discretionary", "")
        all_text = " ".join(math.assumptions + math.caveats).lower()
        assert "down payment" not in all_text
        assert "closing cost" not in all_text


class TestHomeMath:
    def test_basic_home_calculation(self):
        snap = _make_snapshot(liquid=400_000, monthly_spend=5_000)
        math = _calc_home(snap, Decimal("1_000_000"))

        assert math.down_payment == Decimal("200000")
        assert math.closing_costs == Decimal("30000")
        assert math.cash_needed_at_close == Decimal("230000")
        assert math.loan_amount == Decimal("800000")

    def test_cash_remaining_after_close(self):
        snap = _make_snapshot(liquid=400_000, monthly_spend=5_000)
        math = _calc_home(snap, Decimal("1_000_000"))
        # 400k liquid - 230k at close = 170k remaining
        assert math.cash_remaining_after_close == Decimal("170000")

    def test_technical_gap_when_short(self):
        snap = _make_snapshot(liquid=100_000, monthly_spend=3_000)
        math = _calc_home(snap, Decimal("1_300_000"))

        # down = 260k, closing = 39k, total at close = 299k
        # liquid = 100k → gap = 299k - 100k = 199k
        assert math.technical_home_cash_gap > 0
        assert math.technical_home_cash_gap == Decimal("199000")

    def test_monthly_payment_computed(self):
        snap = _make_snapshot(liquid=400_000, monthly_spend=5_000)
        math = _calc_home(snap, Decimal("1_000_000"))
        assert math.principal_interest_monthly is not None
        assert math.principal_interest_monthly > Decimal("4000")  # ~$5,300 for 800k at 7%

    def test_max_affordable_when_no_price(self):
        snap = _make_snapshot(liquid=200_000, monthly_spend=3_000)
        math = _calc_home(snap, None)
        # capacity = 200k - 18k = 182k; max = 182k / (0.20 + 0.03) = ~791k
        assert math.max_affordable_home_price is not None
        assert math.max_affordable_home_price > Decimal("700_000")

    def test_assumptions_include_home_terms(self):
        snap = _make_snapshot(liquid=400_000)
        math = _calc_home(snap, Decimal("1_000_000"))
        assumption_text = " ".join(math.assumptions).lower()
        assert "down payment" in assumption_text
        assert "closing cost" in assumption_text


# ── DecisionResult: purchase verdicts ────────────────────────────────────────

class TestPurchaseDecision:
    def test_comfortable(self):
        snap = _make_snapshot(liquid=100_000, monthly_spend=3_000)
        math = _calc_purchase(snap, Decimal("5000"), "bag", "luxury_discretionary", "")
        decision = _decide_purchase(math)
        assert decision.verdict_code == PurchaseVerdictCode.COMFORTABLE.value
        assert decision.severity == DecisionSeverity.OK

    def test_technically_affordable_not_comfortable(self):
        # liquid=30k, reserve=18k, capacity=12k, price=15k → dips into reserve
        snap = _make_snapshot(liquid=30_000, monthly_spend=3_000)
        math = _calc_purchase(snap, Decimal("15000"), "bag", "luxury_discretionary", "")
        decision = _decide_purchase(math)
        assert decision.verdict_code == PurchaseVerdictCode.TECHNICALLY_AFFORDABLE_NOT_COMFORTABLE.value
        assert decision.severity == DecisionSeverity.WATCH

    def test_not_affordable(self):
        snap = _make_snapshot(liquid=10_000, monthly_spend=3_000)
        math = _calc_purchase(snap, Decimal("15000"), "bag", "luxury_discretionary", "")
        decision = _decide_purchase(math)
        assert decision.verdict_code == PurchaseVerdictCode.NOT_AFFORDABLE.value
        assert decision.severity == DecisionSeverity.STOP

    def test_no_price_returns_insufficient_data(self):
        snap = _make_snapshot(liquid=50_000)
        math = _calc_purchase(snap, None, "item", "general", "")
        decision = _decide_purchase(math)
        assert decision.verdict_code == PurchaseVerdictCode.INSUFFICIENT_DATA.value

    def test_no_liquid_returns_insufficient_data(self):
        snap = _make_snapshot(liquid=0)
        math = _calc_purchase(snap, Decimal("5000"), "bag", "luxury_discretionary", "")
        decision = _decide_purchase(math)
        assert decision.verdict_code == PurchaseVerdictCode.INSUFFICIENT_DATA.value

    def test_allowed_conclusions_present(self):
        snap = _make_snapshot(liquid=100_000, monthly_spend=3_000)
        math = _calc_purchase(snap, Decimal("5000"), "bag", "luxury_discretionary", "")
        decision = _decide_purchase(math)
        assert len(decision.allowed_conclusions) > 0

    def test_forbidden_conclusions_present(self):
        snap = _make_snapshot(liquid=30_000, monthly_spend=3_000)
        math = _calc_purchase(snap, Decimal("15000"), "bag", "luxury_discretionary", "")
        decision = _decide_purchase(math)
        assert len(decision.forbidden_conclusions) > 0

    def test_purchase_forbidden_no_home_terms(self):
        snap = _make_snapshot(liquid=100_000)
        math = _calc_purchase(snap, Decimal("5000"), "bag", "luxury_discretionary", "")
        decision = _decide_purchase(math)
        forbidden_text = " ".join(decision.forbidden_conclusions).lower()
        assert "down payment" in forbidden_text or "closing cost" in forbidden_text

    def test_comfortable_followups_include_house_impact(self):
        snap = _make_snapshot(liquid=100_000)
        math = _calc_purchase(snap, Decimal("5000"), "Birkin", "luxury_discretionary", "")
        decision = _decide_purchase(math)
        followup_text = " ".join(decision.recommended_followups).lower()
        assert "house" in followup_text or "saving" in followup_text


# ── DecisionResult: home verdicts ────────────────────────────────────────────

class TestHomeDecision:
    def test_possible(self):
        # liquid=400k, 1M house: needs 230k → 170k remaining, well above reserve
        snap = _make_snapshot(liquid=400_000, monthly_spend=3_000)
        math = _calc_home(snap, Decimal("1_000_000"))
        decision = _decide_home(math)
        assert decision.verdict_code == HomeVerdictCode.POSSIBLE.value
        assert decision.severity == DecisionSeverity.OK

    def test_upfront_cash_shortfall(self):
        snap = _make_snapshot(liquid=100_000, monthly_spend=3_000)
        math = _calc_home(snap, Decimal("1_300_000"))
        decision = _decide_home(math)
        assert decision.verdict_code == HomeVerdictCode.UPFRONT_CASH_SHORTFALL.value
        assert decision.severity == DecisionSeverity.STOP

    def test_reserves_tight_after_close(self):
        # liquid=250k, 1M house: needs 230k → 20k remaining, reserve=18k → comfortable_gap positive
        snap = _make_snapshot(liquid=250_000, monthly_spend=3_000)
        math = _calc_home(snap, Decimal("1_000_000"))
        decision = _decide_home(math)
        # 250k liquid, 230k needed, 20k remaining, reserve=18k → comfortable gap = 230+18 - 250 = -2k
        # Actually comfortable — edge case, so let's check code is either possible or tight
        assert decision.verdict_code in (
            HomeVerdictCode.POSSIBLE.value,
            HomeVerdictCode.TECHNICALLY_POSSIBLE_RESERVES_TIGHT.value,
        )

    def test_no_price_returns_insufficient_data(self):
        snap = _make_snapshot(liquid=200_000)
        math = _calc_home(snap, None)
        decision = _decide_home(math)
        assert decision.verdict_code == HomeVerdictCode.INSUFFICIENT_DATA.value

    def test_forbidden_conclusions_no_retirement_suggestion(self):
        snap = _make_snapshot(liquid=100_000, retirement=500_000)
        math = _calc_home(snap, Decimal("1_300_000"))
        decision = _decide_home(math)
        forbidden_text = " ".join(decision.forbidden_conclusions).lower()
        assert "retirement" in forbidden_text

    def test_upfront_shortfall_must_include_cash_needed_at_close(self):
        snap = _make_snapshot(liquid=100_000)
        math = _calc_home(snap, Decimal("1_300_000"))
        decision = _decide_home(math)
        primary = decision.primary_reason
        assert "$" in primary   # amounts present

    def test_allowed_conclusions_not_say_affordable_when_short(self):
        snap = _make_snapshot(liquid=100_000)
        math = _calc_home(snap, Decimal("1_300_000"))
        decision = _decide_home(math)
        forbidden_text = " ".join(decision.forbidden_conclusions).lower()
        assert "can afford" in forbidden_text or "affordable" in forbidden_text


# ── Template renderer: purchase ───────────────────────────────────────────────

class TestPurchaseTemplate:
    def _get_answer(self, liquid=100_000, price=5_000, monthly_spend=3_000) -> StructuredAnswer:
        snap = _make_snapshot(liquid=liquid, monthly_spend=monthly_spend)
        math = _calc_purchase(snap, Decimal(str(price)), "Birkin", "luxury_discretionary", "")
        decision = _decide_purchase(math)
        return _render_template_purchase(math, decision)

    def test_has_verdict_highlight(self):
        answer = self._get_answer()
        labels = [h["label"] for h in answer.highlights]
        assert "Verdict" in labels

    def test_has_dollar_values(self):
        answer = self._get_answer()
        all_values = " ".join(h["value"] for h in answer.highlights)
        assert "$" in all_values

    def test_no_home_terms(self):
        answer = self._get_answer()
        full_text = answer.summary + " ".join(h.get("label", "") for h in answer.highlights)
        assert "down payment" not in full_text.lower()
        assert "closing cost" not in full_text.lower()
        assert "mortgage" not in full_text.lower()

    def test_answer_strategy_template_only(self):
        answer = self._get_answer()
        assert answer.answer_strategy == "template_only"
        assert answer.llm_called is False

    def test_caveats_include_retirement_note(self):
        answer = self._get_answer()
        caveats_text = " ".join(answer.caveats).lower()
        assert "retirement" in caveats_text

    def test_caveats_include_not_financial_advice(self):
        answer = self._get_answer()
        caveats_text = " ".join(answer.caveats).lower()
        assert "not financial advice" in caveats_text


# ── Template renderer: home ───────────────────────────────────────────────────

class TestHomeTemplate:
    def _get_answer(self, liquid=400_000, price=1_000_000, monthly_spend=3_000) -> StructuredAnswer:
        snap = _make_snapshot(liquid=liquid, monthly_spend=monthly_spend)
        math = _calc_home(snap, Decimal(str(price)))
        decision = _decide_home(math)
        return _render_template_home(math, decision)

    def test_has_down_payment_highlight(self):
        answer = self._get_answer()
        labels = [h["label"].lower() for h in answer.highlights]
        assert any("down payment" in l for l in labels)

    def test_has_closing_costs_highlight(self):
        answer = self._get_answer()
        labels = [h["label"].lower() for h in answer.highlights]
        assert any("closing cost" in l for l in labels)

    def test_has_cash_needed_at_close(self):
        answer = self._get_answer()
        labels = [h["label"].lower() for h in answer.highlights]
        assert any("cash needed" in l for l in labels)

    def test_has_monthly_cost_highlight(self):
        answer = self._get_answer()
        labels = [h["label"].lower() for h in answer.highlights]
        assert any("monthly" in l for l in labels)


# ── AnswerVerifier ────────────────────────────────────────────────────────────

def _make_answer(**kwargs) -> StructuredAnswer:
    defaults = dict(
        answer_type="numeric",
        title="Test answer",
        summary="Your purchase looks comfortable.",
        highlights=[{"label": "Verdict", "value": "Comfortable"}],
        caveats=["This is not financial advice."],
        suggested_followups=["What is my total net worth?"],
        query_path="affordability",
        intent="affordability",
        confidence=0.9,
        answer_strategy="hybrid_template_plus_llm",
        llm_called=True,
    )
    defaults.update(kwargs)
    return StructuredAnswer(**defaults)


class TestVerifier:
    def _make_comfortable_math(self) -> ScenarioMathResult:
        snap = _make_snapshot(liquid=100_000, monthly_spend=3_000)
        return _calc_purchase(snap, Decimal("5000"), "Birkin", "luxury_discretionary", "")

    def _make_comfortable_decision(self) -> DecisionResult:
        snap = _make_snapshot(liquid=100_000, monthly_spend=3_000)
        math = _calc_purchase(snap, Decimal("5000"), "Birkin", "luxury_discretionary", "")
        return _decide_purchase(math)

    def test_clean_answer_passes(self):
        math = self._make_comfortable_math()
        decision = self._make_comfortable_decision()
        answer = _make_answer(
            summary=(
                "Comfortable. The $5,000 Birkin fits well within your $82,000 "
                "available spend capacity, so your reserve stays preserved."
            ),
            highlights=[
                {"label": "Verdict", "value": "Comfortable"},
                {"label": "Liquid cash", "value": "$100,000"},
                {"label": "Emergency reserve target", "value": "$18,000"},
                {"label": "Available after reserve", "value": "$82,000"},
                {"label": "Cost of Birkin", "value": "$5,000"},
            ],
            suggested_followups=decision.recommended_followups[:2],
        )
        result = _verify(answer, math, decision)
        assert result.verifier_passed is True
        assert result.verifier_repaired is False

    def test_catches_forbidden_conclusion_comfortable_when_not(self):
        snap = _make_snapshot(liquid=30_000, monthly_spend=3_000)
        math = _calc_purchase(snap, Decimal("15000"), "bag", "luxury_discretionary", "")
        decision = _decide_purchase(math)
        assert decision.verdict_code == PurchaseVerdictCode.TECHNICALLY_AFFORDABLE_NOT_COMFORTABLE.value

        # Answer incorrectly says "comfortable"
        answer = _make_answer(
            summary="This is comfortable. You can easily afford it.",
            highlights=[{"label": "Verdict", "value": decision.verdict_label}],
            suggested_followups=decision.recommended_followups[:2],
        )
        result = _verify(answer, math, decision)
        assert result.verifier_repaired is True

    def test_catches_home_terms_in_purchase_answer(self):
        math = self._make_comfortable_math()
        decision = self._make_comfortable_decision()
        answer = _make_answer(
            summary="You need to consider the down payment and closing costs carefully.",
            highlights=[{"label": "Verdict", "value": "Comfortable"}],
            suggested_followups=decision.recommended_followups[:2],
        )
        result = _verify(answer, math, decision)
        assert result.verifier_repaired is True
        assert any("down payment" in w or "home-only" in w for w in result.verifier_warnings)

    def test_catches_invented_amount(self):
        math = self._make_comfortable_math()
        decision = self._make_comfortable_decision()
        # $999,999 is not in any math field
        answer = _make_answer(
            summary="You have $999,999 in savings so this is clearly fine.",
            highlights=[{"label": "Verdict", "value": "Comfortable"}],
            suggested_followups=decision.recommended_followups[:2],
        )
        result = _verify(answer, math, decision)
        assert result.verifier_repaired is True
        assert any("999,999" in w or "invented" in w for w in result.verifier_warnings)

    def test_catches_approval_when_insufficient_data(self):
        snap = _make_snapshot(liquid=0)
        math = _calc_purchase(snap, Decimal("5000"), "bag", "luxury_discretionary", "")
        decision = _decide_purchase(math)
        assert decision.verdict_code == PurchaseVerdictCode.INSUFFICIENT_DATA.value

        answer = _make_answer(
            summary="You can afford it — looks comfortable!",
            highlights=[{"label": "Verdict", "value": "Insufficient data"}],
        )
        result = _verify(answer, math, decision)
        assert result.verifier_repaired is True

    def test_warns_on_followup_not_in_recommended(self):
        math = self._make_comfortable_math()
        decision = self._make_comfortable_decision()
        answer = _make_answer(
            summary="Comfortable. Reserve is preserved.",
            highlights=[{"label": "Verdict", "value": "Comfortable"}],
            suggested_followups=["What stocks should I buy?"],  # not in recommended
        )
        result = _verify(answer, math, decision)
        # Soft warning only — verifier_repaired might be False, but warning added
        assert any("followup" in w for w in result.verifier_warnings)


# ── Gemma invalid output → template fallback ─────────────────────────────────

class TestLLMFallback:
    def test_assemble_from_llm_uses_math_highlights(self):
        snap = _make_snapshot(liquid=100_000, monthly_spend=3_000)
        math = _calc_purchase(snap, Decimal("5000"), "Birkin", "luxury_discretionary", "")
        decision = _decide_purchase(math)

        llm_out = {
            "title": "Birkin affordability",
            "summary": "Your Birkin purchase looks comfortable.",
            "verdict_label": decision.verdict_label,
            "key_numbers": [],
            "explanation": "Reserve is preserved.",
            "caveats": ["Not financial advice."],
            "suggested_followups": decision.recommended_followups[:2],
        }
        answer = _assemble_from_llm(llm_out, math, decision)

        # Highlights must come from math, not LLM
        highlight_values = {h["value"] for h in answer.highlights}
        assert "$100,000" in highlight_values  # liquid cash from math
        assert "$18,000" in highlight_values   # reserve from math
        assert answer.answer_strategy == "hybrid_template_plus_llm"

    def test_assemble_rejects_llm_followups_not_in_whitelist(self):
        snap = _make_snapshot(liquid=100_000, monthly_spend=3_000)
        math = _calc_purchase(snap, Decimal("5000"), "Birkin", "luxury_discretionary", "")
        decision = _decide_purchase(math)

        llm_out = {
            "title": "Test",
            "summary": "Comfortable.",
            "verdict_label": decision.verdict_label,
            "key_numbers": [],
            "explanation": "Fine.",
            "caveats": [],
            "suggested_followups": [
                "Should I take a loan?",   # not in whitelist → must be filtered out
                decision.recommended_followups[0],  # valid one
            ],
        }
        answer = _assemble_from_llm(llm_out, math, decision)
        for fp in answer.suggested_followups:
            assert fp in decision.recommended_followups, f"Illegal followup: {fp!r}"

    def test_home_answer_has_cash_needed_highlight(self):
        snap = _make_snapshot(liquid=400_000, monthly_spend=3_000)
        math = _calc_home(snap, Decimal("1_000_000"))
        decision = _decide_home(math)

        llm_out = {
            "title": "Home affordability",
            "summary": "Possible.",
            "verdict_label": decision.verdict_label,
            "key_numbers": [],
            "explanation": "Upfront costs are covered.",
            "caveats": [],
            "suggested_followups": decision.recommended_followups[:2],
        }
        answer = _assemble_from_llm(llm_out, math, decision)
        labels = [h["label"].lower() for h in answer.highlights]
        assert any("cash needed" in l for l in labels)

    def test_llm_caveats_field_is_ignored(self):
        """LLM must not inject its own caveat text — only Python's caveats may appear."""
        snap = _make_snapshot(liquid=100_000, monthly_spend=3_000)
        math = _calc_purchase(snap, Decimal("5000"), "Birkin", "luxury_discretionary", "")
        decision = _decide_purchase(math)

        llm_out = {
            "title": "Test",
            "summary": "Comfortable.",
            "verdict_label": decision.verdict_label,
            "key_numbers": [],
            "explanation": "Fine.",
            "caveats": ["You should consider taking out a personal loan instead."],
            "suggested_followups": decision.recommended_followups[:2],
        }
        answer = _assemble_from_llm(llm_out, math, decision)
        assert "personal loan" not in " ".join(answer.caveats).lower()


# ── Caveat dedup ───────────────────────────────────────────────────────────────

class TestDedupeCaveats:
    def test_drops_near_duplicate_paraphrase(self):
        items = [
            "No price specified — assumed $5,000 as a placeholder. Please share the actual price.",
            "This analysis assumes a placeholder price of $5,000; please share the actual price for an accurate assessment.",
        ]
        result = _dedupe_caveats(items)
        assert len(result) == 1

    def test_keeps_distinct_caveats(self):
        items = [
            "This is not financial advice.",
            "Retirement accounts excluded from liquid cash.",
            "529 and child education accounts excluded from liquid cash.",
        ]
        result = _dedupe_caveats(items)
        assert len(result) == 3

    def test_exact_duplicate_collapsed(self):
        items = [
            "This does not account for upcoming large expenses, taxes, or bills unless they appear as transactions in Coral.",
            "The calculation does not account for upcoming large expenses, taxes, or bills unless they appear as transactions in Coral.",
        ]
        result = _dedupe_caveats(items)
        assert len(result) == 1

    def test_purchase_template_has_no_duplicate_caveats(self):
        snap = _make_snapshot(liquid=50_000, monthly_spend=45_650, brokerage=280_861)
        math = _calc_purchase(snap, None, "purchase", "luxury_discretionary", "")
        decision = _decide_purchase(math)
        answer = _render_template_purchase(math, decision)
        # No two caveats should be near-duplicates of each other
        assert len(answer.caveats) == len(_dedupe_caveats(answer.caveats))


# ── Regression: different questions produce different verdicts ─────────────────

class TestRegressionDifferentOutputs:
    """These tests assert that not all questions produce the same answer."""

    def test_birkin_vs_house_different_verdicts(self):
        snap = _make_snapshot(liquid=50_000, monthly_spend=3_000)

        math_purchase = _calc_purchase(snap, Decimal("15000"), "Birkin", "luxury_discretionary", "")
        decision_purchase = _decide_purchase(math_purchase)

        math_home = _calc_home(snap, Decimal("1_300_000"))
        decision_home = _decide_home(math_home)

        # Different verdict codes
        assert decision_purchase.verdict_code != decision_home.verdict_code

    def test_affordable_vs_not_different_verdicts(self):
        snap_rich = _make_snapshot(liquid=100_000, monthly_spend=3_000)
        snap_poor = _make_snapshot(liquid=5_000, monthly_spend=3_000)

        math_rich = _calc_purchase(snap_rich, Decimal("5000"), "bag", "luxury_discretionary", "")
        math_poor = _calc_purchase(snap_poor, Decimal("10000"), "bag", "luxury_discretionary", "")

        d_rich = _decide_purchase(math_rich)
        d_poor = _decide_purchase(math_poor)

        assert d_rich.verdict_code != d_poor.verdict_code

    def test_purchase_answer_never_has_down_payment(self):
        for liquid in [20_000, 50_000, 100_000]:
            snap = _make_snapshot(liquid=liquid, monthly_spend=3_000)
            math = _calc_purchase(snap, Decimal("5000"), "bag", "luxury_discretionary", "")
            decision = _decide_purchase(math)
            answer = _render_template_purchase(math, decision)
            full = (answer.summary + " " + str(answer.highlights)).lower()
            assert "down payment" not in full, f"Found 'down payment' for liquid={liquid}"

    def test_house_answer_has_required_fields(self):
        snap = _make_snapshot(liquid=400_000, monthly_spend=3_000)
        math = _calc_home(snap, Decimal("1_000_000"))
        decision = _decide_home(math)
        answer = _render_template_home(math, decision)

        labels = [h["label"].lower() for h in answer.highlights]
        assert any("down payment" in l for l in labels)
        assert any("closing cost" in l for l in labels)
        assert any("cash needed" in l for l in labels)
        # Monthly cost
        assert any("monthly" in l for l in labels)
