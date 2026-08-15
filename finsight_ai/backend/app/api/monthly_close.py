"""Monthly Coral Close API (PR 15)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.api.plan_vs_actual import _resolve_period
from app.db.engine import get_session
from app.domain.monthly_close import MonthlyCloseResult
from app.services import monthly_close as service

router = APIRouter(prefix="/api/v1/monthly-close", tags=["monthly-close"])


@router.get("", response_model=MonthlyCloseResult)
async def get_monthly_close(
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: str | None = None,
) -> MonthlyCloseResult:
    """Read-only close report for a historical or selected month."""
    period = _resolve_period(year, month, start_date, end_date)
    async with get_session() as session:
        return await service.get_monthly_close(session, period, account_id=account_id)
