"""
InvestmentsAnalyticsService — bucket-aware analytics for the INVESTMENTS bucket.

Returns rich portfolio overviews, holding breakdowns, fee trends, and
period-over-period changes.  Every public method returns
``PartialResult[T]`` and NEVER raises — warnings are surfaced instead so
the API layer can return ``partial=True`` responses rather than HTTP 500s.

Design rules:
- All monetary arithmetic uses Decimal; no float.
- Queries hit the canonical tables (holdings, balance_snapshots, fees,
  statements, accounts) — never the staged/review tables.
- Account/date filters are applied as early as possible to minimise
  data loaded into memory.
- If a query returns no rows, return an appropriate empty structure with
  a warning rather than raising.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Generic, List, Optional, TypeVar

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AccountModel,
    BalanceSnapshotModel,
    FeeModel,
    HoldingModel,
    InstitutionModel,
    StatementModel,
)
from app.domain.enums import BucketType, ExtractionStatus, INVESTMENTS_ACCOUNT_TYPES

logger = structlog.get_logger(__name__)

T = TypeVar("T")

_ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# PartialResult container
# ---------------------------------------------------------------------------

@dataclass
class PartialResult(Generic[T]):
    """Wraps a service result with an optional warning list.

    ``partial`` is True when data is present but incomplete (e.g., some
    accounts missing, date range trimmed, etc.).
    """

    data: T
    warnings: List[str] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        return len(self.warnings) > 0


# ---------------------------------------------------------------------------
# Value objects / data transfer objects
# ---------------------------------------------------------------------------

@dataclass
class AccountSummary:
    """High-level summary of a single investment account."""

    account_id: str
    account_name: str
    account_type: str
    institution: str
    current_value: Decimal
    as_of_date: Optional[date]
    # Percentage of total portfolio value (0–100)
    portfolio_pct: Decimal


@dataclass
class HoldingRow:
    """A single holding row for the holdings table."""

    symbol: Optional[str]
    description: str
    quantity: Optional[Decimal]
    price: Optional[Decimal]
    market_value: Decimal
    cost_basis: Optional[Decimal]
    unrealized_gain_loss: Optional[Decimal]
    unrealized_pct: Optional[Decimal]  # gain/loss as pct of cost basis
    asset_class: Optional[str]
    account_id: str
    account_name: str
    institution: str


@dataclass
class MonthlyFee:
    """Aggregated fees for one calendar month."""

    year: int
    month: int
    total_fees: Decimal
    fee_count: int
    by_category: dict[str, Decimal]


@dataclass
class BalancePoint:
    """A single data point for the portfolio balance trend chart."""

    snapshot_date: date
    total_value: Decimal
    account_id: str
    account_name: str
    institution: str


@dataclass
class PeriodChange:
    """What changed between the latest and previous statement for an account."""

    account_id: str
    account_name: str
    institution: str
    previous_value: Optional[Decimal]
    current_value: Decimal
    change_amount: Optional[Decimal]
    change_pct: Optional[Decimal]
    period_start: Optional[date]
    period_end: Optional[date]


@dataclass
class InvestmentsOverview:
    """Top-level investments analytics returned to the API layer."""

    total_portfolio_value: Decimal
    accounts: List[AccountSummary]
    holdings_breakdown: List[HoldingRow]
    fee_trend: List[MonthlyFee]
    balance_trend: List[BalancePoint]
    period_changes: List[PeriodChange]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class InvestmentsAnalyticsService:
    """Bucket-aware analytics service for the INVESTMENTS bucket.

    All methods accept an ``AsyncSession`` and optional filters. They
    return ``PartialResult[T]`` — never raise.

    Usage::

        svc = InvestmentsAnalyticsService(session)
        result = await svc.get_overview(
            account_ids=["..."],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        overview = result.data     # InvestmentsOverview
        warnings = result.warnings  # List[str]
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_overview(
        self,
        account_ids: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> PartialResult[InvestmentsOverview]:
        """Return a complete investments overview.

        Never raises.  All sub-queries are individually guarded and
        contribute warnings on failure.
        """
        warnings: List[str] = []
        end_date = end_date or date.today()
        start_date = start_date or (end_date - timedelta(days=365))

        # 1. Resolve investment accounts
        accounts_result = await self._get_investment_accounts(account_ids, warnings)

        if not accounts_result:
            warnings.append("No investment accounts found in the database.")
            return PartialResult(
                data=InvestmentsOverview(
                    total_portfolio_value=_ZERO,
                    accounts=[],
                    holdings_breakdown=[],
                    fee_trend=[],
                    balance_trend=[],
                    period_changes=[],
                ),
                warnings=warnings,
            )

        account_id_strs = [a.id for a in accounts_result]
        inst_map = await self._build_institution_map(accounts_result)

        # 2. Latest balance snapshot per account → portfolio total
        latest_balances = await self._latest_balance_per_account(
            account_id_strs, end_date, warnings
        )

        # 3. Account summaries
        total_value = sum(
            (b.total_value_decimal for b in latest_balances.values()), _ZERO
        )
        account_summaries = self._build_account_summaries(
            accounts_result, inst_map, latest_balances, total_value
        )

        # 4. Holdings breakdown (most recent statement per account)
        holdings_result = await self._get_latest_holdings(
            account_id_strs, end_date, warnings
        )

        # 5. Fee trend (monthly buckets in range)
        fee_trend = await self._get_fee_trend(
            account_id_strs, start_date, end_date, warnings
        )

        # 6. Balance trend (all snapshots in range)
        balance_trend = await self._get_balance_trend(
            account_id_strs, start_date, end_date, inst_map, accounts_result, warnings
        )

        # 7. Period changes (current vs previous statement)
        period_changes = await self._get_period_changes(
            account_id_strs, inst_map, accounts_result, warnings
        )

        overview = InvestmentsOverview(
            total_portfolio_value=total_value,
            accounts=account_summaries,
            holdings_breakdown=holdings_result,
            fee_trend=fee_trend,
            balance_trend=balance_trend,
            period_changes=period_changes,
        )

        logger.info(
            "investments_analytics.overview_built",
            accounts=len(accounts_result),
            total_value=str(total_value),
            warnings=len(warnings),
        )
        return PartialResult(data=overview, warnings=warnings)

    async def get_portfolio_trend(
        self,
        account_ids: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> PartialResult[List[BalancePoint]]:
        """Return portfolio balance trend (one point per snapshot date per account)."""
        warnings: List[str] = []
        end_date = end_date or date.today()
        start_date = start_date or (end_date - timedelta(days=365))

        accounts_result = await self._get_investment_accounts(account_ids, warnings)
        if not accounts_result:
            warnings.append("No investment accounts found.")
            return PartialResult(data=[], warnings=warnings)

        account_id_strs = [a.id for a in accounts_result]
        inst_map = await self._build_institution_map(accounts_result)
        points = await self._get_balance_trend(
            account_id_strs, start_date, end_date, inst_map, accounts_result, warnings
        )
        return PartialResult(data=points, warnings=warnings)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_investment_accounts(
        self,
        account_ids: Optional[List[str]],
        warnings: List[str],
    ) -> List[AccountModel]:
        """Load all investment accounts, optionally filtered by ID list."""
        try:
            stmt = select(AccountModel).where(
                AccountModel.account_type.in_(
                    [at.value for at in INVESTMENTS_ACCOUNT_TYPES]
                )
            )
            if account_ids:
                stmt = stmt.where(AccountModel.id.in_(account_ids))
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as exc:  # noqa: BLE001
            logger.warning("investments_analytics.account_query_failed", error=str(exc))
            warnings.append(f"Could not load investment accounts: {exc}")
            return []

    async def _build_institution_map(
        self, accounts: List[AccountModel]
    ) -> dict[str, str]:
        """Return {account_id: institution_name} from the institutions table."""
        inst_ids = list({a.institution_id for a in accounts if a.institution_id})
        if not inst_ids:
            return {}
        try:
            result = await self._session.execute(
                select(InstitutionModel).where(InstitutionModel.id.in_(inst_ids))
            )
            insts = result.scalars().all()
            id_to_name: dict[str, str] = {i.id: i.name for i in insts}
            # Build account → institution name map
            return {
                a.id: id_to_name.get(a.institution_id or "", "Unknown")
                for a in accounts
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("investments_analytics.institution_map_failed", error=str(exc))
            return {a.id: "Unknown" for a in accounts}

    @dataclass
    class _BalanceInfo:
        total_value_decimal: Decimal
        as_of_date: Optional[date]

    async def _latest_balance_per_account(
        self,
        account_ids: List[str],
        as_of: date,
        warnings: List[str],
    ) -> dict[str, "_InvestmentsAnalyticsService._BalanceInfo"]:  # type: ignore[name-defined]
        """Return latest balance snapshot per account on or before *as_of*."""
        result: dict[str, InvestmentsAnalyticsService._BalanceInfo] = {}
        if not account_ids:
            return result
        try:
            # Subquery: max snapshot_date per account up to as_of
            subq = (
                select(
                    BalanceSnapshotModel.account_id,
                    func.max(BalanceSnapshotModel.snapshot_date).label("max_date"),
                )
                .where(BalanceSnapshotModel.account_id.in_(account_ids))
                .where(BalanceSnapshotModel.snapshot_date <= as_of)
                .group_by(BalanceSnapshotModel.account_id)
                .subquery()
            )
            rows = await self._session.execute(
                select(BalanceSnapshotModel).join(
                    subq,
                    (BalanceSnapshotModel.account_id == subq.c.account_id)
                    & (BalanceSnapshotModel.snapshot_date == subq.c.max_date),
                )
            )
            for snap in rows.scalars().all():
                try:
                    val = Decimal(snap.total_value)
                except (InvalidOperation, TypeError):
                    warnings.append(
                        f"Invalid balance value for account {snap.account_id}: "
                        f"{snap.total_value!r}"
                    )
                    val = _ZERO
                result[snap.account_id] = InvestmentsAnalyticsService._BalanceInfo(
                    total_value_decimal=val,
                    as_of_date=snap.snapshot_date,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("investments_analytics.balance_query_failed", error=str(exc))
            warnings.append(f"Balance snapshot query failed: {exc}")
        return result

    def _build_account_summaries(
        self,
        accounts: List[AccountModel],
        inst_map: dict[str, str],
        latest_balances: dict[str, "_InvestmentsAnalyticsService._BalanceInfo"],  # type: ignore[name-defined]
        total_value: Decimal,
    ) -> List[AccountSummary]:
        summaries: List[AccountSummary] = []
        for acc in accounts:
            balance_info = latest_balances.get(acc.id)
            current_value = balance_info.total_value_decimal if balance_info else _ZERO
            as_of = balance_info.as_of_date if balance_info else None
            pct = (
                (current_value / total_value * 100).quantize(Decimal("0.01"))
                if total_value > _ZERO
                else _ZERO
            )
            summaries.append(
                AccountSummary(
                    account_id=acc.id,
                    account_name=acc.account_name or acc.account_type or "Unknown",
                    account_type=acc.account_type or "UNKNOWN",
                    institution=inst_map.get(acc.id, "Unknown"),
                    current_value=current_value,
                    as_of_date=as_of,
                    portfolio_pct=pct,
                )
            )
        # Sort by current_value descending
        summaries.sort(key=lambda s: s.current_value, reverse=True)
        return summaries

    async def _get_latest_holdings(
        self,
        account_ids: List[str],
        as_of: date,
        warnings: List[str],
    ) -> List[HoldingRow]:
        """Return holdings from the most recent statement per account."""
        if not account_ids:
            return []
        try:
            # Latest statement per account up to as_of
            subq = (
                select(
                    StatementModel.account_id,
                    func.max(StatementModel.period_end).label("max_end"),
                )
                .where(StatementModel.account_id.in_(account_ids))
                .where(StatementModel.period_end <= as_of)
                .where(
                    StatementModel.extraction_status.in_(
                        [ExtractionStatus.SUCCESS.value, ExtractionStatus.PARTIAL.value]
                    )
                )
                .group_by(StatementModel.account_id)
                .subquery()
            )
            stmt_rows = await self._session.execute(
                select(StatementModel).join(
                    subq,
                    (StatementModel.account_id == subq.c.account_id)
                    & (StatementModel.period_end == subq.c.max_end),
                )
            )
            latest_stmts = {s.account_id: s.id for s in stmt_rows.scalars().all()}

            if not latest_stmts:
                warnings.append("No statements found for investment accounts in date range.")
                return []

            # Load holdings for those statements
            holdings_rows = await self._session.execute(
                select(HoldingModel, AccountModel)
                .join(AccountModel, HoldingModel.account_id == AccountModel.id)
                .where(HoldingModel.statement_id.in_(list(latest_stmts.values())))
            )

            # Also need institution names
            acc_ids_in_result = list(latest_stmts.keys())
            acc_result = await self._session.execute(
                select(AccountModel, InstitutionModel)
                .join(InstitutionModel, AccountModel.institution_id == InstitutionModel.id, isouter=True)
                .where(AccountModel.id.in_(acc_ids_in_result))
            )
            acc_inst_map: dict[str, tuple[str, str]] = {}
            for acc, inst in acc_result:
                acc_inst_map[acc.id] = (
                    acc.account_name or acc.account_type or "Unknown",
                    inst.name if inst else "Unknown",
                )

            rows: List[HoldingRow] = []
            for holding, account in holdings_rows:
                try:
                    market_value = Decimal(holding.market_value)
                except (InvalidOperation, TypeError):
                    market_value = _ZERO

                acc_name, inst_name = acc_inst_map.get(
                    holding.account_id, ("Unknown", "Unknown")
                )

                def _safe_decimal(v: str | None) -> Optional[Decimal]:
                    if v is None:
                        return None
                    try:
                        return Decimal(v)
                    except (InvalidOperation, TypeError):
                        return None

                cost_basis = _safe_decimal(holding.cost_basis)
                unrealized = _safe_decimal(holding.unrealized_gain_loss)
                unrealized_pct: Optional[Decimal] = None
                if cost_basis and cost_basis != _ZERO and unrealized is not None:
                    unrealized_pct = (unrealized / cost_basis * 100).quantize(
                        Decimal("0.01")
                    )

                rows.append(
                    HoldingRow(
                        symbol=holding.symbol,
                        description=holding.description or "",
                        quantity=_safe_decimal(holding.quantity),
                        price=_safe_decimal(holding.price),
                        market_value=market_value,
                        cost_basis=cost_basis,
                        unrealized_gain_loss=unrealized,
                        unrealized_pct=unrealized_pct,
                        asset_class=holding.asset_class,
                        account_id=holding.account_id,
                        account_name=acc_name,
                        institution=inst_name,
                    )
                )

            # Sort by market_value descending
            rows.sort(key=lambda h: h.market_value, reverse=True)
            return rows

        except Exception as exc:  # noqa: BLE001
            logger.warning("investments_analytics.holdings_query_failed", error=str(exc))
            warnings.append(f"Holdings query failed: {exc}")
            return []

    async def _get_fee_trend(
        self,
        account_ids: List[str],
        start_date: date,
        end_date: date,
        warnings: List[str],
    ) -> List[MonthlyFee]:
        """Aggregate fees into monthly buckets within the date range."""
        if not account_ids:
            return []
        try:
            result = await self._session.execute(
                select(FeeModel)
                .where(FeeModel.account_id.in_(account_ids))
                .where(FeeModel.fee_date >= start_date)
                .where(FeeModel.fee_date <= end_date)
                .order_by(FeeModel.fee_date)
            )
            fees = result.scalars().all()

            monthly: dict[tuple[int, int], MonthlyFee] = {}
            for fee in fees:
                key = (fee.fee_date.year, fee.fee_date.month)
                if key not in monthly:
                    monthly[key] = MonthlyFee(
                        year=key[0],
                        month=key[1],
                        total_fees=_ZERO,
                        fee_count=0,
                        by_category={},
                    )
                try:
                    amount = Decimal(fee.amount)
                except (InvalidOperation, TypeError):
                    amount = _ZERO
                monthly[key].total_fees += amount
                monthly[key].fee_count += 1
                cat = fee.fee_category or "OTHER"
                monthly[key].by_category[cat] = (
                    monthly[key].by_category.get(cat, _ZERO) + amount
                )

            return sorted(monthly.values(), key=lambda m: (m.year, m.month))

        except Exception as exc:  # noqa: BLE001
            logger.warning("investments_analytics.fee_trend_failed", error=str(exc))
            warnings.append(f"Fee trend query failed: {exc}")
            return []

    async def _get_balance_trend(
        self,
        account_ids: List[str],
        start_date: date,
        end_date: date,
        inst_map: dict[str, str],
        accounts: List[AccountModel],
        warnings: List[str],
    ) -> List[BalancePoint]:
        """Return all balance snapshots within the date range."""
        if not account_ids:
            return []
        try:
            result = await self._session.execute(
                select(BalanceSnapshotModel)
                .where(BalanceSnapshotModel.account_id.in_(account_ids))
                .where(BalanceSnapshotModel.snapshot_date >= start_date)
                .where(BalanceSnapshotModel.snapshot_date <= end_date)
                .order_by(BalanceSnapshotModel.snapshot_date)
            )
            snaps = result.scalars().all()

            acc_name_map = {
                a.id: (a.account_name or a.account_type or "Unknown") for a in accounts
            }

            points: List[BalancePoint] = []
            for snap in snaps:
                try:
                    val = Decimal(snap.total_value)
                except (InvalidOperation, TypeError):
                    continue
                points.append(
                    BalancePoint(
                        snapshot_date=snap.snapshot_date,
                        total_value=val,
                        account_id=snap.account_id,
                        account_name=acc_name_map.get(snap.account_id, "Unknown"),
                        institution=inst_map.get(snap.account_id, "Unknown"),
                    )
                )
            return points

        except Exception as exc:  # noqa: BLE001
            logger.warning("investments_analytics.balance_trend_failed", error=str(exc))
            warnings.append(f"Balance trend query failed: {exc}")
            return []

    async def _get_period_changes(
        self,
        account_ids: List[str],
        inst_map: dict[str, str],
        accounts: List[AccountModel],
        warnings: List[str],
    ) -> List[PeriodChange]:
        """Compare the two most recent balance snapshots per account."""
        if not account_ids:
            return []
        acc_name_map = {
            a.id: (a.account_name or a.account_type or "Unknown") for a in accounts
        }
        changes: List[PeriodChange] = []
        try:
            for acc_id in account_ids:
                result = await self._session.execute(
                    select(BalanceSnapshotModel)
                    .where(BalanceSnapshotModel.account_id == acc_id)
                    .order_by(BalanceSnapshotModel.snapshot_date.desc())
                    .limit(2)
                )
                snaps = result.scalars().all()
                if not snaps:
                    continue

                current_snap = snaps[0]
                prev_snap = snaps[1] if len(snaps) > 1 else None

                try:
                    current_val = Decimal(current_snap.total_value)
                except (InvalidOperation, TypeError):
                    warnings.append(
                        f"Invalid current balance for account {acc_id}"
                    )
                    continue

                prev_val: Optional[Decimal] = None
                if prev_snap:
                    try:
                        prev_val = Decimal(prev_snap.total_value)
                    except (InvalidOperation, TypeError):
                        pass

                change_amount = (current_val - prev_val) if prev_val is not None else None
                change_pct: Optional[Decimal] = None
                if prev_val and prev_val != _ZERO and change_amount is not None:
                    change_pct = (change_amount / prev_val * 100).quantize(
                        Decimal("0.01")
                    )

                changes.append(
                    PeriodChange(
                        account_id=acc_id,
                        account_name=acc_name_map.get(acc_id, "Unknown"),
                        institution=inst_map.get(acc_id, "Unknown"),
                        previous_value=prev_val,
                        current_value=current_val,
                        change_amount=change_amount,
                        change_pct=change_pct,
                        period_start=prev_snap.snapshot_date if prev_snap else None,
                        period_end=current_snap.snapshot_date,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("investments_analytics.period_changes_failed", error=str(exc))
            warnings.append(f"Period changes query failed: {exc}")

        return changes
