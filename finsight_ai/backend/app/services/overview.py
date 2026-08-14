"""
Overview page service — wires the pure domain logic in
app.domain.overview_insights to the database, on top of the already-built
app.services.plan_vs_actual service layer (PR 04). No new financial
computation lives here or in app.domain.overview_insights: every dollar
figure traces back to app.domain.plan_vs_actual's Decimal engine.

Two entry points, both period-aware (PR 05 unified start_date/end_date or
year/month contract, resolved by the caller in app.api.overview):

  - get_overview_insights: financial status header + Coral Insights (<=3) +
    Next Month Plan preview (<=3) for one period.
  - get_monthly_flow_summary: one row per calendar month in the period, for
    the Income vs Spent vs Saved/Invested grouped bar chart.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.overview_insights import (
    MonthlyFlowSummary,
    OverviewInsightsResult,
    build_overview_insights,
    summarize_monthly_flow,
)
from app.domain.plan_vs_actual import Period
from app.domain.transaction_classification import MasterBucket
from app.services import plan_vs_actual as plan_vs_actual_service


async def get_overview_insights(
    session: AsyncSession, period: Period, *, account_id: str | None = None,
) -> OverviewInsightsResult:
    """Financial status header + Coral Insights + Next Month Plan for one
    period. Category-level candidates are fetched only for Savings and
    Investments — the only buckets with plan-defined suballocation targets
    (see app.domain.plan_vs_actual._category_target_percentage); Needs/Wants
    category rows would only ever resolve to DriftStatus.UNKNOWN and are
    intentionally not fetched."""
    result = await plan_vs_actual_service.get_plan_vs_actual(session, period, account_id=account_id)
    savings_categories = await plan_vs_actual_service.get_bucket_breakdown(
        session, period, MasterBucket.SAVINGS, account_id=account_id,
    )
    investment_categories = await plan_vs_actual_service.get_bucket_breakdown(
        session, period, MasterBucket.INVESTMENTS, account_id=account_id,
    )
    return build_overview_insights(result, savings_categories + investment_categories)


async def get_monthly_flow_summary(
    session: AsyncSession, period: Period, *, account_id: str | None = None,
) -> list[MonthlyFlowSummary]:
    """One row per calendar month overlapping `period` (a single-month
    period yields a single-element list) — see
    Period.split_by_calendar_month. Each row independently re-resolves the
    plan version in effect for that specific calendar month (never "just the
    latest"), matching app.services.plan_vs_actual's existing per-period
    plan resolution.

    KNOWN GRANULARITY EFFECT: the engine's canonical-contribution-leg rule
    (app.domain.plan_vs_actual, "coverage-aware hybrid") evaluates
    savings/investment account coverage per requested period. Because each
    row here is computed over one calendar month, a month with no ingested
    savings/investment statement counts the checking-side origin leg, while
    that same month inside a longer whole-period Plan vs Actual request may
    have that leg excluded (another month in the range supplied coverage).
    Neither view ever double counts a transfer — each counts exactly one leg
    — but the per-month Saved/Invested bars can therefore sum to slightly
    more than the whole-period Plan vs Actual Savings + Investments actuals
    when statement coverage is intermittent. Removing that seam needs a
    period-level coverage override inside the PR 04 engine and is
    deliberately out of PR 06's scope."""
    sub_periods = period.split_by_calendar_month()
    summaries: list[MonthlyFlowSummary] = []
    for sub_period in sub_periods:
        result = await plan_vs_actual_service.get_plan_vs_actual(
            session, sub_period, account_id=account_id
        )
        summaries.append(summarize_monthly_flow(result))
    return summaries
