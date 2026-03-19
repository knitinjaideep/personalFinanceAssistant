"""
Analytics service — pre-built financial analysis queries.

Provides structured analytics answers (not LLM-generated) for:
- Fee totals and trends
- Balance history
- Monthly comparisons
- Recurring charge detection

These are deterministic SQL-backed calculations, not RAG.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AccountModel,
    BalanceSnapshotModel,
    FeeModel,
    InstitutionModel,
    StatementModel,
    TransactionModel,
)

logger = structlog.get_logger(__name__)


@dataclass
class FeeSummary:
    institution: str
    account: str
    total_fees: Decimal
    fee_count: int
    period_start: date
    period_end: date
    categories: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class BalancePoint:
    account_id: str
    account_masked: str
    institution: str
    snapshot_date: date
    total_value: Decimal


@dataclass
class MonthlyComparison:
    period: str           # "YYYY-MM"
    institution: str
    total_fees: Decimal
    total_deposits: Decimal
    total_withdrawals: Decimal
    ending_balance: Decimal | None


class AnalyticsService:
    """Pre-built analytics queries for the frontend dashboards."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_fee_summary(
        self,
        start_date: date,
        end_date: date,
        institution_type: str | None = None,
    ) -> list[FeeSummary]:
        """Aggregate fees by institution and account for a date range."""
        stmt = (
            select(
                InstitutionModel.name.label("institution_name"),
                AccountModel.account_number_masked.label("account"),
                func.sum(func.cast(FeeModel.amount, text("REAL"))).label("total_fees"),
                func.count(FeeModel.id).label("fee_count"),
                FeeModel.fee_category,
            )
            .join(AccountModel, FeeModel.account_id == AccountModel.id)
            .join(InstitutionModel, AccountModel.institution_id == InstitutionModel.id)
            .where(FeeModel.fee_date >= start_date)
            .where(FeeModel.fee_date <= end_date)
            .group_by(
                InstitutionModel.name,
                AccountModel.account_number_masked,
                FeeModel.fee_category,
            )
        )

        if institution_type:
            stmt = stmt.where(InstitutionModel.institution_type == institution_type)

        result = await self._session.execute(stmt)
        rows = result.fetchall()

        # Aggregate by institution+account
        summaries: dict[str, FeeSummary] = {}
        for row in rows:
            key = f"{row.institution_name}::{row.account}"
            if key not in summaries:
                summaries[key] = FeeSummary(
                    institution=row.institution_name,
                    account=row.account,
                    total_fees=Decimal("0"),
                    fee_count=0,
                    period_start=start_date,
                    period_end=end_date,
                )
            summaries[key].total_fees += Decimal(str(row.total_fees or 0))
            summaries[key].fee_count += row.fee_count or 0
            if row.fee_category:
                cat = summaries[key].categories
                cat[row.fee_category] = cat.get(row.fee_category, Decimal("0")) + Decimal(
                    str(row.total_fees or 0)
                )

        return sorted(summaries.values(), key=lambda x: x.total_fees, reverse=True)

    async def get_balance_history(
        self,
        account_id: str | None = None,
        institution_type: str | None = None,
        limit: int = 24,
    ) -> list[BalancePoint]:
        """Return balance snapshots over time for charting."""
        stmt = (
            select(
                AccountModel.id.label("account_id"),
                AccountModel.account_number_masked.label("account_masked"),
                InstitutionModel.name.label("institution"),
                BalanceSnapshotModel.snapshot_date,
                BalanceSnapshotModel.total_value,
            )
            .join(AccountModel, BalanceSnapshotModel.account_id == AccountModel.id)
            .join(InstitutionModel, AccountModel.institution_id == InstitutionModel.id)
            .order_by(BalanceSnapshotModel.snapshot_date.desc())
            .limit(limit)
        )

        if account_id:
            stmt = stmt.where(BalanceSnapshotModel.account_id == account_id)
        if institution_type:
            stmt = stmt.where(InstitutionModel.institution_type == institution_type)

        result = await self._session.execute(stmt)
        return [
            BalancePoint(
                account_id=row.account_id,
                account_masked=row.account_masked,
                institution=row.institution,
                snapshot_date=row.snapshot_date,
                total_value=Decimal(str(row.total_value or 0)),
            )
            for row in result.fetchall()
        ]

    async def get_missing_statements(self, year: int) -> list[dict]:
        """
        Detect which months are missing statements for each account.

        Compares expected months (all 12) against periods in the DB.
        """
        stmt = select(
            AccountModel.id,
            AccountModel.account_number_masked,
            InstitutionModel.name,
            StatementModel.period_start,
            StatementModel.period_end,
        ).join(
            StatementModel, StatementModel.account_id == AccountModel.id
        ).join(
            InstitutionModel, AccountModel.institution_id == InstitutionModel.id
        ).where(
            func.strftime("%Y", StatementModel.period_end) == str(year)
        )

        result = await self._session.execute(stmt)
        rows = result.fetchall()

        # Group covered months by account
        covered: dict[str, set[int]] = {}
        account_info: dict[str, dict] = {}
        for row in rows:
            acct_key = row[0]
            covered.setdefault(acct_key, set())
            covered[acct_key].add(row.period_start.month)
            account_info[acct_key] = {
                "account": row.account_number_masked,
                "institution": row.name,
            }

        # Find missing months
        missing: list[dict] = []
        for acct_key, info in account_info.items():
            all_months = set(range(1, 13))
            missing_months = sorted(all_months - covered.get(acct_key, set()))
            if missing_months:
                missing.append(
                    {
                        **info,
                        "year": year,
                        "missing_months": missing_months,
                        "missing_month_names": [
                            date(year, m, 1).strftime("%B") for m in missing_months
                        ],
                    }
                )
        return missing
