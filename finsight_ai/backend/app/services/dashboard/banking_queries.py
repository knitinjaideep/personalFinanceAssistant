"""
Banking dashboard queries — all queries for the Banking bucket live here.

All functions return plain dicts/lists for direct JSON serialization.
No LLM calls. No inference. Pure SQL + simple Python aggregation.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.models import (
    AccountModel,
    DocumentModel,
    FeeModel,
    InstitutionModel,
    StatementModel,
    TransactionModel,
)

# Banking institution types
_BANKING_TYPES = ["chase", "amex", "discover", "bofa", "marcus"]

# Spend categories to display (ordered for UI)
SPEND_CATEGORIES = [
    "groceries", "restaurants", "subscriptions", "travel",
    "shopping", "gas", "utilities", "healthcare", "entertainment",
    "education", "insurance", "transfers", "fees", "atm_cash", "other",
]


def _dec(value: str | None) -> Decimal:
    if not value:
        return Decimal("0")
    try:
        return Decimal(value)
    except InvalidOperation:
        return Decimal("0")


def _fmt(value: Decimal) -> str:
    return f"{value:,.2f}"


# ── Monthly spend ─────────────────────────────────────────────────────────────

async def banking_spend_by_month(
    session: AsyncSession, months: int = 12
) -> list[dict]:
    """
    Monthly total spend (purchases only, not payments/transfers) for banking accounts.
    Returns one row per (YYYY-MM) for the last N months, sorted chronologically.
    """
    rows = await session.execute(
        text("""
            SELECT
                strftime('%Y-%m', t.transaction_date)  AS month,
                SUM(CAST(t.amount AS REAL))             AS total_spend,
                COUNT(t.id)                             AS txn_count
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE a.institution_type IN ('chase','amex','discover','bofa','marcus')
              AND t.transaction_type NOT IN ('deposit','payment','transfer')
              AND CAST(t.amount AS REAL) > 0
              AND t.transaction_date >= date('now', :offset)
            GROUP BY month
            ORDER BY month
        """),
        {"offset": f"-{months} months"},
    )
    return [
        {
            "month": r[0],
            "total_spend": round(float(r[1] or 0), 2),
            "total_spend_fmt": _fmt(Decimal(str(r[1] or 0))),
            "transaction_count": r[2],
        }
        for r in rows.fetchall()
    ]


# ── Spend by category ─────────────────────────────────────────────────────────

async def banking_spend_by_category(session: AsyncSession) -> list[dict]:
    """
    Total spend grouped by transaction category across all banking accounts.
    Returns rows for all categories (0 for missing categories for consistent charting).
    """
    rows = await session.execute(
        text("""
            SELECT
                COALESCE(t.category, 'other') AS category,
                SUM(CAST(t.amount AS REAL))    AS total,
                COUNT(t.id)                    AS txn_count
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE a.institution_type IN ('chase','amex','discover','bofa','marcus')
              AND t.transaction_type NOT IN ('deposit','payment','transfer')
              AND CAST(t.amount AS REAL) > 0
            GROUP BY category
        """),
    )

    totals: dict[str, dict] = {
        cat: {"category": cat, "total": 0.0, "total_fmt": "0.00", "transaction_count": 0}
        for cat in SPEND_CATEGORIES
    }
    for r in rows.fetchall():
        cat = r[0] if r[0] in totals else "other"
        totals[cat]["total"] += float(r[1] or 0)
        totals[cat]["transaction_count"] += r[2]

    # Reformat amounts and filter empty categories for cleaner charts
    result = []
    for cat in SPEND_CATEGORIES:
        entry = totals[cat]
        entry["total"] = round(entry["total"], 2)
        entry["total_fmt"] = _fmt(Decimal(str(entry["total"])))
        if entry["total"] > 0:
            result.append(entry)

    return sorted(result, key=lambda x: x["total"], reverse=True)


# ── Top merchants ─────────────────────────────────────────────────────────────

async def banking_top_merchants(
    session: AsyncSession, limit: int = 10
) -> list[dict]:
    """
    Top N merchants by total spend across all banking accounts.
    """
    rows = await session.execute(
        text("""
            SELECT
                COALESCE(t.merchant_name, t.description)  AS merchant,
                SUM(CAST(t.amount AS REAL))                AS total,
                COUNT(t.id)                                AS txn_count
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE a.institution_type IN ('chase','amex','discover','bofa','marcus')
              AND t.transaction_type NOT IN ('deposit','payment','transfer')
              AND CAST(t.amount AS REAL) > 0
              AND merchant IS NOT NULL
            GROUP BY merchant
            ORDER BY total DESC
            LIMIT :limit
        """),
        {"limit": limit},
    )
    return [
        {
            "merchant": r[0],
            "total": round(float(r[1] or 0), 2),
            "total_fmt": _fmt(Decimal(str(r[1] or 0))),
            "transaction_count": r[2],
        }
        for r in rows.fetchall()
    ]


# ── Per-card spend summary ────────────────────────────────────────────────────

async def banking_card_spend_summary(session: AsyncSession) -> list[dict]:
    """
    Total spend broken down by account (card) — useful for per-card dashboards.
    Joins DocumentModel.account_product for product labels.
    """
    rows = await session.execute(
        text("""
            SELECT
                a.account_name,
                a.account_type,
                a.institution_type,
                MAX(d.account_product)                  AS product_label,
                SUM(CAST(t.amount AS REAL))             AS total_spend,
                COUNT(t.id)                             AS txn_count,
                MAX(s.period_end)                       AS latest_statement
            FROM transactions t
            JOIN accounts a       ON a.id = t.account_id
            JOIN statements s     ON s.id = t.statement_id
            LEFT JOIN documents d ON d.id = s.document_id
            WHERE a.institution_type IN ('chase','amex','discover','bofa','marcus')
              AND t.transaction_type NOT IN ('deposit','payment','transfer')
              AND CAST(t.amount AS REAL) > 0
            GROUP BY a.id
            ORDER BY total_spend DESC
        """),
    )
    return [
        {
            "account_name": r[0] or r[1],
            "account_type": r[1],
            "institution_type": r[2],
            "product_label": r[3] or r[0] or r[1],
            "total_spend": round(float(r[4] or 0), 2),
            "total_spend_fmt": _fmt(Decimal(str(r[4] or 0))),
            "transaction_count": r[5],
            "latest_statement": str(r[6]) if r[6] else None,
        }
        for r in rows.fetchall()
    ]


# ── Cash flow (inflow vs outflow) ─────────────────────────────────────────────

async def banking_cash_flow(
    session: AsyncSession, months: int = 12
) -> list[dict]:
    """
    Monthly inflow (deposits, credits) vs outflow (purchases, withdrawals).
    Useful for checking accounts.
    """
    rows = await session.execute(
        text("""
            SELECT
                strftime('%Y-%m', t.transaction_date) AS month,
                SUM(CASE WHEN CAST(t.amount AS REAL) > 0
                          THEN CAST(t.amount AS REAL) ELSE 0 END) AS outflow,
                SUM(CASE WHEN CAST(t.amount AS REAL) < 0
                          THEN ABS(CAST(t.amount AS REAL)) ELSE 0 END) AS inflow
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE a.institution_type IN ('chase','bofa','marcus')
              AND a.account_type IN ('checking','savings')
              AND t.transaction_date >= date('now', :offset)
            GROUP BY month
            ORDER BY month
        """),
        {"offset": f"-{months} months"},
    )
    return [
        {
            "month": r[0],
            "outflow": round(float(r[1] or 0), 2),
            "inflow": round(float(r[2] or 0), 2),
            "net": round(float((r[2] or 0) - (r[1] or 0)), 2),
        }
        for r in rows.fetchall()
    ]


# ── Subscriptions ─────────────────────────────────────────────────────────────

async def banking_subscriptions(session: AsyncSession) -> list[dict]:
    """
    Transactions flagged as recurring (is_recurring=True) grouped by merchant.
    """
    rows = await session.execute(
        text("""
            SELECT
                COALESCE(t.merchant_name, t.description) AS merchant,
                t.category,
                AVG(CAST(t.amount AS REAL))               AS avg_amount,
                COUNT(t.id)                               AS occurrences,
                MAX(t.transaction_date)                   AS last_seen
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE a.institution_type IN ('chase','amex','discover','bofa','marcus')
              AND t.is_recurring = 1
            GROUP BY merchant
            ORDER BY avg_amount DESC
        """),
    )
    return [
        {
            "merchant": r[0],
            "category": r[1],
            "avg_monthly_amount": round(float(r[2] or 0), 2),
            "avg_monthly_amount_fmt": _fmt(Decimal(str(r[2] or 0))),
            "occurrences": r[3],
            "last_seen": str(r[4]) if r[4] else None,
        }
        for r in rows.fetchall()
    ]


# ── Document coverage ─────────────────────────────────────────────────────────

async def document_coverage_banking(session: AsyncSession) -> list[dict]:
    """
    Per-institution document count and date range for Banking bucket.
    """
    rows = await session.execute(
        text("""
            SELECT
                i.name,
                i.institution_type,
                COUNT(DISTINCT d.id)    AS doc_count,
                MIN(s.period_start)     AS earliest,
                MAX(s.period_end)       AS latest
            FROM institutions i
            JOIN documents d ON d.institution_type = i.institution_type
            JOIN statements s ON s.document_id = d.id
            WHERE i.institution_type IN ('chase','amex','discover','bofa','marcus')
            GROUP BY i.institution_type
            ORDER BY doc_count DESC
        """),
    )
    return [
        {
            "institution": r[0],
            "institution_type": r[1],
            "doc_count": r[2],
            "earliest_statement": str(r[3]) if r[3] else None,
            "latest_statement": str(r[4]) if r[4] else None,
        }
        for r in rows.fetchall()
    ]
