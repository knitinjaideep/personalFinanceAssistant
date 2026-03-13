"""
SQLModel ORM models — the persistence layer.

Design decisions:
- SQLModel is used so models serve as both SQLAlchemy table definitions
  AND Pydantic validation schemas (via model_validate / model_dump).
- Monetary values are stored as String to avoid SQLite float precision loss.
  The application layer converts to/from Decimal.
- UUIDs are stored as String in SQLite (no native UUID type).
- All tables use soft-deletable patterns via status columns rather than
  hard deletes, so audit trails are preserved.
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ── Institution ───────────────────────────────────────────────────────────────

class InstitutionModel(SQLModel, table=True):
    __tablename__ = "institutions"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    name: str = Field(index=True)
    institution_type: str                       # InstitutionType enum value
    website: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)

    # Relationships
    accounts: List["AccountModel"] = Relationship(back_populates="institution")


# ── Account ───────────────────────────────────────────────────────────────────

class AccountModel(SQLModel, table=True):
    __tablename__ = "accounts"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    institution_id: str = Field(foreign_key="institutions.id", index=True)
    account_number_masked: str
    account_name: Optional[str] = None
    account_type: str = "unknown"               # AccountType enum value
    currency: str = "USD"
    created_at: datetime = Field(default_factory=_now)

    # Relationships
    institution: Optional[InstitutionModel] = Relationship(back_populates="accounts")
    balance_snapshots: List["BalanceSnapshotModel"] = Relationship(back_populates="account")
    transactions: List["TransactionModel"] = Relationship(back_populates="account")
    fees: List["FeeModel"] = Relationship(back_populates="account")
    holdings: List["HoldingModel"] = Relationship(back_populates="account")


# ── Statement Document (raw upload) ──────────────────────────────────────────

class StatementDocumentModel(SQLModel, table=True):
    __tablename__ = "statement_documents"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    original_filename: str
    stored_filename: str
    file_path: str
    file_size_bytes: int
    mime_type: str
    institution_type: str = "unknown"
    document_status: str = "uploaded"           # DocumentStatus enum value
    page_count: Optional[int] = None
    upload_timestamp: datetime = Field(default_factory=_now)
    processed_timestamp: Optional[datetime] = None
    error_message: Optional[str] = None

    # Relationships
    statements: List["StatementModel"] = Relationship(back_populates="document")


# ── Statement (parsed + normalized) ──────────────────────────────────────────

class StatementModel(SQLModel, table=True):
    __tablename__ = "statements"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    document_id: str = Field(foreign_key="statement_documents.id", index=True)
    institution_id: str = Field(foreign_key="institutions.id", index=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    statement_type: str = "unknown"
    period_start: date
    period_end: date
    currency: str = "USD"
    extraction_status: str = "pending"          # ExtractionStatus enum value
    overall_confidence: float = 0.0
    extraction_notes: str = "[]"                # JSON array of strings
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    # Relationships
    document: Optional[StatementDocumentModel] = Relationship(back_populates="statements")
    balance_snapshots: List["BalanceSnapshotModel"] = Relationship(back_populates="statement")
    transactions: List["TransactionModel"] = Relationship(back_populates="statement")
    fees: List["FeeModel"] = Relationship(back_populates="statement")
    holdings: List["HoldingModel"] = Relationship(back_populates="statement")


# ── Balance Snapshot ──────────────────────────────────────────────────────────

class BalanceSnapshotModel(SQLModel, table=True):
    __tablename__ = "balance_snapshots"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    statement_id: str = Field(foreign_key="statements.id", index=True)
    snapshot_date: date = Field(index=True)
    total_value: str                            # Decimal as string
    cash_value: Optional[str] = None
    invested_value: Optional[str] = None
    unrealized_gain_loss: Optional[str] = None
    currency: str = "USD"
    confidence: float = 1.0
    source_page: Optional[int] = None
    source_section: Optional[str] = None

    # Relationships
    account: Optional[AccountModel] = Relationship(back_populates="balance_snapshots")
    statement: Optional[StatementModel] = Relationship(back_populates="balance_snapshots")


# ── Transaction ───────────────────────────────────────────────────────────────

class TransactionModel(SQLModel, table=True):
    __tablename__ = "transactions"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    statement_id: str = Field(foreign_key="statements.id", index=True)
    transaction_date: date = Field(index=True)
    settlement_date: Optional[date] = None
    description: str
    transaction_type: str = "other"             # TransactionType enum value
    amount: str                                 # Decimal as string
    currency: str = "USD"
    quantity: Optional[str] = None
    price_per_unit: Optional[str] = None
    symbol: Optional[str] = None
    confidence: float = 1.0
    source_page: Optional[int] = None
    source_section: Optional[str] = None

    # Relationships
    account: Optional[AccountModel] = Relationship(back_populates="transactions")
    statement: Optional[StatementModel] = Relationship(back_populates="transactions")


# ── Fee ───────────────────────────────────────────────────────────────────────

class FeeModel(SQLModel, table=True):
    __tablename__ = "fees"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    statement_id: str = Field(foreign_key="statements.id", index=True)
    transaction_id: Optional[str] = None        # Optional link to transaction
    fee_date: date = Field(index=True)
    description: str
    amount: str                                 # Always positive Decimal string
    fee_category: Optional[str] = None
    annualized_rate: Optional[str] = None
    currency: str = "USD"
    confidence: float = 1.0
    source_page: Optional[int] = None
    source_section: Optional[str] = None

    # Relationships
    account: Optional[AccountModel] = Relationship(back_populates="fees")
    statement: Optional[StatementModel] = Relationship(back_populates="fees")


# ── Holding ───────────────────────────────────────────────────────────────────

class HoldingModel(SQLModel, table=True):
    __tablename__ = "holdings"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    statement_id: str = Field(foreign_key="statements.id", index=True)
    symbol: Optional[str] = None
    description: str
    quantity: Optional[str] = None
    price: Optional[str] = None
    market_value: str                           # Decimal as string
    cost_basis: Optional[str] = None
    unrealized_gain_loss: Optional[str] = None
    percent_of_portfolio: Optional[str] = None
    asset_class: Optional[str] = None
    currency: str = "USD"
    confidence: float = 1.0
    source_page: Optional[int] = None
    source_section: Optional[str] = None

    # Relationships
    account: Optional[AccountModel] = Relationship(back_populates="holdings")
    statement: Optional[StatementModel] = Relationship(back_populates="holdings")


# ── Bucket ─────────────────────────────────────────────────────────────────────

class BucketModel(SQLModel, table=True):
    """
    A bucket is an agent-scoped workspace with its own document collection
    and retrieval context.  Buckets are first-class entities, not tags.
    """

    __tablename__ = "buckets"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    institution_type: Optional[str] = None  # InstitutionType enum value or None
    status: str = "active"                  # BucketStatus enum value
    color: str = "#3b82f6"
    icon: Optional[str] = None
    document_count: int = 0
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    # Relationships
    document_links: List["BucketDocumentModel"] = Relationship(back_populates="bucket")


# ── Bucket ↔ Document link ────────────────────────────────────────────────────

class BucketDocumentModel(SQLModel, table=True):
    """Many-to-many join between buckets and documents."""

    __tablename__ = "bucket_documents"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    bucket_id: str = Field(foreign_key="buckets.id", index=True)
    document_id: str = Field(foreign_key="statement_documents.id", index=True)
    assigned_at: datetime = Field(default_factory=_now)

    # Relationships
    bucket: Optional[BucketModel] = Relationship(back_populates="document_links")
    document: Optional[StatementDocumentModel] = Relationship()


# ── Processing Event ──────────────────────────────────────────────────────────

class ProcessingEventModel(SQLModel, table=True):
    """
    Persisted processing events for audit and replay.

    Events are primarily streamed via SSE; this table provides a durable
    history that the frontend can query for completed sessions.
    """

    __tablename__ = "processing_events"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    session_id: str = Field(index=True)
    event_type: str                         # ProcessingEventType enum value
    status: str                             # ProcessingEventStatus enum value
    agent_name: str
    step_name: str
    message: str
    bucket_id: Optional[str] = None
    bucket_name: Optional[str] = None
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    progress: Optional[float] = None        # 0.0–1.0
    metadata_json: str = "{}"              # JSON-serialized metadata dict
    timestamp: datetime = Field(default_factory=_now)


# ── Derived Monthly Metrics ───────────────────────────────────────────────────

class DerivedMonthlyMetricModel(SQLModel, table=True):
    """
    Pre-aggregated monthly financial metrics per account.

    Generated by MetricsService after a statement is approved/processed.
    Enables fast trend queries without re-scanning raw transaction tables.

    Monetary values are stored as String (Decimal) to avoid float precision loss.
    """

    __tablename__ = "derived_monthly_metrics"

    id: str = Field(default_factory=_new_uuid, primary_key=True)

    # Scope
    account_id: str = Field(foreign_key="accounts.id", index=True)
    institution_id: str = Field(foreign_key="institutions.id", index=True)
    statement_id: Optional[str] = Field(default=None, foreign_key="statements.id", index=True)

    # Period (always the first day of the month)
    month_start: date = Field(index=True)
    """First calendar day of the month this metric represents."""

    year: int = Field(index=True)
    month: int  # 1–12

    # Balance metrics
    total_value: Optional[str] = None
    """Portfolio / account total value at end of period (Decimal string)."""

    cash_value: Optional[str] = None
    invested_value: Optional[str] = None
    unrealized_gain_loss: Optional[str] = None

    # Transaction flow metrics
    total_deposits: Optional[str] = None
    """Sum of all deposit transactions in the month."""

    total_withdrawals: Optional[str] = None
    """Sum of all withdrawal transactions (stored as positive)."""

    total_fees: Optional[str] = None
    """Sum of all fees charged in the month."""

    total_dividends: Optional[str] = None
    net_cash_flow: Optional[str] = None
    """Deposits − Withdrawals − Fees."""

    transaction_count: int = 0
    fee_count: int = 0

    # Holdings snapshot (summary)
    holding_count: int = 0
    top_holding_symbol: Optional[str] = None
    top_holding_value: Optional[str] = None

    # Metadata
    currency: str = "USD"
    generated_at: datetime = Field(default_factory=_now)
    source: str = "ingestion"
    """How this record was created: 'ingestion' | 'manual_approval' | 'recompute'."""


# ── Deletion Record ───────────────────────────────────────────────────────────

class DeletionRecordModel(SQLModel, table=True):
    """Audit trail for document deletions."""

    __tablename__ = "deletion_records"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    document_id: str = Field(index=True)
    original_filename: str
    deleted_at: datetime = Field(default_factory=_now)
    deleted_by: str = "user"
    bucket_ids_removed: str = "[]"          # JSON array of strings
    embedding_ids_removed: int = 0
    sql_rows_json: str = "{}"              # JSON dict of table → count
