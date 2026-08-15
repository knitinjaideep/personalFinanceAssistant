"""Monthly Close service (PR 15)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.monthly_close import MonthlyCloseResult, build_monthly_close
from app.domain.plan_vs_actual import Period
from app.services import next_month_planner as next_month_planner_service
from app.services import overview as overview_service
from app.services import plan_vs_actual as plan_vs_actual_service
from app.services import savings_goals as savings_goals_service

_MERCHANT_TOP_N = 3


async def get_monthly_close(
    session: AsyncSession,
    period: Period,
    *,
    account_id: str | None = None,
    generated_on: date | None = None,
) -> MonthlyCloseResult:
    """Dynamic monthly close for a single calendar month.

    Nothing is persisted: each call reuses the canonical Plan vs Actual,
    Overview, Savings Goals, merchant-driver, and Next Month Planner
    services so historical closes use the plan version effective for that
    month.
    """
    plan_vs_actual = await plan_vs_actual_service.get_plan_vs_actual(
        session, period, account_id=account_id,
    )
    overview = await overview_service.get_overview_insights(
        session, period, account_id=account_id,
    )
    merchant_drivers = await plan_vs_actual_service.get_merchant_drivers(
        session, period, account_id=account_id, top_n=_MERCHANT_TOP_N,
    )
    savings_goals = await savings_goals_service.list_goal_progress(session, as_of=period.end)
    next_month_plan = await next_month_planner_service.get_next_month_plan(
        session, period, account_id=account_id,
    )
    return build_monthly_close(
        plan_vs_actual=plan_vs_actual,
        overview=overview,
        merchant_drivers=merchant_drivers,
        savings_goals=savings_goals,
        next_month_plan=next_month_plan,
        generated_on=generated_on or date.today(),
    )
