"""
advisory_context.py — Synthesizes math + decision into a rich advisory framing.

AdvisoryContext is the most important new layer. It turns the deterministic
math + verdict into the conceptual framing that makes an answer feel like
advice rather than a report. It answers:

  - What is the real tension here? (core_tension)
  - What is the single biggest constraint? (primary_constraint)
  - What else is worth watching? (secondary_constraints)
  - What is NOT the problem? (what_is_not_the_problem)
  - What would change the answer? (what_would_make_it_work)
  - What should the user do next? (recommended_next_step)

The LLM narrator receives this context and uses it to shape the tone and
emphasis of the answer. No Python math or verdict is ever altered here.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .data_collector import FinancialSnapshot
from .decision_engine import DecisionResult, VerdictCode
from .math_engine import MathResult
from .scenario_parser import AffordabilityScenario

# Re-export these so consumers can import from advisory_context only
from app.chat.answer_style import AnswerMode, ResponseShape


class AdvisoryContext(BaseModel):
    """
    Synthesized advisory framing derived entirely from math + decision.
    No numbers here — only interpretive context the LLM narrator can use.
    """
    scenario_type: str

    # The one-sentence direct answer (mirrors verdict_label with a sentence)
    direct_answer: str

    # The central tension in this situation
    core_tension: str

    # The single most important limiting factor
    primary_constraint: str

    # Other constraints worth mentioning (2–3 max)
    secondary_constraints: list[str] = Field(default_factory=list)

    # Facts that are NOT the problem — prevents the LLM from over-indexing
    what_is_not_the_problem: list[str] = Field(default_factory=list)

    # Conditions that would change the answer
    what_would_make_it_work: list[str] = Field(default_factory=list)

    # Single most actionable next step
    recommended_next_step: str

    # Risk level for UI display
    risk_level: Literal["low", "medium", "high"] = "medium"

    # Emotional frame — the tone the narrator should adopt
    emotional_frame: str = "calm and direct"

    # Style guidance passed to the narrative builder
    answer_mode: str = AnswerMode.ADVISORY.value
    response_shape: str = ResponseShape.NATURAL_ADVISORY.value

    # Semantic framing from query planner
    protected_goals: list[str] = Field(default_factory=list)
    time_horizon: str | None = None
    user_is_asking_for: str = ""


def _fmt(v) -> str:
    if v is None:
        return "N/A"
    from decimal import Decimal
    return f"${Decimal(str(v)):,.0f}"


# ── Scenario-specific advisory builders ───────────────────────────────────────

def _home_advisory(
    math: MathResult,
    decision: DecisionResult,
    scenario: AffordabilityScenario,
) -> AdvisoryContext:
    price = math.purchase_amount
    liquid = math.liquid_cash
    cash_at_close = math.cash_needed_at_close
    cash_gap = math.cash_gap_at_close
    reserve = math.emergency_reserve_target
    comfortable_gap = math.comfortable_cash_gap
    dti = math.dti_pct
    total_housing = math.total_monthly_housing
    income = math.monthly_income

    verdict = decision.verdict_code

    if verdict == VerdictCode.NEEDS_MORE_INFO:
        if price is None:
            direct = "There isn't enough information to give you a clear answer — no home price was provided."
        else:
            direct = "There isn't enough balance data to assess this purchase."
        return AdvisoryContext(
            scenario_type="home_purchase",
            direct_answer=direct,
            core_tension="Without a price or balance data, the analysis can't proceed.",
            primary_constraint="missing data",
            recommended_next_step="Share the target home price and upload a bank statement.",
            risk_level="medium",
            emotional_frame="helpful and encouraging",
            answer_mode=AnswerMode.ADVISORY.value,
            response_shape=ResponseShape.NATURAL_ADVISORY.value,
        )

    if verdict == VerdictCode.NOT_AFFORDABLE:
        core = (
            f"The household may have meaningful assets, but this purchase requires "
            f"too much upfront cash. The down payment and closing costs alone exceed "
            f"what's available in liquid accounts."
        )
        constraint = f"cash to close ({_fmt(cash_at_close)}) exceeds liquid cash ({_fmt(liquid)})"
        not_problem: list[str] = []
        if income and total_housing and (total_housing / income * 100) < 30:
            not_problem.append("This is not primarily a monthly payment problem.")
        if math.investment_value > 0:
            not_problem.append(
                f"Having {_fmt(math.investment_value)} in investments is positive, "
                "but those funds aren't freely available for closing day."
            )
        would_work = [
            f"Lower the target price so upfront costs fit within liquid cash of {_fmt(liquid)}.",
        ]
        if math.investment_value > 0:
            would_work.append(
                "Liquidating some investments (with tax advice) could bridge the gap — "
                "but that's a decision to make carefully."
            )
        return AdvisoryContext(
            scenario_type="home_purchase",
            direct_answer=f"Not right now — the upfront cash required ({_fmt(cash_at_close)}) exceeds your liquid savings ({_fmt(liquid)}).",
            core_tension=core,
            primary_constraint=constraint,
            secondary_constraints=[f"Shortfall: {_fmt(cash_gap)}"],
            what_is_not_the_problem=not_problem,
            what_would_make_it_work=would_work,
            recommended_next_step=f"Estimate a safer purchase price based on available cash ({_fmt(liquid)}) and desired reserve ({_fmt(reserve)}).",
            risk_level="high",
            emotional_frame="honest and constructive",
            protected_goals=scenario.protected_goals,
            time_horizon=scenario.time_horizon,
            user_is_asking_for=scenario.user_is_asking_for,
        )

    if verdict == VerdictCode.STRETCH:
        core = (
            "You can cover the upfront costs, but closing day would leave the emergency fund "
            "significantly below target — that's the main risk."
        )
        return AdvisoryContext(
            scenario_type="home_purchase",
            direct_answer=f"Technically yes, but it would be a stretch — you'd have only {_fmt(liquid - (cash_at_close or 0))} left after close.",
            core_tension=core,
            primary_constraint=f"post-close reserve gap ({_fmt(comfortable_gap)})",
            secondary_constraints=(
                [f"Monthly housing cost {_fmt(total_housing)} ({dti}% of income) above 28% guideline."]
                if dti and dti > 28 else []
            ),
            what_is_not_the_problem=["The upfront cash is technically available."],
            what_would_make_it_work=[
                f"Build liquid savings by {_fmt((comfortable_gap or 0) + (cash_at_close or 0))} before buying.",
                "Consider a lower purchase price that leaves the reserve intact.",
            ],
            recommended_next_step="Focus on building liquid savings before committing to this purchase.",
            risk_level="high",
            emotional_frame="honest and constructive",
            protected_goals=scenario.protected_goals,
            time_horizon=scenario.time_horizon,
            user_is_asking_for=scenario.user_is_asking_for,
        )

    if verdict == VerdictCode.REASONABLE:
        core = (
            "The upfront costs are manageable, but the ongoing monthly payment is worth watching."
        )
        return AdvisoryContext(
            scenario_type="home_purchase",
            direct_answer=f"Yes, upfront costs look manageable — but the monthly payment ({_fmt(total_housing)}) is on the high side.",
            core_tension=core,
            primary_constraint="monthly housing burden relative to income",
            secondary_constraints=[
                f"DTI of {dti}% is above the 28% guideline." if dti else "",
            ],
            what_is_not_the_problem=["The upfront cash appears sufficient."],
            what_would_make_it_work=["A lower purchase price would bring the monthly payment within guideline."],
            recommended_next_step="Model a lower purchase price to get the monthly payment below 28% of income.",
            risk_level="medium",
            emotional_frame="calm and direct",
            protected_goals=scenario.protected_goals,
        )

    # COMFORTABLE
    remaining = (math.liquid_cash or 0) - (cash_at_close or 0)
    return AdvisoryContext(
        scenario_type="home_purchase",
        direct_answer=f"Yes, this looks feasible — you can cover the {_fmt(cash_at_close)} needed at close and still have {_fmt(remaining)} left.",
        core_tension="Upfront costs are manageable and reserves are maintained.",
        primary_constraint="none significant",
        what_is_not_the_problem=["The cash to close is covered.", "Monthly payment appears within guidelines."],
        what_would_make_it_work=["Already looks workable — consult a lender for final qualification."],
        recommended_next_step="Get pre-approved by a lender to confirm your actual rate and qualification.",
        risk_level="low",
        emotional_frame="warm and affirming",
        protected_goals=scenario.protected_goals,
        time_horizon=scenario.time_horizon,
        user_is_asking_for=scenario.user_is_asking_for,
    )


def _purchase_advisory(
    math: MathResult,
    decision: DecisionResult,
    scenario: AffordabilityScenario,
) -> AdvisoryContext:
    price = math.purchase_amount
    liquid = math.liquid_cash
    reserve = math.emergency_reserve_target
    capacity = math.comfortable_spend_capacity
    cash_after = math.cash_after_purchase
    reserve_gap = math.reserve_gap_after
    item = math.purchase_item or "this purchase"
    verdict = decision.verdict_code
    income = math.monthly_income
    spending = math.monthly_spending

    if verdict == VerdictCode.NEEDS_MORE_INFO:
        if liquid == 0:
            direct = "There isn't enough balance data to assess affordability."
            core = "Without account balance data, there's nothing to work with."
            primary = "missing balance data"
            next_step = "Upload a bank or savings statement to Coral."
        else:
            direct = f"Share the price of the {item} and I can give you a precise answer."
            core = "The math can't run without a price."
            primary = "missing purchase price"
            next_step = f"What does the {item} cost?"
        return AdvisoryContext(
            scenario_type=scenario.scenario_type,
            direct_answer=direct,
            core_tension=core,
            primary_constraint=primary,
            recommended_next_step=next_step,
            risk_level="medium",
            emotional_frame="helpful",
        )

    if verdict == VerdictCode.NOT_AFFORDABLE:
        shortfall = (price or 0) - liquid
        not_problem: list[str] = []
        if income and spending and (income - spending) > 0:
            not_problem.append("This is not primarily an income problem.")
        if math.investment_value > 0:
            not_problem.append(f"The {_fmt(math.investment_value)} in investments doesn't solve this immediately.")
        return AdvisoryContext(
            scenario_type=scenario.scenario_type,
            direct_answer=f"No — the {item} costs {_fmt(price)}, which is more than your liquid cash of {_fmt(liquid)}.",
            core_tension=f"The purchase price exceeds available liquid cash by {_fmt(shortfall)}.",
            primary_constraint="insufficient liquid cash",
            secondary_constraints=[f"Shortfall: {_fmt(shortfall)}"],
            what_is_not_the_problem=not_problem,
            what_would_make_it_work=[
                "Save the shortfall amount before making this purchase.",
                f"If monthly surplus is available, it would take ~{math.months_to_save_for_purchase or '?'} months to bridge the gap.",
            ] if math.months_to_save_for_purchase else [
                "Save the shortfall amount before making this purchase.",
            ],
            recommended_next_step=f"Save {_fmt(shortfall)} before committing to this purchase.",
            risk_level="high",
            emotional_frame="honest and constructive",
            protected_goals=scenario.protected_goals,
            time_horizon=scenario.time_horizon,
            user_is_asking_for=scenario.user_is_asking_for,
        )

    if verdict == VerdictCode.COMFORTABLE:
        remaining = capacity - (price or 0)
        not_problem: list[str] = []
        if reserve_gap == 0:
            not_problem.append("The emergency reserve is fully preserved.")
        tension = (
            f"This purchase fits comfortably within available discretionary cash."
        )
        # If user is worried about a protected goal, acknowledge it
        if scenario.protected_goals:
            goal = scenario.protected_goals[0]
            tension = (
                f"This purchase fits comfortably within available discretionary cash, "
                f"and it doesn't threaten {goal}."
            )
        return AdvisoryContext(
            scenario_type=scenario.scenario_type,
            direct_answer=f"Yes — the {_fmt(price)} {item} is well within reach.",
            core_tension=tension,
            primary_constraint="none",
            what_is_not_the_problem=not_problem,
            what_would_make_it_work=["Already looks comfortable — no changes needed."],
            recommended_next_step=f"You're in good shape. Proceed if it fits your priorities.",
            risk_level="low",
            emotional_frame="warm and affirming",
            protected_goals=scenario.protected_goals,
            time_horizon=scenario.time_horizon,
            user_is_asking_for=scenario.user_is_asking_for,
        )

    if verdict == VerdictCode.REASONABLE:
        return AdvisoryContext(
            scenario_type=scenario.scenario_type,
            direct_answer=f"You can afford the {_fmt(price)} {item}, though it would modestly dip into your emergency reserve.",
            core_tension=(
                f"The purchase is payable, but it leaves the emergency reserve {_fmt(reserve_gap)} "
                "short of the target."
            ),
            primary_constraint=f"small reserve gap after purchase ({_fmt(reserve_gap)})",
            what_is_not_the_problem=["This isn't a question of whether you can physically pay."],
            what_would_make_it_work=[
                f"Waiting {math.months_to_save_for_purchase or 'a few'} more months would make this comfortable.",
                "Spending a little less elsewhere to rebuild the reserve quickly afterward.",
            ],
            recommended_next_step=f"Plan to rebuild the reserve within 2–3 months after the purchase.",
            risk_level="medium",
            emotional_frame="calm and direct",
            protected_goals=scenario.protected_goals,
            time_horizon=scenario.time_horizon,
            user_is_asking_for=scenario.user_is_asking_for,
        )

    # STRETCH
    return AdvisoryContext(
        scenario_type=scenario.scenario_type,
        direct_answer=f"Technically yes, but the {_fmt(price)} {item} would leave the emergency fund well short of target.",
        core_tension=(
            "The purchase may be technically possible, but it significantly depletes "
            "the financial buffer needed for emergencies."
        ),
        primary_constraint="emergency reserve depletion",
        secondary_constraints=(
            ["This competes with larger financial goals."]
            if scenario.protected_goals else []
        ),
        what_is_not_the_problem=["The money exists in the account."],
        what_would_make_it_work=[
            f"Saving {_fmt(reserve_gap)} more would make this comfortable.",
            "Reconsidering timing if there are upcoming large expenses.",
        ],
        recommended_next_step=f"Build the reserve by {_fmt(reserve_gap)} before proceeding.",
        risk_level="high",
        emotional_frame="honest and measured",
        protected_goals=scenario.protected_goals,
        time_horizon=scenario.time_horizon,
        user_is_asking_for=scenario.user_is_asking_for,
    )


# ── Main builder ──────────────────────────────────────────────────────────────

def build(
    math: MathResult,
    decision: DecisionResult,
    scenario: AffordabilityScenario,
) -> AdvisoryContext:
    """Build AdvisoryContext from the computed math and decision."""
    if scenario.scenario_type == "home_purchase":
        ctx = _home_advisory(math, decision, scenario)
    else:
        ctx = _purchase_advisory(math, decision, scenario)

    # Exploratory mode: if the user is doing a what-if, nudge the shape
    if scenario.user_is_asking_for in ("impact_analysis", "safety_check"):
        ctx.answer_mode = AnswerMode.EXPLORATORY.value
        ctx.response_shape = ResponseShape.WHAT_IF_EXPLANATION.value

    return ctx
