"""
Investment contribution planning service (PR 11).

This wires the pure contribution model to the database. It intentionally uses
classified cash-flow transactions and the active financial plan; it does not
read investment holdings, balances, or portfolio allocation tables.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.investment_plan import (
    InvestmentContributionPlanResult,
    compute_investment_contribution_plan,
)
from app.domain.plan_vs_actual import DEFAULT_STATUS_THRESHOLDS, Period, StatusThresholds
from app.services import plan_vs_actual as plan_vs_actual_service


async def get_investment_contribution_plan(
    session: AsyncSession,
    period: Period,
    *,
    account_id: str | None = None,
    thresholds: StatusThresholds = DEFAULT_STATUS_THRESHOLDS,
) -> InvestmentContributionPlanResult:
    """Return target-vs-actual investment contributions by vehicle.

    The account scoping behavior mirrors Plan vs Actual: scoping narrows both
    the actual contribution rows and the plannable-income denominator.
    """
    plan, changed_mid_period = await plan_vs_actual_service._resolve_plan(session, period)
    transactions = await plan_vs_actual_service._load_classified_transactions(
        session, period, account_id=account_id,
    )
    return compute_investment_contribution_plan(
        period,
        transactions,
        plan,
        thresholds=thresholds,
        plan_version_changed_mid_period=changed_mid_period,
    )
