"""
Analytics API — bucket-aware financial analytics endpoints (Phase 3).

Routes:
  GET /api/v1/analytics/investments              Full investments overview
  GET /api/v1/analytics/investments/portfolio   Portfolio value trend
  GET /api/v1/analytics/banking                 Full banking overview
  GET /api/v1/analytics/banking/spend           Spend by category + merchant
  GET /api/v1/analytics/banking/subscriptions   Recurring subscription detection

  Legacy (kept for backwards-compatibility):
  GET /api/v1/analytics/fees
  GET /api/v1/analytics/balances
  GET /api/v1/analytics/missing
  GET /api/v1/analytics/institutions

All new endpoints return { data: ..., warnings: [...], partial: bool }.
They NEVER return HTTP 500 — errors are surfaced as warnings + partial=True.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, get_analytics_service
from app.database.models import InstitutionModel
from app.services.analytics import BankingAnalyticsService, InvestmentsAnalyticsService
from app.services.analytics.investments_analytics import (
    AccountSummary,
    BalancePoint,
    HoldingRow,
    InvestmentsOverview,
    MonthlyFee,
    PeriodChange,
)
from app.services.analytics.banking_analytics import (
    BankingOverview,
    CardBalance,
    CheckingInOutSummary,
    MerchantSpend,
    Subscription,
)
from app.services.analytics_service import AnalyticsService

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _d(value: Optional[Decimal]) -> Optional[str]:
    """Safely convert Decimal to string; None → None."""
    return str(value) if value is not None else None


def _serialise_investments(overview: InvestmentsOverview) -> dict:
    return {
        "total_portfolio_value": _d(overview.total_portfolio_value),
        "accounts": [_serialise_account(a) for a in overview.accounts],
        "holdings_breakdown": [_serialise_holding(h) for h in overview.holdings_breakdown],
        "fee_trend": [_serialise_monthly_fee(f) for f in overview.fee_trend],
        "balance_trend": [_serialise_balance_point(b) for b in overview.balance_trend],
        "period_changes": [_serialise_period_change(p) for p in overview.period_changes],
    }


def _serialise_account(a: AccountSummary) -> dict:
    return {
        "account_id": a.account_id,
        "account_name": a.account_name,
        "account_type": a.account_type,
        "institution": a.institution,
        "current_value": _d(a.current_value),
        "as_of_date": str(a.as_of_date) if a.as_of_date else None,
        "portfolio_pct": _d(a.portfolio_pct),
    }


def _serialise_holding(h: HoldingRow) -> dict:
    return {
        "symbol": h.symbol,
        "description": h.description,
        "quantity": _d(h.quantity),
        "price": _d(h.price),
        "market_value": _d(h.market_value),
        "cost_basis": _d(h.cost_basis),
        "unrealized_gain_loss": _d(h.unrealized_gain_loss),
        "unrealized_pct": _d(h.unrealized_pct),
        "asset_class": h.asset_class,
        "account_id": h.account_id,
        "account_name": h.account_name,
        "institution": h.institution,
    }


def _serialise_monthly_fee(f: MonthlyFee) -> dict:
    return {
        "year": f.year,
        "month": f.month,
        "total_fees": _d(f.total_fees),
        "fee_count": f.fee_count,
        "by_category": {k: str(v) for k, v in f.by_category.items()},
    }


def _serialise_balance_point(b: BalancePoint) -> dict:
    return {
        "snapshot_date": str(b.snapshot_date),
        "total_value": _d(b.total_value),
        "account_id": b.account_id,
        "account_name": b.account_name,
        "institution": b.institution,
    }


def _serialise_period_change(p: PeriodChange) -> dict:
    return {
        "account_id": p.account_id,
        "account_name": p.account_name,
        "institution": p.institution,
        "previous_value": _d(p.previous_value),
        "current_value": _d(p.current_value),
        "change_amount": _d(p.change_amount),
        "change_pct": _d(p.change_pct),
        "period_start": str(p.period_start) if p.period_start else None,
        "period_end": str(p.period_end) if p.period_end else None,
    }


def _serialise_banking(overview: BankingOverview) -> dict:
    return {
        "total_spend_this_month": _d(overview.total_spend_this_month),
        "spend_by_category": {k: str(v) for k, v in overview.spend_by_category.items()},
        "spend_by_merchant": [_serialise_merchant(m) for m in overview.spend_by_merchant],
        "subscriptions": [_serialise_subscription(s) for s in overview.subscriptions],
        "credit_card_balances": [_serialise_card_balance(cb) for cb in overview.credit_card_balances],
        "checking_summary": _serialise_checking(overview.checking_summary),
        "top_transactions": [_serialise_tx(t) for t in overview.top_transactions],
        "unusual_transactions": [_serialise_tx(t) for t in overview.unusual_transactions],
    }


def _serialise_merchant(m: MerchantSpend) -> dict:
    return {
        "merchant_name": m.merchant_name,
        "total_amount": _d(m.total_amount),
        "transaction_count": m.transaction_count,
        "category": m.category,
    }


def _serialise_subscription(s: Subscription) -> dict:
    return {
        "merchant_name": s.merchant_name,
        "typical_amount": _d(s.typical_amount),
        "frequency_days": s.frequency_days,
        "last_charged": str(s.last_charged),
        "category": s.category,
        "transaction_ids": s.transaction_ids,
    }


def _serialise_card_balance(cb: CardBalance) -> dict:
    return {
        "account_id": cb.account_id,
        "account_name": cb.account_name,
        "institution": cb.institution,
        "current_balance": _d(cb.current_balance),
        "as_of_date": str(cb.as_of_date) if cb.as_of_date else None,
    }


def _serialise_checking(c: CheckingInOutSummary) -> dict:
    return {
        "total_inflows": _d(c.total_inflows),
        "total_outflows": _d(c.total_outflows),
        "net": _d(c.net),
    }


def _serialise_tx(tx: dict) -> dict:
    return {
        "id": tx.get("id"),
        "account_id": tx.get("account_id"),
        "transaction_date": str(tx.get("transaction_date", "")),
        "description": tx.get("description", ""),
        "merchant_name": tx.get("merchant_name", ""),
        "amount": _d(tx.get("amount")),
        "spend_amount": _d(tx.get("spend_amount")),
        "type": tx.get("type"),
        "category": tx.get("category"),
    }


def _envelope(data: Any, warnings: List[str]) -> JSONResponse:
    return JSONResponse(
        content={
            "data": data,
            "warnings": warnings,
            "partial": len(warnings) > 0,
        }
    )


# ---------------------------------------------------------------------------
# Investments endpoints
# ---------------------------------------------------------------------------

@router.get("/investments", summary="Investments overview (portfolio, holdings, fees, changes)")
async def get_investments_overview(
    account_ids: Optional[str] = Query(
        default=None,
        description="Comma-separated list of account UUIDs to filter",
    ),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Return a full investments overview.

    Returns ``partial=True`` with warnings if some data could not be loaded.
    Never returns HTTP 500.
    """
    parsed_account_ids: Optional[List[str]] = (
        [a.strip() for a in account_ids.split(",") if a.strip()]
        if account_ids
        else None
    )
    svc = InvestmentsAnalyticsService(session)
    result = await svc.get_overview(
        account_ids=parsed_account_ids,
        start_date=start_date,
        end_date=end_date,
    )
    return _envelope(_serialise_investments(result.data), result.warnings)


@router.get("/investments/portfolio", summary="Portfolio value trend (time-series)")
async def get_portfolio_trend(
    account_ids: Optional[str] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Return portfolio balance trend — one data point per snapshot per account."""
    parsed_account_ids: Optional[List[str]] = (
        [a.strip() for a in account_ids.split(",") if a.strip()]
        if account_ids
        else None
    )
    svc = InvestmentsAnalyticsService(session)
    result = await svc.get_portfolio_trend(
        account_ids=parsed_account_ids,
        start_date=start_date,
        end_date=end_date,
    )
    return _envelope(
        [_serialise_balance_point(b) for b in result.data],
        result.warnings,
    )


# ---------------------------------------------------------------------------
# Banking endpoints
# ---------------------------------------------------------------------------

@router.get("/banking", summary="Banking overview (spend, cards, subscriptions, checking)")
async def get_banking_overview(
    institution_ids: Optional[str] = Query(
        default=None,
        description="Comma-separated institution UUIDs",
    ),
    account_ids: Optional[str] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Return full banking overview.  Never returns HTTP 500."""
    svc = BankingAnalyticsService(session)
    result = await svc.get_overview(
        institution_ids=_csv(institution_ids),
        account_ids=_csv(account_ids),
        start_date=start_date,
        end_date=end_date,
    )
    return _envelope(_serialise_banking(result.data), result.warnings)


@router.get("/banking/spend", summary="Spend by category and merchant")
async def get_spend_breakdown(
    institution_ids: Optional[str] = Query(default=None),
    account_ids: Optional[str] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Return spend broken down by category and top merchants."""
    svc = BankingAnalyticsService(session)
    result = await svc.get_spend_breakdown(
        institution_ids=_csv(institution_ids),
        account_ids=_csv(account_ids),
        start_date=start_date,
        end_date=end_date,
    )
    return _envelope(result.data, result.warnings)


@router.get("/banking/subscriptions", summary="Detected recurring subscriptions")
async def get_subscriptions(
    institution_ids: Optional[str] = Query(default=None),
    account_ids: Optional[str] = Query(default=None),
    lookback_days: int = Query(default=90, ge=30, le=365),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Detect and return recurring subscription charges."""
    svc = BankingAnalyticsService(session)
    result = await svc.get_subscriptions(
        institution_ids=_csv(institution_ids),
        account_ids=_csv(account_ids),
        lookback_days=lookback_days,
    )
    return _envelope(
        [_serialise_subscription(s) for s in result.data],
        result.warnings,
    )


# ---------------------------------------------------------------------------
# Legacy endpoints (preserved for backwards-compatibility)
# ---------------------------------------------------------------------------

@router.get("/fees", summary="[Legacy] Fee summary for a date range")
async def get_fees(
    start_date: date = Query(default=None),
    end_date: date = Query(default=None),
    institution_type: Optional[str] = Query(default=None),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
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


@router.get("/balances", summary="[Legacy] Balance history for charting")
async def get_balance_history(
    account_id: Optional[str] = Query(default=None),
    institution_type: Optional[str] = Query(default=None),
    limit: int = Query(default=24, le=120),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
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


@router.get("/missing", summary="[Legacy] Detect missing monthly statements")
async def get_missing_statements(
    year: Optional[int] = Query(default=None),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> JSONResponse:
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _csv(value: Optional[str]) -> Optional[List[str]]:
    """Parse a comma-separated query param into a list, or None."""
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]
