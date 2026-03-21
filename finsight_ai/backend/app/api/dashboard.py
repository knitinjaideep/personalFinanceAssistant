"""
Dashboard API — deterministic DB-backed endpoints for the Home page dashboards.

Endpoints:
  GET /api/v1/dashboard/summary      — top-level KPI counts
  GET /api/v1/dashboard/investments  — portfolio summary + holdings + fees + balance history
  GET /api/v1/dashboard/banking      — spend by month, by category, top merchants, cash flow
  GET /api/v1/dashboard/coverage     — per-institution and per-product document counts

All data comes from canonical DB tables. No LLM is called here.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter

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


@router.get("/summary")
async def get_summary():
    """
    Top-level KPI counts: documents, statements, transactions, fees, holdings, accounts.
    Powers the 4-card metric row on the Home page.
    """
    async with get_session() as session:
        return await summary_counts(session)


@router.get("/investments")
async def get_investments_dashboard():
    """
    Full investments dashboard payload.

    Returns:
      - portfolio_summary: total value, unrealized G/L, per-account breakdown
      - allocation: % of portfolio per account
      - top_holdings: top 10 by market value
      - top_gainers: top 10 by unrealized gain
      - top_losers: top 10 by unrealized loss
      - fees: total fees by category
      - balance_history: monthly balance snapshots for timeline chart
      - coverage: document counts and date ranges per institution
    """
    async with get_session() as session:
        portfolio   = await investment_portfolio_summary(session)
        allocation  = await allocation_by_account(session)
        top_hold    = await top_holdings_by_value(session, limit=10)
        top_gain    = await top_holdings_by_gain_loss(session, limit=10, direction="gain")
        top_loss    = await top_holdings_by_gain_loss(session, limit=10, direction="loss")
        fees        = await investment_fees_summary(session)
        history     = await balance_history_by_account(session)
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
    }


@router.get("/banking")
async def get_banking_dashboard(months: int = 12):
    """
    Full banking dashboard payload.

    Query params:
      months (int, default 12): rolling window for spend and cash-flow trends.

    Returns:
      - spend_by_month: monthly total spend for trend charts
      - spend_by_category: totals per category for pie/bar chart
      - top_merchants: top 10 by total spend
      - card_summary: per-card spend breakdown
      - cash_flow: monthly inflow vs outflow (checking/savings only)
      - subscriptions: recurring transactions
      - coverage: document counts per institution
    """
    async with get_session() as session:
        monthly     = await banking_spend_by_month(session, months=months)
        by_cat      = await banking_spend_by_category(session)
        merchants   = await banking_top_merchants(session, limit=10)
        cards       = await banking_card_spend_summary(session)
        cash_flow   = await banking_cash_flow(session, months=months)
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
