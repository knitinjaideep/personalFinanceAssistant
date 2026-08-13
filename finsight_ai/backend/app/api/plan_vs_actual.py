"""
Plan vs Actual API — read-only drill-down over app.services.plan_vs_actual.

All business logic lives in the service/domain layers; this module only
opens sessions, resolves the requested period, and translates domain errors
to HTTP responses. See docs/PLAN_VS_ACTUAL_ENGINE.md.
"""

from __future__ import annotations

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


def _resolve_period(year: int, month: int) -> Period:
    try:
        return Period.for_month(year, month)
    except ValueError as exc:
        raise HTTPException(422, f"Invalid year/month: {exc}") from exc


def _resolve_bucket(bucket: str) -> MasterBucket:
    try:
        return MasterBucket(bucket)
    except ValueError as exc:
        raise HTTPException(
            422, f"Invalid bucket {bucket!r}; expected one of {[b.value for b in MasterBucket]}"
        ) from exc


@router.get("", response_model=PlanVsActualResult)
async def get_plan_vs_actual(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    account_id: str | None = None,
) -> PlanVsActualResult:
    period = _resolve_period(year, month)
    async with get_session() as session:
        return await service.get_plan_vs_actual(session, period, account_id=account_id)


@router.get("/buckets/{bucket}", response_model=list[CategoryDrift])
async def get_bucket_breakdown(
    bucket: str,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    account_id: str | None = None,
) -> list[CategoryDrift]:
    period = _resolve_period(year, month)
    master_bucket = _resolve_bucket(bucket)
    async with get_session() as session:
        return await service.get_bucket_breakdown(
            session, period, master_bucket, account_id=account_id,
        )


@router.get("/merchants", response_model=list[MerchantDriver])
async def get_merchant_drivers(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    bucket: str | None = None,
    category: str | None = None,
    account_id: str | None = None,
    limit: int = Query(10, ge=1, le=100),
) -> list[MerchantDriver]:
    period = _resolve_period(year, month)
    master_bucket = _resolve_bucket(bucket) if bucket else None
    async with get_session() as session:
        return await service.get_merchant_drivers(
            session, period, bucket=master_bucket, category=category,
            account_id=account_id, top_n=limit,
        )
