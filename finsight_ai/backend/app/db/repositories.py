"""
Repository functions — all database access goes through here.

Clean abstraction over SQLModel queries. Services never construct raw SQL.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
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
    FinancialPlanModel,
    FinancialPlanVersionModel,
    HoldingModel,
    InstitutionModel,
    MerchantClassificationRuleModel,
    MorganStanleyDetailModel,
    PlanAllocationModel,
    PlanSuballocationModel,
    StatementModel,
    TextChunkModel,
    TransactionClassificationOverrideModel,
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
        # Delete child records — iterate per-ID so SQLite binding stays simple
        for model in [TransactionModel, FeeModel, HoldingModel, BalanceSnapshotModel]:
            for sid in stmt_ids:
                await session.execute(
                    text(f"DELETE FROM {model.__tablename__} WHERE statement_id = :sid"),
                    {"sid": sid}
                )
        # Delete bank-specific details
        for model in [MorganStanleyDetailModel, ChaseDetailModel, EtradeDetailModel,
                      AmexDetailModel, DiscoverDetailModel]:
            for sid in stmt_ids:
                await session.execute(
                    text(f"DELETE FROM {model.__tablename__} WHERE statement_id = :sid"),
                    {"sid": sid}
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

# Concurrent ingestion tasks (bulk upload fires one asyncio task per document)
# each run their own find-or-create check-then-act in a separate session/
# transaction. SQLite gives no row locking to prevent two tasks from both
# seeing "no match" and inserting duplicates, so we serialize the
# check-then-act with a process-wide lock instead.
_institution_lock = asyncio.Lock()
_account_lock = asyncio.Lock()


async def get_or_create_institution(
    session: AsyncSession, institution_type: str, name: str
) -> InstitutionModel:
    async with _institution_lock:
        result = await session.execute(
            select(InstitutionModel)
            .where(InstitutionModel.institution_type == institution_type)
            .order_by(InstitutionModel.created_at)
        )
        # Tolerate pre-existing duplicates: deterministically reuse the oldest match
        # rather than raising MultipleResultsFound.
        inst = result.scalars().first()
        if inst is None:
            inst = InstitutionModel(name=name, institution_type=institution_type)
            session.add(inst)
            await session.flush()
        return inst


# ── Accounts ─────────────────────────────────────────────────────────────────

_UNKNOWN_MASKS = {"", "unknown", "none", "n/a"}


async def get_or_create_account(
    session: AsyncSession,
    institution_id: str,
    institution_type: str,
    account_number_masked: str,
    account_type: str = "unknown",
    account_name: str | None = None,
) -> AccountModel:
    """Find or create an account for an institution.

    Matching key:
      - Normally `(institution_id, account_number_masked)` — a real masked card/
        account number uniquely identifies the account.
      - When the masked number is unknown/blank (the parser couldn't read it, e.g.
        Chase credit cards), fall back to `(institution_id, account_name)` so that
        distinct products (Prime Visa vs Freedom vs Sapphire) don't all collapse
        into a single "unknown" account. Without a name we keep the legacy single
        "unknown" bucket.
    """
    mask_known = account_number_masked.strip().lower() not in _UNKNOWN_MASKS

    if mask_known:
        stmt = (
            select(AccountModel)
            .where(
                AccountModel.institution_id == institution_id,
                AccountModel.account_number_masked == account_number_masked,
            )
            .order_by(AccountModel.created_at)
        )
    elif account_name:
        # Disambiguate unknown-masked accounts by their product name.
        stmt = (
            select(AccountModel)
            .where(
                AccountModel.institution_id == institution_id,
                AccountModel.account_number_masked == account_number_masked,
                AccountModel.account_name == account_name,
            )
            .order_by(AccountModel.created_at)
        )
    else:
        stmt = (
            select(AccountModel)
            .where(
                AccountModel.institution_id == institution_id,
                AccountModel.account_number_masked == account_number_masked,
                AccountModel.account_name.is_(None),
            )
            .order_by(AccountModel.created_at)
        )

    async with _account_lock:
        result = await session.execute(stmt)
        # Tolerate pre-existing duplicates: deterministically reuse the oldest match
        # rather than raising MultipleResultsFound.
        acct = result.scalars().first()
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
        else:
            # Update stale account_type — the parser is authoritative; an account
            # created from an earlier (or wrong) parse may have the wrong type.
            _VAGUE_TYPES = {"unknown", "brokerage", ""}
            if acct.account_type in _VAGUE_TYPES and account_type not in _VAGUE_TYPES:
                acct.account_type = account_type
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


async def delete_chunks_for_document(session: AsyncSession, doc_id: str) -> int:
    """Delete all text chunks (and their stored embeddings) for a document.

    Returns the number of chunk rows removed. FTS rows are removed separately via
    app.db.fts.delete_fts_for_document.
    """
    count_result = await session.execute(
        select(TextChunkModel.id).where(TextChunkModel.document_id == doc_id)
    )
    n = len(count_result.fetchall())
    await session.execute(
        text("DELETE FROM text_chunks WHERE document_id = :doc_id"),
        {"doc_id": doc_id},
    )
    return n


async def count_transactions_for_document(session: AsyncSession, doc_id: str) -> int:
    result = await session.execute(
        text("""
            SELECT COUNT(*) FROM transactions t
            JOIN statements s ON t.statement_id = s.id
            WHERE s.document_id = :doc_id
        """),
        {"doc_id": doc_id},
    )
    return int(result.scalar() or 0)


async def count_chunks_for_document(session: AsyncSession, doc_id: str, *, with_embedding: bool = False) -> int:
    sql = "SELECT COUNT(*) FROM text_chunks WHERE document_id = :doc_id"
    if with_embedding:
        sql += " AND embedding IS NOT NULL"
    result = await session.execute(text(sql), {"doc_id": doc_id})
    return int(result.scalar() or 0)


async def _count_child_for_document(session: AsyncSession, table: str, doc_id: str) -> int:
    """Count rows in a statement-child table (holdings/fees/balance_snapshots) for a doc."""
    result = await session.execute(
        text(f"""
            SELECT COUNT(*) FROM {table} x
            JOIN statements s ON x.statement_id = s.id
            WHERE s.document_id = :doc_id
        """),
        {"doc_id": doc_id},
    )
    return int(result.scalar() or 0)


async def count_holdings_for_document(session: AsyncSession, doc_id: str) -> int:
    return await _count_child_for_document(session, "holdings", doc_id)


async def count_fees_for_document(session: AsyncSession, doc_id: str) -> int:
    return await _count_child_for_document(session, "fees", doc_id)


async def count_balances_for_document(session: AsyncSession, doc_id: str) -> int:
    return await _count_child_for_document(session, "balance_snapshots", doc_id)


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


# ── Financial Plan ───────────────────────────────────────────────────────────

async def create_financial_plan(session: AsyncSession, **kwargs: Any) -> FinancialPlanModel:
    plan = FinancialPlanModel(**kwargs)
    session.add(plan)
    await session.flush()
    return plan


async def get_active_financial_plan(session: AsyncSession) -> FinancialPlanModel | None:
    result = await session.execute(
        select(FinancialPlanModel)
        .where(FinancialPlanModel.is_active == True)  # noqa: E712
        .order_by(FinancialPlanModel.created_at.asc())
    )
    return result.scalars().first()


async def create_plan_version(session: AsyncSession, **kwargs: Any) -> FinancialPlanVersionModel:
    version = FinancialPlanVersionModel(**kwargs)
    session.add(version)
    await session.flush()
    return version


async def get_plan_version(session: AsyncSession, version_id: str) -> FinancialPlanVersionModel:
    result = await session.execute(
        select(FinancialPlanVersionModel).where(FinancialPlanVersionModel.id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise EntityNotFoundError("FinancialPlanVersion", version_id)
    return version


async def get_version_by_effective_date(
    session: AsyncSession, plan_id: str, effective_from: date,
) -> FinancialPlanVersionModel | None:
    result = await session.execute(
        select(FinancialPlanVersionModel)
        .where(FinancialPlanVersionModel.plan_id == plan_id)
        .where(FinancialPlanVersionModel.effective_from == effective_from)
    )
    return result.scalar_one_or_none()


async def get_latest_version_for_date(
    session: AsyncSession, plan_id: str, target_date: date,
) -> FinancialPlanVersionModel | None:
    result = await session.execute(
        select(FinancialPlanVersionModel)
        .where(FinancialPlanVersionModel.plan_id == plan_id)
        .where(FinancialPlanVersionModel.effective_from <= target_date)
        .order_by(FinancialPlanVersionModel.effective_from.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_max_version_number(session: AsyncSession, plan_id: str) -> int:
    result = await session.execute(
        select(func.max(FinancialPlanVersionModel.version_number))
        .where(FinancialPlanVersionModel.plan_id == plan_id)
    )
    return result.scalar() or 0


async def list_versions_for_plan(session: AsyncSession, plan_id: str) -> list[FinancialPlanVersionModel]:
    result = await session.execute(
        select(FinancialPlanVersionModel)
        .where(FinancialPlanVersionModel.plan_id == plan_id)
        .order_by(FinancialPlanVersionModel.effective_from.desc())
    )
    return list(result.scalars().all())


async def create_allocation(session: AsyncSession, **kwargs: Any) -> PlanAllocationModel:
    allocation = PlanAllocationModel(**kwargs)
    session.add(allocation)
    await session.flush()
    return allocation


async def create_suballocation(session: AsyncSession, **kwargs: Any) -> PlanSuballocationModel:
    sub = PlanSuballocationModel(**kwargs)
    session.add(sub)
    await session.flush()
    return sub


async def get_allocations_for_version(session: AsyncSession, version_id: str) -> list[PlanAllocationModel]:
    result = await session.execute(
        select(PlanAllocationModel)
        .where(PlanAllocationModel.plan_version_id == version_id)
        .order_by(PlanAllocationModel.sort_order.asc())
    )
    return list(result.scalars().all())


async def get_suballocations_for_allocation(
    session: AsyncSession, allocation_id: str,
) -> list[PlanSuballocationModel]:
    result = await session.execute(
        select(PlanSuballocationModel)
        .where(PlanSuballocationModel.allocation_id == allocation_id)
        .order_by(PlanSuballocationModel.sort_order.asc())
    )
    return list(result.scalars().all())


async def get_transaction(session: AsyncSession, transaction_id: str) -> TransactionModel:
    result = await session.execute(
        select(TransactionModel).where(TransactionModel.id == transaction_id)
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        raise EntityNotFoundError("Transaction", transaction_id)
    return txn


async def list_transactions(
    session: AsyncSession,
    *,
    account_id: str | None = None,
    unclassified_only: bool = False,
    needs_review_only: bool = False,
    limit: int | None = None,
) -> list[TransactionModel]:
    q = select(TransactionModel)
    if account_id:
        q = q.where(TransactionModel.account_id == account_id)
    if unclassified_only:
        q = q.where(TransactionModel.classification_source.is_(None))
    if needs_review_only:
        q = q.where(TransactionModel.needs_review == True)  # noqa: E712
    q = q.order_by(TransactionModel.transaction_date.desc())
    if limit:
        q = q.limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())


async def list_transactions_for_period(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    account_id: str | None = None,
) -> list[TransactionModel]:
    """All transactions with transaction_date in [date_from, date_to]
    (inclusive both ends), used by app.services.plan_vs_actual. Callers are
    responsible for auto-classifying (classify_batch) before relying on the
    derived classification columns — this is a plain, unfiltered date-range
    read."""
    q = select(TransactionModel).where(
        TransactionModel.transaction_date >= date_from,
        TransactionModel.transaction_date <= date_to,
    )
    if account_id:
        q = q.where(TransactionModel.account_id == account_id)
    q = q.order_by(TransactionModel.transaction_date.asc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_accounts_by_ids(
    session: AsyncSession, account_ids: list[str],
) -> dict[str, AccountModel]:
    """Bulk account lookup keyed by id — avoids N+1 lazy-loads of
    TransactionModel.account under async SQLAlchemy."""
    if not account_ids:
        return {}
    result = await session.execute(
        select(AccountModel).where(AccountModel.id.in_(set(account_ids)))
    )
    return {a.id: a for a in result.scalars().all()}


# ── Transaction classification overrides (tier 1) ───────────────────────────

async def get_transaction_override(
    session: AsyncSession, transaction_id: str
) -> TransactionClassificationOverrideModel | None:
    result = await session.execute(
        select(TransactionClassificationOverrideModel)
        .where(TransactionClassificationOverrideModel.transaction_id == transaction_id)
    )
    return result.scalar_one_or_none()


async def upsert_transaction_override(
    session: AsyncSession,
    transaction_id: str,
    *,
    master_bucket: str,
    category: str | None,
    cash_flow_type: str,
) -> TransactionClassificationOverrideModel:
    existing = await get_transaction_override(session, transaction_id)
    if existing is not None:
        existing.master_bucket = master_bucket
        existing.category = category
        existing.cash_flow_type = cash_flow_type
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        await session.flush()
        return existing
    override = TransactionClassificationOverrideModel(
        transaction_id=transaction_id,
        master_bucket=master_bucket,
        category=category,
        cash_flow_type=cash_flow_type,
    )
    session.add(override)
    await session.flush()
    return override


# ── Merchant classification rules (tier 2) ──────────────────────────────────

async def create_merchant_rule(
    session: AsyncSession,
    *,
    scope: str,
    master_bucket: str,
    cash_flow_type: str,
    category: str | None = None,
    merchant_key: str | None = None,
    source_category: str | None = None,
    account_id: str | None = None,
) -> MerchantClassificationRuleModel:
    rule = MerchantClassificationRuleModel(
        scope=scope,
        merchant_key=merchant_key,
        source_category=source_category,
        account_id=account_id,
        master_bucket=master_bucket,
        category=category,
        cash_flow_type=cash_flow_type,
    )
    session.add(rule)
    await session.flush()
    return rule


async def list_merchant_rules(session: AsyncSession) -> list[MerchantClassificationRuleModel]:
    result = await session.execute(
        select(MerchantClassificationRuleModel)
        .order_by(MerchantClassificationRuleModel.created_at.desc())
    )
    return list(result.scalars().all())


async def find_merchant_rule(
    session: AsyncSession,
    *,
    text: str,
    raw_category: str | None,
    account_id: str | None,
) -> MerchantClassificationRuleModel | None:
    """Find the best-matching user merchant rule for a transaction.

    Preference order when multiple rules could match: merchant_account (most
    specific) > merchant > category. `text` is the lowercased merchant/
    description text already produced by TransactionClassificationInput.text().
    """
    rules = await list_merchant_rules(session)

    merchant_account_match = None
    merchant_match = None
    category_match = None

    for rule in rules:
        # merchant_key is normalized to lowercase on write, but lowercase again
        # here so a rule created directly via the repository still matches.
        if rule.scope == "merchant_account" and rule.merchant_key and rule.account_id:
            if rule.account_id == account_id and rule.merchant_key.lower() in text:
                merchant_account_match = merchant_account_match or rule
        elif rule.scope == "merchant" and rule.merchant_key:
            if rule.merchant_key.lower() in text:
                merchant_match = merchant_match or rule
        elif rule.scope == "category" and rule.source_category:
            if raw_category and rule.source_category.lower() == raw_category.lower():
                category_match = category_match or rule

    return merchant_account_match or merchant_match or category_match


async def delete_allocations_for_version(session: AsyncSession, version_id: str) -> None:
    """Delete all allocations (and cascade suballocations) for a version — used when
    replacing a not-yet-effective version's allocations in place."""
    allocations = await get_allocations_for_version(session, version_id)
    for alloc in allocations:
        await session.execute(
            text("DELETE FROM plan_suballocations WHERE allocation_id = :aid"),
            {"aid": alloc.id},
        )
    await session.execute(
        text("DELETE FROM plan_allocations WHERE plan_version_id = :vid"),
        {"vid": version_id},
    )
