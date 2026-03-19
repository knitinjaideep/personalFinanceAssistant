"""
Metrics service — Phase 2.8 longitudinal derived metrics.

Responsibilities:
1. ``generate_for_statement()`` — called after a statement is processed/approved.
   Computes monthly aggregates from the canonical SQL tables and upserts
   ``DerivedMonthlyMetricModel`` rows.

2. ``get_net_worth_trend()`` — returns monthly total_value across all accounts
   (or filtered by institution/account) suitable for a time-series chart.

3. ``get_spending_trend()`` — returns monthly fee + withdrawal totals.

4. ``get_monthly_summary()`` — returns a single-month snapshot across all accounts.

5. ``recompute_all()`` — full recompute triggered on demand.

Design notes:
- Uses SQLAlchemy 2 async text queries for aggregation (faster than ORM for
  set-oriented operations).
- Monetary arithmetic is done in Python (Decimal) to avoid SQLite REAL precision.
- All monetary results are returned as Decimal strings, not floats.
- Idempotent: generates stable deterministic rows keyed by (account_id, month_start).
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DerivedMonthlyMetricModel

logger = structlog.get_logger(__name__)

_ZERO = Decimal("0.00")


def _safe_decimal(value: Any) -> Decimal:
    """Convert a raw SQL value to Decimal; return 0 on failure."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return _ZERO


def _new_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


# ── Generation ────────────────────────────────────────────────────────────────

class MetricsService:
    """
    Generates and queries derived monthly financial metrics.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Core generation ────────────────────────────────────────────────────────

    async def generate_for_statement(self, statement_id: str, source: str = "ingestion") -> int:
        """
        Compute and upsert derived monthly metrics for a single statement.

        Returns the number of metric rows written.
        """
        # Fetch statement metadata
        stmt_row = await self._session.execute(
            text(
                "SELECT account_id, institution_id, period_start, period_end "
                "FROM statements WHERE id = :id"
            ),
            {"id": statement_id},
        )
        row = stmt_row.fetchone()
        if not row:
            logger.warning("metrics.generate.statement_not_found", statement_id=statement_id)
            return 0

        account_id, institution_id = row[0], row[1]
        period_start = date.fromisoformat(str(row[2]))
        period_end = date.fromisoformat(str(row[3]))

        # Generate one metric row per calendar month in the statement period
        months = self._months_in_range(period_start, period_end)
        written = 0

        for month_start in months:
            month_end = date(
                month_start.year,
                month_start.month,
                calendar.monthrange(month_start.year, month_start.month)[1],
            )

            metric = await self._compute_month(
                account_id=account_id,
                institution_id=institution_id,
                statement_id=statement_id,
                month_start=month_start,
                month_end=month_end,
                source=source,
            )

            await self._upsert_metric(metric)
            written += 1

        await self._session.commit()
        logger.info(
            "metrics.generate.done",
            statement_id=statement_id,
            months_written=written,
        )
        return written

    async def recompute_all(self) -> int:
        """Recompute derived metrics for every statement in the database."""
        result = await self._session.execute(text("SELECT id FROM statements"))
        statement_ids = [r[0] for r in result.fetchall()]
        total = 0
        for sid in statement_ids:
            total += await self.generate_for_statement(sid, source="recompute")
        logger.info("metrics.recompute_all.done", total_rows=total)
        return total

    # ── Trend queries ──────────────────────────────────────────────────────────

    async def get_net_worth_trend(
        self,
        account_id: str | None = None,
        institution_id: str | None = None,
        months: int = 24,
    ) -> list[dict]:
        """
        Return monthly net worth (sum of total_value across accounts) for the
        last ``months`` calendar months.

        Returns list of {month, year, total_value, institution_type, account_id}.
        Sorted ascending by month_start.
        """
        filters = ["1=1"]
        params: dict = {"months": months}

        if account_id:
            filters.append("m.account_id = :account_id")
            params["account_id"] = account_id
        if institution_id:
            filters.append("m.institution_id = :institution_id")
            params["institution_id"] = institution_id

        where = " AND ".join(filters)

        query = text(f"""
            SELECT
                m.month_start,
                m.year,
                m.month,
                m.account_id,
                a.account_number_masked AS account_label,
                i.institution_type,
                i.name AS institution_name,
                m.total_value,
                m.invested_value,
                m.cash_value,
                m.unrealized_gain_loss
            FROM derived_monthly_metrics m
            JOIN accounts a ON a.id = m.account_id
            JOIN institutions i ON i.id = m.institution_id
            WHERE {where}
              AND m.total_value IS NOT NULL
            ORDER BY m.month_start ASC
            LIMIT :months * 20
        """)

        result = await self._session.execute(query, params)
        cols = list(result.keys())
        rows = [dict(zip(cols, r)) for r in result.fetchall()]

        # Group by month, aggregate across accounts
        monthly: dict[str, dict] = {}
        for r in rows:
            key = r["month_start"]
            if key not in monthly:
                monthly[key] = {
                    "month_start": key,
                    "year": r["year"],
                    "month": r["month"],
                    "total_value": _ZERO,
                    "accounts": [],
                }
            monthly[key]["total_value"] += _safe_decimal(r["total_value"])
            monthly[key]["accounts"].append(
                {
                    "account_id": r["account_id"],
                    "account_label": r["account_label"],
                    "institution_type": r["institution_type"],
                    "total_value": r["total_value"],
                }
            )

        output = []
        for key in sorted(monthly.keys()):
            m = monthly[key]
            output.append(
                {
                    "month_start": str(m["month_start"]),
                    "year": m["year"],
                    "month": m["month"],
                    "total_value": str(m["total_value"]),
                    "accounts": m["accounts"],
                }
            )
        return output[-months:]

    async def get_spending_trend(
        self,
        account_id: str | None = None,
        institution_id: str | None = None,
        months: int = 12,
    ) -> list[dict]:
        """
        Return monthly spending (fees + withdrawals) and deposit totals.

        Returns list of {month_start, year, month, total_fees, total_withdrawals,
        total_deposits, net_cash_flow}.
        """
        filters = ["1=1"]
        params: dict = {}

        if account_id:
            filters.append("account_id = :account_id")
            params["account_id"] = account_id
        if institution_id:
            filters.append("institution_id = :institution_id")
            params["institution_id"] = institution_id

        where = " AND ".join(filters)

        query = text(f"""
            SELECT
                month_start, year, month,
                SUM(CAST(COALESCE(total_fees, '0') AS REAL)) AS total_fees,
                SUM(CAST(COALESCE(total_withdrawals, '0') AS REAL)) AS total_withdrawals,
                SUM(CAST(COALESCE(total_deposits, '0') AS REAL)) AS total_deposits,
                SUM(CAST(COALESCE(net_cash_flow, '0') AS REAL)) AS net_cash_flow,
                SUM(CAST(COALESCE(total_dividends, '0') AS REAL)) AS total_dividends
            FROM derived_monthly_metrics
            WHERE {where}
            GROUP BY month_start, year, month
            ORDER BY month_start ASC
            LIMIT :limit
        """)
        params["limit"] = months * 4

        result = await self._session.execute(query, params)
        cols = list(result.keys())
        rows = [dict(zip(cols, r)) for r in result.fetchall()]

        output = []
        for r in rows:
            output.append(
                {
                    "month_start": str(r["month_start"]),
                    "year": r["year"],
                    "month": r["month"],
                    "total_fees": str(round(Decimal(str(r["total_fees"] or 0)), 2)),
                    "total_withdrawals": str(round(Decimal(str(r["total_withdrawals"] or 0)), 2)),
                    "total_deposits": str(round(Decimal(str(r["total_deposits"] or 0)), 2)),
                    "net_cash_flow": str(round(Decimal(str(r["net_cash_flow"] or 0)), 2)),
                    "total_dividends": str(round(Decimal(str(r["total_dividends"] or 0)), 2)),
                }
            )
        return output[-months:]

    async def get_monthly_summary(self, year: int, month: int) -> dict:
        """
        Return a cross-account summary for a single calendar month.
        """
        query = text("""
            SELECT
                m.account_id,
                a.account_number_masked AS account_label,
                i.institution_type,
                i.name AS institution_name,
                m.total_value,
                m.total_fees,
                m.total_deposits,
                m.total_withdrawals,
                m.net_cash_flow,
                m.transaction_count,
                m.holding_count
            FROM derived_monthly_metrics m
            JOIN accounts a ON a.id = m.account_id
            JOIN institutions i ON i.id = m.institution_id
            WHERE m.year = :year AND m.month = :month
            ORDER BY CAST(COALESCE(m.total_value, '0') AS REAL) DESC
        """)

        result = await self._session.execute(query, {"year": year, "month": month})
        cols = list(result.keys())
        accounts = [dict(zip(cols, r)) for r in result.fetchall()]

        total_value = sum(_safe_decimal(a["total_value"]) for a in accounts if a["total_value"])
        total_fees = sum(_safe_decimal(a["total_fees"]) for a in accounts if a["total_fees"])

        return {
            "year": year,
            "month": month,
            "account_count": len(accounts),
            "total_value": str(total_value),
            "total_fees": str(total_fees),
            "accounts": accounts,
        }

    async def list_available_months(self) -> list[dict]:
        """Return distinct (year, month) pairs that have metric data, newest first."""
        result = await self._session.execute(
            text(
                "SELECT DISTINCT year, month, month_start FROM derived_monthly_metrics "
                "ORDER BY month_start DESC LIMIT 36"
            )
        )
        return [{"year": r[0], "month": r[1], "month_start": str(r[2])} for r in result.fetchall()]

    # ── Private helpers ────────────────────────────────────────────────────────

    def _months_in_range(self, start: date, end: date) -> list[date]:
        """Return the first-of-month dates for every month in [start, end]."""
        months: list[date] = []
        cur = date(start.year, start.month, 1)
        end_anchor = date(end.year, end.month, 1)
        while cur <= end_anchor:
            months.append(cur)
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)
        return months

    async def _compute_month(
        self,
        account_id: str,
        institution_id: str,
        statement_id: str,
        month_start: date,
        month_end: date,
        source: str,
    ) -> DerivedMonthlyMetricModel:
        """Aggregate one calendar month of data into a metric row."""

        # Balance snapshot (latest in the month)
        bal = await self._session.execute(
            text("""
                SELECT total_value, cash_value, invested_value, unrealized_gain_loss
                FROM balance_snapshots
                WHERE account_id = :account_id
                  AND snapshot_date >= :start AND snapshot_date <= :end
                ORDER BY snapshot_date DESC LIMIT 1
            """),
            {"account_id": account_id, "start": month_start, "end": month_end},
        )
        bal_row = bal.fetchone()

        # Transaction aggregates
        txn = await self._session.execute(
            text("""
                SELECT
                    SUM(CASE WHEN transaction_type IN ('deposit','transfer')
                             THEN CAST(amount AS REAL) ELSE 0 END) AS total_deposits,
                    SUM(CASE WHEN transaction_type = 'withdrawal'
                             THEN ABS(CAST(amount AS REAL)) ELSE 0 END) AS total_withdrawals,
                    SUM(CASE WHEN transaction_type = 'dividend'
                             THEN CAST(amount AS REAL) ELSE 0 END) AS total_dividends,
                    COUNT(*) AS transaction_count
                FROM transactions
                WHERE account_id = :account_id
                  AND transaction_date >= :start AND transaction_date <= :end
            """),
            {"account_id": account_id, "start": month_start, "end": month_end},
        )
        txn_row = txn.fetchone()

        # Fee aggregate
        fee = await self._session.execute(
            text("""
                SELECT
                    SUM(CAST(amount AS REAL)) AS total_fees,
                    COUNT(*) AS fee_count
                FROM fees
                WHERE account_id = :account_id
                  AND fee_date >= :start AND fee_date <= :end
            """),
            {"account_id": account_id, "start": month_start, "end": month_end},
        )
        fee_row = fee.fetchone()

        # Holdings summary
        hold = await self._session.execute(
            text("""
                SELECT COUNT(*) AS holding_count,
                       symbol AS top_symbol,
                       market_value AS top_value
                FROM holdings
                WHERE account_id = :account_id
                  AND statement_id = :statement_id
                ORDER BY CAST(market_value AS REAL) DESC
                LIMIT 1
            """),
            {"account_id": account_id, "statement_id": statement_id},
        )
        hold_row = hold.fetchone()

        # Compute net cash flow
        deposits = _safe_decimal(txn_row[0] if txn_row else None)
        withdrawals = _safe_decimal(txn_row[1] if txn_row else None)
        dividends = _safe_decimal(txn_row[2] if txn_row else None)
        fees = _safe_decimal(fee_row[0] if fee_row else None)
        net_cash_flow = deposits - withdrawals - fees

        return DerivedMonthlyMetricModel(
            id=_new_uuid(),
            account_id=account_id,
            institution_id=institution_id,
            statement_id=statement_id,
            month_start=month_start,
            year=month_start.year,
            month=month_start.month,
            # Balance
            total_value=str(bal_row[0]) if bal_row and bal_row[0] else None,
            cash_value=str(bal_row[1]) if bal_row and bal_row[1] else None,
            invested_value=str(bal_row[2]) if bal_row and bal_row[2] else None,
            unrealized_gain_loss=str(bal_row[3]) if bal_row and bal_row[3] else None,
            # Flows
            total_deposits=str(deposits) if txn_row else None,
            total_withdrawals=str(withdrawals) if txn_row else None,
            total_dividends=str(dividends) if txn_row else None,
            total_fees=str(fees) if fee_row else None,
            net_cash_flow=str(net_cash_flow),
            transaction_count=int(txn_row[3]) if txn_row and txn_row[3] else 0,
            fee_count=int(fee_row[1]) if fee_row and fee_row[1] else 0,
            # Holdings
            holding_count=int(hold_row[0]) if hold_row and hold_row[0] else 0,
            top_holding_symbol=str(hold_row[1]) if hold_row and hold_row[1] else None,
            top_holding_value=str(hold_row[2]) if hold_row and hold_row[2] else None,
            source=source,
        )

    async def _upsert_metric(self, metric: DerivedMonthlyMetricModel) -> None:
        """
        Insert or replace a metric row keyed by (account_id, month_start).
        SQLite REPLACE INTO handles the upsert semantics.
        """
        await self._session.execute(
            text("""
                DELETE FROM derived_monthly_metrics
                WHERE account_id = :account_id AND month_start = :month_start
            """),
            {"account_id": metric.account_id, "month_start": metric.month_start},
        )
        self._session.add(metric)
