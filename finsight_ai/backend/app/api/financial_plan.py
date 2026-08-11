"""
Financial Plan API — the user's INTENDED allocation (Needs/Wants/Savings/
Investments, versioned and effective-dated), kept separate from actual
transactions. All business logic lives in app.services.financial_plan; this
module only opens sessions and translates domain errors to HTTP responses.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.db.engine import get_session
from app.domain.entities import (
    PlanVersionCreateRequest,
    PlanVersionSnapshot,
    PlanVersionSummary,
    PlanVersionUpdateRequest,
)
from app.domain.errors import (
    DuplicateEffectiveDateError,
    EntityNotFoundError,
    PlanValidationError,
    PlanVersionImmutableError,
)
from app.services import financial_plan as plan_service

router = APIRouter(prefix="/api/v1/financial-plan", tags=["financial-plan"])


@router.get("/current", response_model=PlanVersionSnapshot)
async def get_current_plan() -> PlanVersionSnapshot:
    async with get_session() as session:
        snapshot = await plan_service.get_current_plan(session)
    if snapshot is None:
        raise HTTPException(404, "No financial plan is currently in effect.")
    return snapshot


@router.get("", response_model=PlanVersionSnapshot)
async def get_plan_by_date(target_date: date = Query(..., alias="date")) -> PlanVersionSnapshot:
    async with get_session() as session:
        snapshot = await plan_service.get_plan_for_date(session, target_date)
    if snapshot is None:
        raise HTTPException(404, f"No financial plan is in effect on {target_date}.")
    return snapshot


@router.get("/versions", response_model=list[PlanVersionSummary])
async def list_versions() -> list[PlanVersionSummary]:
    async with get_session() as session:
        return await plan_service.list_plan_versions(session)


@router.post("/versions", response_model=PlanVersionSnapshot, status_code=201)
async def create_version(body: PlanVersionCreateRequest) -> PlanVersionSnapshot:
    try:
        async with get_session() as session:
            return await plan_service.create_plan_version(
                session, effective_from=body.effective_from,
                allocations=body.allocations, notes=body.notes,
            )
    except PlanValidationError as exc:
        raise HTTPException(422, exc.message) from exc
    except DuplicateEffectiveDateError as exc:
        raise HTTPException(409, exc.message) from exc
    except EntityNotFoundError as exc:
        raise HTTPException(404, exc.message) from exc


@router.patch("/versions/{version_id}", response_model=PlanVersionSnapshot)
async def update_version(version_id: str, body: PlanVersionUpdateRequest) -> PlanVersionSnapshot:
    try:
        async with get_session() as session:
            return await plan_service.update_plan_version(
                session, version_id=version_id, allocations=body.allocations,
            )
    except PlanValidationError as exc:
        raise HTTPException(422, exc.message) from exc
    except PlanVersionImmutableError as exc:
        raise HTTPException(409, exc.message) from exc
    except EntityNotFoundError as exc:
        raise HTTPException(404, exc.message) from exc
