"""
Repository functions — all database access goes through here.

Clean abstraction over SQLModel queries. Services never construct raw SQL.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import structlog
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.models import (
    AccountModel,
    AmexDetailModel,
    BalanceSnapshotModel,
    ChaseDetailModel,
    DerivedMetricModel,
    DiscoverDetailModel,
    DocumentModel,
    EtradeDetailModel,
    FeeModel,
    HoldingModel,
    InstitutionModel,
    MorganStanleyDetailModel,
    StatementModel,
    TextChunkModel,
    TransactionModel,
)
from app.domain.errors import EntityNotFoundError

logger = structlog.get_logger(__name__)


# ── Documents ────────────────────────────────────────────────────────────────

async def create_document(session: AsyncSession, **kwargs: Any) -> DocumentModel:
    doc = DocumentModel(**kwargs)
    session.add(doc)
    await session.flush()
    return doc


async def get_document(session: AsyncSession, doc_id: str) -> DocumentModel:
    result = await session.execute(select(DocumentModel).where(DocumentModel.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise EntityNotFoundError("Document", doc_id)
    return doc


async def list_documents(session: AsyncSession) -> list[DocumentModel]:
    result = await session.execute(
        select(DocumentModel).order_by(DocumentModel.upload_time.desc())
    )
    return list(result.scalars().all())


async def update_document(session: AsyncSession, doc_id: str, **kwargs: Any) -> DocumentModel:
    doc = await get_document(session, doc_id)
    for k, v in kwargs.items():
        setattr(doc, k, v)
    session.add(doc)
    await session.flush()
    return doc


async def delete_document_cascade(session: AsyncSession, doc_id: str) -> None:
    """Delete a document and all related records."""
    # Get statement IDs for this document
    stmt_result = await session.execute(
        select(StatementModel.id).where(StatementModel.document_id == doc_id)
    )
    stmt_ids = [r[0] for r in stmt_result.fetchall()]

    if stmt_ids:
        # Delete child records
        for model in [TransactionModel, FeeModel, HoldingModel, BalanceSnapshotModel]:
            await session.execute(
                text(f"DELETE FROM {model.__tablename__} WHERE statement_id IN :ids"),
                {"ids": tuple(stmt_ids)}
            )
        # Delete bank-specific details
        for model in [MorganStanleyDetailModel, ChaseDetailModel, EtradeDetailModel,
                      AmexDetailModel, DiscoverDetailModel]:
            await session.execute(
                text(f"DELETE FROM {model.__tablename__} WHERE statement_id IN :ids"),
                {"ids": tuple(stmt_ids)}
            )
        # Delete statements
        await session.execute(
            text("DELETE FROM statements WHERE document_id = :doc_id"),
            {"doc_id": doc_id}
        )

    # Delete text chunks
    await session.execute(
        text("DELETE FROM text_chunks WHERE document_id = :doc_id"),
        {"doc_id": doc_id}
    )
    # Delete document
    await session.execute(
        text("DELETE FROM documents WHERE id = :doc_id"),
        {"doc_id": doc_id}
    )


# ── Institutions ─────────────────────────────────────────────────────────────

async def get_or_create_institution(
    session: AsyncSession, institution_type: str, name: str
) -> InstitutionModel:
    result = await session.execute(
        select(InstitutionModel).where(InstitutionModel.institution_type == institution_type)
    )
    inst = result.scalar_one_or_none()
    if inst is None:
        inst = InstitutionModel(name=name, institution_type=institution_type)
        session.add(inst)
        await session.flush()
    return inst


# ── Accounts ─────────────────────────────────────────────────────────────────

async def get_or_create_account(
    session: AsyncSession,
    institution_id: str,
    institution_type: str,
    account_number_masked: str,
    account_type: str = "unknown",
    account_name: str | None = None,
) -> AccountModel:
    result = await session.execute(
        select(AccountModel).where(
            AccountModel.institution_id == institution_id,
            AccountModel.account_number_masked == account_number_masked,
        )
    )
    acct = result.scalar_one_or_none()
    if acct is None:
        acct = AccountModel(
            institution_id=institution_id,
            institution_type=institution_type,
            account_number_masked=account_number_masked,
            account_type=account_type,
            account_name=account_name,
        )
        session.add(acct)
        await session.flush()
    return acct


# ── Statements ───────────────────────────────────────────────────────────────

async def delete_statements_for_document(session: AsyncSession, doc_id: str) -> None:
    """Delete all statements and their child records for a document (for re-ingestion)."""
    stmt_result = await session.execute(
        select(StatementModel.id).where(StatementModel.document_id == doc_id)
    )
    stmt_ids = [r[0] for r in stmt_result.fetchall()]

    if stmt_ids:
        for model in [TransactionModel, FeeModel, HoldingModel, BalanceSnapshotModel]:
            for sid in stmt_ids:
                await session.execute(
                    text(f"DELETE FROM {model.__tablename__} WHERE statement_id = :sid"),
                    {"sid": sid}
                )
        for model in [MorganStanleyDetailModel, ChaseDetailModel, EtradeDetailModel,
                      AmexDetailModel, DiscoverDetailModel]:
            for sid in stmt_ids:
                await session.execute(
                    text(f"DELETE FROM {model.__tablename__} WHERE statement_id = :sid"),
                    {"sid": sid}
                )
        await session.execute(
            text("DELETE FROM statements WHERE document_id = :doc_id"),
            {"doc_id": doc_id}
        )


async def create_statement(session: AsyncSession, **kwargs: Any) -> StatementModel:
    stmt = StatementModel(**kwargs)
    session.add(stmt)
    await session.flush()
    return stmt


async def get_statements_for_document(session: AsyncSession, doc_id: str) -> list[StatementModel]:
    result = await session.execute(
        select(StatementModel).where(StatementModel.document_id == doc_id)
    )
    return list(result.scalars().all())


# ── Transactions ─────────────────────────────────────────────────────────────

async def bulk_create_transactions(session: AsyncSession, transactions: list[dict]) -> int:
    for txn_data in transactions:
        session.add(TransactionModel(**txn_data))
    await session.flush()
    return len(transactions)


# ── Fees ─────────────────────────────────────────────────────────────────────

async def bulk_create_fees(session: AsyncSession, fees: list[dict]) -> int:
    for fee_data in fees:
        session.add(FeeModel(**fee_data))
    await session.flush()
    return len(fees)


# ── Holdings ─────────────────────────────────────────────────────────────────

async def bulk_create_holdings(session: AsyncSession, holdings: list[dict]) -> int:
    for h_data in holdings:
        session.add(HoldingModel(**h_data))
    await session.flush()
    return len(holdings)


# ── Balance Snapshots ────────────────────────────────────────────────────────

async def bulk_create_balance_snapshots(session: AsyncSession, snapshots: list[dict]) -> int:
    for s_data in snapshots:
        session.add(BalanceSnapshotModel(**s_data))
    await session.flush()
    return len(snapshots)


# ── Text Chunks ──────────────────────────────────────────────────────────────

async def bulk_create_text_chunks(session: AsyncSession, chunks: list[dict]) -> list[TextChunkModel]:
    models = []
    for c_data in chunks:
        m = TextChunkModel(**c_data)
        session.add(m)
        models.append(m)
    await session.flush()
    return models


async def get_chunks_for_document(session: AsyncSession, doc_id: str) -> list[TextChunkModel]:
    result = await session.execute(
        select(TextChunkModel).where(TextChunkModel.document_id == doc_id)
        .order_by(TextChunkModel.chunk_index)
    )
    return list(result.scalars().all())


# ── Bank-specific details ────────────────────────────────────────────────────

DETAIL_MODEL_MAP: dict[str, type] = {
    "morgan_stanley": MorganStanleyDetailModel,
    "chase": ChaseDetailModel,
    "etrade": EtradeDetailModel,
    "amex": AmexDetailModel,
    "discover": DiscoverDetailModel,
}


async def create_institution_detail(
    session: AsyncSession, institution_type: str, statement_id: str, details: dict
) -> None:
    model_class = DETAIL_MODEL_MAP.get(institution_type)
    if model_class is None:
        return
    record = model_class(statement_id=statement_id, **details)
    session.add(record)
    await session.flush()


# ── Analytics queries ────────────────────────────────────────────────────────

async def get_analytics_summary(session: AsyncSession) -> dict:
    """Get high-level counts for the analytics summary."""
    docs = await session.execute(select(func.count(DocumentModel.id)))
    stmts = await session.execute(select(func.count(StatementModel.id)))
    txns = await session.execute(select(func.count(TransactionModel.id)))
    fees = await session.execute(select(func.count(FeeModel.id)))
    holdings = await session.execute(select(func.count(HoldingModel.id)))

    inst_result = await session.execute(
        select(InstitutionModel.institution_type).distinct()
    )
    institutions = [r[0] for r in inst_result.fetchall()]

    # Date range
    min_date = await session.execute(select(func.min(StatementModel.period_start)))
    max_date = await session.execute(select(func.max(StatementModel.period_end)))

    return {
        "total_documents": docs.scalar() or 0,
        "total_statements": stmts.scalar() or 0,
        "total_transactions": txns.scalar() or 0,
        "total_fees": fees.scalar() or 0,
        "total_holdings": holdings.scalar() or 0,
        "institutions": institutions,
        "date_range": {
            "start": str(min_date.scalar()) if min_date.scalar() else None,
            "end": str(max_date.scalar()) if max_date.scalar() else None,
        },
    }


async def query_transactions(
    session: AsyncSession,
    institution_type: str | None = None,
    account_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    category: str | None = None,
    transaction_type: str | None = None,
    limit: int = 100,
) -> list[TransactionModel]:
    """Flexible transaction query with filters."""
    q = select(TransactionModel)
    if institution_type:
        q = q.join(AccountModel).where(AccountModel.institution_type == institution_type)
    if account_id:
        q = q.where(TransactionModel.account_id == account_id)
    if date_from:
        q = q.where(TransactionModel.transaction_date >= date_from)
    if date_to:
        q = q.where(TransactionModel.transaction_date <= date_to)
    if category:
        q = q.where(TransactionModel.category == category)
    if transaction_type:
        q = q.where(TransactionModel.transaction_type == transaction_type)
    q = q.order_by(TransactionModel.transaction_date.desc()).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_fee_summary(
    session: AsyncSession,
    institution_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """Fee summary grouped by category."""
    q = select(
        FeeModel.fee_category,
        func.count(FeeModel.id).label("count"),
        func.sum(func.cast(FeeModel.amount, func.literal_column("REAL"))).label("total"),
    ).group_by(FeeModel.fee_category)

    if institution_type:
        q = q.join(AccountModel).where(AccountModel.institution_type == institution_type)
    if date_from:
        q = q.where(FeeModel.fee_date >= date_from)
    if date_to:
        q = q.where(FeeModel.fee_date <= date_to)

    result = await session.execute(q)
    return [
        {"category": row[0] or "uncategorized", "count": row[1], "total": str(row[2] or 0)}
        for row in result.fetchall()
    ]


async def get_holdings_summary(session: AsyncSession, account_id: str | None = None) -> list[dict]:
    """Get latest holdings snapshot."""
    q = select(HoldingModel)
    if account_id:
        q = q.where(HoldingModel.account_id == account_id)
    # Get most recent statement's holdings
    q = q.order_by(HoldingModel.statement_id.desc()).limit(100)
    result = await session.execute(q)
    holdings = result.scalars().all()
    return [
        {
            "symbol": h.symbol,
            "description": h.description,
            "quantity": h.quantity,
            "price": h.price,
            "market_value": h.market_value,
            "asset_class": h.asset_class,
        }
        for h in holdings
    ]


async def get_balance_history(
    session: AsyncSession, account_id: str | None = None
) -> list[dict]:
    """Balance snapshots over time."""
    q = select(BalanceSnapshotModel).order_by(BalanceSnapshotModel.snapshot_date)
    if account_id:
        q = q.where(BalanceSnapshotModel.account_id == account_id)
    result = await session.execute(q)
    return [
        {
            "date": str(b.snapshot_date),
            "total_value": b.total_value,
            "cash_value": b.cash_value,
            "invested_value": b.invested_value,
        }
        for b in result.scalars().all()
    ]
