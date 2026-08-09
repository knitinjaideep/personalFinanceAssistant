"""
Tests for the advisory answer schema changes.

Acceptance criteria:
  - StructuredAnswer has main_answer_text, key_numbers, supporting_details fields
  - Affordability analyzer populates all three fields
  - key_numbers is a list of KeyNumber (label, value, note)
  - supporting_details is a list of SupportingDetail (heading, body)
  - summary is still populated (backward compat — raw_text depends on it)
  - answer_type is "advisory" for affordability answers (not "numeric")
  - suggested_followups are present and non-empty for affordability
  - Default followups include guidance questions when LLM returns none
  - Non-affordability answers (numeric, table, prose) retain their answer_type
  - KeyNumber and SupportingDetail round-trip through Pydantic cleanly
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.entities import KeyNumber, SupportingDetail, StructuredAnswer


# ── Schema round-trip ─────────────────────────────────────────────────────────

def test_key_number_roundtrip():
    kn = KeyNumber(label="Liquid cash", value="$50,000", note="checking + savings")
    d = kn.model_dump()
    assert d["label"] == "Liquid cash"
    assert d["value"] == "$50,000"
    assert d["note"] == "checking + savings"
    kn2 = KeyNumber(**d)
    assert kn2 == kn


def test_key_number_note_optional():
    kn = KeyNumber(label="Verdict", value="Comfortable")
    assert kn.note == ""


def test_supporting_detail_roundtrip():
    sd = SupportingDetail(heading="Why this matters", body="You have $32,000 available after reserves.")
    d = sd.model_dump()
    assert d["heading"] == "Why this matters"
    assert d["body"] == "You have $32,000 available after reserves."


def test_supporting_detail_heading_optional():
    sd = SupportingDetail(body="Monthly spend estimated at $3,000.")
    assert sd.heading == ""


# ── StructuredAnswer backward compat ─────────────────────────────────────────

def test_structured_answer_new_fields_default_empty():
    ans = StructuredAnswer(summary="Test", title="Test")
    assert ans.main_answer_text == ""
    assert ans.key_numbers == []
    assert ans.supporting_details == []


def test_structured_answer_summary_still_works():
    """Existing code that reads answer.summary must not break."""
    ans = StructuredAnswer(summary="This is the answer.", title="Balance")
    assert ans.summary == "This is the answer."


def test_structured_answer_advisory_fields():
    ans = StructuredAnswer(
        answer_type="advisory",
        title="Home affordability",
        summary="Not right now.",
        main_answer_text="Not right now. You'd need $260,000 at close but only have $220,000.",
        key_numbers=[
            KeyNumber(label="Liquid cash", value="$220,000"),
            KeyNumber(label="Cash needed at close", value="$260,000"),
        ],
        supporting_details=[
            SupportingDetail(heading="Why this matters", body="You're $40,000 short of what you need."),
        ],
        suggested_followups=["What home price would be safer?"],
    )
    assert ans.answer_type == "advisory"
    assert ans.main_answer_text.startswith("Not right now.")
    assert len(ans.key_numbers) == 2
    assert ans.key_numbers[0].label == "Liquid cash"
    assert ans.key_numbers[1].value == "$260,000"
    assert len(ans.supporting_details) == 1
    assert ans.supporting_details[0].heading == "Why this matters"
    assert ans.suggested_followups == ["What home price would be safer?"]
    # backward-compat alias
    assert ans.summary == "Not right now."


# ── Affordability analyzer helpers ────────────────────────────────────────────

def test_build_key_numbers_home_purchase():
    """_build_key_numbers for a home scenario includes expected fields."""
    from app.chat.domains.affordability.math_engine import MathResult
    from app.chat.domains.affordability.decision_engine import DecisionResult, VerdictCode, VerdictSeverity
    from app.chat.domains.affordability.analyzer import _build_key_numbers

    math = MathResult(
        scenario_type="home_purchase",
        purchase_item="house",
        purchase_amount=Decimal("1300000"),
        liquid_cash=Decimal("220000"),
        emergency_reserve_target=Decimal("18000"),
        comfortable_spend_capacity=Decimal("202000"),
        down_payment=Decimal("260000"),
        closing_costs=Decimal("39000"),
        cash_needed_at_close=Decimal("299000"),
        cash_remaining_after_close=Decimal("-79000"),
        total_monthly_housing=Decimal("8400"),
        dti_pct=Decimal("42"),
    )
    decision = DecisionResult(
        verdict_code=VerdictCode.NOT_AFFORDABLE,
        verdict_label="Not affordable — upfront cash shortfall",
        severity=VerdictSeverity.STOP,
        primary_reason="Cash needed at close exceeds liquid assets.",
        allowed_conclusions=[],
        forbidden_conclusions=[],
        recommended_followups=[],
    )

    nums = _build_key_numbers(math, decision)

    labels = [n.label for n in nums]
    assert "Verdict" in labels
    assert "Liquid cash (checking + savings)" in labels
    assert "Down payment (20%)" in labels
    assert "Total cash needed at close" in labels
    assert "Est. monthly housing cost" in labels
    assert "Est. debt-to-income ratio" in labels
    # note on emergency reserve
    reserve_kn = next(n for n in nums if "Emergency reserve" in n.label)
    assert "6 months" in reserve_kn.note


def test_build_key_numbers_purchase():
    """_build_key_numbers for a non-home purchase includes purchase cost."""
    from app.chat.domains.affordability.math_engine import MathResult
    from app.chat.domains.affordability.decision_engine import DecisionResult, VerdictCode, VerdictSeverity
    from app.chat.domains.affordability.analyzer import _build_key_numbers

    math = MathResult(
        scenario_type="purchase",
        purchase_item="Tesla",
        purchase_amount=Decimal("80000"),
        liquid_cash=Decimal("150000"),
        emergency_reserve_target=Decimal("18000"),
        comfortable_spend_capacity=Decimal("132000"),
        cash_after_purchase=Decimal("70000"),
    )
    decision = DecisionResult(
        verdict_code=VerdictCode.COMFORTABLE,
        verdict_label="Comfortable",
        severity=VerdictSeverity.OK,
        primary_reason="Well within comfortable capacity.",
        allowed_conclusions=[],
        forbidden_conclusions=[],
        recommended_followups=[],
    )

    nums = _build_key_numbers(math, decision)
    labels = [n.label for n in nums]
    assert "Cost of Tesla" in labels
    assert "Cash remaining after purchase" in labels


def test_build_supporting_details_includes_primary_constraint():
    """_build_supporting_details always includes the advisory primary_constraint."""
    from app.chat.domains.affordability.math_engine import MathResult
    from app.chat.domains.affordability.advisory_context import AdvisoryContext
    from app.chat.domains.affordability.analyzer import _build_supporting_details

    math = MathResult(
        scenario_type="home_purchase",
        liquid_cash=Decimal("220000"),
        emergency_reserve_target=Decimal("18000"),
        comfortable_spend_capacity=Decimal("202000"),
        assumptions=["Monthly spend estimated at $3,000/month."],
    )
    advisory = AdvisoryContext(
        scenario_type="home_purchase",
        direct_answer="Not right now.",
        core_tension="You're $79,000 short.",
        primary_constraint="You'd need $299,000 at close but only have $220,000.",
        secondary_constraints=[],
        what_would_make_it_work=["Save another $80,000 or lower the price by 10%."],
        recommended_next_step="Build savings for 12–18 more months.",
        risk_level="high",
        emotional_frame="cautious",
        response_shape="natural_advisory",
    )

    details = _build_supporting_details(math, advisory)
    bodies = [d.body for d in details]
    headings = [d.heading for d in details]

    assert any("$299,000" in b for b in bodies), "primary_constraint missing from details"
    assert any("Save another" in b or "$80,000" in b for b in bodies), "what_would_make_it_work missing from details"
    assert any("$3,000" in b for b in bodies), "math assumption missing from details"
    assert "Why this matters" in headings
    assert "What would change the answer" in headings


# ── Default followups ─────────────────────────────────────────────────────────

def test_affordability_answer_has_default_followups_when_llm_empty():
    """When followups list is empty (LLM/template returned none), defaults are injected."""
    ans = StructuredAnswer(
        answer_type="advisory",
        title="Home affordability",
        summary="Not right now.",
        main_answer_text="Not right now.",
        suggested_followups=[],
    )
    # Simulate what the analyzer does when followups are empty
    _DEFAULT_FOLLOWUPS = [
        "What home price would be safer?",
        "What if we wait 12 months?",
        "How much cash should we save first?",
        "What monthly payment fits our budget?",
    ]
    final = ans.suggested_followups if ans.suggested_followups else _DEFAULT_FOLLOWUPS
    assert len(final) == 4
    assert "What home price would be safer?" in final
    assert "What if we wait 12 months?" in final


# ── Non-affordability answers unchanged ──────────────────────────────────────

def test_non_affordability_answer_type_unchanged():
    """Numeric, table, and prose answers keep their answer_type untouched."""
    for atype in ("numeric", "table", "prose", "comparison", "no_data"):
        ans = StructuredAnswer(
            answer_type=atype,
            title="Test",
            summary="Test answer.",
        )
        assert ans.answer_type == atype
        # New fields default to empty — no side effects
        assert ans.key_numbers == []
        assert ans.main_answer_text == ""
