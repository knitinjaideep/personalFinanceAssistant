"""
Dashboard API — deterministic DB-backed endpoints for the Home page dashboards.

Endpoints:
  GET /api/v1/dashboard/summary      — top-level KPI counts
  GET /api/v1/dashboard/investments  — portfolio summary + holdings + fees + balance history
  GET /api/v1/dashboard/banking      — spend by month, by category, top merchants, cash flow
  GET /api/v1/dashboard/coverage     — per-institution and per-product document counts

All data comes from canonical DB tables. No LLM is called here.

Period query contract (PR 05 — Global Period Filter): `/banking` and
`/investments` both accept an optional `start_date`/`end_date` (ISO dates,
inclusive) pair — the same unified contract used by
`GET /api/v1/plan-vs-actual` (see app/api/plan_vs_actual.py). Both must be
given together or neither. When omitted, each endpoint preserves its
pre-PR-05 default behavior (banking: legacy rolling `months`-back window;
investments: full history / latest-snapshot, unchanged).
"""

from __future__ import annotations

from datetime import date

import structlog
from fastapi import APIRouter, HTTPException

from app.db.engine import get_session
from app.services.dashboard.investment_queries import (
    allocation_by_account,
    balance_history_by_account,
    document_coverage_investments,
    investment_fees_summary,
    investment_portfolio_summary,
    top_holdings_by_gain_loss,
    top_holdings_by_value,
)
from app.services.dashboard.banking_queries import (
    banking_card_spend_summary,
    banking_cash_flow,
    banking_spend_by_category,
    banking_spend_by_month,
    banking_subscriptions,
    banking_top_merchants,
    document_coverage_banking,
)
from app.services.dashboard.summary_queries import (
    document_count_by_institution,
    document_count_by_product,
    latest_statement_dates,
    summary_counts,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _validate_range(start_date: date | None, end_date: date | None) -> None:
    if (start_date is None) != (end_date is None):
        raise HTTPException(422, "start_date and end_date must both be provided together.")
    if start_date is not None and end_date is not None and end_date < start_date:
        raise HTTPException(422, "end_date must not be before start_date.")


@router.get("/summary")
async def get_summary():
    """
    Top-level KPI counts: documents, statements, transactions, fees, holdings, accounts.
    Powers the 4-card metric row on the Home page.
    """
    async with get_session() as session:
        return await summary_counts(session)


@router.get("/investments")
async def get_investments_dashboard(
    start_date: date | None = None,
    end_date: date | None = None,
):
    """
    Full investments dashboard payload.

    Query params:
      start_date/end_date (ISO dates, optional, must be given together):
        narrows period-activity payloads (`fees`, `balance_history`) to that
        inclusive range, AND resolves the point-in-time payloads
        (`portfolio_summary`, `allocation`, `top_holdings`, `top_gainers`,
        `top_losers`) "as of" `end_date` — i.e. the most recent snapshot /
        statement on or before the end of the selected period, the standard
        "balance as of <date>" reading. This keeps every figure on the page
        anchored to the same period instead of mixing as-of-today headline
        values with a period-filtered timeline. Accounts with no data at or
        before `end_date` are omitted rather than back-filled from a later
        statement.

    Returns:
      - portfolio_summary: total value, unrealized G/L, per-account breakdown
        (as of end_date when a period is given)
      - allocation: % of portfolio per account (as of end_date)
      - top_holdings: top 10 by market value (as of end_date)
      - top_gainers: top 10 by unrealized gain (as of end_date)
      - top_losers: top 10 by unrealized loss (as of end_date)
      - fees: total fees by category (period-filtered)
      - balance_history: balance snapshots for timeline chart (period-filtered)
      - coverage: document counts and date ranges per institution
      - period: the resolved {start_date, end_date} actually applied, or null
    """
    _validate_range(start_date, end_date)
    async with get_session() as session:
        portfolio   = await investment_portfolio_summary(session, as_of=end_date)
        allocation  = await allocation_by_account(session, as_of=end_date)
        top_hold    = await top_holdings_by_value(session, limit=10, as_of=end_date)
        top_gain    = await top_holdings_by_gain_loss(session, limit=10, direction="gain", as_of=end_date)
        top_loss    = await top_holdings_by_gain_loss(session, limit=10, direction="loss", as_of=end_date)
        fees        = await investment_fees_summary(session, date_from=start_date, date_to=end_date)
        history     = await balance_history_by_account(session, date_from=start_date, date_to=end_date)
        coverage    = await document_coverage_investments(session)

    return {
        "portfolio_summary": portfolio,
        "allocation": allocation,
        "top_holdings": top_hold,
        "top_gainers": top_gain,
        "top_losers": top_loss,
        "fees": fees,
        "balance_history": history,
        "coverage": coverage,
        "period": {"start_date": start_date, "end_date": end_date} if start_date and end_date else None,
    }


@router.get("/banking")
async def get_banking_dashboard(
    months: int = 12,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """
    Full banking dashboard payload.

    Query params:
      months (int, default 12): legacy rolling window for spend and
        cash-flow trends, used only when start_date/end_date are omitted.
      start_date/end_date (ISO dates, optional, must be given together):
        the unified PR 05 period contract — narrows spend_by_month,
        spend_by_category, top_merchants, card_summary, and cash_flow to
        that inclusive range. Takes precedence over `months` when given.
        `subscriptions` intentionally always uses a fixed 18-month lookback
        regardless of this filter (see banking_subscriptions docstring).

    Returns:
      - spend_by_month: monthly total spend for trend charts
      - spend_by_category: totals per category for pie/bar chart
      - top_merchants: top 10 by total spend
      - card_summary: per-card spend breakdown
      - cash_flow: monthly inflow vs outflow (checking/savings only)
      - subscriptions: recurring transactions
      - coverage: document counts per institution
      - period: the resolved {start_date, end_date} actually applied, or null
    """
    _validate_range(start_date, end_date)
    async with get_session() as session:
        monthly     = await banking_spend_by_month(session, months=months, date_from=start_date, date_to=end_date)
        by_cat      = await banking_spend_by_category(session, date_from=start_date, date_to=end_date)
        merchants   = await banking_top_merchants(session, limit=10, date_from=start_date, date_to=end_date)
        cards       = await banking_card_spend_summary(session, date_from=start_date, date_to=end_date)
        cash_flow   = await banking_cash_flow(session, months=months, date_from=start_date, date_to=end_date)
        subs        = await banking_subscriptions(session)
        coverage    = await document_coverage_banking(session)

    return {
        "spend_by_month": monthly,
        "spend_by_category": by_cat,
        "top_merchants": merchants,
        "card_summary": cards,
        "cash_flow": cash_flow,
        "subscriptions": subs,
        "coverage": coverage,
        "period": {"start_date": start_date, "end_date": end_date} if start_date and end_date else None,
    }


@router.get("/coverage")
async def get_coverage():
    """
    Per-institution and per-product document/statement coverage.
    Used for the folder-summary cards and the Recent Files section.
    """
    async with get_session() as session:
        by_institution = await document_count_by_institution(session)
        by_product     = await document_count_by_product(session)
        latest_dates   = await latest_statement_dates(session)

    return {
        "by_institution": by_institution,
        "by_product": by_product,
        "latest_statement_dates": latest_dates,
    }
