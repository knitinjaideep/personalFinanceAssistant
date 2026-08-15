"""
Plan vs Actual service — wires the pure domain engine in
app.domain.plan_vs_actual to the database.

Responsibilities:
  - resolve the financial plan version in effect for the requested period
    (app.services.financial_plan; never "just the latest")
  - ensure every transaction in the period has a classification (calls
    TransactionClassificationService.classify_batch for anything still NULL —
    PR 03 populates the columns but nothing calls it during ingestion yet)
  - load transactions + their account (for the cross-statement
    canonical-contribution-leg rule) and hand them to the pure engine
  - expose get_plan_vs_actual / get_bucket_breakdown / get_category_breakdown
    / get_merchant_drivers, as specified in docs/coral-redesign/pr-04-plan-vs-actual.md

No FastAPI imports here — usable from any caller, exactly like
app.services.financial_plan and app.services.transaction_classification.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.db import repositories as repo
from app.db.models import AccountModel, TransactionModel
from app.domain.entities import PlanVersionSnapshot
from app.domain.plan_vs_actual import (
    DEFAULT_STATUS_THRESHOLDS,
    CategoryDrift,
    ClassifiedTxn,
    MerchantDriver,
    Period,
    PlanVsActualResult,
    StatusThresholds,
    TransactionDrift,
    compute_category_breakdown,
    compute_merchant_drivers,
    compute_plan_vs_actual,
    compute_transaction_drivers,
)
from app.domain.transaction_classification import MasterBucket
from app.services import financial_plan as plan_service
from app.services.transaction_classification import TransactionClassificationService

logger = get_logger(__name__)


def _to_classified_txn(txn: TransactionModel, account: AccountModel | None) -> ClassifiedTxn:
    return ClassifiedTxn(
        transaction_id=txn.id,
        account_id=txn.account_id,
        account_type=account.account_type if account else None,
        transaction_date=txn.transaction_date,
        amount=Decimal(txn.amount),
        master_bucket=txn.master_bucket,
        category=txn.classification_category,
        cash_flow_type=txn.cash_flow_type,
        needs_review=txn.needs_review,
        merchant_name=txn.merchant_name,
        description=txn.description or "",
    )


async def _load_classified_transactions(
    session: AsyncSession,
    period: Period,
    *,
    account_id: str | None = None,
    auto_classify: bool = True,
) -> list[ClassifiedTxn]:
    """Load every transaction in the period, guaranteeing each one has a
    (possibly `unclassified`) classification before aggregation.

    `auto_classify=True` (the default) backfills any transaction whose
    classification_source is still NULL by calling
    TransactionClassificationService.classify_batch — nothing in ingestion
    calls this yet (PR 03 note), so without this step every actual $ would
    silently read as $0. Restricted to `only_unclassified=True` so a user's
    prior override/merchant-rule resolution is never recomputed here.
    """
    if auto_classify:
        summary = await TransactionClassificationService().classify_batch(
            session, account_id=account_id, only_unclassified=True,
        )
        if summary.total:
            logger.info(
                "plan_vs_actual.auto_classified",
                extra={"classified": summary.classified, "needs_review": summary.needs_review},
            )

    transactions = await repo.list_transactions_for_period(
        session, date_from=period.start, date_to=period.end, account_id=account_id,
    )
    accounts = await repo.get_accounts_by_ids(
        session, [t.account_id for t in transactions],
    )
    return [_to_classified_txn(t, accounts.get(t.account_id)) for t in transactions]


async def _resolve_plan(
    session: AsyncSession, period: Period,
) -> tuple[PlanVersionSnapshot | None, bool]:
    """Resolve the plan version in effect at the START of the period (per
    docs/coral-redesign/financial-model.md — historical months are judged
    against the plan active during that period, not today's). Also detects
    whether the plan changed again before the period ended, so that edge
    case is surfaced via completeness metadata rather than silently ignored.
    """
    plan_at_start = await plan_service.get_plan_for_date(session, period.start)
    if plan_at_start is None:
        return None, False

    plan_at_end = await plan_service.get_plan_for_date(session, period.end)
    changed_mid_period = plan_at_end is not None and plan_at_end.id != plan_at_start.id
    return plan_at_start, changed_mid_period


async def get_plan_vs_actual(
    session: AsyncSession,
    period: Period,
    *,
    account_id: str | None = None,
    thresholds: StatusThresholds = DEFAULT_STATUS_THRESHOLDS,
) -> PlanVsActualResult:
    """Full Needs/Wants/Savings/Investments Plan vs Actual result for one
    period — the primary entry point for PR 04.

    `account_id` narrows BOTH the actuals and the Plannable Income
    denominator to that single account. Scoping to an account where no
    payroll lands (a credit card, a brokerage) therefore yields
    `income_observed=False` and `DriftStatus.UNKNOWN` percentages rather than
    a percentage computed against a partial denominator. Household-level
    Plan vs Actual must be requested with `account_id=None`.
    """
    plan, changed_mid_period = await _resolve_plan(session, period)
    transactions = await _load_classified_transactions(session, period, account_id=account_id)
    return compute_plan_vs_actual(
        period, transactions, plan,
        thresholds=thresholds, plan_version_changed_mid_period=changed_mid_period,
    )


async def get_bucket_breakdown(
    session: AsyncSession,
    period: Period,
    bucket: MasterBucket,
    *,
    account_id: str | None = None,
    thresholds: StatusThresholds = DEFAULT_STATUS_THRESHOLDS,
) -> list[CategoryDrift]:
    """Recursive drill-down: category-level rows within one master bucket.

    Same `account_id` denominator caveat as `get_plan_vs_actual`.
    """
    plan, _ = await _resolve_plan(session, period)
    transactions = await _load_classified_transactions(session, period, account_id=account_id)
    return compute_category_breakdown(transactions, bucket, plan, thresholds=thresholds)


# Alias — pr-04-plan-vs-actual.md lists get_category_breakdown alongside
# get_bucket_breakdown; both resolve to the same category-level drill-down.
get_category_breakdown = get_bucket_breakdown


async def get_merchant_drivers(
    session: AsyncSession,
    period: Period,
    *,
    bucket: MasterBucket | None = None,
    category: str | None = None,
    account_id: str | None = None,
    top_n: int = 10,
) -> list[MerchantDriver]:
    """Top merchant/description drivers of a bucket (optionally narrowed to
    one category), sorted by absolute net $ within the period."""
    transactions = await _load_classified_transactions(session, period, account_id=account_id)
    return compute_merchant_drivers(transactions, bucket=bucket, category=category, top_n=top_n)


async def get_transaction_drivers(
    session: AsyncSession,
    period: Period,
    *,
    bucket: MasterBucket | None = None,
    category: str | None = None,
    merchant: str | None = None,
    account_id: str | None = None,
) -> list[TransactionDrift]:
    """Individual transactions behind a bucket/category/merchant driver — the
    leaf level of Category -> merchants -> transactions
    (pr-08-banking-drift.md). Mirrors `get_merchant_drivers`'s structure
    exactly: load the period's classified transactions, delegate to the pure
    domain function."""
    transactions = await _load_classified_transactions(session, period, account_id=account_id)
    return compute_transaction_drivers(
        transactions, bucket=bucket, category=category, merchant=merchant,
    )
