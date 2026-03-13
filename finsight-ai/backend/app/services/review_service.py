"""
Review service — Phase 2.2.

Orchestrates the human-in-the-loop review workflow:

1. fetch_queue        — return pending review items (with optional job scope)
2. get_record_detail  — return full detail of any staged record type
3. approve            — mark a staged record APPROVED, resolve review item
4. correct            — apply field corrections, mark CORRECTED, resolve item
5. reject             — mark REJECTED, resolve item
6. skip               — defer item without decision
7. bulk_approve       — approve all EXTRACTED/NEEDS_REVIEW records for a job
8. promote_job        — promote all APPROVED/CORRECTED staged records to
                        canonical tables (Statement, Transaction, Fee, Holding,
                        BalanceSnapshot) and advance the job to COMPLETED.

Promotion writes canonical rows using the existing StatementRepository and
account/institution get_or_create logic, then writes back canonical_*_id to
each staged row so the link is durable.

The service is intentionally stateless — it takes a session at construction
time and uses repositories.  No global state.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AccountModel,
    BalanceSnapshotModel,
    FeeModel,
    HoldingModel,
    InstitutionModel,
    StatementModel,
    TransactionModel,
)
from app.database.repositories.account_repo import AccountRepository, InstitutionRepository
from app.database.repositories.ingestion_job_repository import IngestionJobRepository
from app.database.repositories.review_repository import ReviewItemRepository
from app.database.repositories.staged_repository import (
    StagedBalanceSnapshotRepository,
    StagedFeeRepository,
    StagedHoldingRepository,
    StagedStatementRepository,
    StagedTransactionRepository,
)
from app.database.staged_models import (
    IngestionJobModel,
    ReviewItemModel,
    StagedBalanceSnapshotModel,
    StagedFeeModel,
    StagedHoldingModel,
    StagedStatementModel,
    StagedTransactionModel,
)
from app.domain.enums import (
    IngestionJobStatus,
    ReviewItemStatus,
    ReviewItemType,
    StagedRecordStatus,
)
from app.domain.errors import EntityNotFoundError
from app.services.correction_service import CorrectionService

logger = structlog.get_logger(__name__)


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class ReviewService:
    """
    Orchestrates review queue interactions and staged→canonical promotion.

    All public methods are async and commit nothing themselves — the session
    is committed by the route dependency (get_session context manager).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._jobs = IngestionJobRepository(session)
        self._items = ReviewItemRepository(session)
        self._stmt_repo = StagedStatementRepository(session)
        self._tx_repo = StagedTransactionRepository(session)
        self._fee_repo = StagedFeeRepository(session)
        self._holding_repo = StagedHoldingRepository(session)
        self._bs_repo = StagedBalanceSnapshotRepository(session)
        self._institution_repo = InstitutionRepository(session)
        self._account_repo = AccountRepository(session)
        # Phase 2.5 — correction journal (shared session, same transaction)
        self._correction_svc = CorrectionService(session)

    # ── Queue ──────────────────────────────────────────────────────────────────

    async def fetch_queue(
        self,
        job_id: Optional[str] = None,
        record_type: Optional[ReviewItemType] = None,
        limit: int = 100,
    ) -> tuple[List[ReviewItemModel], int]:
        """
        Return pending review items and total pending count.

        Items are ordered by priority (ascending) then confidence (ascending)
        so the most urgent / least confident appear first.
        """
        items = await self._items.list_pending(
            job_id=job_id, record_type=record_type, limit=limit
        )
        total = await self._items.count_pending(job_id=job_id)
        return items, total

    async def get_job_summary(self, job_id: str) -> IngestionJobModel:
        """Return the ingestion job with staged record counts."""
        job = await self._jobs.get(job_id)
        if job is None:
            raise EntityNotFoundError("IngestionJob", job_id)
        return job

    async def count_staged_records(self, job_id: str) -> Dict[str, int]:
        """Return per-type counts of staged records for a job."""
        return {
            "staged_statements": len(await self._stmt_repo.list_for_job(job_id)),
            "staged_transactions": len(await self._tx_repo.list_for_job(job_id)),
            "staged_fees": len(await self._fee_repo.list_for_job(job_id)),
            "staged_holdings": len(await self._holding_repo.list_for_job(job_id)),
            "staged_balance_snapshots": len(await self._bs_repo.list_for_job(job_id)),
        }

    # ── Record detail ──────────────────────────────────────────────────────────

    async def get_staged_statement(self, record_id: str) -> StagedStatementModel:
        record = await self._stmt_repo.get(record_id)
        if record is None:
            raise EntityNotFoundError("StagedStatement", record_id)
        return record

    async def get_staged_transaction(self, record_id: str) -> StagedTransactionModel:
        record = await self._tx_repo.get(record_id)
        if record is None:
            raise EntityNotFoundError("StagedTransaction", record_id)
        return record

    async def get_staged_fee(self, record_id: str) -> StagedFeeModel:
        record = await self._fee_repo.get(record_id)
        if record is None:
            raise EntityNotFoundError("StagedFee", record_id)
        return record

    async def get_staged_holding(self, record_id: str) -> StagedHoldingModel:
        record = await self._holding_repo.get(record_id)
        if record is None:
            raise EntityNotFoundError("StagedHolding", record_id)
        return record

    async def get_staged_balance_snapshot(
        self, record_id: str
    ) -> StagedBalanceSnapshotModel:
        record = await self._bs_repo.get(record_id)
        if record is None:
            raise EntityNotFoundError("StagedBalanceSnapshot", record_id)
        return record

    # ── Review actions ─────────────────────────────────────────────────────────

    async def approve(
        self,
        review_item_id: str,
        notes: Optional[str] = None,
    ) -> ReviewItemModel:
        """Approve the staged record pointed to by the review item."""
        item = await self._get_item_or_raise(review_item_id)
        self._assert_actionable(item)

        await self._set_record_status(
            item.record_type, item.record_id, StagedRecordStatus.APPROVED, notes
        )
        await self._items.resolve(review_item_id, action="approved", notes=notes)

        logger.info(
            "review.approved",
            item_id=review_item_id,
            record_type=item.record_type,
            record_id=item.record_id,
        )
        return await self._get_item_or_raise(review_item_id)

    async def correct(
        self,
        review_item_id: str,
        field_updates: Dict[str, Any],
        notes: Optional[str] = None,
    ) -> ReviewItemModel:
        """
        Apply field corrections to the staged record and mark it CORRECTED.

        Phase 2.5: Captures the current field values *before* applying the
        correction, then journals each changed field to the ``field_corrections``
        table via ``CorrectionService``.  This enables:
        - Extraction hint retrieval for future documents (same institution + field).
        - Confidence calibration for systematically wrong fields.
        - Full correction history in the review drawer.
        """
        item = await self._get_item_or_raise(review_item_id)
        self._assert_actionable(item)

        # ── Snapshot original values before applying changes ───────────────────
        original_values, original_confidence, institution_type, job_id = (
            await self._snapshot_record(item.record_type, item.record_id)
        )

        # ── Apply the correction to the staged record ──────────────────────────
        await self._apply_correction(item.record_type, item.record_id, field_updates)
        if notes:
            await self._set_record_notes(item.record_type, item.record_id, notes)
        await self._items.resolve(review_item_id, action="corrected", notes=notes)

        # ── Resolve institution (non-statement types return None from snapshot) ──
        if institution_type is None and job_id:
            institution_type = await self._resolve_institution(job_id)

        # ── Journal each changed field to the correction store ─────────────────
        if field_updates and institution_type and job_id:
            try:
                await self._correction_svc.record_bulk(
                    institution_type=institution_type,
                    record_type=item.record_type,
                    staged_record_id=item.record_id,
                    ingestion_job_id=job_id,
                    field_updates=field_updates,
                    original_values=original_values,
                    original_confidence=original_confidence,
                    correction_reason=notes,
                )
            except Exception as exc:
                # Correction journaling is non-fatal — the review action itself
                # has already succeeded.  Log and continue.
                logger.warning(
                    "review.correction_journal_failed",
                    item_id=review_item_id,
                    error=str(exc),
                )

        logger.info(
            "review.corrected",
            item_id=review_item_id,
            record_type=item.record_type,
            record_id=item.record_id,
            fields_changed=list(field_updates.keys()),
        )
        return await self._get_item_or_raise(review_item_id)

    async def reject(
        self,
        review_item_id: str,
        notes: Optional[str] = None,
    ) -> ReviewItemModel:
        """Reject the staged record — it will not be promoted."""
        item = await self._get_item_or_raise(review_item_id)
        self._assert_actionable(item)

        await self._set_record_status(
            item.record_type, item.record_id, StagedRecordStatus.REJECTED, notes
        )
        await self._items.resolve(review_item_id, action="rejected", notes=notes)

        logger.info(
            "review.rejected",
            item_id=review_item_id,
            record_type=item.record_type,
            record_id=item.record_id,
        )
        return await self._get_item_or_raise(review_item_id)

    async def skip(self, review_item_id: str) -> ReviewItemModel:
        """Defer the item without making a decision."""
        item = await self._get_item_or_raise(review_item_id)
        if item.status != ReviewItemStatus.PENDING.value:
            raise ValueError(
                f"Review item {review_item_id} is not in PENDING state "
                f"(current: {item.status})"
            )
        await self._items.skip(review_item_id)
        return await self._get_item_or_raise(review_item_id)

    async def bulk_approve(
        self,
        job_id: str,
        notes: Optional[str] = None,
    ) -> int:
        """
        Approve all EXTRACTED and NEEDS_REVIEW staged records for a job.

        Returns the count of records approved.
        Skips records already in APPROVED, CORRECTED, or REJECTED state.
        """
        job = await self._jobs.get(job_id)
        if job is None:
            raise EntityNotFoundError("IngestionJob", job_id)

        approved_count = 0
        pending_items = await self._items.list_pending(job_id=job_id, limit=1000)

        for item in pending_items:
            await self._set_record_status(
                item.record_type, item.record_id, StagedRecordStatus.APPROVED, notes
            )
            await self._items.resolve(item.id, action="approved", notes=notes)
            approved_count += 1

        logger.info(
            "review.bulk_approved",
            job_id=job_id,
            count=approved_count,
        )
        return approved_count

    # ── Promotion ──────────────────────────────────────────────────────────────

    async def promote_job(self, job_id: str) -> Dict[str, Any]:
        """
        Promote all APPROVED and CORRECTED staged records to canonical tables.

        Steps:
        1. Validate that no PENDING review items remain.
        2. For each staged statement:
           a. get_or_create Institution + Account
           b. write StatementModel
           c. write child TransactionModel / FeeModel / HoldingModel /
              BalanceSnapshotModel rows
           d. write back canonical_*_id to staged rows
        3. Mark job COMPLETED.

        Returns promotion counts and any warnings.
        Raises ValueError if pending items still exist.
        """
        pending_count = await self._items.count_pending(job_id=job_id)
        if pending_count > 0:
            raise ValueError(
                f"Cannot promote job {job_id}: {pending_count} review items "
                "are still pending. Resolve all items first."
            )

        job = await self._jobs.get(job_id)
        if job is None:
            raise EntityNotFoundError("IngestionJob", job_id)

        warnings: List[str] = json.loads(job.warnings_json or "[]")
        counts = {
            "statements": 0,
            "transactions": 0,
            "fees": 0,
            "holdings": 0,
            "balance_snapshots": 0,
            "rejected": 0,
        }

        staged_statements = await self._stmt_repo.list_for_job(job_id)

        for ss in staged_statements:
            if ss.status == StagedRecordStatus.REJECTED.value:
                counts["rejected"] += 1
                continue

            if ss.status not in (
                StagedRecordStatus.APPROVED.value,
                StagedRecordStatus.CORRECTED.value,
            ):
                warnings.append(
                    f"Staged statement {ss.id} skipped promotion "
                    f"(status={ss.status})"
                )
                continue

            try:
                canonical_stmt = await self._promote_statement(ss, warnings)
                counts["statements"] += 1

                txs = await self._tx_repo.list_for_staged_statement(ss.id)
                for tx in txs:
                    if tx.status == StagedRecordStatus.REJECTED.value:
                        counts["rejected"] += 1
                        continue
                    if tx.status not in (
                        StagedRecordStatus.APPROVED.value,
                        StagedRecordStatus.CORRECTED.value,
                        StagedRecordStatus.EXTRACTED.value,  # auto-approve high-confidence
                    ):
                        continue
                    await self._promote_transaction(tx, canonical_stmt)
                    counts["transactions"] += 1

                fees = await self._fee_repo.list_for_job(job_id)
                for fee in fees:
                    if fee.staged_statement_id != ss.id:
                        continue
                    if fee.status == StagedRecordStatus.REJECTED.value:
                        counts["rejected"] += 1
                        continue
                    if fee.status not in (
                        StagedRecordStatus.APPROVED.value,
                        StagedRecordStatus.CORRECTED.value,
                        StagedRecordStatus.EXTRACTED.value,
                    ):
                        continue
                    await self._promote_fee(fee, canonical_stmt)
                    counts["fees"] += 1

                holdings = await self._holding_repo.list_for_job(job_id)
                for holding in holdings:
                    if holding.staged_statement_id != ss.id:
                        continue
                    if holding.status == StagedRecordStatus.REJECTED.value:
                        counts["rejected"] += 1
                        continue
                    if holding.status not in (
                        StagedRecordStatus.APPROVED.value,
                        StagedRecordStatus.CORRECTED.value,
                        StagedRecordStatus.EXTRACTED.value,
                    ):
                        continue
                    await self._promote_holding(holding, canonical_stmt)
                    counts["holdings"] += 1

                snapshots = await self._bs_repo.list_for_job(job_id)
                for snap in snapshots:
                    if snap.staged_statement_id != ss.id:
                        continue
                    if snap.status == StagedRecordStatus.REJECTED.value:
                        counts["rejected"] += 1
                        continue
                    if snap.status not in (
                        StagedRecordStatus.APPROVED.value,
                        StagedRecordStatus.CORRECTED.value,
                        StagedRecordStatus.EXTRACTED.value,
                    ):
                        continue
                    await self._promote_balance_snapshot(snap, canonical_stmt)
                    counts["balance_snapshots"] += 1

            except Exception as exc:
                msg = f"Failed to promote staged statement {ss.id}: {exc}"
                logger.error("promotion.statement_failed", error=msg)
                warnings.append(msg)
                # Continue with remaining statements rather than aborting entirely

        await self._jobs.mark_completed(job_id)
        logger.info("promotion.completed", job_id=job_id, counts=counts)

        return {
            "job_id": job_id,
            "statements_promoted": counts["statements"],
            "transactions_promoted": counts["transactions"],
            "fees_promoted": counts["fees"],
            "holdings_promoted": counts["holdings"],
            "balance_snapshots_promoted": counts["balance_snapshots"],
            "records_rejected": counts["rejected"],
            "warnings": warnings,
        }

    # ── Promotion helpers ──────────────────────────────────────────────────────

    async def _promote_statement(
        self,
        ss: StagedStatementModel,
        warnings: List[str],
    ) -> StatementModel:
        """Write a canonical StatementModel row from a staged statement."""
        # get_or_create Institution
        inst_result = await self._session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(InstitutionModel).where(
                InstitutionModel.institution_type == ss.institution_type
            )
        )
        institution = inst_result.scalar_one_or_none()
        if institution is None:
            institution = InstitutionModel(
                id=_new_uuid(),
                name=ss.institution_type.replace("_", " ").title(),
                institution_type=ss.institution_type,
            )
            self._session.add(institution)
            await self._session.flush()

        # get_or_create Account
        from sqlalchemy import select as sa_select
        acct_result = await self._session.execute(
            sa_select(AccountModel).where(
                AccountModel.institution_id == institution.id,
                AccountModel.account_number_masked == (ss.account_number_masked or "unknown"),
            )
        )
        account = acct_result.scalar_one_or_none()
        if account is None:
            account = AccountModel(
                id=_new_uuid(),
                institution_id=institution.id,
                account_number_masked=ss.account_number_masked or "unknown",
                account_name=ss.account_name,
                account_type=ss.account_type,
                currency=ss.currency,
            )
            self._session.add(account)
            await self._session.flush()

        from datetime import date as date_type
        period_start = ss.period_start or date_type.today()
        period_end = ss.period_end or date_type.today()

        canonical = StatementModel(
            id=_new_uuid(),
            document_id=ss.document_id,
            institution_id=institution.id,
            account_id=account.id,
            statement_type=ss.statement_type,
            period_start=period_start,
            period_end=period_end,
            currency=ss.currency,
            extraction_status="success",
            overall_confidence=ss.overall_confidence,
            extraction_notes=ss.extraction_notes_json,
        )
        self._session.add(canonical)
        await self._session.flush()

        await self._stmt_repo.set_canonical_id(ss.id, canonical.id)
        logger.info(
            "promotion.statement",
            staged_id=ss.id,
            canonical_id=canonical.id,
            period_start=str(period_start),
            period_end=str(period_end),
        )
        return canonical

    async def _promote_transaction(
        self,
        tx: StagedTransactionModel,
        canonical_stmt: StatementModel,
    ) -> TransactionModel:
        from datetime import date as date_type
        canonical = TransactionModel(
            id=_new_uuid(),
            account_id=canonical_stmt.account_id,
            statement_id=canonical_stmt.id,
            transaction_date=tx.transaction_date or date_type.today(),
            settlement_date=tx.settlement_date,
            description=tx.description,
            transaction_type=tx.transaction_type,
            amount=tx.amount,
            currency=tx.currency,
            quantity=tx.quantity,
            price_per_unit=tx.price_per_unit,
            symbol=tx.symbol,
            confidence=tx.confidence,
            source_page=tx.source_page,
            source_section=tx.source_section,
        )
        self._session.add(canonical)
        await self._session.flush()
        await self._tx_repo.set_canonical_id(tx.id, canonical.id)
        return canonical

    async def _promote_fee(
        self,
        fee: StagedFeeModel,
        canonical_stmt: StatementModel,
    ) -> FeeModel:
        from datetime import date as date_type
        canonical = FeeModel(
            id=_new_uuid(),
            account_id=canonical_stmt.account_id,
            statement_id=canonical_stmt.id,
            fee_date=fee.fee_date or date_type.today(),
            description=fee.description,
            amount=fee.amount,
            fee_category=fee.fee_category,
            annualized_rate=fee.annualized_rate,
            currency=fee.currency,
            confidence=fee.confidence,
            source_page=fee.source_page,
            source_section=fee.source_section,
        )
        self._session.add(canonical)
        await self._session.flush()
        await self._fee_repo.set_canonical_id(fee.id, canonical.id)
        return canonical

    async def _promote_holding(
        self,
        holding: StagedHoldingModel,
        canonical_stmt: StatementModel,
    ) -> HoldingModel:
        canonical = HoldingModel(
            id=_new_uuid(),
            account_id=canonical_stmt.account_id,
            statement_id=canonical_stmt.id,
            symbol=holding.symbol,
            description=holding.description,
            quantity=holding.quantity,
            price=holding.price,
            market_value=holding.market_value,
            cost_basis=holding.cost_basis,
            unrealized_gain_loss=holding.unrealized_gain_loss,
            percent_of_portfolio=holding.percent_of_portfolio,
            asset_class=holding.asset_class,
            currency=holding.currency,
            confidence=holding.confidence,
            source_page=holding.source_page,
            source_section=holding.source_section,
        )
        self._session.add(canonical)
        await self._session.flush()
        await self._holding_repo.set_canonical_id(holding.id, canonical.id)
        return canonical

    async def _promote_balance_snapshot(
        self,
        snap: StagedBalanceSnapshotModel,
        canonical_stmt: StatementModel,
    ) -> BalanceSnapshotModel:
        from datetime import date as date_type
        canonical = BalanceSnapshotModel(
            id=_new_uuid(),
            account_id=canonical_stmt.account_id,
            statement_id=canonical_stmt.id,
            snapshot_date=snap.snapshot_date or date_type.today(),
            total_value=snap.total_value,
            cash_value=snap.cash_value,
            invested_value=snap.invested_value,
            unrealized_gain_loss=snap.unrealized_gain_loss,
            currency=snap.currency,
            confidence=snap.confidence,
            source_page=snap.source_page,
            source_section=snap.source_section,
        )
        self._session.add(canonical)
        await self._session.flush()
        await self._bs_repo.set_canonical_id(snap.id, canonical.id)
        return canonical

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _snapshot_record(
        self,
        record_type: str,
        record_id: str,
    ) -> tuple[Dict[str, Any], float, Optional[str], Optional[str]]:
        """
        Fetch the current field values of a staged record before correction.

        Returns a 4-tuple:
          (original_values, original_confidence, institution_type, ingestion_job_id)

        ``original_values`` is a dict of field_name → current value.
        Used by ``correct()`` to journal what changed vs. what was there before.

        Returns empty defaults if the record cannot be found (non-fatal).
        """
        try:
            if record_type == ReviewItemType.STAGED_TRANSACTION.value:
                rec = await self._tx_repo.get(record_id)
                if rec:
                    return (
                        {
                            "transaction_date": str(rec.transaction_date) if rec.transaction_date else None,
                            "settlement_date": str(rec.settlement_date) if rec.settlement_date else None,
                            "description": rec.description,
                            "transaction_type": rec.transaction_type,
                            "amount": rec.amount,
                            "currency": rec.currency,
                            "quantity": rec.quantity,
                            "price_per_unit": rec.price_per_unit,
                            "symbol": rec.symbol,
                        },
                        rec.confidence,
                        None,  # institution resolved from job below
                        rec.ingestion_job_id,
                    )
            elif record_type == ReviewItemType.STAGED_FEE.value:
                rec = await self._fee_repo.get(record_id)
                if rec:
                    return (
                        {
                            "fee_date": str(rec.fee_date) if rec.fee_date else None,
                            "description": rec.description,
                            "amount": rec.amount,
                            "fee_category": rec.fee_category,
                            "annualized_rate": rec.annualized_rate,
                            "currency": rec.currency,
                        },
                        rec.confidence,
                        None,
                        rec.ingestion_job_id,
                    )
            elif record_type == ReviewItemType.STAGED_HOLDING.value:
                rec = await self._holding_repo.get(record_id)
                if rec:
                    return (
                        {
                            "symbol": rec.symbol,
                            "description": rec.description,
                            "quantity": rec.quantity,
                            "price": rec.price,
                            "market_value": rec.market_value,
                            "cost_basis": rec.cost_basis,
                            "unrealized_gain_loss": rec.unrealized_gain_loss,
                            "percent_of_portfolio": rec.percent_of_portfolio,
                            "asset_class": rec.asset_class,
                            "currency": rec.currency,
                        },
                        rec.confidence,
                        None,
                        rec.ingestion_job_id,
                    )
            elif record_type == ReviewItemType.STAGED_BALANCE_SNAPSHOT.value:
                rec = await self._bs_repo.get(record_id)
                if rec:
                    return (
                        {
                            "snapshot_date": str(rec.snapshot_date) if rec.snapshot_date else None,
                            "total_value": rec.total_value,
                            "cash_value": rec.cash_value,
                            "invested_value": rec.invested_value,
                            "unrealized_gain_loss": rec.unrealized_gain_loss,
                            "currency": rec.currency,
                        },
                        rec.confidence,
                        None,
                        rec.ingestion_job_id,
                    )
            elif record_type == ReviewItemType.STAGED_STATEMENT.value:
                rec = await self._stmt_repo.get(record_id)
                if rec:
                    return (
                        {
                            "institution_type": rec.institution_type,
                            "account_number_masked": rec.account_number_masked,
                            "account_name": rec.account_name,
                            "account_type": rec.account_type,
                            "statement_type": rec.statement_type,
                            "period_start": str(rec.period_start) if rec.period_start else None,
                            "period_end": str(rec.period_end) if rec.period_end else None,
                            "currency": rec.currency,
                        },
                        rec.overall_confidence,
                        rec.institution_type,
                        rec.ingestion_job_id,
                    )
        except Exception as exc:
            logger.warning(
                "review.snapshot_failed",
                record_type=record_type,
                record_id=record_id,
                error=str(exc),
            )

        return {}, 1.0, None, None

    async def _resolve_institution(self, job_id: str) -> Optional[str]:
        """Return the institution_type for an ingestion job via its staged statement."""
        stmts = await self._stmt_repo.list_for_job(job_id)
        if stmts:
            return stmts[0].institution_type
        return None

    async def _get_item_or_raise(self, item_id: str) -> ReviewItemModel:
        item = await self._items.get(item_id)
        if item is None:
            raise EntityNotFoundError("ReviewItem", item_id)
        return item

    def _assert_actionable(self, item: ReviewItemModel) -> None:
        """Raise if the item is not in a state that accepts approve/correct/reject."""
        if item.status not in (
            ReviewItemStatus.PENDING.value,
            ReviewItemStatus.SKIPPED.value,
        ):
            raise ValueError(
                f"Review item {item.id} is not actionable "
                f"(current status: {item.status})"
            )

    async def _set_record_status(
        self,
        record_type: str,
        record_id: str,
        status: StagedRecordStatus,
        notes: Optional[str],
    ) -> None:
        repo = self._repo_for_type(record_type)
        await repo.set_status(record_id, status, reviewer_notes=notes)

    async def _set_record_notes(
        self, record_type: str, record_id: str, notes: str
    ) -> None:
        repo = self._repo_for_type(record_type)
        await repo.set_status(record_id, StagedRecordStatus.CORRECTED, reviewer_notes=notes)

    async def _apply_correction(
        self, record_type: str, record_id: str, field_updates: Dict[str, Any]
    ) -> None:
        if record_type == ReviewItemType.STAGED_TRANSACTION.value:
            await self._tx_repo.apply_correction(record_id, field_updates)
        elif record_type == ReviewItemType.STAGED_FEE.value:
            await self._fee_repo.apply_correction(record_id, field_updates)
        elif record_type == ReviewItemType.STAGED_HOLDING.value:
            await self._holding_repo.apply_correction(record_id, field_updates)
        elif record_type == ReviewItemType.STAGED_BALANCE_SNAPSHOT.value:
            await self._bs_repo.apply_correction(record_id, field_updates)
        elif record_type == ReviewItemType.STAGED_STATEMENT.value:
            # Statement corrections go through set_status only (header fields
            # are set via the correction store in Phase 2.5)
            await self._stmt_repo.set_status(
                record_id, StagedRecordStatus.CORRECTED
            )
        else:
            raise ValueError(f"Unknown record type for correction: {record_type}")

    def _repo_for_type(self, record_type: str):  # type: ignore[return]
        mapping = {
            ReviewItemType.STAGED_STATEMENT.value: self._stmt_repo,
            ReviewItemType.STAGED_TRANSACTION.value: self._tx_repo,
            ReviewItemType.STAGED_FEE.value: self._fee_repo,
            ReviewItemType.STAGED_HOLDING.value: self._holding_repo,
            ReviewItemType.STAGED_BALANCE_SNAPSHOT.value: self._bs_repo,
        }
        repo = mapping.get(record_type)
        if repo is None:
            raise ValueError(f"No repository for record type: {record_type}")
        return repo
