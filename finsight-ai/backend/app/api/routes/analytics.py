"""
Analytics endpoints — structured financial analysis queries.

Routes:
  GET /api/v1/analytics/fees           Fee summary for a date range
  GET /api/v1/analytics/balances       Balance history for charting
  GET /api/v1/analytics/missing        Missing statements detection
  GET /api/v1/analytics/institutions   List institutions in DB
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, get_analytics_service
from app.database.models import AccountModel, InstitutionModel
from app.services.analytics_service import AnalyticsService

router = APIRouter()


@router.get("/fees", summary="Get fee summary for a date range")
async def get_fees(
    start_date: date = Query(default=None, description="Start date (ISO format)"),
    end_date: date = Query(default=None, description="End date (ISO format)"),
    institution_type: str | None = Query(default=None),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
    """Aggregate fees by institution and account for the specified period."""
    if start_date is None:
        start_date = date.today() - timedelta(days=180)
    if end_date is None:
        end_date = date.today()

    summaries = await analytics.get_fee_summary(
        start_date=start_date,
        end_date=end_date,
        institution_type=institution_type,
    )
    return JSONResponse(
        content={
            "period": {"start": str(start_date), "end": str(end_date)},
            "institution_filter": institution_type,
            "total_fees": str(sum(s.total_fees for s in summaries)),
            "summaries": [
                {
                    "institution": s.institution,
                    "account": s.account,
                    "total_fees": str(s.total_fees),
                    "fee_count": s.fee_count,
                    "categories": {k: str(v) for k, v in s.categories.items()},
                }
                for s in summaries
            ],
        }
    )


@router.get("/balances", summary="Get balance history for charting")
async def get_balance_history(
    account_id: str | None = Query(default=None),
    institution_type: str | None = Query(default=None),
    limit: int = Query(default=24, le=120),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
    """Return time-series balance data for frontend charts."""
    balances = await analytics.get_balance_history(
        account_id=account_id,
        institution_type=institution_type,
        limit=limit,
    )
    return JSONResponse(
        content=[
            {
                "account_id": b.account_id,
                "account": b.account_masked,
                "institution": b.institution,
                "date": str(b.snapshot_date),
                "total_value": str(b.total_value),
            }
            for b in balances
        ]
    )


@router.get("/missing", summary="Detect missing monthly statements")
async def get_missing_statements(
    year: int = Query(default=None, description="Year to check (defaults to current year)"),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
    """Identify which monthly statements are missing for each account."""
    if year is None:
        year = date.today().year
    missing = await analytics.get_missing_statements(year=year)
    return JSONResponse(content={"year": year, "missing": missing})


@router.get("/institutions", summary="List all institutions in the database")
async def list_institutions(
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    result = await session.execute(select(InstitutionModel))
    institutions = result.scalars().all()
    return JSONResponse(
        content=[
            {
                "id": inst.id,
                "name": inst.name,
                "institution_type": inst.institution_type,
            }
            for inst in institutions
        ]
    )
