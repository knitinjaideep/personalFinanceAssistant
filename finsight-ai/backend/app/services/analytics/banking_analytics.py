"""
BankingAnalyticsService — bucket-aware analytics for the BANKING bucket.

Returns spend summaries, category breakdowns, merchant tables, subscription
detection, credit card balances, and checking in/out summaries.

Every public method returns ``PartialResult[T]`` and NEVER raises — warnings
are surfaced to the API layer which returns ``partial=True`` instead of 500.

Subscription detection heuristic:
- A transaction is "recurring" if its ``is_recurring`` flag is True,  OR
- The same merchant appears ≥ 2 times within any 35-day window with amounts
  within ±10% of each other.

Unusual transaction detection:
- Transactions whose |amount| is > 2σ above the mean absolute amount for
  the same category (or overall if category sample is too small).
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Dict, Generic, List, Optional, TypeVar

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AccountModel,
    BalanceSnapshotModel,
    InstitutionModel,
    StatementModel,
    TransactionModel,
)
from app.domain.enums import (
    BucketType,
    ExtractionStatus,
    TransactionCategory,
    TransactionType,
    BANKING_ACCOUNT_TYPES,
)
# Re-use PartialResult from the sibling module
from app.services.analytics.investments_analytics import PartialResult

logger = structlog.get_logger(__name__)

_ZERO = Decimal("0")
T = TypeVar("T")


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass
class MerchantSpend:
    """Total spend at a single merchant over the query period."""

    merchant_name: str
    total_amount: Decimal
    transaction_count: int
    category: Optional[str]


@dataclass
class Subscription:
    """A detected recurring subscription."""

    merchant_name: str
    typical_amount: Decimal
    frequency_days: int  # approximate days between charges (28/30/365…)
    last_charged: date
    category: Optional[str]
    transaction_ids: List[str]


@dataclass
class CardBalance:
    """Credit card balance snapshot."""

    account_id: str
    account_name: str
    institution: str
    current_balance: Decimal  # outstanding balance (positive = owed)
    as_of_date: Optional[date]


@dataclass
class CheckingInOutSummary:
    """Total inflows and outflows for checking/savings accounts."""

    total_inflows: Decimal
    total_outflows: Decimal
    net: Decimal  # inflows − outflows


@dataclass
class BankingOverview:
    """Top-level banking analytics payload."""

    total_spend_this_month: Decimal
    spend_by_category: Dict[str, Decimal]          # TransactionCategory.value → amount
    spend_by_merchant: List[MerchantSpend]
    subscriptions: List[Subscription]
    credit_card_balances: List[CardBalance]
    checking_summary: CheckingInOutSummary
    top_transactions: List[dict]                   # serialisable transaction dicts
    unusual_transactions: List[dict]               # > 2σ from category mean


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class BankingAnalyticsService:
    """Bucket-aware analytics service for the BANKING bucket.

    Usage::

        svc = BankingAnalyticsService(session)
        result = await svc.get_overview(
            institution_ids=["..."],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_overview(
        self,
        institution_ids: Optional[List[str]] = None,
        account_ids: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> PartialResult[BankingOverview]:
        """Full banking analytics overview.  Never raises."""
        warnings: List[str] = []
        end_date = end_date or date.today()
        start_date = start_date or date(end_date.year, end_date.month, 1)

        # Resolve banking accounts
        accounts = await self._get_banking_accounts(
            institution_ids, account_ids, warnings
        )
        if not accounts:
            warnings.append("No banking accounts found in the database.")
            return PartialResult(
                data=BankingOverview(
                    total_spend_this_month=_ZERO,
                    spend_by_category={},
                    spend_by_merchant=[],
                    subscriptions=[],
                    credit_card_balances=[],
                    checking_summary=CheckingInOutSummary(_ZERO, _ZERO, _ZERO),
                    top_transactions=[],
                    unusual_transactions=[],
                ),
                warnings=warnings,
            )

        account_id_strs = [a.id for a in accounts]
        inst_map = await self._build_institution_map(accounts)

        # Load transactions in range
        transactions = await self._load_transactions(
            account_id_strs, start_date, end_date, warnings
        )

        # Spend aggregations (exclude inflows / credits)
        spend_txs = [
            t for t in transactions
            if t.get("type") in _SPEND_TYPES and t["amount"] < _ZERO
        ]
        # Normalise: flip negative to positive for spend reporting
        for tx in spend_txs:
            tx["spend_amount"] = abs(tx["amount"])

        total_spend = sum((t["spend_amount"] for t in spend_txs), _ZERO)
        spend_by_category = self._aggregate_by_category(spend_txs)
        spend_by_merchant = self._aggregate_by_merchant(spend_txs)

        # Subscriptions (all transactions for detection, not just spend window)
        all_txs = await self._load_transactions(
            account_id_strs,
            end_date - timedelta(days=90),
            end_date,
            warnings,
        )
        subscriptions = self._detect_subscriptions(all_txs)

        # Credit card balances
        cc_balances = await self._get_credit_card_balances(
            accounts, inst_map, end_date, warnings
        )

        # Checking in/out summary
        checking_summary = self._compute_checking_summary(transactions)

        # Top 10 transactions by spend amount
        top_txs = sorted(spend_txs, key=lambda t: t["spend_amount"], reverse=True)[:10]

        # Unusual transactions (> 2σ from category mean)
        unusual = self._detect_unusual(spend_txs)

        overview = BankingOverview(
            total_spend_this_month=total_spend,
            spend_by_category=spend_by_category,
            spend_by_merchant=spend_by_merchant,
            subscriptions=subscriptions,
            credit_card_balances=cc_balances,
            checking_summary=checking_summary,
            top_transactions=top_txs,
            unusual_transactions=unusual,
        )

        logger.info(
            "banking_analytics.overview_built",
            accounts=len(accounts),
            total_spend=str(total_spend),
            subscriptions=len(subscriptions),
            unusual=len(unusual),
            warnings=len(warnings),
        )
        return PartialResult(data=overview, warnings=warnings)

    async def get_spend_breakdown(
        self,
        institution_ids: Optional[List[str]] = None,
        account_ids: Optional[List[str]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> PartialResult[dict]:
        """Return spend by category and merchant for the date range."""
        warnings: List[str] = []
        end_date = end_date or date.today()
        start_date = start_date or date(end_date.year, end_date.month, 1)

        accounts = await self._get_banking_accounts(
            institution_ids, account_ids, warnings
        )
        if not accounts:
            warnings.append("No banking accounts found.")
            return PartialResult(
                data={"by_category": {}, "by_merchant": []}, warnings=warnings
            )

        account_id_strs = [a.id for a in accounts]
        transactions = await self._load_transactions(
            account_id_strs, start_date, end_date, warnings
        )
        spend_txs = [
            t for t in transactions
            if t.get("type") in _SPEND_TYPES and t["amount"] < _ZERO
        ]
        for tx in spend_txs:
            tx["spend_amount"] = abs(tx["amount"])

        return PartialResult(
            data={
                "by_category": self._aggregate_by_category(spend_txs),
                "by_merchant": [
                    {
                        "merchant_name": m.merchant_name,
                        "total_amount": str(m.total_amount),
                        "transaction_count": m.transaction_count,
                        "category": m.category,
                    }
                    for m in self._aggregate_by_merchant(spend_txs)
                ],
            },
            warnings=warnings,
        )

    async def get_subscriptions(
        self,
        institution_ids: Optional[List[str]] = None,
        account_ids: Optional[List[str]] = None,
        lookback_days: int = 90,
    ) -> PartialResult[List[Subscription]]:
        """Detect recurring subscriptions in the last *lookback_days* days."""
        warnings: List[str] = []
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)

        accounts = await self._get_banking_accounts(
            institution_ids, account_ids, warnings
        )
        if not accounts:
            warnings.append("No banking accounts found.")
            return PartialResult(data=[], warnings=warnings)

        account_id_strs = [a.id for a in accounts]
        transactions = await self._load_transactions(
            account_id_strs, start_date, end_date, warnings
        )
        subs = self._detect_subscriptions(transactions)
        return PartialResult(data=subs, warnings=warnings)

    # ------------------------------------------------------------------
    # Private helpers — data loading
    # ------------------------------------------------------------------

    async def _get_banking_accounts(
        self,
        institution_ids: Optional[List[str]],
        account_ids: Optional[List[str]],
        warnings: List[str],
    ) -> List[AccountModel]:
        try:
            stmt = select(AccountModel).where(
                AccountModel.account_type.in_(
                    [at.value for at in BANKING_ACCOUNT_TYPES]
                )
            )
            if institution_ids:
                stmt = stmt.where(AccountModel.institution_id.in_(institution_ids))
            if account_ids:
                stmt = stmt.where(AccountModel.id.in_(account_ids))
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except Exception as exc:  # noqa: BLE001
            logger.warning("banking_analytics.account_query_failed", error=str(exc))
            warnings.append(f"Could not load banking accounts: {exc}")
            return []

    async def _build_institution_map(
        self, accounts: List[AccountModel]
    ) -> dict[str, str]:
        inst_ids = list({a.institution_id for a in accounts if a.institution_id})
        if not inst_ids:
            return {}
        try:
            result = await self._session.execute(
                select(InstitutionModel).where(InstitutionModel.id.in_(inst_ids))
            )
            id_to_name = {i.id: i.name for i in result.scalars().all()}
            return {a.id: id_to_name.get(a.institution_id or "", "Unknown") for a in accounts}
        except Exception:  # noqa: BLE001
            return {a.id: "Unknown" for a in accounts}

    async def _load_transactions(
        self,
        account_ids: List[str],
        start_date: date,
        end_date: date,
        warnings: List[str],
    ) -> List[dict]:
        """Load transactions as plain dicts (avoids passing ORM objects around)."""
        if not account_ids:
            return []
        try:
            result = await self._session.execute(
                select(TransactionModel)
                .where(TransactionModel.account_id.in_(account_ids))
                .where(TransactionModel.transaction_date >= start_date)
                .where(TransactionModel.transaction_date <= end_date)
                .order_by(TransactionModel.transaction_date.desc())
            )
            rows = result.scalars().all()
            out: List[dict] = []
            for tx in rows:
                try:
                    amount = Decimal(tx.amount)
                except (InvalidOperation, TypeError):
                    continue
                out.append(
                    {
                        "id": tx.id,
                        "account_id": tx.account_id,
                        "transaction_date": tx.transaction_date,
                        "description": tx.description or "",
                        "merchant_name": tx.merchant_name or tx.description or "",
                        "amount": amount,
                        "type": tx.transaction_type,
                        "category": tx.category,
                        "is_recurring": bool(tx.is_recurring),
                        "statement_id": tx.statement_id,
                    }
                )
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("banking_analytics.tx_query_failed", error=str(exc))
            warnings.append(f"Transaction query failed: {exc}")
            return []

    async def _get_credit_card_balances(
        self,
        accounts: List[AccountModel],
        inst_map: dict[str, str],
        as_of: date,
        warnings: List[str],
    ) -> List[CardBalance]:
        cc_accounts = [
            a for a in accounts if a.account_type == "CREDIT_CARD"
        ]
        if not cc_accounts:
            return []
        balances: List[CardBalance] = []
        try:
            cc_ids = [a.id for a in cc_accounts]
            acc_name_map = {
                a.id: (a.account_name or a.account_type or "Unknown") for a in cc_accounts
            }
            # Latest snapshot per account
            subq = (
                select(
                    BalanceSnapshotModel.account_id,
                    func.max(BalanceSnapshotModel.snapshot_date).label("max_date"),
                )
                .where(BalanceSnapshotModel.account_id.in_(cc_ids))
                .where(BalanceSnapshotModel.snapshot_date <= as_of)
                .group_by(BalanceSnapshotModel.account_id)
                .subquery()
            )
            result = await self._session.execute(
                select(BalanceSnapshotModel).join(
                    subq,
                    (BalanceSnapshotModel.account_id == subq.c.account_id)
                    & (BalanceSnapshotModel.snapshot_date == subq.c.max_date),
                )
            )
            for snap in result.scalars().all():
                try:
                    val = Decimal(snap.total_value)
                except (InvalidOperation, TypeError):
                    continue
                balances.append(
                    CardBalance(
                        account_id=snap.account_id,
                        account_name=acc_name_map.get(snap.account_id, "Unknown"),
                        institution=inst_map.get(snap.account_id, "Unknown"),
                        current_balance=val,
                        as_of_date=snap.snapshot_date,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("banking_analytics.cc_balance_failed", error=str(exc))
            warnings.append(f"Credit card balance query failed: {exc}")
        return balances

    # ------------------------------------------------------------------
    # Private helpers — aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_by_category(spend_txs: List[dict]) -> Dict[str, Decimal]:
        totals: Dict[str, Decimal] = defaultdict(lambda: _ZERO)
        for tx in spend_txs:
            cat = tx.get("category") or TransactionCategory.OTHER.value
            totals[cat] += tx["spend_amount"]
        # Sort descending by spend
        return dict(
            sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        )

    @staticmethod
    def _aggregate_by_merchant(spend_txs: List[dict]) -> List[MerchantSpend]:
        by_merchant: Dict[str, MerchantSpend] = {}
        for tx in spend_txs:
            name = (tx.get("merchant_name") or "Unknown").strip()
            if name not in by_merchant:
                by_merchant[name] = MerchantSpend(
                    merchant_name=name,
                    total_amount=_ZERO,
                    transaction_count=0,
                    category=tx.get("category"),
                )
            by_merchant[name].total_amount += tx["spend_amount"]
            by_merchant[name].transaction_count += 1

        result = sorted(
            by_merchant.values(), key=lambda m: m.total_amount, reverse=True
        )
        return result[:50]  # top 50 merchants

    @staticmethod
    def _detect_subscriptions(transactions: List[dict]) -> List[Subscription]:
        """Identify recurring charges using the is_recurring flag and frequency analysis."""
        # Group by merchant
        by_merchant: Dict[str, List[dict]] = defaultdict(list)
        for tx in transactions:
            if tx.get("amount", _ZERO) < _ZERO:  # charges only
                name = (tx.get("merchant_name") or "").strip()
                if name:
                    by_merchant[name].append(tx)

        subscriptions: List[Subscription] = []
        for merchant, txs in by_merchant.items():
            # Either flagged recurring, or detected by frequency
            flagged = any(t.get("is_recurring") for t in txs)
            detected = _has_recurring_pattern(txs)

            if not (flagged or detected):
                continue

            amounts = [abs(t["amount"]) for t in txs]
            typical = sum(amounts, _ZERO) / len(amounts)

            dates_sorted = sorted(t["transaction_date"] for t in txs)
            freq = 30  # default
            if len(dates_sorted) >= 2:
                gaps = [
                    (dates_sorted[i + 1] - dates_sorted[i]).days
                    for i in range(len(dates_sorted) - 1)
                ]
                freq = round(sum(gaps) / len(gaps))

            subscriptions.append(
                Subscription(
                    merchant_name=merchant,
                    typical_amount=typical.quantize(Decimal("0.01")),
                    frequency_days=freq,
                    last_charged=max(t["transaction_date"] for t in txs),
                    category=txs[0].get("category"),
                    transaction_ids=[t["id"] for t in txs],
                )
            )

        subscriptions.sort(key=lambda s: s.typical_amount, reverse=True)
        return subscriptions

    @staticmethod
    def _compute_checking_summary(transactions: List[dict]) -> CheckingInOutSummary:
        inflows = _ZERO
        outflows = _ZERO
        for tx in transactions:
            if tx["type"] in _INFLOW_TYPES and tx["amount"] > _ZERO:
                inflows += tx["amount"]
            elif tx["amount"] < _ZERO:
                outflows += abs(tx["amount"])
        return CheckingInOutSummary(
            total_inflows=inflows,
            total_outflows=outflows,
            net=inflows - outflows,
        )

    @staticmethod
    def _detect_unusual(spend_txs: List[dict]) -> List[dict]:
        """Return transactions whose spend amount is > 2σ above the category mean."""
        if len(spend_txs) < 4:
            return []

        # Group by category
        by_cat: Dict[str, List[Decimal]] = defaultdict(list)
        for tx in spend_txs:
            cat = tx.get("category") or "OTHER"
            by_cat[cat].append(tx["spend_amount"])

        unusual: List[dict] = []
        for tx in spend_txs:
            cat = tx.get("category") or "OTHER"
            amounts = by_cat[cat]
            if len(amounts) < 3:
                # Fall back to overall distribution
                amounts = [t["spend_amount"] for t in spend_txs]
            if len(amounts) < 3:
                continue
            try:
                mean = float(sum(amounts, _ZERO)) / len(amounts)
                stdev = statistics.stdev([float(a) for a in amounts])
                if stdev == 0:
                    continue
                z = (float(tx["spend_amount"]) - mean) / stdev
                if z > 2.0:
                    unusual.append(tx)
            except (statistics.StatisticsError, ZeroDivisionError):
                continue

        unusual.sort(key=lambda t: t["spend_amount"], reverse=True)
        return unusual


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_SPEND_TYPES = {
    TransactionType.PURCHASE.value,
    TransactionType.PAYMENT.value,
    TransactionType.FEE.value,
    TransactionType.OTHER.value,
}

_INFLOW_TYPES = {
    TransactionType.DEPOSIT.value,
    TransactionType.TRANSFER.value,
    TransactionType.INTEREST.value,
    TransactionType.REFUND.value,
}


def _has_recurring_pattern(txs: List[dict], tolerance: float = 0.10) -> bool:
    """Return True if transactions show a recurring charge pattern.

    Criteria:
    - ≥ 2 transactions
    - All amounts within ±10% of the median amount
    - At least one gap between charges is 25–35 days (monthly) or 335–395 (annual)
    """
    if len(txs) < 2:
        return False

    amounts = sorted(abs(t["amount"]) for t in txs)
    median = amounts[len(amounts) // 2]
    if median == _ZERO:
        return False

    all_similar = all(
        abs(a - median) / median <= tolerance for a in amounts
    )
    if not all_similar:
        return False

    dates = sorted(t["transaction_date"] for t in txs)
    gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    return any((25 <= g <= 35) or (335 <= g <= 395) for g in gaps)
