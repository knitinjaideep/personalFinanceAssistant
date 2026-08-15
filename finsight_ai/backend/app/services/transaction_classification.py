"""
TransactionClassificationService — wires the pure classification engine in
app.domain.transaction_classification to the database.

Responsibilities:
  - classify a single transaction (fetch user override/merchant rule, run the
    deterministic engine, optionally consult an injectable LLM fallback,
    persist the result)
  - batch-classify transactions (e.g. after ingestion, or a full re-run)
  - apply a user override to one transaction (tier 1 — always wins, never
    silently overwritten by later automation)
  - apply/record a user merchant rule (tier 2 — applies going forward, and
    optionally reclassifies existing non-overridden transactions)
  - surface transactions flagged needs_review for the user to resolve

No FastAPI imports here — usable from any caller (ingestion pipeline, chat
domain, a future API route), exactly like app.services.financial_plan.

`transactions.category` (the raw, parser-assigned value) is NEVER modified by
this service — see accounting-invariants.md #9 (source preservation) and
docs/TRANSACTION_CLASSIFICATION.md.
"""

from __future__ import annotations

import calendar
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.db import repositories as repo
from app.db.models import AccountModel, TransactionModel
from app.domain.classification_review import ReclassifyScope
from app.domain.transaction_classification import (
    CashFlowType,
    ClassificationResult,
    ClassificationSource,
    MasterBucket,
    MerchantRule,
    RuleScope,
    TransactionClassificationInput,
    UserOverride,
    classify_transaction,
)

logger = get_logger(__name__)

# Optional injectable LLM fallback (tier 6). Given (transaction_input), return
# a ClassificationResult suggestion or None if the LLM declines to guess.
# Coral never requires this to be wired — deterministic tiers 1-5 and 7 work
# with no LLM at all, and no test in this suite depends on Ollama running.
LLMClassifierFn = Callable[[TransactionClassificationInput], Awaitable[ClassificationResult | None]]


@dataclass
class BatchClassificationSummary:
    total: int = 0
    classified: int = 0
    needs_review: int = 0
    by_source: dict[str, int] = field(default_factory=dict)


def _to_input(
    txn: TransactionModel, account_type: str | None, account_name: str | None
) -> TransactionClassificationInput:
    return TransactionClassificationInput(
        transaction_id=txn.id,
        description=txn.description or "",
        merchant_name=txn.merchant_name,
        transaction_type=txn.transaction_type or "other",
        amount=txn.amount,
        raw_category=txn.category,
        account_type=account_type,
        account_name=account_name,
    )


def derive_merchant_key(txn: TransactionModel) -> str:
    """Best-effort normalized merchant identifier for a merchant-scoped rule,
    matching the exact substring-match semantics `find_merchant_rule` already
    uses (`rule.merchant_key.lower() in text`, where
    `text = f"{description} {merchant_name}".lower()`). Prefers the parsed
    `merchant_name`; falls back to the full lowercased `description` when a
    parser didn't populate `merchant_name`. Either way the derived key is
    guaranteed to match the transaction it was derived from — used by PR 09's
    merchant_future/merchant_this_month reclassify scopes."""
    name = (txn.merchant_name or "").strip()
    if name:
        return name.lower()
    return (txn.description or "").strip().lower()


def _persist(txn: TransactionModel, result: ClassificationResult) -> None:
    """Write ONLY the derived classification fields. `category` (raw/imported)
    is deliberately untouched."""
    txn.master_bucket = result.master_bucket.value
    txn.classification_category = result.category
    txn.cash_flow_type = result.cash_flow_type.value
    txn.classification_source = result.source.value
    txn.classification_confidence = result.confidence
    txn.needs_review = result.needs_review


class TransactionClassificationService:
    """Classifies transactions deterministically, applying user overrides and
    merchant rules with the precedence documented in
    docs/TRANSACTION_CLASSIFICATION.md."""

    def __init__(self, llm_classifier: LLMClassifierFn | None = None) -> None:
        self._llm_classifier = llm_classifier

    # ── Account lookup helper ────────────────────────────────────────────────

    async def _account_info(
        self, session: AsyncSession, txn: TransactionModel
    ) -> tuple[str | None, str | None]:
        if not txn.account_id:
            return None, None
        account = await session.get(AccountModel, txn.account_id)
        if account is None:
            return None, None
        return account.account_type, account.account_name

    # ── Resolution (no persistence) ──────────────────────────────────────────

    async def resolve(
        self,
        session: AsyncSession,
        txn: TransactionModel,
        *,
        account_type: str | None = None,
        account_name: str | None = None,
    ) -> ClassificationResult:
        """Compute (but do not persist) the classification for one transaction."""
        if account_type is None and account_name is None:
            account_type, account_name = await self._account_info(session, txn)

        txn_input = _to_input(txn, account_type, account_name)

        override_row = await repo.get_transaction_override(session, txn.id)
        user_override: UserOverride | None = None
        if override_row is not None:
            user_override = UserOverride(
                master_bucket=MasterBucket(override_row.master_bucket),
                category=override_row.category,
                cash_flow_type=CashFlowType(override_row.cash_flow_type),
            )

        merchant_rule: MerchantRule | None = None
        if user_override is None:
            rule_row = await repo.find_merchant_rule(
                session,
                text=txn_input.text(),
                raw_category=txn.category,
                account_id=txn.account_id,
            )
            if rule_row is not None:
                merchant_rule = MerchantRule(
                    scope=RuleScope(rule_row.scope),
                    master_bucket=MasterBucket(rule_row.master_bucket),
                    category=rule_row.category,
                    cash_flow_type=CashFlowType(rule_row.cash_flow_type),
                )

        llm_result: ClassificationResult | None = None
        if user_override is None and merchant_rule is None and self._llm_classifier is not None:
            # Probe deterministically first so we only call the LLM when tiers
            # 3-5 truly found nothing (never call an LLM speculatively).
            probe = classify_transaction(
                txn_input, user_override=user_override, merchant_rule=merchant_rule,
            )
            if probe.source == ClassificationSource.UNKNOWN:
                try:
                    llm_result = await self._llm_classifier(txn_input)
                except Exception:  # noqa: BLE001 — LLM fallback is best-effort
                    # app.core.logger.get_logger returns a stdlib Logger, which
                    # only accepts structured fields via `extra=` (passing
                    # transaction_id= directly raises TypeError and would turn a
                    # best-effort fallback into a hard failure).
                    logger.warning(
                        "classification.llm_fallback_failed",
                        extra={"transaction_id": txn.id},
                        exc_info=True,
                    )
                    llm_result = None

        return classify_transaction(
            txn_input,
            user_override=user_override,
            merchant_rule=merchant_rule,
            llm_result=llm_result,
        )

    # ── Single-transaction classify + persist ────────────────────────────────

    async def classify(
        self,
        session: AsyncSession,
        transaction_id: str,
        *,
        persist: bool = True,
    ) -> ClassificationResult:
        txn = await repo.get_transaction(session, transaction_id)
        result = await self.resolve(session, txn)
        if persist:
            _persist(txn, result)
            session.add(txn)
            await session.flush()
        return result

    # ── Batch classify ───────────────────────────────────────────────────────

    async def classify_batch(
        self,
        session: AsyncSession,
        *,
        account_id: str | None = None,
        only_unclassified: bool = True,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int | None = None,
    ) -> BatchClassificationSummary:
        """Classify a set of transactions and persist the results.

        By default only touches transactions that have never been classified
        (classification_source IS NULL), so a user's prior tier-1 override
        result is never silently reclassified by a batch run — the override
        row is still consulted every time regardless, but this flag avoids
        needlessly recomputing settled classifications on every ingest.

        `date_from`/`date_to` (optional, inclusive) bound the backfill to one
        period; omitting them keeps the original all-history behaviour.
        """
        transactions = await repo.list_transactions(
            session, account_id=account_id, unclassified_only=only_unclassified,
            date_from=date_from, date_to=date_to, limit=limit,
        )
        summary = BatchClassificationSummary(total=len(transactions))
        for txn in transactions:
            result = await self.resolve(session, txn)
            _persist(txn, result)
            session.add(txn)
            summary.classified += 1
            if result.needs_review:
                summary.needs_review += 1
            source_value = result.source.value
            summary.by_source[source_value] = summary.by_source.get(source_value, 0) + 1
        await session.flush()
        return summary

    # ── User overrides (tier 1) ──────────────────────────────────────────────

    async def apply_user_override(
        self,
        session: AsyncSession,
        transaction_id: str,
        *,
        master_bucket: MasterBucket | str,
        cash_flow_type: CashFlowType | str,
        category: str | None = None,
    ) -> ClassificationResult:
        """Record an explicit user override for ONE transaction and re-persist
        its derived classification immediately. This always wins over every
        automated tier from now on — subsequent classify()/classify_batch()
        calls will keep finding this override first."""
        bucket = MasterBucket(master_bucket) if isinstance(master_bucket, str) else master_bucket
        flow = CashFlowType(cash_flow_type) if isinstance(cash_flow_type, str) else cash_flow_type

        await repo.upsert_transaction_override(
            session,
            transaction_id,
            master_bucket=bucket.value,
            category=category,
            cash_flow_type=flow.value,
        )
        return await self.classify(session, transaction_id, persist=True)

    # ── Merchant rules (tier 2) ──────────────────────────────────────────────

    async def apply_merchant_rule(
        self,
        session: AsyncSession,
        *,
        master_bucket: MasterBucket | str,
        cash_flow_type: CashFlowType | str,
        category: str | None = None,
        scope: RuleScope | str = RuleScope.MERCHANT,
        merchant_key: str | None = None,
        source_category: str | None = None,
        account_id: str | None = None,
        reclassify_existing: bool = True,
    ) -> BatchClassificationSummary | None:
        """Create a user merchant/category rule and (by default) reclassify
        matching existing transactions that do not already have an explicit
        per-transaction override (which always outranks a merchant rule)."""
        bucket = MasterBucket(master_bucket) if isinstance(master_bucket, str) else master_bucket
        flow = CashFlowType(cash_flow_type) if isinstance(cash_flow_type, str) else cash_flow_type
        rule_scope = RuleScope(scope) if isinstance(scope, str) else scope

        if rule_scope in (RuleScope.MERCHANT, RuleScope.MERCHANT_ACCOUNT) and not merchant_key:
            raise ValueError("merchant_key is required for merchant/merchant_account scoped rules")
        if rule_scope == RuleScope.CATEGORY and not source_category:
            raise ValueError("source_category is required for category-scoped rules")

        await repo.create_merchant_rule(
            session,
            scope=rule_scope.value,
            master_bucket=bucket.value,
            category=category,
            cash_flow_type=flow.value,
            merchant_key=merchant_key.lower() if merchant_key else None,
            source_category=source_category,
            account_id=account_id,
        )

        if not reclassify_existing:
            return None

        # Reclassify every existing transaction — resolve() re-checks the
        # per-transaction override first, so overridden rows are unaffected.
        return await self.classify_batch(session, only_unclassified=False)

    # ── Review queue ──────────────────────────────────────────────────────────

    async def get_needs_review(
        self,
        session: AsyncSession,
        *,
        limit: int = 100,
        date_from: date | None = None,
        date_to: date | None = None,
        auto_classify: bool = True,
    ) -> list[TransactionModel]:
        """Prioritized review queue (pr-09-classification-review.md: "Do not
        show every transaction. Prioritize: low-confidence transactions,
        ambiguous merchants, high financial impact..."). Fetches the full
        `needs_review` set (unbounded — personal-finance scale, not a
        pagination-worthy table) then sorts by least-confident first, tie-
        broken by largest absolute dollar impact first, before truncating to
        `limit`. `list_transactions`' own ordering (transaction_date desc) is
        deliberately not relied on here — a page of the 25 most *recent*
        flagged transactions is not the same as the 25 most worth reviewing.

        `date_from`/`date_to` (optional, inclusive) restrict the queue to one
        period. The Banking page always passes the globally-selected period
        (pr-05-period-filter.md: the selected period "should drive backend
        API queries" and "update all three financial pages"), which is also
        what makes the work order's "transactions that materially affect plan
        results" concrete — a correction to a row inside the displayed period
        visibly moves the Plan vs Actual numbers on the same screen.

        `auto_classify=True` (the default) first backfills any transaction
        whose `classification_source` is still NULL — exactly the same lazy
        backfill `app.services.plan_vs_actual._load_classified_transactions`
        already performs for a period, bounded to the same date range so the
        review queue never triggers a full-history write on a GET. Restricted
        to `only_unclassified=True` so a user's prior override/merchant-rule
        resolution is never recomputed.
        """
        if auto_classify:
            await self.classify_batch(
                session, only_unclassified=True, date_from=date_from, date_to=date_to,
            )

        candidates = await repo.list_transactions(
            session, needs_review_only=True, date_from=date_from, date_to=date_to,
        )

        def _sort_key(t: TransactionModel) -> tuple[float, Decimal]:
            confidence = (
                t.classification_confidence if t.classification_confidence is not None else 0.0
            )
            try:
                amount = abs(Decimal(t.amount))
            except (InvalidOperation, TypeError):
                amount = Decimal("0")
            return (confidence, -amount)

        candidates.sort(key=_sort_key)
        return candidates[:limit]

    # ── Reclassify (PR 09 "Change" action) ───────────────────────────────────

    async def reclassify_transaction(
        self,
        session: AsyncSession,
        transaction_id: str,
        *,
        master_bucket: MasterBucket,
        cash_flow_type: CashFlowType,
        category: str | None,
        scope: ReclassifyScope,
    ) -> tuple[ClassificationResult, int]:
        """Apply a user 'Change' decision with the requested scope.

        Returns `(this transaction's resulting classification, count of
        OTHER existing transactions also reclassified by this call)` — the
        count is always 0 for `transaction`/`merchant_future` and the number
        of same-merchant, same-calendar-month transactions for
        `merchant_this_month`.

        - `scope=transaction`: tier-1 override, this transaction only.
        - `scope=merchant_future`: tier-1 override for THIS transaction (it
          is the record the user is actively resolving right now, not a
          bystander swept in by a broad rule) PLUS a forward-looking tier-2
          merchant rule (`reclassify_existing=False`). No OTHER existing
          transaction is touched — verified from `apply_merchant_rule`'s own
          implementation, which returns immediately without calling
          `classify_batch` when `reclassify_existing=False`.
        - `scope=merchant_this_month`: tier-1 override for every transaction
          from this merchant within the SAME calendar month as the
          transaction under review (bounded — never "all history", per the
          work order's "never silently rewrite all historical transactions"),
          EXCEPT any bystander row that already carries its own explicit
          tier-1 override (an earlier user decision is not silently revoked
          by a bulk action aimed at a different transaction — the same
          protection `apply_merchant_rule` documents), PLUS the same
          forward-looking merchant rule as `merchant_future`.
          Implemented as per-transaction overrides rather than
          `apply_merchant_rule(reclassify_existing=True)` because that flag
          reclassifies EVERY matching transaction in the database with no
          date bound at all, which the work order explicitly forbids.
        """
        txn = await repo.get_transaction(session, transaction_id)

        # Always resolve THIS transaction via a tier-1 override, regardless
        # of scope — see docstring above.
        result = await self.apply_user_override(
            session, transaction_id,
            master_bucket=master_bucket, cash_flow_type=cash_flow_type, category=category,
        )

        if scope == ReclassifyScope.TRANSACTION:
            return result, 0

        merchant_key = derive_merchant_key(txn)
        if not merchant_key:
            # Nothing to key a merchant rule on (no description/merchant
            # name at all) — degrade to a transaction-only correction rather
            # than raising, since the per-transaction override above already
            # succeeded.
            return result, 0

        # Forward-looking merchant rule — shared by both remaining scopes.
        # reclassify_existing=False: verified to touch no existing row.
        await self.apply_merchant_rule(
            session,
            master_bucket=master_bucket, cash_flow_type=cash_flow_type, category=category,
            scope=RuleScope.MERCHANT, merchant_key=merchant_key,
            reclassify_existing=False,
        )

        if scope == ReclassifyScope.MERCHANT_FUTURE:
            return result, 0

        # scope == MERCHANT_THIS_MONTH — bounded to the transaction's own
        # calendar month.
        month_start = txn.transaction_date.replace(day=1)
        last_day = calendar.monthrange(txn.transaction_date.year, txn.transaction_date.month)[1]
        month_end = txn.transaction_date.replace(day=last_day)

        matching = await repo.list_transactions_by_merchant_text(
            session, merchant_text=merchant_key, date_from=month_start, date_to=month_end,
        )
        touched = 0
        for other in matching:
            if other.id == transaction_id:
                continue  # already handled above
            # A bystander row the user already resolved explicitly is NOT
            # re-decided by a bulk action aimed at a different transaction —
            # same protection `apply_merchant_rule` documents for tier-1
            # overrides. The user is correcting THIS row and asking Coral to
            # apply the same call to look-alikes, not to revoke an earlier
            # explicit decision they never revisited.
            if await repo.get_transaction_override(session, other.id) is not None:
                continue
            await self.apply_user_override(
                session, other.id,
                master_bucket=master_bucket, cash_flow_type=cash_flow_type, category=category,
            )
            touched += 1
        return result, touched
