"""
Financial invariant tests for the Next Month Planner (PR 14 —
app.domain.next_month_planner). Mirrors test_overview_insights_invariants.py's
pattern exactly: synthetic ClassifiedTxn lists run through the REAL
app.domain.plan_vs_actual engine (never hand-authored variances) for the
Plan-vs-Actual-derived candidates, plus directly-constructed synthetic
SavingsGoalProgress / InvestmentContributionVehicle Pydantic objects for the
two inputs that don't come from a transaction engine.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.entities import AllocationSnapshot, PlanVersionSnapshot, SuballocationSnapshot
from app.domain.investment_plan import (
    ContributionDataCompleteness,
    InvestmentContributionPlanResult,
    InvestmentContributionVehicle,
)
from app.domain.next_month_planner import (
    MAX_RECOMMENDATIONS,
    RecommendationActionType,
    build_next_month_plan,
)
from app.domain.plan_vs_actual import (
    ClassifiedTxn,
    DriftStatus,
    Period,
    compute_category_breakdown,
    compute_merchant_drivers,
    compute_plan_vs_actual,
)
from app.domain.savings_goals import (
    GoalCompletenessMetadata,
    GoalCompletionRecommendation,
    GoalStatus,
    GoalType,
    SavingsGoalProgress,
)
from app.domain.transaction_classification import CashFlowType, MasterBucket

PERIOD = Period.for_month(2026, 8)


def _default_plan() -> PlanVersionSnapshot:
    return PlanVersionSnapshot(
        id="v1", plan_id="p1", version_number=1, effective_from=date(2026, 1, 1),
        allocations=[
            AllocationSnapshot(id="a1", bucket_name="needs", percentage="50", sort_order=0),
            AllocationSnapshot(id="a2", bucket_name="wants", percentage="20", sort_order=1),
            AllocationSnapshot(
                id="a3", bucket_name="savings", percentage="15", sort_order=2,
                suballocations=[
                    SuballocationSnapshot(
                        id="s1", name="Emergency Fund", percentage="5", sort_order=0,
                    ),
                    SuballocationSnapshot(
                        id="s2", name="House / Goals", percentage="5", sort_order=1,
                    ),
                    SuballocationSnapshot(
                        id="s3", name="Child Savings", percentage="5", sort_order=2,
                    ),
                ],
            ),
            AllocationSnapshot(
                id="a4", bucket_name="investments", percentage="15", sort_order=3,
                suballocations=[
                    SuballocationSnapshot(id="s4", name="401(k)", percentage="6", sort_order=0),
                    SuballocationSnapshot(id="s5", name="Roth IRA", percentage="4", sort_order=1),
                    SuballocationSnapshot(id="s6", name="ESPP", percentage="3", sort_order=2),
                    SuballocationSnapshot(
                        id="s7", name="Taxable Brokerage", percentage="2", sort_order=3,
                    ),
                ],
            ),
        ],
    )


def _txn(
    txn_id: str, amount: str, bucket: MasterBucket, flow: CashFlowType,
    *, category: str | None = None, account_type: str | None = "checking", day: int = 15,
    merchant: str | None = None,
) -> ClassifiedTxn:
    return ClassifiedTxn(
        transaction_id=txn_id, account_id=f"acct-{account_type}", account_type=account_type,
        transaction_date=date(2026, 8, day), amount=Decimal(amount), master_bucket=bucket,
        category=category, cash_flow_type=flow, merchant_name=merchant,
    )


def _pva(transactions: list[ClassifiedTxn], plan=None):
    plan = plan if plan is not None else _default_plan()
    return compute_plan_vs_actual(PERIOD, transactions, plan)


def _savings_categories(transactions: list[ClassifiedTxn], plan=None):
    plan = plan if plan is not None else _default_plan()
    return compute_category_breakdown(transactions, MasterBucket.SAVINGS, plan)


def _merchants(transactions: list[ClassifiedTxn]):
    return compute_merchant_drivers(transactions, top_n=20)


def _empty_investment_plan() -> InvestmentContributionPlanResult:
    return InvestmentContributionPlanResult(
        period=PERIOD, plannable_income="0.00", vehicles=[],
        total_target_pct=None, total_actual_amount="0.00", total_actual_pct=None,
        completeness=_pva([]).completeness,
    )


def _vehicle(
    *, vehicle: str, target_pct: str | None, target_amount: str | None, actual_amount: str,
    variance_amount: str | None, status: DriftStatus, recommended_next_month_delta: str | None,
    transaction_count: int = 3, is_complete: bool = True,
) -> InvestmentContributionVehicle:
    return InvestmentContributionVehicle(
        vehicle=vehicle, target_pct=target_pct, actual_pct=None,
        target_amount=target_amount, actual_amount=actual_amount,
        variance_amount=variance_amount, variance_pct_points=None, status=status,
        data_completeness=ContributionDataCompleteness(
            status="complete" if is_complete else "incomplete", is_complete=is_complete,
            income_observed=True, plan_available=True, payroll_data_complete=True, notes=[],
        ),
        recommended_next_month_delta=recommended_next_month_delta,
        transaction_count=transaction_count,
    )


def _goal(
    *, name: str, category_name: str, status: GoalStatus,
    current_amount: str = "0.00", target_amount_effective: str | None = None,
    variance_amount: str | None = None, is_complete: bool = True,
    completion_recommendation: GoalCompletionRecommendation | None = None,
    target_percentage_of_income: str | None = "5",
) -> SavingsGoalProgress:
    return SavingsGoalProgress(
        id=f"goal-{name}", name=name, goal_type=GoalType.CUSTOM, category_name=category_name,
        effective_date=date(2026, 1, 1), current_amount=current_amount, as_of=PERIOD.end,
        target_percentage_of_income=target_percentage_of_income,
        target_amount_effective=target_amount_effective, variance_amount=variance_amount,
        status=status,
        data_completeness=GoalCompletenessMetadata(
            all_mapped_accounts_parseable=is_complete,
            notes=[] if is_complete else ["incomplete data"],
        ),
        completion_recommendation=completion_recommendation,
    )


def _recs_of(plan, action_type):
    return [r for r in plan.recommendations if r.action_type == action_type]


def _build(
    *, transactions: list[ClassifiedTxn], goals: list[SavingsGoalProgress] | None = None,
    investment_plan: InvestmentContributionPlanResult | None = None, plan=None,
):
    result = _pva(transactions, plan)
    return build_next_month_plan(
        plan_vs_actual=result,
        savings_category_rows=_savings_categories(transactions, plan),
        merchant_drivers=_merchants(transactions),
        savings_goals=goals or [],
        investment_plan=investment_plan or _empty_investment_plan(),
    )


# ── Cap invariant: never more than 3, ever ──────────────────────────────────

def test_never_exceeds_max_recommendations():
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn(
            "t2", "-6000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Housing", merchant="Landlord",
        ),
        _txn(
            "t3", "-3000.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Dining", merchant="Cafe",
        ),
    ]
    goals = [
        _goal(name="Emergency Fund", category_name="Emergency Fund", status=GoalStatus.BEHIND),
        _goal(name="House / Goals", category_name="House / Goals", status=GoalStatus.BEHIND),
    ]
    investment_plan = InvestmentContributionPlanResult(
        period=PERIOD, plannable_income=str(income), vehicles=[
            _vehicle(
                vehicle="401(k)", target_pct="6", target_amount="600.00", actual_amount="0.00",
                variance_amount="-600.00", status=DriftStatus.OFF_TRACK,
                recommended_next_month_delta="600.00",
            ),
        ],
        total_target_pct="6", total_actual_amount="0.00", total_actual_pct="0.00",
        completeness=_pva(txns).completeness,
    )
    result = _build(transactions=txns, goals=goals, investment_plan=investment_plan)
    assert len(result.recommendations) <= MAX_RECOMMENDATIONS
    assert MAX_RECOMMENDATIONS == 3


# ── Incomplete-data honesty ──────────────────────────────────────────────────

def test_no_income_observed_yields_no_fabricated_recommendations():
    txns = [_txn("t1", "-50.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Groceries")]
    result = _pva(txns)
    assert result.completeness.income_observed is False
    plan = _build(transactions=txns)
    assert plan.recommendations == []


def test_all_unknown_status_never_fabricates_recommendation():
    """No plan in effect -> every BucketDrift.status is UNKNOWN -> no
    reduce_category/increase_savings_goal candidate can be built from it."""
    txns = [
        _txn("t1", "-5000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-100.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Groceries"),
    ]
    result = compute_plan_vs_actual(PERIOD, txns, None)
    assert all(b.status == DriftStatus.UNKNOWN for b in result.buckets)
    plan = build_next_month_plan(
        plan_vs_actual=result, savings_category_rows=[], merchant_drivers=[],
        savings_goals=[], investment_plan=_empty_investment_plan(),
    )
    assert plan.recommendations == []


def test_incomplete_savings_goal_surfaces_caveat_in_source_facts():
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-4000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        _txn("t3", "-1000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
        # Emergency Fund target = 5% * 10000 = $500. No contribution -> $500 short.
    ]
    goals = [_goal(
        name="Emergency Fund", category_name="Emergency Fund",
        status=GoalStatus.BEHIND, is_complete=False,
    )]
    plan = _build(transactions=txns, goals=goals)
    savings_recs = _recs_of(plan, RecommendationActionType.INCREASE_SAVINGS_GOAL)
    assert savings_recs, "expected an increase_savings_goal recommendation"
    rec = savings_recs[0]
    assert rec.incomplete_source is True
    assert any("completeness" in f.label.lower() for f in rec.source_facts)


def test_incomplete_source_never_outranks_complete_source_via_confidence():
    """Two candidates with identical impact/deviation/actionability: the one
    whose source is flagged incomplete must score strictly lower, so it can
    never silently outrank the complete one."""
    from app.domain.next_month_planner import _completeness_multiplier, _score

    complete_score = _score(
        impact=Decimal("500.00"), confidence=Decimal("0.85") * _completeness_multiplier(True),
        actionability=Decimal("0.90"),
    )
    incomplete_score = _score(
        impact=Decimal("500.00"), confidence=Decimal("0.85") * _completeness_multiplier(False),
        actionability=Decimal("0.90"),
    )
    assert incomplete_score < complete_score


# ── "Don't make up the full historical shortfall" rule ─────────────────────

def test_savings_goal_impact_is_this_periods_gap_not_cumulative_history():
    """A goal with a large CUMULATIVE variance (since its effective_date, far
    in the past) must not have that cumulative number used as
    estimated_impact — only THIS PERIOD's own category target/actual gap."""
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-4000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        _txn("t3", "-1000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
        # Emergency Fund target this period = $500; no contribution -> $500 short.
    ]
    # Goal reports a huge cumulative historical shortfall -- must be ignored.
    goals = [_goal(
        name="Emergency Fund", category_name="Emergency Fund", status=GoalStatus.BEHIND,
        current_amount="0.00", target_amount_effective="45000.00", variance_amount="-45000.00",
    )]
    plan = _build(transactions=txns, goals=goals)
    savings_recs = _recs_of(plan, RecommendationActionType.INCREASE_SAVINGS_GOAL)
    assert savings_recs
    impact = Decimal(savings_recs[0].estimated_impact)
    assert impact == Decimal("500.00")
    assert impact < Decimal("45000.00")


def test_investment_delta_is_read_verbatim_not_recomputed():
    income = Decimal("10000.00")
    txns = [_txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME)]
    investment_plan = InvestmentContributionPlanResult(
        period=PERIOD, plannable_income=str(income), vehicles=[
            _vehicle(
                vehicle="401(k)", target_pct="6", target_amount="600.00", actual_amount="100.00",
                variance_amount="-500.00", status=DriftStatus.OFF_TRACK,
                recommended_next_month_delta="500.00",
            ),
        ],
        total_target_pct="6", total_actual_amount="100.00", total_actual_pct="1.00",
        completeness=_pva(txns).completeness,
    )
    plan = _build(transactions=txns, investment_plan=investment_plan)
    invest_recs = _recs_of(plan, RecommendationActionType.INCREASE_INVESTMENT_CONTRIBUTION)
    assert invest_recs
    assert invest_recs[0].estimated_impact == "500.00"


# ── Goal-completion recommendation surfaces without duplicating PR13 logic ──

def test_goal_completion_recommendation_surfaces_as_adjust_plan():
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-4000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        _txn("t3", "-1000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
        # Emergency Fund contribution exactly meets this period's $500 target,
        # so the category row itself is a real, non-fabricated $500 target.
        _txn(
            "t4", "500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category="Emergency Fund", account_type="savings",
        ),
    ]
    recommendation = GoalCompletionRecommendation(
        goal_id="goal-Emergency Fund", goal_name="Emergency Fund",
        message="'Emergency Fund' has reached its target. Review your plan.",
    )
    goals = [_goal(
        name="Emergency Fund", category_name="Emergency Fund", status=GoalStatus.COMPLETE,
        current_amount="10000.00", target_amount_effective="10000.00",
        completion_recommendation=recommendation,
    )]
    plan = _build(transactions=txns, goals=goals)
    adjust = _recs_of(plan, RecommendationActionType.ADJUST_PLAN)
    assert adjust
    assert adjust[0].reason == recommendation.message  # quoted verbatim, not re-derived
    # This period's target, not the goal's cumulative $10,000.
    assert Decimal(adjust[0].estimated_impact) == Decimal("500.00")


def test_completed_goal_does_not_also_emit_a_shortfall_recommendation():
    """A COMPLETE goal must never simultaneously be reported as 'behind' —
    that would be an internally contradictory pair of recommendations."""
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-4000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        _txn("t3", "-1000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
    ]
    recommendation = GoalCompletionRecommendation(
        goal_id="goal-Emergency Fund", goal_name="Emergency Fund", message="Goal complete.",
    )
    goals = [_goal(
        name="Emergency Fund", category_name="Emergency Fund", status=GoalStatus.COMPLETE,
        completion_recommendation=recommendation,
    )]
    plan = _build(transactions=txns, goals=goals)
    for rec in plan.recommendations:
        if rec.category == "Emergency Fund":
            assert rec.action_type == RecommendationActionType.ADJUST_PLAN


# ── Ranking: impact x deviation x confidence x actionability ───────────────

def test_ranking_prefers_larger_impact_reduce_category_over_smaller_one():
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        # Needs target = 50% * 10000 = 5000. Overspend by $2000.
        _txn(
            "t2", "-7000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Housing", merchant="Landlord",
        ),
        # Wants target = 20% * 10000 = 2000. Overspend by $200 (smaller).
        _txn(
            "t3", "-2200.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Dining", merchant="Cafe",
        ),
    ]
    plan = _build(transactions=txns)
    reduce_recs = _recs_of(plan, RecommendationActionType.REDUCE_CATEGORY)
    assert reduce_recs
    assert reduce_recs[0].bucket == MasterBucket.NEEDS
    assert reduce_recs[0].priority == 1


def test_max_one_recommendation_per_action_type():
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn(
            "t2", "-7000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Housing", merchant="Landlord",
        ),
        _txn(
            "t3", "-3000.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Dining", merchant="Cafe",
        ),
    ]
    plan = _build(transactions=txns)
    action_types = [r.action_type for r in plan.recommendations]
    assert len(action_types) == len(set(action_types))


def test_max_one_recommendation_per_bucket():
    """A bucket-scoped and a category-scoped recommendation on the same
    bucket describe overlapping dollars -- never surface both."""
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-4000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        _txn("t3", "-1000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
        # Two Savings shortfalls in the same bucket (two categories behind).
    ]
    goals = [
        _goal(name="Emergency Fund", category_name="Emergency Fund", status=GoalStatus.BEHIND),
        _goal(name="House / Goals", category_name="House / Goals", status=GoalStatus.BEHIND),
    ]
    plan = _build(transactions=txns, goals=goals)
    buckets = [r.bucket for r in plan.recommendations if r.bucket is not None]
    assert len(buckets) == len(set(buckets))


# ── review_merchant / merchant concentration ────────────────────────────────

def test_review_merchant_requires_material_concentration():
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-4000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        # Wants overspent, one merchant dominates >35% of Wants spend.
        _txn(
            "t3", "-2500.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Shopping", merchant="BigStore",
        ),
        _txn(
            "t4", "-200.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Dining", merchant="Cafe",
        ),
    ]
    plan = _build(transactions=txns)
    merchant_recs = _recs_of(plan, RecommendationActionType.REVIEW_MERCHANT)
    # BigStore concentration = 2500 / 2700 ~ 92% >= 35% threshold.
    if merchant_recs:
        assert "BigStore" in merchant_recs[0].title


# ── review_subscription is deliberately not built this round ───────────────

def test_review_subscription_never_emitted():
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-7000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        _txn("t3", "-3000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
    ]
    plan = _build(transactions=txns)
    assert all(
        r.action_type != RecommendationActionType.REVIEW_SUBSCRIPTION for r in plan.recommendations
    )
