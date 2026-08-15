"""
Next Month Planner service (PR 14) — wires the pure domain engine in
app.domain.next_month_planner to the database, on top of the already-built
Plan vs Actual (PR 04), Savings Goals (PR 13), and Investment Contribution
Model (PR 11) service layers. No new financial computation lives here or in
app.domain.next_month_planner: every dollar figure traces back to one of
those three already-tested engines.

No FastAPI imports here — usable from any caller, exactly like the other
service modules in this package.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.next_month_planner import NextMonthPlanResult, build_next_month_plan
from app.domain.plan_vs_actual import Period
from app.domain.transaction_classification import MasterBucket
from app.services import investment_plan as investment_plan_service
from app.services import plan_vs_actual as plan_vs_actual_service
from app.services import savings_goals as savings_goals_service

# Merchant drivers are fetched across ALL buckets (not bucket-filtered) so a
# NEEDS/WANTS candidate can always cite its true largest contributor, then
# filtered by the domain layer per bucket. 20 is generous headroom beyond
# plan_vs_actual's own default of 10 — cheap (same in-memory transaction
# list, no extra query) and avoids missing a real top contributor merely
# because other buckets' rows outrank it in a combined top-10.
_MERCHANT_TOP_N = 20


async def get_next_month_plan(
    session: AsyncSession, period: Period, *, account_id: str | None = None,
) -> NextMonthPlanResult:
    """Full ranked, capped-at-3 Next Month Plan for one period.

    `account_id` narrows every underlying input exactly the way it narrows
    Plan vs Actual/Investment Contribution Plan (see
    app.services.plan_vs_actual.get_plan_vs_actual's own docstring) — scoping
    to an account where no payroll lands yields no income-observed
    candidates. Savings goal progress is NOT account-scoped (goals are
    household-level by design — see app.domain.savings_goals), so
    `account_id` only narrows the Plan vs Actual / merchant / investment
    inputs.
    """
    plan_vs_actual = await plan_vs_actual_service.get_plan_vs_actual(
        session, period, account_id=account_id,
    )
    savings_category_rows = await plan_vs_actual_service.get_bucket_breakdown(
        session, period, MasterBucket.SAVINGS, account_id=account_id,
    )
    merchant_drivers = await plan_vs_actual_service.get_merchant_drivers(
        session, period, account_id=account_id, top_n=_MERCHANT_TOP_N,
    )
    savings_goals = await savings_goals_service.list_goal_progress(session, as_of=period.end)
    investment_plan = await investment_plan_service.get_investment_contribution_plan(
        session, period, account_id=account_id,
    )

    return build_next_month_plan(
        plan_vs_actual=plan_vs_actual,
        savings_category_rows=savings_category_rows,
        merchant_drivers=merchant_drivers,
        savings_goals=savings_goals,
        investment_plan=investment_plan,
    )
