"""
Plan vs Actual API — read-only drill-down over app.services.plan_vs_actual.

All business logic lives in the service/domain layers; this module only
opens sessions, resolves the requested period, and translates domain errors
to HTTP responses. See docs/PLAN_VS_ACTUAL_ENGINE.md.

Period query contract (PR 05 — Global Period Filter): every route accepts
EITHER `start_date`+`end_date` (explicit ISO dates, the unified contract
shared with `GET /dashboard/banking` and `GET /dashboard/investments`) OR
the original `year`+`month` (a single whole calendar month, PR 04's
contract). `start_date`/`end_date` take precedence when both forms are
supplied. Exactly one form must resolve — see `_resolve_period`.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.db.engine import get_session
from app.domain.plan_vs_actual import (
    CategoryDrift,
    MerchantDriver,
    Period,
    PlanVsActualResult,
)
from app.domain.transaction_classification import MasterBucket
from app.services import plan_vs_actual as service

router = APIRouter(prefix="/api/v1/plan-vs-actual", tags=["plan-vs-actual"])


def _resolve_period(
    year: int | None,
    month: int | None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Period:
    """Resolve the requested period from either query contract.

    `start_date`/`end_date` (the unified PR 05 range contract) win when
    provided, regardless of whether `year`/`month` were also passed — this
    lets a frontend always send both a resolved range and a display
    year/month without triggering a 422. Falls back to `year`+`month`
    (PR 04's original single-calendar-month contract) otherwise.
    """
    if start_date is not None or end_date is not None:
        if start_date is None or end_date is None:
            raise HTTPException(422, "Both start_date and end_date are required together.")
        try:
            return Period.for_range(start_date, end_date)
        except ValueError as exc:
            raise HTTPException(422, f"Invalid start_date/end_date: {exc}") from exc
    if year is not None and month is not None:
        try:
            return Period.for_month(year, month)
        except ValueError as exc:
            raise HTTPException(422, f"Invalid year/month: {exc}") from exc
    raise HTTPException(422, "Provide either start_date and end_date, or year and month.")


def _resolve_bucket(bucket: str) -> MasterBucket:
    try:
        return MasterBucket(bucket)
    except ValueError as exc:
        raise HTTPException(
            422, f"Invalid bucket {bucket!r}; expected one of {[b.value for b in MasterBucket]}"
        ) from exc


@router.get("", response_model=PlanVsActualResult)
async def get_plan_vs_actual(
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: str | None = None,
) -> PlanVsActualResult:
    period = _resolve_period(year, month, start_date, end_date)
    async with get_session() as session:
        return await service.get_plan_vs_actual(session, period, account_id=account_id)


@router.get("/buckets/{bucket}", response_model=list[CategoryDrift])
async def get_bucket_breakdown(
    bucket: str,
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: str | None = None,
) -> list[CategoryDrift]:
    period = _resolve_period(year, month, start_date, end_date)
    master_bucket = _resolve_bucket(bucket)
    async with get_session() as session:
        return await service.get_bucket_breakdown(
            session, period, master_bucket, account_id=account_id,
        )


@router.get("/merchants", response_model=list[MerchantDriver])
async def get_merchant_drivers(
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    start_date: date | None = None,
    end_date: date | None = None,
    bucket: str | None = None,
    category: str | None = None,
    account_id: str | None = None,
    limit: int = Query(10, ge=1, le=100),
) -> list[MerchantDriver]:
    period = _resolve_period(year, month, start_date, end_date)
    master_bucket = _resolve_bucket(bucket) if bucket else None
    async with get_session() as session:
        return await service.get_merchant_drivers(
            session, period, bucket=master_bucket, category=category,
            account_id=account_id, top_n=limit,
        )
