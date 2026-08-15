"""
Classification Review API — thin routes over
`app.services.transaction_classification.TransactionClassificationService`
(PR 09, see docs/coral-redesign/pr-09-classification-review.md).

No classification logic lives here — every route opens a session, calls the
already-existing service (built in PR 03), and translates domain errors to
HTTP responses, exactly like `app/api/plan_vs_actual.py`/
`app/api/financial_plan.py`. No route here ever calls an LLM: every path is
either a pure DB write (`apply_user_override`/`apply_merchant_rule`, both
already tested in PR 03) or a read of already-classified data.

Plan vs Actual (`app.services.plan_vs_actual`) queries transactions fresh on
every call with no cache/materialization to invalidate, so a correction
persisted here is already reflected on the very next Plan-vs-Actual/Banking/
Overview fetch — no explicit invalidation call is needed from this module.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db import repositories as repo
from app.db.engine import get_session
from app.domain.classification_review import (
    ClassificationActionResult,
    ReclassifyChoice,
    ReclassifyScope,
    TransactionReviewItem,
    describe_review_reason,
    resolve_reclassify_choice,
)
from app.domain.errors import EntityNotFoundError
from app.domain.transaction_classification import (
    CATEGORIES_BY_BUCKET,
    CashFlowType,
    ClassificationResult,
    ClassificationSource,
    MasterBucket,
)
from app.services.transaction_classification import TransactionClassificationService

router = APIRouter(prefix="/api/v1/classification", tags=["classification"])

_service = TransactionClassificationService()


def _to_review_item(txn) -> TransactionReviewItem:  # noqa: ANN001 — TransactionModel, avoids importing SQLModel here
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


def _to_action_result(
    transaction_id: str, result: ClassificationResult,
) -> ClassificationActionResult:
    return ClassificationActionResult(
        transaction_id=transaction_id,
        master_bucket=result.master_bucket,
        category=result.category,
        cash_flow_type=result.cash_flow_type,
        confidence=result.confidence,
        needs_review=result.needs_review,
        source=result.source,
    )


@router.get("/needs-review", response_model=list[TransactionReviewItem])
async def get_needs_review(
    limit: int = Query(20, ge=1, le=100),
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[TransactionReviewItem]:
    """Compact, prioritized review queue — NOT every transaction. See
    `TransactionClassificationService.get_needs_review`'s docstring for the
    prioritization rule (least-confident + highest-$-impact first).

    `start_date`/`end_date` follow the same unified PR 05 period contract as
    `app/api/plan_vs_actual.py` (both or neither; inclusive both ends) and
    scope the queue to the period the Banking page is currently showing.
    Omitting them returns the all-history queue.
    """
    if (start_date is None) != (end_date is None):
        raise HTTPException(422, "Both start_date and end_date are required together.")
    if start_date is not None and end_date is not None and end_date < start_date:
        raise HTTPException(422, "end_date must not be before start_date.")
    async with get_session() as session:
        rows = await _service.get_needs_review(
            session, limit=limit, date_from=start_date, date_to=end_date,
        )
        return [_to_review_item(t) for t in rows]


@router.post("/transactions/{transaction_id}/confirm", response_model=ClassificationActionResult)
async def confirm_transaction(transaction_id: str) -> ClassificationActionResult:
    """"Looks right" action — locks in the transaction's CURRENT
    classification as an explicit tier-1 user override, clearing
    `needs_review`. `apply_user_override` always resolves through
    `classify_transaction`'s tier-1 branch, which unconditionally sets
    `needs_review=False`, so no extra step is needed to clear the flag."""
    async with get_session() as session:
        try:
            txn = await repo.get_transaction(session, transaction_id)
        except EntityNotFoundError as exc:
            raise HTTPException(404, exc.message) from exc

        if not txn.master_bucket or not txn.cash_flow_type:
            raise HTTPException(
                422, "This transaction has not been classified yet — nothing to confirm.",
            )

        result = await _service.apply_user_override(
            session, transaction_id,
            master_bucket=MasterBucket(txn.master_bucket),
            cash_flow_type=CashFlowType(txn.cash_flow_type),
            category=txn.classification_category,
        )
        return _to_action_result(transaction_id, result)


class ReclassifyRequest(BaseModel):
    master_bucket: ReclassifyChoice
    category: str | None = None
    scope: ReclassifyScope = ReclassifyScope.TRANSACTION


class ReclassifyResponse(BaseModel):
    transaction: ClassificationActionResult
    scope: ReclassifyScope
    # Count of OTHER existing transactions also reclassified by this call —
    # always 0 for scope=transaction/merchant_future; see
    # TransactionClassificationService.reclassify_transaction's docstring.
    other_transactions_reclassified: int


@router.post("/transactions/{transaction_id}/reclassify", response_model=ReclassifyResponse)
async def reclassify_transaction(
    transaction_id: str, body: ReclassifyRequest,
) -> ReclassifyResponse:
    """"Change" action — user-decided correction, always wins over
    automation (see TransactionClassificationService.reclassify_transaction
    for the scope semantics, especially the bounded `merchant_this_month`
    behavior)."""
    async with get_session() as session:
        try:
            txn = await repo.get_transaction(session, transaction_id)
        except EntityNotFoundError as exc:
            raise HTTPException(404, exc.message) from exc

        try:
            amount = Decimal(txn.amount)
        except Exception:  # noqa: BLE001 — malformed stored amount, treat as 0 for sign resolution only
            amount = Decimal("0")

        bucket, flow = resolve_reclassify_choice(body.master_bucket, amount=amount)

        if body.category:
            # `classification_category` is joined straight onto plan
            # suballocation names by PR 04, so only the fixed taxonomy in
            # transaction_classification.CATEGORIES_BY_BUCKET is storable —
            # including for buckets that legitimately have NO categories
            # (Transfer / Other-Unclassified), which must reject a category
            # outright rather than silently persisting free text.
            valid_categories = CATEGORIES_BY_BUCKET.get(bucket, [])
            if body.category not in valid_categories:
                expected = (
                    f"Expected one of {valid_categories}."
                    if valid_categories
                    else "This bucket does not take a category."
                )
                raise HTTPException(
                    422,
                    f"{body.category!r} is not a valid category for bucket "
                    f"{bucket.value!r}. {expected}",
                )

        result, other_count = await _service.reclassify_transaction(
            session, transaction_id,
            master_bucket=bucket, cash_flow_type=flow, category=body.category,
            scope=body.scope,
        )
        return ReclassifyResponse(
            transaction=_to_action_result(transaction_id, result),
            scope=body.scope,
            other_transactions_reclassified=other_count,
        )
