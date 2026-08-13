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

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.db import repositories as repo
from app.db.models import AccountModel, TransactionModel
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
        limit: int | None = None,
    ) -> BatchClassificationSummary:
        """Classify a set of transactions and persist the results.

        By default only touches transactions that have never been classified
        (classification_source IS NULL), so a user's prior tier-1 override
        result is never silently reclassified by a batch run — the override
        row is still consulted every time regardless, but this flag avoids
        needlessly recomputing settled classifications on every ingest.
        """
        transactions = await repo.list_transactions(
            session, account_id=account_id, unclassified_only=only_unclassified, limit=limit,
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
        self, session: AsyncSession, *, limit: int = 100
    ) -> list[TransactionModel]:
        return await repo.list_transactions(session, needs_review_only=True, limit=limit)
