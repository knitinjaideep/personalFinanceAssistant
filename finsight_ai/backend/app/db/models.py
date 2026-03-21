"""
SQLModel ORM models — canonical tables + bank-specific detail tables.

Design:
- Canonical tables are the primary query surface for chat and analytics.
- Bank-specific detail tables preserve institution-specific fields.
- Monetary values stored as String (Decimal) to avoid SQLite float precision loss.
- UUIDs stored as String in SQLite.
- text_chunks table stores document chunks for FTS5 and optional vector search.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ── Canonical tables ─────────────────────────────────────────────────────────

class InstitutionModel(SQLModel, table=True):
    __tablename__ = "institutions"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True)
    institution_type: str  # InstitutionType enum value
    website: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)

    accounts: list["AccountModel"] = Relationship(back_populates="institution")


class AccountModel(SQLModel, table=True):
    __tablename__ = "accounts"

    id: str = Field(default_factory=_uuid, primary_key=True)
    institution_id: str = Field(foreign_key="institutions.id", index=True)
    institution_type: str = "unknown"
    account_number_masked: str
    account_name: Optional[str] = None
    account_type: str = "unknown"
    currency: str = "USD"
    created_at: datetime = Field(default_factory=_now)

    institution: Optional[InstitutionModel] = Relationship(back_populates="accounts")
    balance_snapshots: list["BalanceSnapshotModel"] = Relationship(back_populates="account")
    transactions: list["TransactionModel"] = Relationship(back_populates="account")
    fees: list["FeeModel"] = Relationship(back_populates="account")
    holdings: list["HoldingModel"] = Relationship(back_populates="account")


class DocumentModel(SQLModel, table=True):
    """Raw document tracking — covers both uploaded files and scanner-discovered files."""
    __tablename__ = "documents"

    id: str = Field(default_factory=_uuid, primary_key=True)
    original_filename: str
    stored_filename: str
    file_path: str
    file_size_bytes: int
    mime_type: str
    institution_type: str = "unknown"
    status: str = "uploaded"  # DocumentStatus
    page_count: Optional[int] = None
    upload_time: datetime = Field(default_factory=_now)
    processed_time: Optional[datetime] = None
    error_message: Optional[str] = None

    # ── Scanner-provided fields (populated when sourced from local folders) ──
    # SHA-256 hex digest of the file — used to deduplicate re-scans.
    file_hash: Optional[str] = Field(default=None, index=True)
    # Absolute path as discovered by the scanner (may differ from stored_filename for uploads).
    source_file_path: Optional[str] = None
    # Human-readable product label, e.g. "Chase Freedom Unlimited", "Morgan Stanley IRA".
    account_product: Optional[str] = None
    # Source ID from StatementSource registry, e.g. "chase_freedom".
    source_id: Optional[str] = Field(default=None, index=True)

    statements: list["StatementModel"] = Relationship(back_populates="document")


class StatementModel(SQLModel, table=True):
    __tablename__ = "statements"

    id: str = Field(default_factory=_uuid, primary_key=True)
    document_id: str = Field(foreign_key="documents.id", index=True)
    institution_id: str = Field(foreign_key="institutions.id", index=True)
    institution_type: str = "unknown"
    account_id: str = Field(foreign_key="accounts.id", index=True)
    account_type: str = "unknown"
    statement_type: str = "unknown"
    period_start: date
    period_end: date
    currency: str = "USD"
    extraction_status: str = "pending"
    overall_confidence: float = 0.0
    warnings: str = "[]"  # JSON array
    created_at: datetime = Field(default_factory=_now)

    document: Optional[DocumentModel] = Relationship(back_populates="statements")
    balance_snapshots: list["BalanceSnapshotModel"] = Relationship(back_populates="statement")
    transactions: list["TransactionModel"] = Relationship(back_populates="statement")
    fees: list["FeeModel"] = Relationship(back_populates="statement")
    holdings: list["HoldingModel"] = Relationship(back_populates="statement")


class TransactionModel(SQLModel, table=True):
    __tablename__ = "transactions"

    id: str = Field(default_factory=_uuid, primary_key=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    statement_id: str = Field(foreign_key="statements.id", index=True)
    transaction_date: date = Field(index=True)
    settlement_date: Optional[date] = None
    description: str
    merchant_name: Optional[str] = None
    transaction_type: str = "other"
    category: Optional[str] = None
    amount: str  # Decimal as string
    currency: str = "USD"
    quantity: Optional[str] = None
    price_per_unit: Optional[str] = None
    symbol: Optional[str] = None
    is_recurring: bool = False
    confidence: float = 1.0
    source_page: Optional[int] = None

    account: Optional[AccountModel] = Relationship(back_populates="transactions")
    statement: Optional[StatementModel] = Relationship(back_populates="transactions")


class FeeModel(SQLModel, table=True):
    __tablename__ = "fees"

    id: str = Field(default_factory=_uuid, primary_key=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    statement_id: str = Field(foreign_key="statements.id", index=True)
    fee_date: date = Field(index=True)
    description: str
    amount: str  # Decimal as string
    fee_category: Optional[str] = None
    annualized_rate: Optional[str] = None
    currency: str = "USD"
    confidence: float = 1.0
    source_page: Optional[int] = None

    account: Optional[AccountModel] = Relationship(back_populates="fees")
    statement: Optional[StatementModel] = Relationship(back_populates="fees")


class HoldingModel(SQLModel, table=True):
    __tablename__ = "holdings"

    id: str = Field(default_factory=_uuid, primary_key=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    statement_id: str = Field(foreign_key="statements.id", index=True)
    symbol: Optional[str] = None
    description: str
    quantity: Optional[str] = None
    price: Optional[str] = None
    market_value: str  # Decimal as string
    cost_basis: Optional[str] = None
    unrealized_gain_loss: Optional[str] = None
    percent_of_portfolio: Optional[str] = None
    asset_class: Optional[str] = None
    currency: str = "USD"
    confidence: float = 1.0
    source_page: Optional[int] = None

    account: Optional[AccountModel] = Relationship(back_populates="holdings")
    statement: Optional[StatementModel] = Relationship(back_populates="holdings")


class BalanceSnapshotModel(SQLModel, table=True):
    __tablename__ = "balance_snapshots"

    id: str = Field(default_factory=_uuid, primary_key=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    statement_id: str = Field(foreign_key="statements.id", index=True)
    snapshot_date: date = Field(index=True)
    total_value: str  # Decimal as string
    cash_value: Optional[str] = None
    invested_value: Optional[str] = None
    unrealized_gain_loss: Optional[str] = None
    currency: str = "USD"
    confidence: float = 1.0
    source_page: Optional[int] = None

    account: Optional[AccountModel] = Relationship(back_populates="balance_snapshots")
    statement: Optional[StatementModel] = Relationship(back_populates="balance_snapshots")


class TextChunkModel(SQLModel, table=True):
    """Document text chunks for FTS5 and optional vector search."""
    __tablename__ = "text_chunks"

    id: str = Field(default_factory=_uuid, primary_key=True)
    document_id: str = Field(foreign_key="documents.id", index=True)
    statement_id: Optional[str] = Field(default=None, foreign_key="statements.id", index=True)
    chunk_index: int
    content: str
    page_number: Optional[int] = None
    section: Optional[str] = None
    institution_type: Optional[str] = None
    # Vector embedding stored as JSON array of floats (optional)
    embedding: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class DerivedMetricModel(SQLModel, table=True):
    """Pre-aggregated monthly metrics per account for fast analytics."""
    __tablename__ = "derived_metrics"

    id: str = Field(default_factory=_uuid, primary_key=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    institution_id: str = Field(foreign_key="institutions.id", index=True)
    institution_type: str = "unknown"
    statement_id: Optional[str] = Field(default=None, foreign_key="statements.id")
    month_start: date = Field(index=True)
    year: int = Field(index=True)
    month: int

    # Balance
    total_value: Optional[str] = None
    cash_value: Optional[str] = None
    invested_value: Optional[str] = None

    # Flow
    total_deposits: Optional[str] = None
    total_withdrawals: Optional[str] = None
    total_fees: Optional[str] = None
    total_dividends: Optional[str] = None
    net_cash_flow: Optional[str] = None

    # Banking spend
    total_spend: Optional[str] = None
    transaction_count: int = 0
    fee_count: int = 0
    holding_count: int = 0

    currency: str = "USD"
    generated_at: datetime = Field(default_factory=_now)


# ── Bank-specific detail tables ──────────────────────────────────────────────

class MorganStanleyDetailModel(SQLModel, table=True):
    """Morgan Stanley-specific statement fields not in the canonical schema."""
    __tablename__ = "morgan_stanley_details"

    id: str = Field(default_factory=_uuid, primary_key=True)
    statement_id: str = Field(foreign_key="statements.id", index=True, unique=True)
    financial_advisor: Optional[str] = None
    advisor_phone: Optional[str] = None
    management_fee_rate: Optional[str] = None
    asset_allocation_json: Optional[str] = None  # JSON
    performance_ytd: Optional[str] = None
    performance_1yr: Optional[str] = None
    tax_lot_details_json: Optional[str] = None  # JSON
    margin_balance: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class ChaseDetailModel(SQLModel, table=True):
    """Chase-specific statement fields."""
    __tablename__ = "chase_details"

    id: str = Field(default_factory=_uuid, primary_key=True)
    statement_id: str = Field(foreign_key="statements.id", index=True, unique=True)
    rewards_earned: Optional[str] = None
    rewards_redeemed: Optional[str] = None
    rewards_balance: Optional[str] = None
    apr_purchase: Optional[str] = None
    apr_cash_advance: Optional[str] = None
    credit_limit: Optional[str] = None
    available_credit: Optional[str] = None
    minimum_payment: Optional[str] = None
    autopay_status: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class EtradeDetailModel(SQLModel, table=True):
    """E*TRADE-specific statement fields."""
    __tablename__ = "etrade_details"

    id: str = Field(default_factory=_uuid, primary_key=True)
    statement_id: str = Field(foreign_key="statements.id", index=True, unique=True)
    margin_buying_power: Optional[str] = None
    option_buying_power: Optional[str] = None
    day_trading_buying_power: Optional[str] = None
    short_positions_json: Optional[str] = None  # JSON
    options_positions_json: Optional[str] = None  # JSON
    realized_gain_loss_ytd: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class AmexDetailModel(SQLModel, table=True):
    """Amex-specific statement fields."""
    __tablename__ = "amex_details"

    id: str = Field(default_factory=_uuid, primary_key=True)
    statement_id: str = Field(foreign_key="statements.id", index=True, unique=True)
    membership_rewards_earned: Optional[str] = None
    membership_rewards_balance: Optional[str] = None
    apr: Optional[str] = None
    credit_limit: Optional[str] = None
    payment_due_date: Optional[str] = None
    minimum_payment: Optional[str] = None
    year_to_date_spend: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class DiscoverDetailModel(SQLModel, table=True):
    """Discover-specific statement fields."""
    __tablename__ = "discover_details"

    id: str = Field(default_factory=_uuid, primary_key=True)
    statement_id: str = Field(foreign_key="statements.id", index=True, unique=True)
    cashback_earned: Optional[str] = None
    cashback_redeemed: Optional[str] = None
    cashback_balance: Optional[str] = None
    apr_purchase: Optional[str] = None
    credit_limit: Optional[str] = None
    minimum_payment: Optional[str] = None
    promotional_balance: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
