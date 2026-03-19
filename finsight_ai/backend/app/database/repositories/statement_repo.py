"""
Repository for Statement and StatementDocument persistence.

Repository pattern:
- All raw SQL / ORM queries live here, not in services.
- Services call repositories; services do NOT import SQLAlchemy directly.
- All methods are async and accept an injected AsyncSession.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Sequence

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    StatementDocumentModel,
    StatementModel,
    BalanceSnapshotModel,
    TransactionModel,
    FeeModel,
    HoldingModel,
)
from app.domain.entities import (
    Statement,
    StatementDocument,
    BalanceSnapshot,
    Transaction,
    Fee,
    Holding,
    SourceLocation,
    StatementPeriod,
    CashFlow,
)
from app.domain.enums import (
    DocumentStatus,
    ExtractionStatus,
    InstitutionType,
    StatementType,
    AccountType,
    TransactionType,
)
from app.domain.errors import EntityNotFoundError

logger = structlog.get_logger(__name__)


class StatementDocumentRepository:
    """CRUD operations for raw uploaded documents."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, document: StatementDocument) -> StatementDocumentModel:
        """Persist a new document record."""
        model = StatementDocumentModel(
            id=str(document.id),
            original_filename=document.original_filename,
            stored_filename=document.stored_filename,
            file_path=document.file_path,
            file_size_bytes=document.file_size_bytes,
            mime_type=document.mime_type,
            institution_type=document.institution_type.value,
            document_status=document.document_status.value,
            page_count=document.page_count,
            upload_timestamp=document.upload_timestamp,
        )
        self._session.add(model)
        await self._session.flush()
        logger.info("document.created", document_id=model.id, filename=model.original_filename)
        return model

    async def get_by_id(self, document_id: uuid.UUID) -> StatementDocumentModel:
        result = await self._session.execute(
            select(StatementDocumentModel).where(
                StatementDocumentModel.id == str(document_id)
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise EntityNotFoundError("StatementDocument", document_id)
        return model

    async def update_status(
        self,
        document_id: uuid.UUID,
        status: DocumentStatus,
        error_message: str | None = None,
    ) -> None:
        model = await self.get_by_id(document_id)
        model.document_status = status.value
        if error_message is not None:
            model.error_message = error_message
        await self._session.flush()

    async def list_all(self, limit: int = 100, offset: int = 0) -> Sequence[StatementDocumentModel]:
        result = await self._session.execute(
            select(StatementDocumentModel)
            .order_by(StatementDocumentModel.upload_timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()


class StatementRepository:
    """CRUD operations for normalized financial statements and child records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, statement: Statement) -> StatementModel:
        """Persist a statement and all its child records atomically."""
        model = StatementModel(
            id=str(statement.id),
            document_id=str(statement.document_id),
            institution_id=str(statement.institution_id),
            account_id=str(statement.account_id),
            statement_type=statement.statement_type.value,
            period_start=statement.period.start_date,
            period_end=statement.period.end_date,
            currency=statement.currency,
            extraction_status=statement.extraction_status.value,
            overall_confidence=statement.overall_confidence,
            extraction_notes=json.dumps(statement.extraction_notes),
        )
        self._session.add(model)
        await self._session.flush()

        # Persist child collections
        for bs in statement.balance_snapshots:
            await self._create_balance_snapshot(bs, statement_model=model)
        for tx in statement.transactions:
            await self._create_transaction(tx, statement_model=model)
        for fee in statement.fees:
            await self._create_fee(fee, statement_model=model)
        for holding in statement.holdings:
            await self._create_holding(holding, statement_model=model)

        logger.info(
            "statement.created",
            statement_id=model.id,
            institution=model.institution_id,
            period_start=str(model.period_start),
            period_end=str(model.period_end),
            transactions=len(statement.transactions),
            fees=len(statement.fees),
        )
        return model

    async def _create_balance_snapshot(
        self, bs: BalanceSnapshot, statement_model: StatementModel
    ) -> BalanceSnapshotModel:
        model = BalanceSnapshotModel(
            id=str(bs.id),
            account_id=str(bs.account_id),
            statement_id=statement_model.id,
            snapshot_date=bs.snapshot_date,
            total_value=str(bs.total_value),
            cash_value=str(bs.cash_value) if bs.cash_value is not None else None,
            invested_value=str(bs.invested_value) if bs.invested_value is not None else None,
            unrealized_gain_loss=(
                str(bs.unrealized_gain_loss) if bs.unrealized_gain_loss is not None else None
            ),
            currency=bs.currency,
            confidence=bs.confidence,
            source_page=bs.source.page if bs.source else None,
            source_section=bs.source.section if bs.source else None,
        )
        self._session.add(model)
        return model

    async def _create_transaction(
        self, tx: Transaction, statement_model: StatementModel
    ) -> TransactionModel:
        model = TransactionModel(
            id=str(tx.id),
            account_id=str(tx.account_id),
            statement_id=statement_model.id,
            transaction_date=tx.transaction_date,
            settlement_date=tx.settlement_date,
            description=tx.description,
            transaction_type=tx.transaction_type.value,
            amount=str(tx.amount),
            currency=tx.currency,
            quantity=str(tx.quantity) if tx.quantity is not None else None,
            price_per_unit=str(tx.price_per_unit) if tx.price_per_unit is not None else None,
            symbol=tx.symbol,
            confidence=tx.confidence,
            source_page=tx.source.page if tx.source else None,
            source_section=tx.source.section if tx.source else None,
        )
        self._session.add(model)
        return model

    async def _create_fee(
        self, fee: Fee, statement_model: StatementModel
    ) -> FeeModel:
        model = FeeModel(
            id=str(fee.id),
            account_id=str(fee.account_id),
            statement_id=statement_model.id,
            transaction_id=str(fee.transaction_id) if fee.transaction_id else None,
            fee_date=fee.fee_date,
            description=fee.description,
            amount=str(fee.amount),
            fee_category=fee.fee_category,
            annualized_rate=str(fee.annualized_rate) if fee.annualized_rate is not None else None,
            currency=fee.currency,
            confidence=fee.confidence,
            source_page=fee.source.page if fee.source else None,
            source_section=fee.source.section if fee.source else None,
        )
        self._session.add(model)
        return model

    async def _create_holding(
        self, holding: Holding, statement_model: StatementModel
    ) -> HoldingModel:
        model = HoldingModel(
            id=str(holding.id),
            account_id=str(holding.account_id),
            statement_id=statement_model.id,
            symbol=holding.symbol,
            description=holding.description,
            quantity=str(holding.quantity) if holding.quantity is not None else None,
            price=str(holding.price) if holding.price is not None else None,
            market_value=str(holding.market_value),
            cost_basis=str(holding.cost_basis) if holding.cost_basis is not None else None,
            unrealized_gain_loss=(
                str(holding.unrealized_gain_loss)
                if holding.unrealized_gain_loss is not None
                else None
            ),
            percent_of_portfolio=(
                str(holding.percent_of_portfolio)
                if holding.percent_of_portfolio is not None
                else None
            ),
            asset_class=holding.asset_class,
            currency=holding.currency,
            confidence=holding.confidence,
            source_page=holding.source.page if holding.source else None,
            source_section=holding.source.section if holding.source else None,
        )
        self._session.add(model)
        return model

    async def get_by_id(self, statement_id: uuid.UUID) -> StatementModel:
        result = await self._session.execute(
            select(StatementModel).where(StatementModel.id == str(statement_id))
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise EntityNotFoundError("Statement", statement_id)
        return model

    async def list_by_institution(
        self, institution_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> Sequence[StatementModel]:
        result = await self._session.execute(
            select(StatementModel)
            .where(StatementModel.institution_id == str(institution_id))
            .order_by(StatementModel.period_end.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_fees_in_range(
        self, start_date: date, end_date: date, institution_id: str | None = None
    ) -> Sequence[FeeModel]:
        """Retrieve all fees within a date range, optionally filtered by institution."""
        stmt = (
            select(FeeModel)
            .join(StatementModel, FeeModel.statement_id == StatementModel.id)
            .where(FeeModel.fee_date >= start_date)
            .where(FeeModel.fee_date <= end_date)
        )
        if institution_id:
            stmt = stmt.where(StatementModel.institution_id == institution_id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_balance_history(
        self, account_id: uuid.UUID, limit: int = 24
    ) -> Sequence[BalanceSnapshotModel]:
        """Return the most recent balance snapshots for an account."""
        result = await self._session.execute(
            select(BalanceSnapshotModel)
            .where(BalanceSnapshotModel.account_id == str(account_id))
            .order_by(BalanceSnapshotModel.snapshot_date.desc())
            .limit(limit)
        )
        return result.scalars().all()
