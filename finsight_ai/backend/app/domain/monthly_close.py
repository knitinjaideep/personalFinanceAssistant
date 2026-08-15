"""
Monthly Coral Close domain model (PR 15).

This module is intentionally a read-only composer over already-computed
financial surfaces. It does not persist a close and it does not recompute
ledger totals outside the Plan vs Actual engine. The close is a summary
experience: one completed calendar month, the core buckets, deterministic
observations, goal progress, biggest merchant drivers, and the next-month
plan.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.next_month_planner import NextMonthPlanResult, Recommendation
from app.domain.overview_insights import CoralInsight, OverviewInsightsResult
from app.domain.plan_vs_actual import BucketDrift, MerchantDriver, Period, PlanVsActualResult
from app.domain.savings_goals import SavingsGoalProgress
from app.domain.transaction_classification import MasterBucket

CloseStatus = Literal["good", "warning", "danger", "neutral"]

_BUCKET_LABEL: dict[MasterBucket, str] = {
    MasterBucket.NEEDS: "Needs",
    MasterBucket.WANTS: "Wants",
    MasterBucket.SAVINGS: "Savings",
    MasterBucket.INVESTMENTS: "Investments",
}

_BUCKET_ORDER = [
    MasterBucket.NEEDS,
    MasterBucket.WANTS,
    MasterBucket.SAVINGS,
    MasterBucket.INVESTMENTS,
]


class MonthlyCloseLineItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    bucket: MasterBucket | None = None
    target_amount: str | None
    actual_amount: str
    variance_amount: str | None
    status: CloseStatus
    note: str | None = None


class MonthlyCloseDriver(BaseModel):
    model_config = ConfigDict(frozen=True)

    merchant: str
    bucket: MasterBucket
    category: str | None
    amount: str
    transaction_count: int


class MonthlyCloseGoalProgress(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    category_name: str
    current_amount: str
    target_amount_effective: str | None
    variance_amount: str | None
    status: str
    incomplete_source: bool


class MonthlyCloseResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    period: Period
    generated_on: date
    is_completed_month: bool
    summary: str
    line_items: list[MonthlyCloseLineItem]
    went_well: list[CoralInsight] = Field(default_factory=list)
    needs_attention: list[CoralInsight] = Field(default_factory=list)
    biggest_drivers: list[MonthlyCloseDriver] = Field(default_factory=list)
    goal_progress: list[MonthlyCloseGoalProgress] = Field(default_factory=list)
    next_month_plan: list[Recommendation] = Field(default_factory=list)
    completeness_notes: list[str] = Field(default_factory=list)


def _status_from_bucket(row: BucketDrift) -> CloseStatus:
    if row.status.value == "on_track":
        return "good"
    if row.status.value == "watch":
        return "warning"
    if row.status.value == "off_track":
        return "danger"
    return "neutral"


def _money_text(value: str) -> str:
    amount = Decimal(value)
    if amount == amount.to_integral_value():
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


def _income_line(result: PlanVsActualResult) -> MonthlyCloseLineItem:
    observed = result.completeness.income_observed
    return MonthlyCloseLineItem(
        label="Income",
        bucket=None,
        target_amount=None,
        actual_amount=result.plannable_income,
        variance_amount=None,
        status="good" if observed else "neutral",
        note="Observed income" if observed else "No income observed for this month.",
    )


def _bucket_line(row: BucketDrift) -> MonthlyCloseLineItem:
    return MonthlyCloseLineItem(
        label=_BUCKET_LABEL[row.bucket],
        bucket=row.bucket,
        target_amount=row.target_amount,
        actual_amount=row.actual_amount,
        variance_amount=row.variance_amount,
        status=_status_from_bucket(row),
    )


def _summarize_status(overview: OverviewInsightsResult, period: Period) -> str:
    if overview.status.data_available:
        return overview.status.headline
    return f"Coral does not yet have enough data to close {period.label}."


def _split_insights(insights: list[CoralInsight]) -> tuple[list[CoralInsight], list[CoralInsight]]:
    went_well = [item for item in insights if item.tone == "good"][:3]
    needs_attention = [item for item in insights if item.tone in ("warning", "danger")][:3]
    return went_well, needs_attention


def _fallback_good_items(result: PlanVsActualResult) -> list[CoralInsight]:
    good_rows = [row for row in result.buckets if row.status.value == "on_track"]
    return [
        CoralInsight(
            title=f"{_BUCKET_LABEL[row.bucket]} ended on track",
            description=(
                f"{_BUCKET_LABEL[row.bucket]} closed at {_money_text(row.actual_amount)}"
                + (
                    f" against a {_money_text(row.target_amount)} target."
                    if row.target_amount is not None
                    else "."
                )
            ),
            tone="good",
            bucket=row.bucket,
            category=None,
            variance_amount=row.variance_amount,
            target_amount=row.target_amount,
            actual_amount=row.actual_amount,
        )
        for row in good_rows[:3]
    ]


def build_monthly_close(
    *,
    plan_vs_actual: PlanVsActualResult,
    overview: OverviewInsightsResult,
    merchant_drivers: list[MerchantDriver],
    savings_goals: list[SavingsGoalProgress],
    next_month_plan: NextMonthPlanResult,
    generated_on: date,
) -> MonthlyCloseResult:
    """Create a monthly close report from existing deterministic outputs."""
    lines = [_income_line(plan_vs_actual)]
    buckets = {row.bucket: row for row in plan_vs_actual.buckets}
    for bucket in _BUCKET_ORDER:
        row = buckets.get(bucket)
        if row is not None:
            lines.append(_bucket_line(row))

    went_well, needs_attention = _split_insights(overview.insights)
    if not went_well:
        went_well = _fallback_good_items(plan_vs_actual)

    drivers = [
        MonthlyCloseDriver(
            merchant=driver.merchant,
            bucket=driver.bucket,
            category=driver.category,
            amount=driver.amount,
            transaction_count=driver.transaction_count,
        )
        for driver in merchant_drivers[:3]
    ]

    goals = [
        MonthlyCloseGoalProgress(
            name=goal.name,
            category_name=goal.category_name,
            current_amount=goal.current_amount,
            target_amount_effective=goal.target_amount_effective,
            variance_amount=goal.variance_amount,
            status=goal.status.value,
            incomplete_source=not goal.data_completeness.is_complete,
        )
        for goal in savings_goals[:3]
    ]

    notes = list(plan_vs_actual.completeness.notes)
    return MonthlyCloseResult(
        period=plan_vs_actual.period,
        generated_on=generated_on,
        is_completed_month=plan_vs_actual.period.end < generated_on,
        summary=_summarize_status(overview, plan_vs_actual.period),
        line_items=lines,
        went_well=went_well,
        needs_attention=needs_attention,
        biggest_drivers=drivers,
        goal_progress=goals,
        next_month_plan=next_month_plan.recommendations,
        completeness_notes=notes,
    )
