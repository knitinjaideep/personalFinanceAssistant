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

async def investment_portfolio_summary(
    session: AsyncSession, as_of: date | None = None,
) -> dict:
    """
    Returns the total portfolio value per account plus an overall total, as of
    a point in time.

    Uses the most recent balance_snapshot per account to avoid double-counting
    when multiple statements exist for the same account.

    `as_of` (PR 05 — Global Period Filter) selects the most recent snapshot
    with `snapshot_date <= as_of` instead of the most recent snapshot overall,
    i.e. the standard "balance as of <date>" reading of a point-in-time figure
    under a period filter. Accounts with no snapshot at or before `as_of` are
    honestly omitted rather than back-filled with a later value. Omitting
    `as_of` (the default) preserves the original latest-ever behavior.
    """
    # Subquery: latest snapshot_date per account (bounded by `as_of` when given)
    latest_sub_q = (
        select(
            BalanceSnapshotModel.account_id,
            func.max(BalanceSnapshotModel.snapshot_date).label("max_date"),
        )
        .join(AccountModel, BalanceSnapshotModel.account_id == AccountModel.id)
        .where(AccountModel.institution_type.in_(_INVESTMENT_TYPES))
    )
    if as_of is not None:
        latest_sub_q = latest_sub_q.where(BalanceSnapshotModel.snapshot_date <= as_of)
    latest_sub = latest_sub_q.group_by(BalanceSnapshotModel.account_id).subquery()

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
    stmt_q = (
        select(
            StatementModel.account_id,
            func.max(StatementModel.period_end).label("latest_stmt"),
        )
        .join(AccountModel, StatementModel.account_id == AccountModel.id)
        .where(AccountModel.institution_type.in_(_INVESTMENT_TYPES))
    )
    if as_of is not None:
        stmt_q = stmt_q.where(StatementModel.period_end <= as_of)
    stmt_rows = await session.execute(stmt_q.group_by(StatementModel.account_id))
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

def _latest_statement_subquery(as_of: date | None):
    """Most recent statement `period_end` per investment account, optionally
    bounded to statements that had already closed on/before `as_of` (PR 05 —
    "holdings as of <date>"). Shared by both holdings queries so they can
    never drift apart."""
    q = (
        select(
            StatementModel.account_id,
            func.max(StatementModel.period_end).label("max_end"),
        )
        .join(AccountModel, StatementModel.account_id == AccountModel.id)
        .where(AccountModel.institution_type.in_(_INVESTMENT_TYPES))
    )
    if as_of is not None:
        q = q.where(StatementModel.period_end <= as_of)
    return q.group_by(StatementModel.account_id).subquery()


async def top_holdings_by_value(
    session: AsyncSession, limit: int = 10, as_of: date | None = None,
) -> list[dict]:
    """
    Top N holdings by market value from the most recent statement per account.

    Returns a flat list sorted by market_value descending.

    `as_of` (PR 05) reads holdings from the most recent statement whose
    `period_end <= as_of` — the "holdings as of <date>" reading of this
    point-in-time figure under a period filter. Omitting it preserves the
    original latest-ever behavior.
    """
    latest_stmt = _latest_statement_subquery(as_of)

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
    session: AsyncSession, limit: int = 10, direction: str = "gain",
    as_of: date | None = None,
) -> list[dict]:
    """
    Top N holdings by unrealized gain (direction='gain') or loss (direction='loss').

    `as_of` (PR 05) — same "holdings as of <date>" semantics as
    `top_holdings_by_value`.
    """
    latest_stmt = _latest_statement_subquery(as_of)

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


async def allocation_by_account(
    session: AsyncSession, as_of: date | None = None,
) -> list[dict]:
    """
    Portfolio allocation (% of total) broken down by account.
    Uses latest market_value per account from balance_snapshots.

    `as_of` (PR 05) is forwarded to `investment_portfolio_summary` so the
    denominator and the per-account numerators always come from the same
    point in time — never a mix of as-of and latest-ever values.
    """
    summary = await investment_portfolio_summary(session, as_of=as_of)
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

async def balance_history_by_account(
    session: AsyncSession, date_from: date | None = None, date_to: date | None = None,
) -> list[dict]:
    """
    Balance snapshots per account for the timeline chart.
    Returns one row per (account, snapshot_date) sorted chronologically.

    `date_from`/`date_to` (PR 05 unified period contract) narrow to an
    inclusive `snapshot_date` range; omitted (the default) preserves the
    original full-history behavior.
    """
    query = (
        select(
            BalanceSnapshotModel.snapshot_date,
            BalanceSnapshotModel.total_value,
            AccountModel.account_name,
            AccountModel.account_type,
            AccountModel.institution_type,
        )
        .join(AccountModel, BalanceSnapshotModel.account_id == AccountModel.id)
        .where(AccountModel.institution_type.in_(_INVESTMENT_TYPES))
    )
    if date_from is not None:
        query = query.where(BalanceSnapshotModel.snapshot_date >= date_from)
    if date_to is not None:
        query = query.where(BalanceSnapshotModel.snapshot_date <= date_to)
    query = query.order_by(BalanceSnapshotModel.snapshot_date)

    rows = await session.execute(query)
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

async def investment_fees_summary(
    session: AsyncSession, date_from: date | None = None, date_to: date | None = None,
) -> dict:
    """
    Total investment fees by category (advisory, management, etc.).

    `date_from`/`date_to` (PR 05) narrow the totals/by_category breakdown to
    an inclusive `fee_date` range; omitted (the default) preserves the
    original all-time behavior. `recent_trend` intentionally stays a fixed
    rolling 6-month window regardless of the selected period — it's a
    trend-shape indicator ("recent 3mo vs prior 3mo"), not a total, and a
    short selected range would make the trend comparison meaningless.
    """
    query = (
        select(
            FeeModel.fee_category,
            func.count(FeeModel.id).label("count"),
            func.sum(
                cast(FeeModel.amount, Float)
            ).label("total"),
        )
        .join(AccountModel, FeeModel.account_id == AccountModel.id)
        .where(AccountModel.institution_type.in_(["morgan_stanley", "etrade"]))
    )
    if date_from is not None:
        query = query.where(FeeModel.fee_date >= date_from)
    if date_to is not None:
        query = query.where(FeeModel.fee_date <= date_to)
    query = query.group_by(FeeModel.fee_category)

    rows = await session.execute(query)

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
