"""
Overview API — read-only endpoints backing the Overview/Home page redesign
(docs/coral-redesign/pr-06-overview.md). All business logic lives in
app.services.overview / app.domain.overview_insights; this module only opens
sessions, resolves the requested period, and translates domain errors to
HTTP responses — same pattern as app/api/plan_vs_actual.py.

Period query contract: identical to GET /api/v1/plan-vs-actual (PR 05) —
either `start_date`+`end_date` or `year`+`month`. Reuses that module's
`_resolve_period` directly rather than re-implementing the same parsing
logic a second time (reuse-first per .claude/rules/backend.md).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.api.plan_vs_actual import _resolve_period
from app.db.engine import get_session
from app.domain.overview_insights import MonthlyFlowSummary, OverviewInsightsResult
from app.services import overview as service

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])


@router.get("/insights", response_model=OverviewInsightsResult)
async def get_overview_insights(
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: str | None = None,
) -> OverviewInsightsResult:
    """Financial status header + Coral Insights (<=3) + Next Month Plan
    preview (<=3) for the requested period."""
    period = _resolve_period(year, month, start_date, end_date)
    async with get_session() as session:
        return await service.get_overview_insights(session, period, account_id=account_id)


@router.get("/monthly-flow", response_model=list[MonthlyFlowSummary])
async def get_monthly_flow(
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: str | None = None,
) -> list[MonthlyFlowSummary]:
    """One Income/Spent/Saved+Invested row per calendar month in the
    requested period — powers the Overview grouped bar chart. A
    single-month period selection returns a single-element list."""
    period = _resolve_period(year, month, start_date, end_date)
    async with get_session() as session:
        return await service.get_monthly_flow_summary(session, period, account_id=account_id)
