"""Service wrapper for deterministic Banking Insights (PR 10)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TransactionModel
from app.domain.banking_insights import BankingInsightsResult, build_banking_insights
from app.domain.classification_review import (
    TransactionReviewItem,
    describe_review_reason,
)
from app.domain.plan_vs_actual import Period
from app.domain.transaction_classification import (
    CashFlowType,
    ClassificationSource,
    MasterBucket,
)
from app.services import plan_vs_actual
from app.services.transaction_classification import TransactionClassificationService


def _to_review_item(txn: TransactionModel) -> TransactionReviewItem:
    return TransactionReviewItem(
        transaction_id=txn.id,
        transaction_date=txn.transaction_date,
        description=txn.description,
        merchant=txn.merchant_name,
        amount=txn.amount,
        master_bucket=(
            MasterBucket(txn.master_bucket) if txn.master_bucket else MasterBucket.UNCLASSIFIED
        ),
        category=txn.classification_category,
        cash_flow_type=(
            CashFlowType(txn.cash_flow_type) if txn.cash_flow_type else CashFlowType.OTHER
        ),
        confidence=txn.classification_confidence or 0.0,
        needs_review=txn.needs_review,
        classification_source=(
            ClassificationSource(txn.classification_source)
            if txn.classification_source else ClassificationSource.UNKNOWN
        ),
        review_reason=describe_review_reason(
            description=txn.description,
            merchant_name=txn.merchant_name,
            classification_source=txn.classification_source,
        ),
    )


async def get_banking_insights(
    session: AsyncSession,
    period: Period,
    *,
    account_id: str | None = None,
) -> BankingInsightsResult:
    """Gather already-authoritative facts and compose at most three insights."""
    result = await plan_vs_actual.get_plan_vs_actual(session, period, account_id=account_id)
    merchant_drivers = []
    for bucket in (MasterBucket.NEEDS, MasterBucket.WANTS):
        merchant_drivers.extend(
            await plan_vs_actual.get_merchant_drivers(
                session, period, bucket=bucket, account_id=account_id, top_n=5,
            )
        )
    review_rows = await TransactionClassificationService().get_needs_review(
        session,
        limit=None,
        account_id=account_id,
        date_from=period.start,
        date_to=period.end,
    )
    review_items = [_to_review_item(row) for row in review_rows]
    return build_banking_insights(result, merchant_drivers, review_items)
