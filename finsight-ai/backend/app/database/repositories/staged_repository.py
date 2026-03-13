"""
Repository for all staged record models.

Provides typed CRUD for staged statements, transactions, fees, holdings,
and balance snapshots.  The review service (Phase 2.2) will call this
repository when approving/correcting/rejecting records and when promoting
them to canonical tables.

All methods accept a session injected by the service layer — no session
management happens here.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.staged_models import (
    StagedBalanceSnapshotModel,
    StagedFeeModel,
    StagedHoldingModel,
    StagedStatementModel,
    StagedTransactionModel,
)
from app.domain.enums import StagedRecordStatus

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Staged Statement
# ─────────────────────────────────────────────────────────────────────────────

class StagedStatementRepository:
    """CRUD for StagedStatementModel."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: StagedStatementModel) -> StagedStatementModel:
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, record_id: str) -> Optional[StagedStatementModel]:
        result = await self._session.execute(
            select(StagedStatementModel).where(StagedStatementModel.id == record_id)
        )
        return result.scalar_one_or_none()

    async def list_for_job(self, job_id: str) -> List[StagedStatementModel]:
        result = await self._session.execute(
            select(StagedStatementModel)
            .where(StagedStatementModel.ingestion_job_id == job_id)
            .order_by(StagedStatementModel.created_at.asc())  # type: ignore[union-attr]
        )
        return list(result.scalars().all())

    async def list_needing_review(self) -> List[StagedStatementModel]:
        result = await self._session.execute(
            select(StagedStatementModel).where(
                StagedStatementModel.status == StagedRecordStatus.NEEDS_REVIEW.value
            )
        )
        return list(result.scalars().all())

    async def set_status(
        self,
        record_id: str,
        status: StagedRecordStatus,
        reviewer_notes: Optional[str] = None,
    ) -> None:
        values: dict = {
            "status": status.value,
            "updated_at": datetime.utcnow(),
        }
        if status in (
            StagedRecordStatus.APPROVED,
            StagedRecordStatus.CORRECTED,
            StagedRecordStatus.REJECTED,
        ):
            values["reviewed_at"] = datetime.utcnow()
        if reviewer_notes is not None:
            values["reviewer_notes"] = reviewer_notes
        await self._session.execute(
            update(StagedStatementModel)
            .where(StagedStatementModel.id == record_id)
            .values(**values)
        )

    async def set_canonical_id(
        self, record_id: str, canonical_statement_id: str
    ) -> None:
        """Write back the canonical FK after successful promotion."""
        await self._session.execute(
            update(StagedStatementModel)
            .where(StagedStatementModel.id == record_id)
            .values(
                canonical_statement_id=canonical_statement_id,
                updated_at=datetime.utcnow(),
            )
        )

    async def update_field_flags(
        self, record_id: str, flags: dict[str, str]
    ) -> None:
        """Replace the field_flags_json blob."""
        await self._session.execute(
            update(StagedStatementModel)
            .where(StagedStatementModel.id == record_id)
            .values(
                field_flags_json=json.dumps(flags),
                updated_at=datetime.utcnow(),
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
# Staged Transaction
# ─────────────────────────────────────────────────────────────────────────────

class StagedTransactionRepository:
    """CRUD for StagedTransactionModel."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: StagedTransactionModel) -> StagedTransactionModel:
        self._session.add(record)
        await self._session.flush()
        return record

    async def bulk_create(
        self, records: List[StagedTransactionModel]
    ) -> List[StagedTransactionModel]:
        for r in records:
            self._session.add(r)
        await self._session.flush()
        return records

    async def get(self, record_id: str) -> Optional[StagedTransactionModel]:
        result = await self._session.execute(
            select(StagedTransactionModel).where(
                StagedTransactionModel.id == record_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_job(self, job_id: str) -> List[StagedTransactionModel]:
        result = await self._session.execute(
            select(StagedTransactionModel)
            .where(StagedTransactionModel.ingestion_job_id == job_id)
            .order_by(StagedTransactionModel.transaction_date.asc())  # type: ignore[union-attr]
        )
        return list(result.scalars().all())

    async def list_for_staged_statement(
        self, staged_statement_id: str
    ) -> List[StagedTransactionModel]:
        result = await self._session.execute(
            select(StagedTransactionModel)
            .where(
                StagedTransactionModel.staged_statement_id == staged_statement_id
            )
            .order_by(StagedTransactionModel.transaction_date.asc())  # type: ignore[union-attr]
        )
        return list(result.scalars().all())

    async def list_needing_review(
        self, job_id: Optional[str] = None
    ) -> List[StagedTransactionModel]:
        q = select(StagedTransactionModel).where(
            StagedTransactionModel.status == StagedRecordStatus.NEEDS_REVIEW.value
        )
        if job_id:
            q = q.where(StagedTransactionModel.ingestion_job_id == job_id)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def set_status(
        self,
        record_id: str,
        status: StagedRecordStatus,
        reviewer_notes: Optional[str] = None,
    ) -> None:
        values: dict = {
            "status": status.value,
            "updated_at": datetime.utcnow(),
        }
        if status in (
            StagedRecordStatus.APPROVED,
            StagedRecordStatus.CORRECTED,
            StagedRecordStatus.REJECTED,
        ):
            values["reviewed_at"] = datetime.utcnow()
        if reviewer_notes is not None:
            values["reviewer_notes"] = reviewer_notes
        await self._session.execute(
            update(StagedTransactionModel)
            .where(StagedTransactionModel.id == record_id)
            .values(**values)
        )

    async def apply_correction(
        self, record_id: str, field_updates: dict[str, object]
    ) -> None:
        """
        Apply a field-level correction dict and mark the record CORRECTED.

        Only whitelisted fields are mutated.  Unknown keys are silently ignored
        to prevent accidental schema corruption.
        """
        allowed = {
            "transaction_date", "settlement_date", "description",
            "transaction_type", "amount", "currency", "quantity",
            "price_per_unit", "symbol",
        }
        safe_updates = {k: v for k, v in field_updates.items() if k in allowed}
        if not safe_updates:
            return
        safe_updates["status"] = StagedRecordStatus.CORRECTED.value
        safe_updates["reviewed_at"] = datetime.utcnow()
        safe_updates["updated_at"] = datetime.utcnow()
        await self._session.execute(
            update(StagedTransactionModel)
            .where(StagedTransactionModel.id == record_id)
            .values(**safe_updates)
        )

    async def set_canonical_id(
        self, record_id: str, canonical_transaction_id: str
    ) -> None:
        await self._session.execute(
            update(StagedTransactionModel)
            .where(StagedTransactionModel.id == record_id)
            .values(
                canonical_transaction_id=canonical_transaction_id,
                updated_at=datetime.utcnow(),
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
# Staged Fee
# ─────────────────────────────────────────────────────────────────────────────

class StagedFeeRepository:
    """CRUD for StagedFeeModel."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: StagedFeeModel) -> StagedFeeModel:
        self._session.add(record)
        await self._session.flush()
        return record

    async def bulk_create(
        self, records: List[StagedFeeModel]
    ) -> List[StagedFeeModel]:
        for r in records:
            self._session.add(r)
        await self._session.flush()
        return records

    async def get(self, record_id: str) -> Optional[StagedFeeModel]:
        result = await self._session.execute(
            select(StagedFeeModel).where(StagedFeeModel.id == record_id)
        )
        return result.scalar_one_or_none()

    async def list_for_job(self, job_id: str) -> List[StagedFeeModel]:
        result = await self._session.execute(
            select(StagedFeeModel)
            .where(StagedFeeModel.ingestion_job_id == job_id)
            .order_by(StagedFeeModel.fee_date.asc())  # type: ignore[union-attr]
        )
        return list(result.scalars().all())

    async def set_status(
        self,
        record_id: str,
        status: StagedRecordStatus,
        reviewer_notes: Optional[str] = None,
    ) -> None:
        values: dict = {
            "status": status.value,
            "updated_at": datetime.utcnow(),
        }
        if status in (
            StagedRecordStatus.APPROVED,
            StagedRecordStatus.CORRECTED,
            StagedRecordStatus.REJECTED,
        ):
            values["reviewed_at"] = datetime.utcnow()
        if reviewer_notes is not None:
            values["reviewer_notes"] = reviewer_notes
        await self._session.execute(
            update(StagedFeeModel)
            .where(StagedFeeModel.id == record_id)
            .values(**values)
        )

    async def apply_correction(
        self, record_id: str, field_updates: dict[str, object]
    ) -> None:
        allowed = {"fee_date", "description", "amount", "fee_category",
                   "annualized_rate", "currency"}
        safe_updates = {k: v for k, v in field_updates.items() if k in allowed}
        if not safe_updates:
            return
        safe_updates["status"] = StagedRecordStatus.CORRECTED.value
        safe_updates["reviewed_at"] = datetime.utcnow()
        safe_updates["updated_at"] = datetime.utcnow()
        await self._session.execute(
            update(StagedFeeModel)
            .where(StagedFeeModel.id == record_id)
            .values(**safe_updates)
        )

    async def set_canonical_id(self, record_id: str, canonical_fee_id: str) -> None:
        await self._session.execute(
            update(StagedFeeModel)
            .where(StagedFeeModel.id == record_id)
            .values(canonical_fee_id=canonical_fee_id, updated_at=datetime.utcnow())
        )


# ─────────────────────────────────────────────────────────────────────────────
# Staged Holding
# ─────────────────────────────────────────────────────────────────────────────

class StagedHoldingRepository:
    """CRUD for StagedHoldingModel."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: StagedHoldingModel) -> StagedHoldingModel:
        self._session.add(record)
        await self._session.flush()
        return record

    async def bulk_create(
        self, records: List[StagedHoldingModel]
    ) -> List[StagedHoldingModel]:
        for r in records:
            self._session.add(r)
        await self._session.flush()
        return records

    async def get(self, record_id: str) -> Optional[StagedHoldingModel]:
        result = await self._session.execute(
            select(StagedHoldingModel).where(StagedHoldingModel.id == record_id)
        )
        return result.scalar_one_or_none()

    async def list_for_job(self, job_id: str) -> List[StagedHoldingModel]:
        result = await self._session.execute(
            select(StagedHoldingModel)
            .where(StagedHoldingModel.ingestion_job_id == job_id)
            .order_by(StagedHoldingModel.description.asc())  # type: ignore[union-attr]
        )
        return list(result.scalars().all())

    async def set_status(
        self,
        record_id: str,
        status: StagedRecordStatus,
        reviewer_notes: Optional[str] = None,
    ) -> None:
        values: dict = {
            "status": status.value,
            "updated_at": datetime.utcnow(),
        }
        if status in (
            StagedRecordStatus.APPROVED,
            StagedRecordStatus.CORRECTED,
            StagedRecordStatus.REJECTED,
        ):
            values["reviewed_at"] = datetime.utcnow()
        if reviewer_notes is not None:
            values["reviewer_notes"] = reviewer_notes
        await self._session.execute(
            update(StagedHoldingModel)
            .where(StagedHoldingModel.id == record_id)
            .values(**values)
        )

    async def apply_correction(
        self, record_id: str, field_updates: dict[str, object]
    ) -> None:
        allowed = {
            "symbol", "description", "quantity", "price", "market_value",
            "cost_basis", "unrealized_gain_loss", "percent_of_portfolio",
            "asset_class", "currency",
        }
        safe_updates = {k: v for k, v in field_updates.items() if k in allowed}
        if not safe_updates:
            return
        safe_updates["status"] = StagedRecordStatus.CORRECTED.value
        safe_updates["reviewed_at"] = datetime.utcnow()
        safe_updates["updated_at"] = datetime.utcnow()
        await self._session.execute(
            update(StagedHoldingModel)
            .where(StagedHoldingModel.id == record_id)
            .values(**safe_updates)
        )

    async def set_canonical_id(
        self, record_id: str, canonical_holding_id: str
    ) -> None:
        await self._session.execute(
            update(StagedHoldingModel)
            .where(StagedHoldingModel.id == record_id)
            .values(
                canonical_holding_id=canonical_holding_id,
                updated_at=datetime.utcnow(),
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
# Staged Balance Snapshot
# ─────────────────────────────────────────────────────────────────────────────

class StagedBalanceSnapshotRepository:
    """CRUD for StagedBalanceSnapshotModel."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, record: StagedBalanceSnapshotModel
    ) -> StagedBalanceSnapshotModel:
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(self, record_id: str) -> Optional[StagedBalanceSnapshotModel]:
        result = await self._session.execute(
            select(StagedBalanceSnapshotModel).where(
                StagedBalanceSnapshotModel.id == record_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_job(self, job_id: str) -> List[StagedBalanceSnapshotModel]:
        result = await self._session.execute(
            select(StagedBalanceSnapshotModel)
            .where(StagedBalanceSnapshotModel.ingestion_job_id == job_id)
            .order_by(StagedBalanceSnapshotModel.snapshot_date.asc())  # type: ignore[union-attr]
        )
        return list(result.scalars().all())

    async def set_status(
        self,
        record_id: str,
        status: StagedRecordStatus,
        reviewer_notes: Optional[str] = None,
    ) -> None:
        values: dict = {
            "status": status.value,
            "updated_at": datetime.utcnow(),
        }
        if status in (
            StagedRecordStatus.APPROVED,
            StagedRecordStatus.CORRECTED,
            StagedRecordStatus.REJECTED,
        ):
            values["reviewed_at"] = datetime.utcnow()
        if reviewer_notes is not None:
            values["reviewer_notes"] = reviewer_notes
        await self._session.execute(
            update(StagedBalanceSnapshotModel)
            .where(StagedBalanceSnapshotModel.id == record_id)
            .values(**values)
        )

    async def apply_correction(
        self, record_id: str, field_updates: dict[str, object]
    ) -> None:
        allowed = {
            "snapshot_date", "total_value", "cash_value",
            "invested_value", "unrealized_gain_loss", "currency",
        }
        safe_updates = {k: v for k, v in field_updates.items() if k in allowed}
        if not safe_updates:
            return
        safe_updates["status"] = StagedRecordStatus.CORRECTED.value
        safe_updates["reviewed_at"] = datetime.utcnow()
        safe_updates["updated_at"] = datetime.utcnow()
        await self._session.execute(
            update(StagedBalanceSnapshotModel)
            .where(StagedBalanceSnapshotModel.id == record_id)
            .values(**safe_updates)
        )

    async def set_canonical_id(
        self, record_id: str, canonical_balance_snapshot_id: str
    ) -> None:
        await self._session.execute(
            update(StagedBalanceSnapshotModel)
            .where(StagedBalanceSnapshotModel.id == record_id)
            .values(
                canonical_balance_snapshot_id=canonical_balance_snapshot_id,
                updated_at=datetime.utcnow(),
            )
        )
