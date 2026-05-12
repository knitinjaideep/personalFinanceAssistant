"""
Investment dashboard queries — all queries for the Investments bucket live here.

Design principles:
- Every function returns plain Python dicts/lists (JSON-serializable).
- Monetary values are returned as float (for chart rendering) AND as formatted
  strings (for display). Callers can choose which to use.
- All queries are deterministic SQL — no LLM, no inference.
- Functions are composable: the API layer calls them individually and assembles
  the response payload.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Float, cast, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.models import (
    AccountModel,
    BalanceSnapshotModel,
    DocumentModel,
    FeeModel,
    HoldingModel,
    InstitutionModel,
    StatementModel,
)
from app.services.dashboard.utils import dec as _dec, fmt as _fmt

_INVESTMENT_TYPES = ["morgan_stanley", "etrade"]


# ── Portfolio summary ─────────────────────────────────────────────────────────

async def investment_portfolio_summary(session: AsyncSession) -> dict:
    """
    Returns the latest total portfolio value per account plus an overall total.

    Uses the most recent balance_snapshot per account to avoid double-counting
    when multiple statements exist for the same account.
    """
    # Subquery: latest snapshot_date per account
    latest_sub = (
        select(
            BalanceSnapshotModel.account_id,
            func.max(BalanceSnapshotModel.snapshot_date).label("max_date"),
        )
        .join(AccountModel, BalanceSnapshotModel.account_id == AccountModel.id)
        .where(AccountModel.institution_type.in_(_INVESTMENT_TYPES))
        .group_by(BalanceSnapshotModel.account_id)
        .subquery()
    )

    rows = await session.execute(
        select(
            AccountModel.id,
            AccountModel.account_name,
            AccountModel.account_type,
            AccountModel.institution_type,
            BalanceSnapshotModel.total_value,
            BalanceSnapshotModel.invested_value,
            BalanceSnapshotModel.cash_value,
            BalanceSnapshotModel.unrealized_gain_loss,
            BalanceSnapshotModel.snapshot_date,
        )
        .join(AccountModel, BalanceSnapshotModel.account_id == AccountModel.id)
        .join(
            latest_sub,
            (latest_sub.c.account_id == BalanceSnapshotModel.account_id)
            & (latest_sub.c.max_date == BalanceSnapshotModel.snapshot_date),
        )
    )

    # Latest statement date per account (for account card display)
    stmt_rows = await session.execute(
        select(
            StatementModel.account_id,
            func.max(StatementModel.period_end).label("latest_stmt"),
        )
        .join(AccountModel, StatementModel.account_id == AccountModel.id)
        .where(AccountModel.institution_type.in_(_INVESTMENT_TYPES))
        .group_by(StatementModel.account_id)
    )
    latest_stmt_by_account: dict[str, str] = {
        str(r.account_id): str(r.latest_stmt) for r in stmt_rows.fetchall() if r.latest_stmt
    }

    accounts = []
    total_value = Decimal("0")
    total_gain_loss = Decimal("0")
    latest_snapshot_date: str | None = None

    for row in rows.fetchall():
        tv = _dec(row.total_value)
        gl = _dec(row.unrealized_gain_loss)
        cost = _dec(row.invested_value)   # invested_value used as cost proxy
        total_value += tv
        total_gain_loss += gl

        # Track the most recent snapshot date across all accounts for "last updated"
        snap_str = str(row.snapshot_date) if row.snapshot_date else None
        if snap_str and (latest_snapshot_date is None or snap_str > latest_snapshot_date):
            latest_snapshot_date = snap_str

        # Gain/loss percent: (total_value - cost_basis) / cost_basis * 100
        gain_loss_pct: float | None = None
        if cost > 0:
            gain_loss_pct = round(float((tv - cost) / cost * 100), 2)

        accounts.append({
            "account_name": row.account_name or row.account_type,
            "account_type": row.account_type,
            "institution_type": row.institution_type,
            "total_value": float(tv),
            "total_value_fmt": _fmt(tv),
            "invested_value": float(cost),
            "cash_value": float(_dec(row.cash_value)),
            "unrealized_gain_loss": float(gl),
            "unrealized_gain_loss_fmt": _fmt(gl),
            "gain_loss_pct": gain_loss_pct,
            "snapshot_date": snap_str,
            "latest_statement_date": latest_stmt_by_account.get(str(row.id)),
        })

    return {
        "total_portfolio_value": float(total_value),
        "total_portfolio_value_fmt": _fmt(total_value),
        "total_unrealized_gain_loss": float(total_gain_loss),
        "total_unrealized_gain_loss_fmt": _fmt(total_gain_loss),
        "last_updated": latest_snapshot_date,
        "accounts": accounts,
    }


# ── Holdings ──────────────────────────────────────────────────────────────────

async def top_holdings_by_value(session: AsyncSession, limit: int = 10) -> list[dict]:
    """
    Top N holdings by market value from the most recent statement per account.

    Returns a flat list sorted by market_value descending.
    """
    # Most recent statement per account for investment institutions
    latest_stmt = (
        select(
            StatementModel.account_id,
            func.max(StatementModel.period_end).label("max_end"),
        )
        .join(AccountModel, StatementModel.account_id == AccountModel.id)
        .where(AccountModel.institution_type.in_(_INVESTMENT_TYPES))
        .group_by(StatementModel.account_id)
        .subquery()
    )

    rows = await session.execute(
        select(
            HoldingModel.symbol,
            HoldingModel.description,
            HoldingModel.market_value,
            HoldingModel.unrealized_gain_loss,
            HoldingModel.cost_basis,
            HoldingModel.quantity,
            HoldingModel.asset_class,
            AccountModel.account_name,
            AccountModel.institution_type,
        )
        .join(AccountModel, HoldingModel.account_id == AccountModel.id)
        .join(StatementModel, HoldingModel.statement_id == StatementModel.id)
        .join(
            latest_stmt,
            (latest_stmt.c.account_id == StatementModel.account_id)
            & (latest_stmt.c.max_end == StatementModel.period_end),
        )
        .order_by(
            cast(HoldingModel.market_value, Float).desc()
        )
        .limit(limit)
    )

    all_rows = rows.fetchall()
    total_mv = sum(_dec(r.market_value) for r in all_rows)

    return [
        {
            "symbol": r.symbol,
            "description": r.description,
            "market_value": float(_dec(r.market_value)),
            "market_value_fmt": _fmt(_dec(r.market_value)),
            "unrealized_gain_loss": float(_dec(r.unrealized_gain_loss)),
            "unrealized_gain_loss_fmt": _fmt(_dec(r.unrealized_gain_loss)),
            "cost_basis": float(_dec(r.cost_basis)),
            "quantity": float(_dec(r.quantity)) if r.quantity else None,
            "asset_class": r.asset_class,
            "account_name": r.account_name,
            "institution_type": r.institution_type,
            "portfolio_weight": round(
                float(_dec(r.market_value) / total_mv * 100), 2
            ) if total_mv > 0 else None,
        }
        for r in all_rows
    ]


async def top_holdings_by_gain_loss(
    session: AsyncSession, limit: int = 10, direction: str = "gain"
) -> list[dict]:
    """
    Top N holdings by unrealized gain (direction='gain') or loss (direction='loss').
    """
    latest_stmt = (
        select(
            StatementModel.account_id,
            func.max(StatementModel.period_end).label("max_end"),
        )
        .join(AccountModel, StatementModel.account_id == AccountModel.id)
        .where(AccountModel.institution_type.in_(_INVESTMENT_TYPES))
        .group_by(StatementModel.account_id)
        .subquery()
    )

    gl_cast = cast(HoldingModel.unrealized_gain_loss, Float)
    order = gl_cast.desc() if direction == "gain" else gl_cast.asc()

    rows = await session.execute(
        select(
            HoldingModel.symbol,
            HoldingModel.description,
            HoldingModel.market_value,
            HoldingModel.unrealized_gain_loss,
            HoldingModel.cost_basis,
            AccountModel.account_name,
            AccountModel.institution_type,
        )
        .join(AccountModel, HoldingModel.account_id == AccountModel.id)
        .join(StatementModel, HoldingModel.statement_id == StatementModel.id)
        .join(
            latest_stmt,
            (latest_stmt.c.account_id == StatementModel.account_id)
            & (latest_stmt.c.max_end == StatementModel.period_end),
        )
        .where(HoldingModel.unrealized_gain_loss.isnot(None))
        .order_by(order)
        .limit(limit)
    )

    return [
        {
            "symbol": r.symbol,
            "description": r.description,
            "market_value": float(_dec(r.market_value)),
            "unrealized_gain_loss": float(_dec(r.unrealized_gain_loss)),
            "unrealized_gain_loss_fmt": _fmt(_dec(r.unrealized_gain_loss)),
            "cost_basis": float(_dec(r.cost_basis)),
            "account_name": r.account_name,
            "institution_type": r.institution_type,
        }
        for r in rows.fetchall()
    ]


async def allocation_by_account(session: AsyncSession) -> list[dict]:
    """
    Portfolio allocation (% of total) broken down by account.
    Uses latest market_value per account from balance_snapshots.
    """
    summary = await investment_portfolio_summary(session)
    total = Decimal(str(summary["total_portfolio_value"]))
    if total == 0:
        return []
    return [
        {
            **acct,
            "pct_of_portfolio": round(float(Decimal(str(acct["total_value"])) / total * 100), 2),
        }
        for acct in summary["accounts"]
    ]


# ── Balance history ───────────────────────────────────────────────────────────

async def balance_history_by_account(session: AsyncSession) -> list[dict]:
    """
    Monthly balance snapshots per account for timeline chart.
    Returns one row per (account, snapshot_date) sorted chronologically.
    """
    rows = await session.execute(
        select(
            BalanceSnapshotModel.snapshot_date,
            BalanceSnapshotModel.total_value,
            AccountModel.account_name,
            AccountModel.account_type,
            AccountModel.institution_type,
        )
        .join(AccountModel, BalanceSnapshotModel.account_id == AccountModel.id)
        .where(AccountModel.institution_type.in_(_INVESTMENT_TYPES))
        .order_by(BalanceSnapshotModel.snapshot_date)
    )
    return [
        {
            "date": str(r.snapshot_date),
            "total_value": float(_dec(r.total_value)),
            "account_name": r.account_name or r.account_type,
            "institution_type": r.institution_type,
        }
        for r in rows.fetchall()
    ]


# ── Fees ──────────────────────────────────────────────────────────────────────

async def investment_fees_summary(session: AsyncSession) -> dict:
    """
    Total investment fees by category (advisory, management, etc.).
    """
    rows = await session.execute(
        select(
            FeeModel.fee_category,
            func.count(FeeModel.id).label("count"),
            func.sum(
                cast(FeeModel.amount, Float)
            ).label("total"),
        )
        .join(AccountModel, FeeModel.account_id == AccountModel.id)
        .where(AccountModel.institution_type.in_(["morgan_stanley", "etrade"]))
        .group_by(FeeModel.fee_category)
    )

    categories = []
    grand_total = Decimal("0")
    for r in rows.fetchall():
        amt = Decimal(str(r.total or 0))
        grand_total += amt
        categories.append({
            "category": r.fee_category or "uncategorized",
            "count": r.count,
            "total": float(amt),
            "total_fmt": _fmt(amt),
        })

    # Recent trend: last 3 months vs prior 3 months
    trend_rows = await session.execute(
        text("""
            SELECT
                strftime('%Y-%m', f.fee_date) AS month,
                SUM(CAST(f.amount AS REAL))   AS total
            FROM fees f
            JOIN accounts a ON a.id = f.account_id
            WHERE a.institution_type IN ('morgan_stanley','etrade')
              AND f.fee_date >= date('now', '-6 months')
            GROUP BY month
            ORDER BY month
        """),
    )
    fee_trend = [
        {"month": r[0], "total": round(float(r[1] or 0), 2)}
        for r in trend_rows.fetchall()
    ]

    return {
        "total_fees": float(grand_total),
        "total_fees_fmt": _fmt(grand_total),
        "by_category": sorted(categories, key=lambda x: x["total"], reverse=True),
        "recent_trend": fee_trend,
    }


# ── Document coverage ─────────────────────────────────────────────────────────

async def document_coverage_investments(session: AsyncSession) -> list[dict]:
    """
    Per-institution document count and statement date range for Investments bucket.
    Includes a `missing_recent_data` warning flag if no statement exists in the
    last 60 days (likely the institution hasn't had a recent statement uploaded).
    """
    cutoff = (date.today() - timedelta(days=60)).isoformat()

    rows = await session.execute(
        select(
            InstitutionModel.name,
            InstitutionModel.institution_type,
            func.count(DocumentModel.id).label("doc_count"),
            func.min(StatementModel.period_start).label("earliest"),
            func.max(StatementModel.period_end).label("latest"),
        )
        .join(DocumentModel, DocumentModel.institution_type == InstitutionModel.institution_type)
        .join(StatementModel, StatementModel.document_id == DocumentModel.id)
        .where(InstitutionModel.institution_type.in_(_INVESTMENT_TYPES))
        .group_by(InstitutionModel.institution_type)
    )
    return [
        {
            "institution": r.name,
            "institution_type": r.institution_type,
            "doc_count": r.doc_count,
            "earliest_statement": str(r.earliest) if r.earliest else None,
            "latest_statement": str(r.latest) if r.latest else None,
            "missing_recent_data": (str(r.latest) < cutoff) if r.latest else True,
        }
        for r in rows.fetchall()
    ]
