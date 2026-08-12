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

from sqlalchemy import UniqueConstraint
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


# ── Financial Plan ────────────────────────────────────────────────────────────
#
# The user's INTENDED allocation of income, kept separate from actual
# transactions. Versioned and effective-dated: a plan has many versions, each
# starting on a given date and remaining in effect until the next version's
# effective_from. There is no effective_until column — the active window is
# derived at query time (see FinancialPlanService.get_plan_for_date) so it can
# never drift out of sync with the version list.
#
# Fixed 2-level tree: plan_allocations are top-level buckets (Needs, Wants,
# Savings, Investments, or a custom bucket the user adds later — bucket_name is
# a free string, not an enum). plan_suballocations are optional children of a
# bucket; their percentage is a share of the TOTAL plan (e.g. Emergency Fund =
# 5%), not of the parent bucket's share, so a bucket's suballocations must sum
# to exactly that bucket's own percentage.

class FinancialPlanModel(SQLModel, table=True):
    """Container for the user's financial allocation plan, versioned over time.

    Coral is single-user/local-first, so exactly one active FinancialPlanModel
    row is expected to exist in practice (auto-seeded on first boot).
    """
    __tablename__ = "financial_plans"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = "Master Plan"
    is_active: bool = True
    created_at: datetime = Field(default_factory=_now)

    versions: list["FinancialPlanVersionModel"] = Relationship(back_populates="plan")


class FinancialPlanVersionModel(SQLModel, table=True):
    """A single effective-dated version of a plan's allocations."""
    __tablename__ = "financial_plan_versions"
    __table_args__ = (
        UniqueConstraint("plan_id", "effective_from", name="uq_plan_version_effective_from"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    plan_id: str = Field(foreign_key="financial_plans.id", index=True)
    version_number: int
    effective_from: date = Field(index=True)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)

    plan: Optional[FinancialPlanModel] = Relationship(back_populates="versions")
    allocations: list["PlanAllocationModel"] = Relationship(back_populates="plan_version")


class PlanAllocationModel(SQLModel, table=True):
    """Top-level bucket within a plan version (Needs, Wants, Savings, Investments, or custom)."""
    __tablename__ = "plan_allocations"

    id: str = Field(default_factory=_uuid, primary_key=True)
    plan_version_id: str = Field(foreign_key="financial_plan_versions.id", index=True)
    bucket_name: str
    percentage: str  # Decimal as string, e.g. "50"
    sort_order: int = 0

    plan_version: Optional[FinancialPlanVersionModel] = Relationship(back_populates="allocations")
    suballocations: list["PlanSuballocationModel"] = Relationship(back_populates="allocation")


class PlanSuballocationModel(SQLModel, table=True):
    """Child of a plan_allocation. Percentage is of the TOTAL plan, not of the parent's share."""
    __tablename__ = "plan_suballocations"

    id: str = Field(default_factory=_uuid, primary_key=True)
    allocation_id: str = Field(foreign_key="plan_allocations.id", index=True)
    name: str
    percentage: str  # Decimal as string, e.g. "5"
    sort_order: int = 0

    allocation: Optional[PlanAllocationModel] = Relationship(back_populates="suballocations")
