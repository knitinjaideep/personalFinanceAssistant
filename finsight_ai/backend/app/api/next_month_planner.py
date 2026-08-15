"""
Next Month Planner API (PR 14) — a single, general, read-only endpoint.

The work order lists three consumers ("Expose to: Overview -> Next Month
Plan, Banking -> insights/actions, Investments -> contribution plan"). All
three can share ONE ranked list (capped at 3, per
app.domain.next_month_planner.MAX_RECOMMENDATIONS): each `Recommendation`
already carries `bucket`/`action_type`, so a consumer that wants only its own
slice (e.g. Investments wanting `increase_investment_contribution`/
`maintain_contribution` rows) can filter client-side without a second
backend route — see app.domain.next_month_planner module docstring. Only
Overview's frontend is wired to this endpoint in this PR (see PR14 report);
Banking/Investments wiring is left for whoever picks up that frontend work
next, per the PR14 work order's scope boundary.

Period query contract: identical to GET /api/v1/plan-vs-actual (PR 05) —
either `start_date`+`end_date` or `year`+`month`. Reuses that module's
`_resolve_period` directly (reuse-first per .claude/rules/backend.md).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.api.plan_vs_actual import _resolve_period
from app.db.engine import get_session
from app.domain.next_month_planner import NextMonthPlanResult
from app.services import next_month_planner as service

router = APIRouter(prefix="/api/v1/next-month-plan", tags=["next-month-plan"])


@router.get("", response_model=NextMonthPlanResult)
async def get_next_month_plan(
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: str | None = None,
) -> NextMonthPlanResult:
    """Ranked, capped-at-3 deterministic recommendations for the period
    following the one requested — closes THIS period's own drift, never a
    cumulative historical shortfall (see app.domain.next_month_planner)."""
    period = _resolve_period(year, month, start_date, end_date)
    async with get_session() as session:
        return await service.get_next_month_plan(session, period, account_id=account_id)
