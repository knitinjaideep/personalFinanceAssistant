"""
Needs/Wants Classification Review — response shapes + deterministic helpers
for the compact "Transactions to Review" Banking section (PR 09, see
docs/coral-redesign/pr-09-classification-review.md).

This module is pure Pydantic/plain-Python (no DB, no HTTP, no LLM) and
mirrors already-computed fields from `app.domain.transaction_classification`
and `TransactionModel` 1:1 — it never invents a parallel number. The
classification ENGINE and SERVICE already exist (PR 03); this module only
adds:

  - `TransactionReviewItem` / `ClassificationActionResult` — API response
    shapes for the review queue and the confirm/reclassify actions.
  - `describe_review_reason` — a presentation-only label ("why is this
    flagged?") derived from already-persisted confidence/source plus the
    engine's own `is_ambiguous_merchant` check. Never a new financial
    judgment, just naming a fact the engine already established.
  - `ReclassifyChoice` / `resolve_reclassify_choice` — the user-facing
    "Change" bucket options (pr-09's list: Needs/Wants/Savings/Investments/
    Transfer/Other) resolved to the (MasterBucket, CashFlowType) pair
    `TransactionClassificationService.apply_user_override`/
    `apply_merchant_rule` require. "Transfer" and "Other/Unclassified" both
    resolve to `MasterBucket.UNCLASSIFIED` (transfers are not one of the four
    master budget buckets — accounting-invariants.md #1) but are kept as
    distinct user-facing choices with different `CashFlowType`s.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from app.domain.transaction_classification import (
    CashFlowType,
    ClassificationSource,
    MasterBucket,
    is_ambiguous_merchant,
)

# ── Review reason (presentation-only label) ─────────────────────────────────

class ReviewReason(str, Enum):
    """Why a transaction is flagged `needs_review` — purely descriptive,
    computed from fields the classification engine already persisted."""

    UNCLASSIFIED = "unclassified"
    AMBIGUOUS_MERCHANT = "ambiguous_merchant"
    LOW_CONFIDENCE = "low_confidence"


def describe_review_reason(
    *,
    description: str,
    merchant_name: str | None,
    classification_source: str | None,
) -> ReviewReason:
    """Deterministic reason label for one review-queue row. Reuses the exact
    `is_ambiguous_merchant` predicate the classification engine itself
    applies (tier gate before 4/5, see transaction_classification.py) so this
    label can never disagree with why the engine actually flagged the row.

    Deliberately does NOT take the persisted confidence: re-deriving a reason
    from a confidence threshold here would be a second, independent judgment
    that could disagree with the engine's own. Source + the engine's own
    ambiguity predicate are sufficient and cannot drift."""
    text = f"{description or ''} {merchant_name or ''}".strip().lower()
    if classification_source in (None, ClassificationSource.UNKNOWN.value):
        return ReviewReason.UNCLASSIFIED
    if is_ambiguous_merchant(text):
        return ReviewReason.AMBIGUOUS_MERCHANT
    return ReviewReason.LOW_CONFIDENCE


# ── Review queue row ─────────────────────────────────────────────────────────

class TransactionReviewItem(BaseModel):
    """One row of the compact review queue
    (GET /api/v1/classification/needs-review). Mirrors
    `TransactionModel`'s already-persisted derived-classification fields
    directly — no reshaping/recomputation."""

    transaction_id: str
    transaction_date: date
    description: str
    merchant: str | None
    amount: str
    master_bucket: MasterBucket
    category: str | None
    cash_flow_type: CashFlowType
    confidence: float
    needs_review: bool
    classification_source: ClassificationSource
    review_reason: ReviewReason


# ── Action results (confirm / reclassify) ───────────────────────────────────

class ClassificationActionResult(BaseModel):
    """Result of confirming or reclassifying ONE transaction — the same
    fields `ClassificationResult` carries, keyed by `transaction_id` for the
    API response."""

    transaction_id: str
    master_bucket: MasterBucket
    category: str | None
    cash_flow_type: CashFlowType
    confidence: float
    needs_review: bool
    source: ClassificationSource


class ReclassifyScope(str, Enum):
    """Scope of a 'Change' action (pr-09's Change → scope options)."""

    TRANSACTION = "transaction"
    MERCHANT_FUTURE = "merchant_future"
    MERCHANT_THIS_MONTH = "merchant_this_month"


class ReclassifyChoice(str, Enum):
    """User-facing bucket choice for the 'Change' action. A superset of
    `MasterBucket` — TRANSFER is a distinct, meaningful choice for the user
    even though it resolves to the same `MasterBucket.UNCLASSIFIED` as
    UNCLASSIFIED (see `resolve_reclassify_choice`)."""

    NEEDS = "needs"
    WANTS = "wants"
    SAVINGS = "savings"
    INVESTMENTS = "investments"
    TRANSFER = "transfer"
    UNCLASSIFIED = "unclassified"


def resolve_reclassify_choice(
    choice: ReclassifyChoice, *, amount: Decimal,
) -> tuple[MasterBucket, CashFlowType]:
    """Deterministically resolve a user's 'Change' choice to the
    (MasterBucket, CashFlowType) pair `apply_user_override`/
    `apply_merchant_rule` require. Pure lookup + one sign check — never an
    LLM call, never a new classification judgment.

    The sign check for Needs/Wants mirrors the classification engine's own
    `_spend_flow` convention (transaction_classification.py): a positive
    amount landing in a spending bucket is a refund, not new spending
    (accounting-invariants.md #6), so a user correcting a refund into
    Needs/Wants still gets an accurate cash-flow type instead of always
    `expense`.

    Savings/Investments are assumed to be contributions (the common manual-
    correction case is an unrecognized transfer INTO savings/investments that
    the deterministic engine missed) — a genuine withdrawal is better
    expressed by the user picking Transfer/Unclassified instead.
    """
    if choice == ReclassifyChoice.NEEDS:
        flow = CashFlowType.REFUND if amount > 0 else CashFlowType.EXPENSE
        return MasterBucket.NEEDS, flow
    if choice == ReclassifyChoice.WANTS:
        flow = CashFlowType.REFUND if amount > 0 else CashFlowType.EXPENSE
        return MasterBucket.WANTS, flow
    if choice == ReclassifyChoice.SAVINGS:
        return MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION
    if choice == ReclassifyChoice.INVESTMENTS:
        return MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_CONTRIBUTION
    if choice == ReclassifyChoice.TRANSFER:
        return MasterBucket.UNCLASSIFIED, CashFlowType.TRANSFER
    return MasterBucket.UNCLASSIFIED, CashFlowType.OTHER
