"""
Savings Goals API — read-mostly surface over app.services.savings_goals,
sized to what Overview and Banking need (pr-13-savings-goals.md: "Expose APIs
needed by Overview and Banking"). All business logic lives in the
service/domain layers; this module only opens sessions, resolves query
params, and translates domain errors to HTTP responses (same convention as
app.api.plan_vs_actual / app.api.financial_plan).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.engine import get_session
from app.domain.errors import EntityNotFoundError, SavingsGoalValidationError
from app.domain.savings_goals import (
    GoalAccountMapping,
    GoalType,
    SavingsGoalProgress,
)
from app.services import savings_goals as service

router = APIRouter(prefix="/api/v1/savings-goals", tags=["savings-goals"])


class SavingsGoalCreateRequest(BaseModel):
    name: str
    goal_type: GoalType
    effective_date: date
    category_name: str | None = None
    target_amount: str | None = None
    target_percentage_of_income: str | None = None
    target_months_of_expenses: str | None = None
    account_mappings: list[GoalAccountMapping] = Field(default_factory=list)
    priority: int = 0


@router.get("", response_model=list[SavingsGoalProgress])
async def list_goals(as_of: date | None = None) -> list[SavingsGoalProgress]:
    """Every goal's progress as of a single date (defaults to today).

    Deliberately an `as_of` SNAPSHOT rather than PR 05's
    `start_date`/`end_date` range contract: a goal's `current_amount` is a
    cumulative balance since the goal's own `effective_date`, not a
    period flow, so a caller-supplied start would silently truncate the
    accumulation. A surface driven by the global period filter should pass
    the period's `end_date` as `as_of` ("where did this goal stand at the
    end of the selected period"), never its `start_date`.
    """
    async with get_session() as session:
        return await service.list_goal_progress(session, as_of=as_of)


@router.get("/{goal_id}", response_model=SavingsGoalProgress)
async def get_goal(goal_id: str, as_of: date | None = None) -> SavingsGoalProgress:
    """One goal's progress. Same `as_of` snapshot semantics as `list_goals`."""
    try:
        async with get_session() as session:
            return await service.get_goal_progress(session, goal_id, as_of=as_of)
    except EntityNotFoundError as exc:
        raise HTTPException(404, exc.message) from exc


def _parse_decimal(raw: str | None, field: str) -> Decimal | None:
    """Money/percentage fields cross the wire as strings (exact Decimal, no
    float rounding). A non-numeric string is a client error — 422, never an
    unhandled 500."""
    if raw is None or not raw.strip():
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise HTTPException(422, f"{field} must be a decimal number, got {raw!r}.") from exc


@router.post("", response_model=SavingsGoalProgress, status_code=201)
async def create_goal(body: SavingsGoalCreateRequest) -> SavingsGoalProgress:
    target_amount = _parse_decimal(body.target_amount, "target_amount")
    target_percentage = _parse_decimal(
        body.target_percentage_of_income, "target_percentage_of_income",
    )
    target_months = _parse_decimal(
        body.target_months_of_expenses, "target_months_of_expenses",
    )
    try:
        async with get_session() as session:
            goal = await service.create_goal(
                session,
                name=body.name,
                goal_type=body.goal_type,
                effective_date=body.effective_date,
                category_name=body.category_name,
                target_amount=target_amount,
                target_percentage_of_income=target_percentage,
                target_months_of_expenses=target_months,
                account_mappings=body.account_mappings,
                priority=body.priority,
            )
            return await service.get_goal_progress(session, goal.id)
    except SavingsGoalValidationError as exc:
        raise HTTPException(422, exc.message) from exc
