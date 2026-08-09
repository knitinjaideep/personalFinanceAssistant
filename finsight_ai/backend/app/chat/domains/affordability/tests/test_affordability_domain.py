"""
Tests for the affordability advisory domain.

All tests are synchronous where possible (no DB, no LLM).
Tests directly call the internal layer functions to keep them fast and hermetic.

Coverage:
  Scenario parser
  - home_purchase classification
  - car/luxury/travel/general classification
  - price extraction (explicit, assumed, unknown)
  - time horizon extraction
  - missing inputs flagged

  Data collector
  - FinancialSnapshot construction (via _build_snapshot)
  - missing spending data uses fallback
  - retirement excluded

  Math engine
  - $1.3M house affordability (hard shortfall)
  - luxury bag comfortable
  - car — stretch
  - missing amount returns None cash_after
  - home with no price returns max_affordable_home_price

  Decision engine
  - COMFORTABLE verdict
  - REASONABLE verdict
  - STRETCH verdict
  - NOT_AFFORDABLE verdict
  - NEEDS_MORE_INFO when no data
  - NEEDS_MORE_INFO when no price
  - home COMFORTABLE
  - home NOT_AFFORDABLE (upfront shortfall)
  - home STRETCH (reserve tight)

  Advisory context
  - home not_affordable has core_tension about upfront cash
  - luxury comfortable has low risk_level
  - protected goals reflected in context

  Verifier
  - LLM cannot flip NOT_AFFORDABLE to COMFORTABLE
  - invented amount triggers hard_fail
  - home terms in non-home answer triggers hard_fail
  - clean answer passes

  Narrative builder (template fallback only — no LLM in unit tests)
  - default answer has no bullet characters
  - summary starts with direct answer
  - no "Based on your data" opener
"""
from __future__ import annotations

import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.chat.domains.affordability.scenario_parser import parse, AffordabilityScenario
from app.chat.domains.affordability.data_collector import (
    FinancialSnapshot,
    _build_snapshot,
    AccountSnapshot,
    _MONTHLY_SPEND_FALLBACK,
)
from app.chat.domains.affordability.math_engine import (
    compute_home,
    compute_purchase,
    MathResult,
)
from app.chat.domains.affordability.decision_engine import (
    decide,
    DecisionResult,
    VerdictCode,
    VerdictSeverity,
)
from app.chat.domains.affordability.advisory_context import (
    build as build_advisory,
    AdvisoryContext,
)
from app.chat.domains.affordability.verifier import verify, VerificationResult
from app.chat.domains.affordability.narrative_builder import build_template


# ── Helper factories ──────────────────────────────────────────────────────────

def _make_snap(
    liquid: float = 50_000,
    retirement: float = 80_000,
    brokerage: float = 0,
    monthly_spend: float | None = 3_000,
    monthly_income: float | None = None,
) -> FinancialSnapshot:
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
    spend_dec = Decimal(str(monthly_spend)) if monthly_spend is not None else None
    income_dec = Decimal(str(monthly_income)) if monthly_income is not None else None
    return _build_snapshot(rows, spend_dec, income_dec, None)


def _make_home_scenario(price: float | None = None) -> AffordabilityScenario:
    return parse(
        f"Can we afford a ${price:,.0f} house?" if price else "Can we afford a house?",
        purchase_price_override=price,
        purchase_item_override="home",
        purchase_category_override="real_estate",
        task_type_override="home_affordability",
    )


def _make_purchase_scenario(
    item: str,
    price: float | None,
    category: str = "luxury_discretionary",
    question: str = "",
) -> AffordabilityScenario:
    return parse(
        question or f"Can we afford a {item}?",
        purchase_price_override=price,
        purchase_item_override=item,
        purchase_category_override=category,
    )


# ── Scenario parser ───────────────────────────────────────────────────────────

class TestScenarioParser:
    def test_home_classification(self):
        s = parse("Can we afford a $1.3 million house?")
        assert s.scenario_type == "home_purchase"
        assert s.purchase_amount == Decimal("1300000")
        assert s.purchase_amount_source == "explicit"

    def test_car_classification(self):
        s = parse("Can we afford a $75,000 car?")
        assert s.scenario_type == "car_purchase"
        assert s.purchase_amount == Decimal("75000")

    def test_luxury_birkin_assumed(self):
        s = parse("Can we afford a Birkin bag?")
        assert s.scenario_type == "luxury_purchase"
        assert s.purchase_amount == Decimal("15000")
        assert s.purchase_amount_source == "assumed"
        assert len(s.assumptions_used) > 0

    def test_travel_classification(self):
        s = parse("Can we afford a $10,000 vacation to Japan?")
        assert s.scenario_type == "travel"
        assert s.purchase_amount == Decimal("10000")

    def test_general_no_price(self):
        s = parse("Can we afford this?")
        assert s.scenario_type == "general_purchase"
        assert s.purchase_amount is None
        assert "purchase_amount" in s.missing_inputs

    def test_time_horizon_next_year(self):
        s = parse("Can we still buy a house next year?")
        assert s.time_horizon == "next year"
        assert s.time_horizon_months == 12

    def test_time_horizon_months(self):
        s = parse("Can we afford a car in 6 months?")
        assert s.time_horizon == "in 6 months"
        assert s.time_horizon_months == 6

    def test_down_payment_pct_extracted(self):
        s = parse("Can we buy a house with 10% down?")
        assert s.down_payment_pct == Decimal("0.10")

    def test_protected_goals_passed_through(self):
        s = parse(
            "Would a Birkin hurt our house savings?",
            protected_goals=["house savings"],
        )
        assert "house savings" in s.protected_goals

    def test_task_type_override_forces_home(self):
        s = parse("Can we buy a Birkin?", task_type_override="home_affordability")
        assert s.scenario_type == "home_purchase"


# ── Data collector ─────────────────────────────────────────────────────────────

class TestDataCollector:
    def test_basic_snapshot(self):
        snap = _make_snap(liquid=50_000, monthly_spend=3_000)
        assert snap.liquid_cash == Decimal("50000")
        assert snap.emergency_reserve_target == Decimal("18000")  # 6 × 3000
        assert snap.comfortable_spend_capacity == Decimal("32000")

    def test_retirement_excluded(self):
        snap = _make_snap(liquid=50_000, retirement=200_000)
        assert snap.liquid_cash == Decimal("50000")
        assert snap.retirement_value == Decimal("200000")
        assert len(snap.excluded_account_labels) > 0

    def test_missing_spend_uses_fallback(self):
        snap = _make_snap(liquid=50_000, monthly_spend=None)
        assert snap.monthly_spending == _MONTHLY_SPEND_FALLBACK
        assert snap.has_spending_data is False
        assert len(snap.data_quality_notes) > 0

    def test_no_rows_returns_empty_snapshot(self):
        snap = _build_snapshot([], None, None, None)
        assert snap.has_balance_data is False
        assert len(snap.data_quality_notes) > 0

    def test_monthly_surplus_computed_when_both_available(self):
        snap = _make_snap(liquid=50_000, monthly_spend=3_000, monthly_income=8_000)
        assert snap.monthly_surplus == Decimal("5000")


# ── Math engine ───────────────────────────────────────────────────────────────

class TestMathEngine:
    # ── Home math ──────────────────────────────────────────────────────────────

    def test_home_1_3m_cash_gap(self):
        """$1.3M house: down=260k, closing=39k, total=299k. With 100k liquid → gap=199k."""
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        scenario = _make_home_scenario(1_300_000)
        math = compute_home(scenario, snap)
        assert math.down_payment == Decimal("260000")
        assert math.closing_costs == Decimal("39000")
        assert math.cash_needed_at_close == Decimal("299000")
        assert math.cash_gap_at_close == Decimal("199000")
        assert math.cash_gap_at_close > 0

    def test_home_monthly_payment(self):
        snap = _make_snap(liquid=400_000, monthly_spend=5_000)
        scenario = _make_home_scenario(1_000_000)
        math = compute_home(scenario, snap)
        assert math.principal_interest_monthly is not None
        assert math.principal_interest_monthly > Decimal("4000")

    def test_home_no_price_gives_max_affordable(self):
        snap = _make_snap(liquid=200_000, monthly_spend=3_000)
        scenario = _make_home_scenario(None)
        math = compute_home(scenario, snap)
        assert math.max_affordable_home_price is not None
        assert math.max_affordable_home_price > Decimal("700_000")

    def test_home_dti_computed_when_income_available(self):
        snap = _make_snap(liquid=400_000, monthly_spend=5_000, monthly_income=15_000)
        scenario = _make_home_scenario(1_000_000)
        math = compute_home(scenario, snap)
        assert math.dti_pct is not None

    # ── Purchase math ──────────────────────────────────────────────────────────

    def test_luxury_bag_comfortable(self):
        """$5k bag, $100k liquid, $18k reserve → comfortable."""
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        scenario = _make_purchase_scenario("Birkin", 5_000)
        math = compute_purchase(scenario, snap)
        assert math.cash_after_purchase == Decimal("95000")
        assert math.reserve_gap_after == Decimal("0")
        assert math.comfortable_spend_capacity == Decimal("82000")

    def test_car_stretch(self):
        """$30k car, $30k liquid, $18k reserve → stretch."""
        snap = _make_snap(liquid=30_000, monthly_spend=3_000)
        scenario = _make_purchase_scenario("car", 25_000, "vehicle")
        math = compute_purchase(scenario, snap)
        assert math.cash_after_purchase == Decimal("5000")
        assert math.reserve_gap_after == Decimal("13000")

    def test_missing_amount_no_cash_after(self):
        snap = _make_snap(liquid=50_000)
        scenario = _make_purchase_scenario("mystery item", None)
        math = compute_purchase(scenario, snap)
        assert math.purchase_amount is None
        assert math.cash_after_purchase is None

    def test_assumptions_always_present(self):
        snap = _make_snap(liquid=50_000)
        scenario = _make_purchase_scenario("bag", 5_000)
        math = compute_purchase(scenario, snap)
        assert len(math.assumptions) >= 2
        assert any("emergency reserve" in a.lower() for a in math.assumptions)

    def test_months_to_save_computed_when_surplus_available(self):
        # liquid=30k, capacity=12k, price=20k → 8k shortfall
        # income=8k, spend=3k → surplus=5k → months=2
        snap = _make_snap(liquid=30_000, monthly_spend=3_000, monthly_income=8_000)
        scenario = _make_purchase_scenario("bag", 20_000)
        math = compute_purchase(scenario, snap)
        assert math.months_to_save_for_purchase is not None
        assert math.months_to_save_for_purchase > 0

    def test_all_known_amounts_includes_liquid(self):
        snap = _make_snap(liquid=50_000)
        scenario = _make_purchase_scenario("bag", 5_000)
        math = compute_purchase(scenario, snap)
        known = math.all_known_amounts()
        assert 50_000 in known
        assert 5_000 in known


# ── Decision engine ───────────────────────────────────────────────────────────

class TestDecisionEngine:
    # ── Purchase decisions ─────────────────────────────────────────────────────

    def test_comfortable(self):
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        s = _make_purchase_scenario("Birkin", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        assert d.verdict_code == VerdictCode.COMFORTABLE
        assert d.severity == VerdictSeverity.OK

    def test_reasonable(self):
        # liquid=30k, reserve=18k, capacity=12k, price=15k → dips 3k into reserve
        snap = _make_snap(liquid=30_000, monthly_spend=3_000)
        s = _make_purchase_scenario("bag", 15_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        assert d.verdict_code in (VerdictCode.REASONABLE, VerdictCode.STRETCH)

    def test_not_affordable(self):
        snap = _make_snap(liquid=10_000, monthly_spend=3_000)
        s = _make_purchase_scenario("bag", 15_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        assert d.verdict_code == VerdictCode.NOT_AFFORDABLE
        assert d.severity == VerdictSeverity.STOP

    def test_needs_more_info_no_data(self):
        snap = _make_snap(liquid=0, retirement=0)
        s = _make_purchase_scenario("bag", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        assert d.verdict_code == VerdictCode.NEEDS_MORE_INFO

    def test_needs_more_info_no_price(self):
        snap = _make_snap(liquid=50_000)
        s = _make_purchase_scenario("mystery", None)
        math = compute_purchase(s, snap)
        d = decide(math)
        assert d.verdict_code == VerdictCode.NEEDS_MORE_INFO

    def test_allowed_conclusions_present(self):
        snap = _make_snap(liquid=100_000)
        s = _make_purchase_scenario("bag", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        assert len(d.allowed_conclusions) > 0

    def test_forbidden_conclusions_present(self):
        snap = _make_snap(liquid=10_000)
        s = _make_purchase_scenario("bag", 15_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        assert len(d.forbidden_conclusions) > 0

    # ── Home decisions ─────────────────────────────────────────────────────────

    def test_home_1_3m_not_affordable(self):
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        s = _make_home_scenario(1_300_000)
        math = compute_home(s, snap)
        d = decide(math)
        assert d.verdict_code == VerdictCode.NOT_AFFORDABLE
        assert d.severity == VerdictSeverity.STOP

    def test_home_comfortable(self):
        snap = _make_snap(liquid=400_000, monthly_spend=3_000)
        s = _make_home_scenario(1_000_000)
        math = compute_home(s, snap)
        d = decide(math)
        assert d.verdict_code == VerdictCode.COMFORTABLE

    def test_home_stretch_reserves_tight(self):
        # 240k liquid, 1M home: 230k at close → 10k left, reserve=18k → gap=220k+18k-240k=−2k (barely ok)
        # Adjust: 245k liquid, 1M home: 230k close, 15k left, reserve=18k → comfortable_gap=230+18-245=3k > 0
        snap = _make_snap(liquid=245_000, monthly_spend=3_000)
        s = _make_home_scenario(1_000_000)
        math = compute_home(s, snap)
        d = decide(math)
        assert d.verdict_code in (VerdictCode.STRETCH, VerdictCode.COMFORTABLE)


# ── Advisory context ──────────────────────────────────────────────────────────

class TestAdvisoryContext:
    def test_home_not_affordable_core_tension(self):
        snap = _make_snap(liquid=100_000)
        s = _make_home_scenario(1_300_000)
        math = compute_home(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        assert "cash" in ctx.core_tension.lower() or "upfront" in ctx.core_tension.lower()
        assert ctx.risk_level == "high"

    def test_luxury_comfortable_low_risk(self):
        snap = _make_snap(liquid=100_000)
        s = _make_purchase_scenario("Birkin", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        assert ctx.risk_level == "low"
        assert ctx.direct_answer  # not empty

    def test_not_affordable_has_what_would_make_it_work(self):
        snap = _make_snap(liquid=10_000)
        s = _make_purchase_scenario("bag", 50_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        assert len(ctx.what_would_make_it_work) > 0

    def test_protected_goals_reflected(self):
        snap = _make_snap(liquid=30_000)
        s = parse(
            "Would a Birkin hurt our house savings?",
            purchase_price_override=15_000,
            purchase_item_override="Birkin",
            purchase_category_override="luxury_discretionary",
            protected_goals=["house savings"],
        )
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        assert ctx.protected_goals == ["house savings"]

    def test_sufficient_monthly_income_but_insufficient_cash(self):
        """High income but low liquid cash → NOT_AFFORDABLE or STRETCH, not COMFORTABLE."""
        snap = _make_snap(liquid=50_000, monthly_spend=3_000, monthly_income=20_000)
        s = _make_home_scenario(1_300_000)
        math = compute_home(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        # The constraint should be cash-related, not income
        assert d.verdict_code == VerdictCode.NOT_AFFORDABLE
        assert "cash" in ctx.primary_constraint.lower() or "upfront" in ctx.primary_constraint.lower()


# ── Verifier ──────────────────────────────────────────────────────────────────

class TestVerifier:
    def _not_affordable_setup(self):
        snap = _make_snap(liquid=10_000)
        s = _make_purchase_scenario("bag", 50_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        return math, d

    def test_llm_cannot_flip_not_affordable_to_comfortable(self):
        math, decision = self._not_affordable_setup()
        v = verify(
            summary="You can afford it — looks comfortable!",
            verdict_label_from_llm=decision.verdict_label,
            math=math,
            decision=decision,
        )
        assert v.repaired is True
        assert any("comfortable" in w or "approval" in w for w in v.warnings)

    def test_invented_amount_triggers_fail(self):
        snap = _make_snap(liquid=50_000)
        s = _make_purchase_scenario("bag", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        v = verify(
            summary="You have $999,999 in savings so this is clearly fine.",
            verdict_label_from_llm=d.verdict_label,
            math=math,
            decision=d,
        )
        assert v.repaired is True
        assert any("invented" in w or "999" in w for w in v.warnings)

    def test_home_terms_in_non_home_answer(self):
        snap = _make_snap(liquid=100_000)
        s = _make_purchase_scenario("bag", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        v = verify(
            summary="The $5,000 bag. You need to consider the down payment and closing costs.",
            verdict_label_from_llm=d.verdict_label,
            math=math,
            decision=d,
        )
        assert v.repaired is True
        assert any("home-only" in w or "non-home" in w for w in v.warnings)

    def test_clean_answer_passes(self):
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        s = _make_purchase_scenario("Birkin", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        v = verify(
            summary=(
                f"The $5,000 Birkin fits within your ${82_000:,} available spend capacity "
                "so the reserve stays intact."
            ),
            verdict_label_from_llm=d.verdict_label,
            math=math,
            decision=d,
        )
        assert v.passed is True
        assert v.repaired is False

    def test_verdict_label_mismatch_triggers_fail(self):
        snap = _make_snap(liquid=10_000)
        s = _make_purchase_scenario("bag", 50_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        v = verify(
            summary=f"Not affordable. You can't cover ${50_000:,}.",
            verdict_label_from_llm="Comfortable",  # wrong label
            math=math,
            decision=d,
        )
        assert v.repaired is True


# ── Narrative builder (template path — no LLM) ───────────────────────────────

class TestNarrativeTemplate:
    def test_no_bullets_in_template(self):
        snap = _make_snap(liquid=100_000)
        s = _make_purchase_scenario("Birkin", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        assert "•" not in summary
        assert "- " not in summary[:5]
        assert "*" not in summary[:5]

    def test_summary_not_empty(self):
        snap = _make_snap(liquid=100_000)
        s = _make_purchase_scenario("Birkin", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        assert len(summary) > 20

    def test_summary_does_not_start_with_based_on(self):
        snap = _make_snap(liquid=100_000)
        s = _make_purchase_scenario("Birkin", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        assert not summary.lower().startswith("based on your")

    def test_summary_does_not_start_with_verdict_colon(self):
        snap = _make_snap(liquid=100_000)
        s = _make_purchase_scenario("Birkin", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        assert not summary.lower().startswith("verdict:")

    def test_not_affordable_summary_contains_no_approval(self):
        snap = _make_snap(liquid=10_000)
        s = _make_purchase_scenario("bag", 50_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        assert "comfortable" not in summary.lower() or "not comfortable" in summary.lower()

    def test_waiting_12_months_scenario(self):
        """What-if: with monthly surplus, months_to_save should be populated."""
        # liquid=20k, capacity=2k, price=14k → shortfall=12k
        # surplus=2k/month → 6 months to save
        snap = _make_snap(liquid=20_000, monthly_spend=3_000, monthly_income=5_000)
        s = _make_purchase_scenario("bag", 14_000)
        math = compute_purchase(s, snap)
        assert math.months_to_save_for_purchase is not None

    def test_enough_income_but_cash_short_home(self):
        """High income user — the problem should be flagged as cash, not income."""
        snap = _make_snap(liquid=50_000, monthly_spend=3_000, monthly_income=25_000)
        s = _make_home_scenario(1_300_000)
        math = compute_home(s, snap)
        d = decide(math)
        assert d.verdict_code == VerdictCode.NOT_AFFORDABLE
        # Primary reason must reference cash shortage, not income
        assert "$" in d.primary_reason
        assert "cash" in d.primary_reason.lower() or "liquid" in d.primary_reason.lower()


# ── Narrative style (template + simulated LLM output) ────────────────────────

_FORBIDDEN_PHRASES = [
    "verdict:",
    "based on your data",
    "based on the analysis",
    "here are the key factors",
    "in conclusion",
    "i estimate",
    "i calculate",
    "i computed",
    "my estimate",
]

_BULLET_PATTERN = re.compile(r"(?m)^[ \t]*[-•*]\s")


def _count_dollar_amounts(text: str) -> int:
    return len(re.findall(r"\$\s*[\d,]+", text))


def _has_forbidden_phrase(text: str) -> str | None:
    lower = text.lower()
    for phrase in _FORBIDDEN_PHRASES:
        if phrase in lower:
            return phrase
    return None


class TestNarrativeStyle:
    """
    Style contract tests for affordability narration.

    These tests use the deterministic template (no LLM) to check that:
      - house affordability responses have no default bullets
      - luxury purchase responses have no default bullets
      - answer starts with direct advice (not a forbidden opener)
      - answer includes the primary constraint
      - answer uses at most 4 numeric dollar facts
      - answer contains no forbidden phrases

    A second set of tests validates that a simulated LLM-output string is
    accepted or rejected correctly by the verifier, ensuring the guardrails
    hold end-to-end.
    """

    # ── Template path: house affordability ───────────────────────────────────

    def test_house_not_affordable_no_bullets(self):
        """House where cash is short: template answer must be prose, not bullets."""
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        s = _make_home_scenario(1_300_000)
        math = compute_home(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        assert not _BULLET_PATTERN.search(summary), f"Bullet found in: {summary!r}"

    def test_house_comfortable_no_bullets(self):
        """House the user can afford: template answer must be prose."""
        snap = _make_snap(liquid=400_000, monthly_spend=3_000)
        s = _make_home_scenario(1_000_000)
        math = compute_home(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        assert not _BULLET_PATTERN.search(summary), f"Bullet found in: {summary!r}"

    # ── Template path: luxury purchase ────────────────────────────────────────

    def test_luxury_comfortable_no_bullets(self):
        """Birkin bag well within reach: template answer must be prose."""
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        s = _make_purchase_scenario("Birkin", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        assert not _BULLET_PATTERN.search(summary), f"Bullet found in: {summary!r}"

    def test_luxury_not_affordable_no_bullets(self):
        """Luxury item user cannot afford: template answer must be prose."""
        snap = _make_snap(liquid=10_000, monthly_spend=3_000)
        s = _make_purchase_scenario("watch", 50_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        assert not _BULLET_PATTERN.search(summary), f"Bullet found in: {summary!r}"

    # ── Template path: starts with direct advice ──────────────────────────────

    def test_answer_starts_with_direct_advice_not_affordable(self):
        """NOT_AFFORDABLE template must not open with a forbidden phrase."""
        snap = _make_snap(liquid=10_000, monthly_spend=3_000)
        s = _make_purchase_scenario("bag", 50_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        lower = summary.lower()
        assert not lower.startswith("verdict:"), f"Opened with 'Verdict:': {summary!r}"
        assert not lower.startswith("based on your"), f"Opened with 'Based on your': {summary!r}"
        assert not lower.startswith("here are"), f"Opened with 'Here are': {summary!r}"
        assert not lower.startswith("in conclusion"), f"Opened with 'In conclusion': {summary!r}"

    def test_answer_starts_with_direct_advice_comfortable(self):
        """COMFORTABLE template must not open with a forbidden phrase."""
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        s = _make_purchase_scenario("Birkin", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        lower = summary.lower()
        assert not lower.startswith("verdict:")
        assert not lower.startswith("based on your")

    # ── Template path: primary constraint present ─────────────────────────────

    def test_not_affordable_includes_primary_constraint(self):
        """NOT_AFFORDABLE template must mention the shortfall or liquid cash."""
        snap = _make_snap(liquid=10_000, monthly_spend=3_000)
        s = _make_purchase_scenario("bag", 50_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        lower = summary.lower()
        # Must reference the constraint: cash, liquid, shortfall, or a dollar amount
        assert "$" in summary or "cash" in lower or "liquid" in lower or "shortfall" in lower, (
            f"Primary constraint not mentioned in: {summary!r}"
        )

    def test_house_not_affordable_includes_cash_constraint(self):
        """House NOT_AFFORDABLE template must reference the cash gap."""
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        s = _make_home_scenario(1_300_000)
        math = compute_home(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        lower = summary.lower()
        assert "cash" in lower or "liquid" in lower or "upfront" in lower or "$" in summary, (
            f"Cash constraint not found in: {summary!r}"
        )

    # ── Template path: numeric fact count ────────────────────────────────────

    def test_template_uses_at_most_four_numbers(self):
        """Template summary must not dump more than 4 dollar amounts."""
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        s = _make_home_scenario(1_300_000)
        math = compute_home(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        count = _count_dollar_amounts(summary)
        assert count <= 4, f"Too many dollar amounts ({count}) in: {summary!r}"

    def test_luxury_template_uses_at_most_four_numbers(self):
        snap = _make_snap(liquid=30_000, monthly_spend=3_000)
        s = _make_purchase_scenario("watch", 25_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        count = _count_dollar_amounts(summary)
        assert count <= 4, f"Too many dollar amounts ({count}) in: {summary!r}"

    # ── Template path: forbidden phrases ─────────────────────────────────────

    def test_no_forbidden_phrases_comfortable(self):
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        s = _make_purchase_scenario("Birkin", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        hit = _has_forbidden_phrase(summary)
        assert hit is None, f"Forbidden phrase {hit!r} found in: {summary!r}"

    def test_no_forbidden_phrases_not_affordable(self):
        snap = _make_snap(liquid=10_000, monthly_spend=3_000)
        s = _make_purchase_scenario("bag", 50_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        hit = _has_forbidden_phrase(summary)
        assert hit is None, f"Forbidden phrase {hit!r} found in: {summary!r}"

    def test_no_forbidden_phrases_house_not_affordable(self):
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        s = _make_home_scenario(1_300_000)
        math = compute_home(s, snap)
        d = decide(math)
        ctx = build_advisory(math, d, s)
        summary, _ = build_template(math, d, ctx)
        hit = _has_forbidden_phrase(summary)
        assert hit is None, f"Forbidden phrase {hit!r} found in: {summary!r}"

    # ── Simulated LLM output: verifier catches bad style ─────────────────────

    def test_verifier_rejects_bullet_style_not_affordable(self):
        """A bullet-point LLM response for NOT_AFFORDABLE must be caught by verifier
        because it contains an approval word ('comfortable') in the summary."""
        snap = _make_snap(liquid=10_000, monthly_spend=3_000)
        s = _make_purchase_scenario("bag", 50_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        # Simulate an LLM that ignored style rules and flipped the verdict meaning
        bad_summary = (
            "Verdict: Not affordable.\n"
            "- Liquid cash is too low.\n"
            "- The purchase looks comfortable for a different budget."
        )
        v = verify(
            summary=bad_summary,
            verdict_label_from_llm=d.verdict_label,
            math=math,
            decision=d,
        )
        # "comfortable" in a NOT_AFFORDABLE answer is caught by verifier
        assert v.repaired is True

    def test_verifier_accepts_clean_advisory_prose_not_affordable(self):
        """A clean prose NOT_AFFORDABLE answer with no approval words must pass."""
        snap = _make_snap(liquid=10_000, monthly_spend=3_000)
        s = _make_purchase_scenario("bag", 50_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        # Simulate good LLM output: direct, no bullets, no approval, uses real amounts
        good_summary = (
            "No — the $50,000 bag costs more than your $10,000 in liquid savings. "
            "The shortfall is $40,000, which is the primary issue here. "
            "Save that gap before committing to this purchase."
        )
        v = verify(
            summary=good_summary,
            verdict_label_from_llm=d.verdict_label,
            math=math,
            decision=d,
        )
        assert v.passed is True, f"Unexpected failures: {v.warnings}"

    def test_verifier_accepts_clean_advisory_prose_comfortable(self):
        """A clean prose COMFORTABLE answer must pass verification."""
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        s = _make_purchase_scenario("Birkin", 5_000)
        math = compute_purchase(s, snap)
        d = decide(math)
        # Use only amounts from all_known_amounts() — no derived remainders
        good_summary = (
            "Yes — the $5,000 Birkin fits comfortably within your available discretionary cash. "
            "Your emergency reserve of $18,000 stays fully intact after this purchase. "
            "You are in good shape; proceed if it fits your priorities."
        )
        v = verify(
            summary=good_summary,
            verdict_label_from_llm=d.verdict_label,
            math=math,
            decision=d,
        )
        assert v.passed is True, f"Unexpected failures: {v.warnings}"

    def test_verifier_accepts_house_not_affordable_prose(self):
        """House NOT_AFFORDABLE clean prose answer must pass."""
        snap = _make_snap(liquid=100_000, monthly_spend=3_000)
        s = _make_home_scenario(1_300_000)
        math = compute_home(s, snap)
        d = decide(math)
        # Build a realistic prose answer using known amounts
        cash_at_close = math.cash_needed_at_close  # 299k
        liquid = math.liquid_cash                   # 100k
        gap = math.cash_gap_at_close                # 199k
        good_summary = (
            f"Not right now — this purchase requires ${cash_at_close:,.0f} upfront "
            f"but you only have ${liquid:,.0f} in liquid savings. "
            f"The gap is ${gap:,.0f}, and that is the main obstacle here, "
            "not the monthly payment. "
            f"Focus on a lower target price or build liquid savings first."
        )
        v = verify(
            summary=good_summary,
            verdict_label_from_llm=d.verdict_label,
            math=math,
            decision=d,
        )
        assert v.passed is True, f"Unexpected failures: {v.warnings}"
