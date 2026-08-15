"""
Coral Next Month Planner — pure, deterministic, DB-free (PR 14).

Composes deterministic "what to do next period" recommendations out of THREE
already-computed, already-honest input sources — this module never recomputes
a target/actual/variance itself and never calls an LLM for the underlying
numbers (accounting-invariants.md #10, coral-redesign SKILL "An LLM can
explain facts but must not manufacture the facts"):

  1. Current-period Plan vs Actual (`app.domain.plan_vs_actual` — `BucketDrift`
     for Needs/Wants, anchored at the BUCKET level per
     docs/coral-redesign/BLOCKED.md decision 2 (Option B, resolved
     2026-08-15): Needs/Wants have no plan-defined category targets, so a
     category can only ever be cited as a CONTRIBUTOR to its bucket's drift
     (via `compute_merchant_drivers`), never given its own fabricated target.
     `CategoryDrift` for Savings, which DOES have plan-defined suballocation
     targets (Emergency Fund / House-Goals / Child Savings).
  2. Savings goal progress (`app.services.savings_goals.list_goal_progress`)
     — goal-level status/completeness/PR13's own (non-duplicated)
     `completion_recommendation`.
  3. Investment contribution gaps
     (`app.services.investment_plan.get_investment_contribution_plan`) —
     each vehicle's already-computed, already-tested
     `recommended_next_month_delta` is read verbatim, never recomputed here.

Planning rule (work order: "Do not always try to make up every historical
shortfall next month"), carried forward exactly from
`app.domain.overview_insights.build_next_month_plan`'s own documented
precedent: every `estimated_impact` here is THIS PERIOD's own target-vs-actual
gap (from a `BucketDrift`/`CategoryDrift`/`InvestmentContributionVehicle` row
computed for the single requested period), never a goal's cumulative
since-inception shortfall. This is why savings-goal recommendations are
anchored on the per-period `CategoryDrift` row for that goal's category
(exactly the number Plan vs Actual already shows for "this period"), not on
`SavingsGoalProgress.variance_amount` (which is deliberately cumulative since
the goal's `effective_date` — see app.domain.savings_goals module docstring —
and would encourage "make up the whole historical hole in one month").

Completeness-composition policy (new orchestration logic — the one genuinely
new piece of accounting policy this module adds; every underlying NUMBER is
still owned by its source module):

  - A recommendation is never emitted when its own source reports no
    measurable number at all (e.g. Plan vs Actual with no income observed —
    every `BucketDrift.status` is `DriftStatus.UNKNOWN`, which every
    candidate builder below already excludes by construction; a Savings
    `CategoryDrift` with `target_amount is None`; a goal-completion row with
    no measurable per-period target). This is "skip the candidate", never
    "invent a number".
  - A recommendation whose source DOES have a number but that source reports
    itself as `is_complete=False` (`CompletenessMetadata.is_complete` /
    `GoalCompletenessMetadata.is_complete` / `ContributionDataCompleteness.
    is_complete`) is still emitted, but MUST surface the gap in
    `source_facts` (never silently) AND have its `confidence` term in the
    ranking formula discounted via `_completeness_multiplier` — this is the
    concrete mechanism that prevents an incomplete source's candidate from
    "silently outranking" a complete source's candidate: the discount is
    real (0.60x), not cosmetic, and lowers `rank_score` exactly like a real
    low-confidence signal would.

Ranking formula (coral-redesign SKILL "Coral Insights": impact x deviation x
confidence x actionability), generalized from
`app.domain.banking_insights._score` — cited there as the module in this
codebase that most literally implements the skill's own formula — and reused
here verbatim as the canonical ranking function across all three input
sources (rather than `overview_insights._sort_key`'s narrower, single-purpose
dollar-first tuple ordering for on-page insight cards).

Action types (work order lists 7): `reduce_category`,
`increase_savings_goal`, `maintain_contribution`,
`increase_investment_contribution`, `review_merchant` and `adjust_plan` are
built this round — each has a ready-made, already-tested input.
`review_subscription` is declared in `RecommendationActionType` for API
forward-compatibility but never emitted: no reusable multi-month
trend-detection primitive exists anywhere in the domain layer today (the
same real gap that left PR10's `unusual_spending_spike`/
`recurring_charge_increase` unbuilt), and building one bespoke to this PR
within scope would be exactly the kind of new, unaudited financial
computation this module otherwise refuses to do. See docs/NEXT_MONTH_PLANNER.md.

Maximum 3 recommendations, ever (`MAX_RECOMMENDATIONS`) — not caller
configurable, per the work order and every other insights/recommendation
surface in this redesign.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.investment_plan import (
    InvestmentContributionPlanResult,
    InvestmentContributionVehicle,
)
from app.domain.plan_vs_actual import (
    UNCATEGORIZED,
    BucketDrift,
    CategoryDrift,
    DriftStatus,
    MerchantDriver,
    Period,
    PlanVsActualResult,
    compute_status,
)
from app.domain.savings_goals import SavingsGoalProgress
from app.domain.transaction_classification import MasterBucket

_CENTS = Decimal("0.01")
_MATERIALITY_DOLLARS = Decimal("25.00")  # mirrors app.domain.banking_insights._MATERIALITY
# mirrors app.domain.banking_insights._MERCHANT_CONCENTRATION_RATIO
_MERCHANT_CONCENTRATION_RATIO = Decimal("0.35")
_CONSUMPTION_BUCKETS = frozenset({MasterBucket.NEEDS, MasterBucket.WANTS})
MAX_RECOMMENDATIONS = 3

_BUCKET_LABEL: dict[MasterBucket, str] = {
    MasterBucket.NEEDS: "Needs",
    MasterBucket.WANTS: "Wants",
    MasterBucket.SAVINGS: "Savings",
    MasterBucket.INVESTMENTS: "Investments",
}


class RecommendationActionType(StrEnum):
    REDUCE_CATEGORY = "reduce_category"
    INCREASE_SAVINGS_GOAL = "increase_savings_goal"
    MAINTAIN_CONTRIBUTION = "maintain_contribution"
    INCREASE_INVESTMENT_CONTRIBUTION = "increase_investment_contribution"
    REVIEW_MERCHANT = "review_merchant"
    # Deferred this round — no reusable multi-month trend primitive exists
    # yet. Declared for forward-compatibility; never emitted by this module.
    REVIEW_SUBSCRIPTION = "review_subscription"
    ADJUST_PLAN = "adjust_plan"


class RecommendationSourceFact(BaseModel):
    """One auditable fact behind a recommendation — cites the exact number
    and which input source it came from, so a recommendation can never be
    read as an unsupported claim."""

    label: str
    value: str


class Recommendation(BaseModel):
    """One deterministic Next Month Planner recommendation.

    `estimated_impact` is always this period's own $ gap (unsigned) — never a
    cumulative historical shortfall (see module docstring). `priority` is
    1-based, assigned after ranking (1 = highest). `bucket`/`category` are
    additive (not in the work order's minimal field list) so Banking/
    Investments can filter the shared ranked list client-side without a
    second backend concept. `incomplete_source` is True when the underlying
    data this recommendation is based on is itself incomplete — the caveat
    is always ALSO spelled out in `source_facts`, never only this flag.
    """

    model_config = ConfigDict(frozen=True)

    title: str
    reason: str
    estimated_impact: str
    priority: int
    action_type: RecommendationActionType
    source_facts: list[RecommendationSourceFact]
    bucket: MasterBucket | None = None
    category: str | None = None
    incomplete_source: bool = False


class NextMonthPlanResult(BaseModel):
    period: Period
    recommendations: list[Recommendation] = Field(default_factory=list)


class _Candidate(BaseModel):
    """Internal ranking wrapper — never serialized to a caller."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    recommendation: Recommendation
    rank_score: Decimal


def _dec(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS)


def _money(value: Decimal) -> str:
    value = value.copy_abs().quantize(_CENTS)
    if value == value.to_integral_value():
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def _confidence_for_count(count: int) -> Decimal:
    """Mirrors app.domain.banking_insights._confidence_for_transactions —
    reused as the canonical transaction-count-based confidence signal."""
    if count >= 6:
        return Decimal("0.95")
    if count >= 3:
        return Decimal("0.85")
    if count >= 1:
        return Decimal("0.70")
    return Decimal("0.50")


def _completeness_multiplier(is_complete: bool) -> Decimal:
    """The completeness-composition policy's concrete mechanism (see module
    docstring): an incomplete source's confidence is genuinely discounted,
    not cosmetically flagged, so it cannot silently outrank a complete
    source's candidate on fabricated confidence."""
    return Decimal("1.00") if is_complete else Decimal("0.60")


def _score(
    *,
    impact: Decimal,
    confidence: Decimal,
    actionability: Decimal,
    deviation: Decimal = Decimal("1"),
) -> Decimal:
    """Canonical ranking formula (coral-redesign SKILL: impact x deviation x
    confidence x actionability) — generalized from
    app.domain.banking_insights._score, reused verbatim across every input
    source in this module."""
    return (impact.copy_abs() * confidence * actionability * deviation).quantize(_CENTS)


def _completeness_fact(notes: list[str]) -> RecommendationSourceFact:
    return RecommendationSourceFact(
        label="Data completeness caveat",
        value="; ".join(notes) if notes else "This input's underlying data is incomplete.",
    )


def _top_merchant_for_bucket(
    merchant_drivers: list[MerchantDriver], bucket: MasterBucket,
) -> MerchantDriver | None:
    """First (i.e. largest, since `compute_merchant_drivers` output is
    already sorted by descending absolute amount) merchant in this bucket."""
    return next((m for m in merchant_drivers if m.bucket == bucket), None)


# ── reduce_category (Needs/Wants, bucket-anchored per BLOCKED decision 2) ──

def _reduce_category_candidates(
    plan_vs_actual: PlanVsActualResult, merchant_drivers: list[MerchantDriver],
) -> list[_Candidate]:
    is_complete = plan_vs_actual.completeness.is_complete
    candidates: list[_Candidate] = []
    for bucket_row in plan_vs_actual.buckets:
        if bucket_row.bucket not in _CONSUMPTION_BUCKETS:
            continue
        if bucket_row.status not in (DriftStatus.WATCH, DriftStatus.OFF_TRACK):
            continue
        variance = _dec(bucket_row.variance_amount)
        if variance is None or variance < _MATERIALITY_DOLLARS:
            continue

        label = _BUCKET_LABEL[bucket_row.bucket]
        top_merchant = _top_merchant_for_bucket(merchant_drivers, bucket_row.bucket)
        target_txt = _money(_dec(bucket_row.target_amount)) if bucket_row.target_amount else "plan"
        title = f"Reduce {label} by {_money(variance)} next period"
        reason = f"{label} is {_money(variance)} over its {target_txt} target this period."
        if top_merchant is not None:
            reason += (
                f" {top_merchant.merchant} is the largest contributor at "
                f"{_money(Decimal(top_merchant.amount))}."
            )

        facts = [
            RecommendationSourceFact(label="Bucket", value=label),
            RecommendationSourceFact(
                label="Target amount (this period)",
                value=bucket_row.target_amount or "not available",
            ),
            RecommendationSourceFact(
                label="Actual amount (this period)", value=bucket_row.actual_amount,
            ),
            RecommendationSourceFact(
                label="Variance vs target", value=bucket_row.variance_amount or "",
            ),
            RecommendationSourceFact(
                label="Transactions this period", value=str(bucket_row.transaction_count),
            ),
        ]
        if top_merchant is not None:
            facts.append(RecommendationSourceFact(
                label="Largest contributor",
                value=f"{top_merchant.merchant}: {_money(Decimal(top_merchant.amount))}",
            ))
        if not is_complete:
            facts.append(_completeness_fact(plan_vs_actual.completeness.notes))

        base_confidence = _confidence_for_count(bucket_row.transaction_count)
        confidence = base_confidence * _completeness_multiplier(is_complete)
        deviation = abs(_dec(bucket_row.variance_percentage_points) or Decimal("1"))
        rec = Recommendation(
            title=title, reason=reason, estimated_impact=str(_round_money(variance)),
            priority=0, action_type=RecommendationActionType.REDUCE_CATEGORY,
            source_facts=facts, bucket=bucket_row.bucket, category=None,
            incomplete_source=not is_complete,
        )
        candidates.append(_Candidate(
            recommendation=rec,
            rank_score=_score(
                impact=variance, confidence=confidence, actionability=Decimal("1.00"),
                deviation=deviation,
            ),
        ))
    return candidates


# ── review_merchant (concentration pattern from banking_insights) ──────────

def _review_merchant_candidates(
    plan_vs_actual: PlanVsActualResult, merchant_drivers: list[MerchantDriver],
) -> list[_Candidate]:
    is_complete = plan_vs_actual.completeness.is_complete
    buckets_by_name: dict[MasterBucket, BucketDrift] = {
        b.bucket: b for b in plan_vs_actual.buckets
    }
    candidates: list[_Candidate] = []
    for merchant in merchant_drivers:
        if merchant.bucket not in _CONSUMPTION_BUCKETS:
            continue
        amount = Decimal(merchant.amount)
        if amount < _MATERIALITY_DOLLARS:
            continue
        bucket_row = buckets_by_name.get(merchant.bucket)
        adverse_statuses = (DriftStatus.WATCH, DriftStatus.OFF_TRACK)
        if bucket_row is None or bucket_row.status not in adverse_statuses:
            continue
        bucket_actual = _dec(bucket_row.actual_amount)
        if not bucket_actual or bucket_actual <= 0:
            continue
        concentration = amount / bucket_actual
        if concentration < _MERCHANT_CONCENTRATION_RATIO:
            continue

        label = _BUCKET_LABEL[merchant.bucket]
        pct_txt = f"{(concentration * 100).quantize(Decimal('0.1'))}%"
        title = f"Review {merchant.merchant} in {label}"
        reason = (
            f"{merchant.merchant} makes up {pct_txt} of {label} spending "
            f"({_money(amount)} of {_money(bucket_actual)}) this period."
        )
        facts = [
            RecommendationSourceFact(label="Merchant", value=merchant.merchant),
            RecommendationSourceFact(
                label="Merchant spend this period", value=str(amount.quantize(_CENTS)),
            ),
            RecommendationSourceFact(
                label="Bucket actual this period", value=bucket_row.actual_amount,
            ),
            RecommendationSourceFact(label="Share of bucket spend", value=pct_txt),
            RecommendationSourceFact(
                label="Transactions", value=str(merchant.transaction_count),
            ),
        ]
        if not is_complete:
            facts.append(_completeness_fact(plan_vs_actual.completeness.notes))

        base_confidence = _confidence_for_count(merchant.transaction_count)
        confidence = base_confidence * _completeness_multiplier(is_complete)
        rec = Recommendation(
            title=title, reason=reason, estimated_impact=str(amount.quantize(_CENTS)),
            priority=0, action_type=RecommendationActionType.REVIEW_MERCHANT,
            source_facts=facts, bucket=merchant.bucket, category=merchant.category,
            incomplete_source=not is_complete,
        )
        candidates.append(_Candidate(
            recommendation=rec,
            rank_score=_score(
                impact=amount, confidence=confidence, actionability=Decimal("0.75"),
                deviation=concentration,
            ),
        ))
    return candidates


# ── increase_savings_goal / adjust_plan ─────────────────────────────────────

def _increase_savings_goal_candidate(
    row: CategoryDrift, goal: SavingsGoalProgress | None, pva: PlanVsActualResult,
) -> _Candidate:
    variance = _dec(row.variance_amount)
    assert variance is not None and variance < 0  # guaranteed by caller
    adverse = -variance
    target_txt = _money(_dec(row.target_amount)) if row.target_amount else "plan"
    title = f"Add {_money(adverse)} to {row.category} next period"
    reason = f"{row.category} is {_money(adverse)} behind its {target_txt} target this period."

    facts = [
        RecommendationSourceFact(label="Category", value=row.category),
        RecommendationSourceFact(
            label="Target this period", value=row.target_amount or "not available",
        ),
        RecommendationSourceFact(label="Actual this period", value=row.actual_amount),
        RecommendationSourceFact(
            label="Shortfall this period", value=str(adverse.quantize(_CENTS)),
        ),
    ]
    goal_complete = True
    if goal is not None:
        facts.append(RecommendationSourceFact(label="Goal", value=goal.name))
        facts.append(RecommendationSourceFact(label="Goal status", value=goal.status.value))
        goal_complete = goal.data_completeness.is_complete
        if not goal_complete:
            facts.append(_completeness_fact(goal.data_completeness.notes))
    elif not pva.completeness.is_complete:
        goal_complete = False
        facts.append(_completeness_fact(pva.completeness.notes))

    base_confidence = _confidence_for_count(row.transaction_count)
    confidence = base_confidence * _completeness_multiplier(goal_complete)
    rec = Recommendation(
        title=title, reason=reason, estimated_impact=str(adverse.quantize(_CENTS)),
        priority=0, action_type=RecommendationActionType.INCREASE_SAVINGS_GOAL,
        source_facts=facts, bucket=MasterBucket.SAVINGS, category=row.category,
        incomplete_source=not goal_complete,
    )
    deviation = abs(_dec(row.variance_percentage_points) or Decimal("1"))
    return _Candidate(
        recommendation=rec,
        rank_score=_score(
            impact=adverse, confidence=confidence, actionability=Decimal("0.90"),
            deviation=deviation,
        ),
    )


def _increase_savings_goal_bucket_fallback(
    bucket_row: BucketDrift, pva: PlanVsActualResult,
) -> _Candidate | None:
    variance = _dec(bucket_row.variance_amount)
    if variance is None or variance >= 0:
        return None
    adverse = -variance
    if adverse < _MATERIALITY_DOLLARS:
        return None
    target_txt = _money(_dec(bucket_row.target_amount)) if bucket_row.target_amount else "plan"
    title = f"Add {_money(adverse)} to Savings next period"
    reason = (
        f"Savings is {_money(adverse)} behind its {target_txt} target this period; "
        "the shortfall could not be attributed to one specific goal category."
    )
    is_complete = pva.completeness.is_complete
    facts = [
        RecommendationSourceFact(label="Bucket", value="Savings"),
        RecommendationSourceFact(
            label="Target this period", value=bucket_row.target_amount or "not available",
        ),
        RecommendationSourceFact(label="Actual this period", value=bucket_row.actual_amount),
        RecommendationSourceFact(
            label="Shortfall this period", value=str(adverse.quantize(_CENTS)),
        ),
    ]
    if not is_complete:
        facts.append(_completeness_fact(pva.completeness.notes))
    base_confidence = _confidence_for_count(bucket_row.transaction_count)
    confidence = base_confidence * _completeness_multiplier(is_complete)
    deviation = abs(_dec(bucket_row.variance_percentage_points) or Decimal("1"))
    rec = Recommendation(
        title=title, reason=reason, estimated_impact=str(adverse.quantize(_CENTS)),
        priority=0, action_type=RecommendationActionType.INCREASE_SAVINGS_GOAL,
        source_facts=facts, bucket=MasterBucket.SAVINGS, category=None,
        incomplete_source=not is_complete,
    )
    return _Candidate(
        recommendation=rec,
        rank_score=_score(
            impact=adverse, confidence=confidence, actionability=Decimal("0.90"),
            deviation=deviation,
        ),
    )


def _adjust_plan_candidate(row: CategoryDrift, goal: SavingsGoalProgress) -> _Candidate | None:
    """Surfaces PR13's own `GoalCompletionRecommendation` — never duplicates
    its logic (that stays exactly where PR13 built it). `estimated_impact`
    is deliberately THIS PERIOD's own target $ for the goal's category (from
    the already-computed `CategoryDrift` row), never the goal's cumulative
    `current_amount`/`target_amount_effective` (which spans since the goal's
    `effective_date` and would misrepresent scale — see module docstring).
    Returns None (skip, never fabricate) when this period has no measurable
    target for that category at all."""
    if row.target_amount is None:
        return None
    target_amount = _dec(row.target_amount)
    assert target_amount is not None
    rec_msg = goal.completion_recommendation.message  # type: ignore[union-attr]
    title = f"Reallocate '{goal.name}' contributions"
    is_complete = goal.data_completeness.is_complete
    facts = [
        RecommendationSourceFact(label="Goal", value=goal.name),
        RecommendationSourceFact(label="Goal status", value="complete"),
        RecommendationSourceFact(
            label="Current amount (cumulative)", value=goal.current_amount,
        ),
        RecommendationSourceFact(
            label="Target amount (effective)",
            value=goal.target_amount_effective or "not available",
        ),
        RecommendationSourceFact(
            label="This period's target for this category", value=row.target_amount,
        ),
        RecommendationSourceFact(label="Coral recommendation (PR13)", value=rec_msg),
    ]
    if not is_complete:
        facts.append(_completeness_fact(goal.data_completeness.notes))
    confidence = Decimal("0.90") * _completeness_multiplier(is_complete)
    rec = Recommendation(
        title=title, reason=rec_msg, estimated_impact=str(target_amount.quantize(_CENTS)),
        priority=0, action_type=RecommendationActionType.ADJUST_PLAN,
        source_facts=facts, bucket=MasterBucket.SAVINGS, category=row.category,
        incomplete_source=not is_complete,
    )
    return _Candidate(
        recommendation=rec,
        rank_score=_score(
            impact=target_amount, confidence=confidence, actionability=Decimal("0.60"),
        ),
    )


def _synthetic_savings_category_row(
    goal: SavingsGoalProgress, plannable_income: Decimal,
) -> CategoryDrift | None:
    """A CategoryDrift-shaped row for a savings goal's category when
    `compute_category_breakdown` produced no row at all for it.

    `compute_category_breakdown` only ever emits a row for a category that
    has at least one transaction this period (see
    `aggregate_category_actuals`) — a goal that received ZERO contributions
    this period (arguably the most common "behind" case) would otherwise be
    entirely invisible to this planner. This reuses the exact
    `target = plannable_income * target_percentage / 100` formula already
    used throughout app.domain.plan_vs_actual — not a new calculation, just
    applied to a percentage that is already goal-authoritative
    (`SavingsGoalProgress.target_percentage_of_income`, the same value
    app.domain.savings_goals itself uses). Returns None (never a fabricated
    target) when the goal has no measurable percentage target or no income
    was observed this period.
    """
    pct = _dec(goal.target_percentage_of_income)
    if pct is None or pct <= 0 or plannable_income <= 0:
        return None
    target_amount = (plannable_income * pct / Decimal("100")).quantize(_CENTS)
    variance = -target_amount
    variance_pp = -pct  # actual% (0, no observed contribution) - target%
    status = compute_status(MasterBucket.SAVINGS, variance_pp)
    return CategoryDrift(
        bucket=MasterBucket.SAVINGS, category=goal.category_name,
        target_percentage=str(pct), actual_percentage="0.00",
        target_amount=str(target_amount), actual_amount="0.00",
        variance_amount=str(variance), variance_percentage_points=str(variance_pp),
        status=status, transaction_count=0,
    )


def _savings_goal_candidates(
    plan_vs_actual: PlanVsActualResult,
    savings_category_rows: list[CategoryDrift],
    savings_goals: list[SavingsGoalProgress],
) -> list[_Candidate]:
    rows_by_category = {
        r.category: r for r in savings_category_rows if r.bucket == MasterBucket.SAVINGS
    }
    plannable_income = _dec(plan_vs_actual.plannable_income) or Decimal("0")
    candidates: list[_Candidate] = []
    handled_categories: set[str] = set()
    any_category_handled = False

    def _handle(row: CategoryDrift, goal: SavingsGoalProgress | None) -> bool:
        nonlocal candidates
        if goal is not None and goal.completion_recommendation is not None:
            candidate = _adjust_plan_candidate(row, goal)
            if candidate is not None:
                candidates.append(candidate)
                return True
            return False
        if row.status not in (DriftStatus.WATCH, DriftStatus.OFF_TRACK):
            return False
        variance = _dec(row.variance_amount)
        if variance is None or variance >= 0:
            return False
        if -variance < _MATERIALITY_DOLLARS:
            return False
        candidates.append(_increase_savings_goal_candidate(row, goal, plan_vs_actual))
        return True

    for goal in savings_goals:
        category = goal.category_name
        if category == UNCATEGORIZED or category in handled_categories:
            continue
        handled_categories.add(category)
        row = rows_by_category.get(category)
        if row is None:
            row = _synthetic_savings_category_row(goal, plannable_income)
        if row is None:
            continue  # no measurable target this period -> skip, never fabricate
        if _handle(row, goal):
            any_category_handled = True

    for row in savings_category_rows:
        if row.bucket != MasterBucket.SAVINGS or row.category == UNCATEGORIZED:
            continue
        if row.category in handled_categories:
            continue
        handled_categories.add(row.category)
        if _handle(row, None):
            any_category_handled = True

    if not any_category_handled:
        savings_bucket = next(
            (b for b in plan_vs_actual.buckets if b.bucket == MasterBucket.SAVINGS), None,
        )
        adverse_statuses = (DriftStatus.WATCH, DriftStatus.OFF_TRACK)
        if savings_bucket is not None and savings_bucket.status in adverse_statuses:
            fallback = _increase_savings_goal_bucket_fallback(savings_bucket, plan_vs_actual)
            if fallback is not None:
                candidates.append(fallback)

    return candidates


# ── increase_investment_contribution / maintain_contribution ───────────────

def _investment_candidates(investment_plan: InvestmentContributionPlanResult) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for vehicle in investment_plan.vehicles:
        candidate = _investment_gap_candidate(vehicle) or _investment_maintain_candidate(vehicle)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _investment_gap_candidate(vehicle: InvestmentContributionVehicle) -> _Candidate | None:
    if vehicle.status not in (DriftStatus.WATCH, DriftStatus.OFF_TRACK):
        return None
    if not vehicle.recommended_next_month_delta:
        return None
    delta = Decimal(vehicle.recommended_next_month_delta)
    if delta <= 0:
        return None
    is_complete = vehicle.data_completeness.is_complete
    target_txt = _money(_dec(vehicle.target_amount)) if vehicle.target_amount else "plan"
    title = f"Increase {vehicle.vehicle} contribution by {_money(delta)} next period"
    reason = f"{vehicle.vehicle} is {_money(delta)} short of its {target_txt} target this period."
    facts = [
        RecommendationSourceFact(label="Vehicle", value=vehicle.vehicle),
        RecommendationSourceFact(
            label="Target this period", value=vehicle.target_amount or "not available",
        ),
        RecommendationSourceFact(label="Actual this period", value=vehicle.actual_amount),
        RecommendationSourceFact(
            label="Recommended next-month delta (PR11, verbatim)",
            value=vehicle.recommended_next_month_delta,
        ),
    ]
    if not is_complete:
        facts.append(_completeness_fact(vehicle.data_completeness.notes))
    base_confidence = _confidence_for_count(vehicle.transaction_count)
    confidence = base_confidence * _completeness_multiplier(is_complete)
    deviation = abs(_dec(vehicle.variance_pct_points) or Decimal("1"))
    rec = Recommendation(
        title=title, reason=reason, estimated_impact=str(delta.quantize(_CENTS)),
        priority=0, action_type=RecommendationActionType.INCREASE_INVESTMENT_CONTRIBUTION,
        source_facts=facts, bucket=MasterBucket.INVESTMENTS, category=vehicle.vehicle,
        incomplete_source=not is_complete,
    )
    return _Candidate(
        recommendation=rec,
        rank_score=_score(
            impact=delta, confidence=confidence, actionability=Decimal("1.00"),
            deviation=deviation,
        ),
    )


def _investment_maintain_candidate(vehicle: InvestmentContributionVehicle) -> _Candidate | None:
    if vehicle.status != DriftStatus.ON_TRACK:
        return None
    amount = _dec(vehicle.target_amount) or _dec(vehicle.actual_amount)
    if amount is None or amount < _MATERIALITY_DOLLARS:
        return None
    is_complete = vehicle.data_completeness.is_complete
    title = f"Keep contributing {_money(amount)} to {vehicle.vehicle}"
    reason = f"{vehicle.vehicle} is on track this period — stay consistent next period."
    facts = [
        RecommendationSourceFact(label="Vehicle", value=vehicle.vehicle),
        RecommendationSourceFact(
            label="Target this period", value=vehicle.target_amount or "not available",
        ),
        RecommendationSourceFact(label="Actual this period", value=vehicle.actual_amount),
        RecommendationSourceFact(label="Status", value="on_track"),
    ]
    if not is_complete:
        facts.append(_completeness_fact(vehicle.data_completeness.notes))
    base_confidence = _confidence_for_count(vehicle.transaction_count)
    confidence = base_confidence * _completeness_multiplier(is_complete)
    rec = Recommendation(
        title=title, reason=reason, estimated_impact=str(amount.quantize(_CENTS)),
        priority=0, action_type=RecommendationActionType.MAINTAIN_CONTRIBUTION,
        source_facts=facts, bucket=MasterBucket.INVESTMENTS, category=vehicle.vehicle,
        incomplete_source=not is_complete,
    )
    return _Candidate(
        recommendation=rec,
        rank_score=_score(impact=amount, confidence=confidence, actionability=Decimal("0.40")),
    )


# ── Top-level composer ──────────────────────────────────────────────────────

def build_next_month_plan(
    *,
    plan_vs_actual: PlanVsActualResult,
    savings_category_rows: list[CategoryDrift],
    merchant_drivers: list[MerchantDriver],
    savings_goals: list[SavingsGoalProgress],
    investment_plan: InvestmentContributionPlanResult,
) -> NextMonthPlanResult:
    """Build the ranked, capped-at-3 Next Month Plan.

    Selection, after ranking by `rank_score` descending: at most ONE
    recommendation per `action_type` (never repeat the same kind of advice
    across all 3 slots) AND at most one recommendation per `bucket` (a
    bucket-scoped recommendation and a category-scoped recommendation on the
    same bucket describe overlapping/the-same dollars — same anti-
    double-counting discipline as
    `app.domain.overview_insights._SelectionGuard`). Recommendations with no
    bucket (none currently) are exempt from the bucket guard.
    """
    candidates: list[_Candidate] = []
    candidates.extend(_reduce_category_candidates(plan_vs_actual, merchant_drivers))
    candidates.extend(_review_merchant_candidates(plan_vs_actual, merchant_drivers))
    candidates.extend(
        _savings_goal_candidates(plan_vs_actual, savings_category_rows, savings_goals)
    )
    candidates.extend(_investment_candidates(investment_plan))

    def _sort_key(c: _Candidate) -> tuple:
        return (-c.rank_score, c.recommendation.action_type.value, c.recommendation.title)

    candidates.sort(key=_sort_key)

    picked: list[_Candidate] = []
    seen_types: set[RecommendationActionType] = set()
    seen_buckets: set[MasterBucket] = set()
    for c in candidates:
        rec = c.recommendation
        if rec.action_type in seen_types:
            continue
        if rec.bucket is not None and rec.bucket in seen_buckets:
            continue
        picked.append(c)
        seen_types.add(rec.action_type)
        if rec.bucket is not None:
            seen_buckets.add(rec.bucket)
        if len(picked) >= MAX_RECOMMENDATIONS:
            break

    recommendations = [
        c.recommendation.model_copy(update={"priority": i}) for i, c in enumerate(picked, start=1)
    ]
    return NextMonthPlanResult(period=plan_vs_actual.period, recommendations=recommendations)
