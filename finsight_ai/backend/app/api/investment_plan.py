"""Read-only investment contribution planning API (PR 11)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.api.plan_vs_actual import _resolve_period
from app.db.engine import get_session
from app.domain.investment_plan import InvestmentContributionPlanResult
from app.services import investment_plan as service

router = APIRouter(prefix="/api/v1/investment-plan", tags=["investment-plan"])


@router.get("/contributions", response_model=InvestmentContributionPlanResult)
async def get_investment_contribution_plan(
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: str | None = None,
) -> InvestmentContributionPlanResult:
    """Investment contribution targets vs actuals for the selected period."""
    period = _resolve_period(year, month, start_date, end_date)
    async with get_session() as session:
        return await service.get_investment_contribution_plan(
            session, period, account_id=account_id,
        )
