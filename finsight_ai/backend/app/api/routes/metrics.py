"""
Metrics API — Phase 2.8 longitudinal derived metrics endpoints.

Routes:
  GET  /api/v1/metrics/net-worth-trend       Monthly net worth time series
  GET  /api/v1/metrics/spending-trend        Monthly spending / cash flow trend
  GET  /api/v1/metrics/summary/{year}/{month} Single-month cross-account snapshot
  GET  /api/v1/metrics/available-months      Which months have data
  POST /api/v1/metrics/generate/{statement_id} Trigger metric generation for a statement
  POST /api/v1/metrics/recompute             Recompute all derived metrics
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.metrics_service import MetricsService

logger = structlog.get_logger(__name__)
router = APIRouter()


def _get_metrics_service(session: AsyncSession = Depends(get_session)) -> MetricsService:
    return MetricsService(session)


@router.get(
    "/net-worth-trend",
    summary="Monthly net worth time series",
)
async def net_worth_trend(
    account_id: str | None = Query(default=None, description="Filter by account ID"),
    institution_id: str | None = Query(default=None, description="Filter by institution ID"),
    months: int = Query(default=24, ge=1, le=60, description="Number of months to return"),
    svc: MetricsService = Depends(_get_metrics_service),
) -> list[dict]:
    """
    Return monthly total portfolio value across all accounts (or filtered subset).

    Each item includes per-account breakdown for drill-down charting.
    Suitable for a net worth timeline chart.
    """
    try:
        return await svc.get_net_worth_trend(
            account_id=account_id,
            institution_id=institution_id,
            months=months,
        )
    except Exception as exc:
        logger.exception("metrics.net_worth_trend.error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to fetch net worth trend: {exc}")


@router.get(
    "/spending-trend",
    summary="Monthly spending and cash flow trend",
)
async def spending_trend(
    account_id: str | None = Query(default=None),
    institution_id: str | None = Query(default=None),
    months: int = Query(default=12, ge=1, le=60),
    svc: MetricsService = Depends(_get_metrics_service),
) -> list[dict]:
    """
    Return monthly fee, withdrawal, deposit, and net cash flow totals.

    Suitable for a stacked bar chart of spending vs. income.
    """
    try:
        return await svc.get_spending_trend(
            account_id=account_id,
            institution_id=institution_id,
            months=months,
        )
    except Exception as exc:
        logger.exception("metrics.spending_trend.error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to fetch spending trend: {exc}")


@router.get(
    "/summary/{year}/{month}",
    summary="Single-month cross-account financial summary",
)
async def monthly_summary(
    year: int,
    month: int,
    svc: MetricsService = Depends(_get_metrics_service),
) -> dict:
    """
    Return a snapshot of all accounts for the specified calendar month.

    Includes total portfolio value, fee totals, and per-account breakdown.
    """
    if not (1 <= month <= 12):
        raise HTTPException(status_code=422, detail="month must be 1–12")
    try:
        return await svc.get_monthly_summary(year=year, month=month)
    except Exception as exc:
        logger.exception("metrics.monthly_summary.error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to fetch monthly summary: {exc}")


@router.get(
    "/available-months",
    summary="List months that have derived metric data",
)
async def available_months(
    svc: MetricsService = Depends(_get_metrics_service),
) -> list[dict]:
    """
    Return all (year, month) pairs for which derived metrics exist.

    The frontend uses this to populate month-picker dropdowns and show
    coverage gaps.
    """
    try:
        return await svc.list_available_months()
    except Exception as exc:
        logger.exception("metrics.available_months.error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/generate/{statement_id}",
    summary="Generate derived metrics for a processed statement",
    status_code=202,
)
async def generate_for_statement(
    statement_id: str,
    svc: MetricsService = Depends(_get_metrics_service),
) -> dict:
    """
    Compute or recompute derived monthly metrics for a specific statement.

    Called automatically after ingestion completes; can also be triggered
    manually if the statement was corrected or re-approved.
    """
    try:
        written = await svc.generate_for_statement(statement_id, source="manual")
        return {"statement_id": statement_id, "months_written": written, "status": "ok"}
    except Exception as exc:
        logger.exception("metrics.generate.error", statement_id=statement_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Metric generation failed: {exc}")


@router.post(
    "/recompute",
    summary="Recompute all derived metrics from canonical tables",
    status_code=202,
)
async def recompute_all(
    svc: MetricsService = Depends(_get_metrics_service),
) -> dict:
    """
    Full recompute of all derived metrics.

    Use this when:
    - A correction was applied to historical data
    - The metric schema was updated
    - Debugging metric inconsistencies
    """
    try:
        total = await svc.recompute_all()
        return {"total_rows_written": total, "status": "ok"}
    except Exception as exc:
        logger.exception("metrics.recompute_all.error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Recompute failed: {exc}")
