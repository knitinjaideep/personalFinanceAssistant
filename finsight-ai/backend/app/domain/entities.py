"""
Pure Pydantic domain entities.

These models are the canonical data shapes that flow through the entire
application (parsers → agents → services → API responses).

Design decisions:
- No SQLAlchemy/SQLModel here — this is the domain layer, not persistence.
- All monetary values are stored as Decimal strings to avoid float rounding.
- Each extracted field carries an optional confidence score (0.0–1.0) and
  a source location (page, section) for auditability.
- Optional fields default to None rather than raising on missing data,
  since financial statements frequently omit certain sections.
- BucketType is denormalized onto Account and Statement so analytics queries
  can filter by bucket without joining through InstitutionType lookups.
- TransactionCategory is set by the merchant normalizer and stored on
  Transaction for banking analytics (spending by category).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import (
    AccountType,
    BucketStatus,
    BucketType,
    ConfidenceTier,
    DocumentStatus,
    ExtractionStatus,
    InstitutionType,
    ProcessingEventStatus,
    ProcessingEventType,
    StatementType,
    TransactionCategory,
    TransactionType,
    get_bucket_for_account_type,
    get_bucket_for_institution,
)


# ── Source provenance ─────────────────────────────────────────────────────────

class SourceLocation(BaseModel):
    """Pinpoints where in the source document a value was found."""

    page: int | None = None
    section: str | None = None       # e.g., "Account Summary", "Fee Detail"
    raw_text: str | None = None      # verbatim text snippet


class ConfidenceField(BaseModel):
    """A domain value annotated with extraction confidence and provenance."""

    value: Any
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source: SourceLocation | None = None


# ── Core domain entities ──────────────────────────────────────────────────────

class FinancialInstitution(BaseModel):
    """Represents a financial institution (bank, broker, etc.)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    institution_type: InstitutionType
    bucket_type: BucketType | None = None   # Denormalized for fast analytics filtering
    website: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def model_post_init(self, __context: Any) -> None:
        # Auto-populate bucket_type from institution_type if not explicitly set
        if self.bucket_type is None:
            object.__setattr__(
                self, "bucket_type", get_bucket_for_institution(self.institution_type)
            )


class Account(BaseModel):
    """
    A single financial account at an institution.

    bucket_type is denormalized here so analytics services can filter accounts
    by bucket (INVESTMENTS vs BANKING) without re-resolving institution type.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    institution_id: uuid.UUID
    institution_type: InstitutionType = InstitutionType.UNKNOWN
    account_number_masked: str          # e.g., "****1234"
    account_name: str | None = None     # e.g., "Individual Brokerage Account"
    account_type: AccountType = AccountType.UNKNOWN
    bucket_type: BucketType | None = None
    currency: str = "USD"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def model_post_init(self, __context: Any) -> None:
        if self.bucket_type is None:
            # Resolve from account_type first (most specific), then institution
            bt = get_bucket_for_account_type(self.account_type)
            if bt is None:
                bt = get_bucket_for_institution(self.institution_type)
            object.__setattr__(self, "bucket_type", bt)


class BalanceSnapshot(BaseModel):
    """Point-in-time balance for an account."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    account_id: uuid.UUID
    statement_id: uuid.UUID
    snapshot_date: date
    total_value: Decimal
    cash_value: Decimal | None = None
    invested_value: Decimal | None = None
    unrealized_gain_loss: Decimal | None = None
    currency: str = "USD"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source: SourceLocation | None = None

    @field_validator("total_value", mode="before")
    @classmethod
    def coerce_total_value(cls, v: Any) -> Decimal:
        return Decimal(str(v))


class Transaction(BaseModel):
    """
    A single financial transaction.

    For banking accounts (Chase, Amex, Discover), `category` is populated
    by the merchant normalizer after extraction.  For investment accounts,
    category is left as None (use transaction_type instead).
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    account_id: uuid.UUID
    statement_id: uuid.UUID
    transaction_date: date
    settlement_date: date | None = None
    description: str
    merchant_name: str | None = None         # Cleaned merchant name (banking)
    transaction_type: TransactionType = TransactionType.OTHER
    category: TransactionCategory | None = None  # Banking spend category
    amount: Decimal                          # Positive = credit, negative = debit
    currency: str = "USD"
    quantity: Decimal | None = None          # For trades
    price_per_unit: Decimal | None = None
    symbol: str | None = None               # Ticker/CUSIP
    is_recurring: bool = False              # Subscription detection flag
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source: SourceLocation | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> Decimal:
        return Decimal(str(v))


class Fee(BaseModel):
    """An identified fee extracted from a statement.

    Fees are also stored as Transactions (with TransactionType.FEE or
    ADVISORY_FEE), but this model provides richer fee-specific metadata
    for analysis queries.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    account_id: uuid.UUID
    statement_id: uuid.UUID
    transaction_id: uuid.UUID | None = None   # Links back to the transaction
    fee_date: date
    description: str
    amount: Decimal                           # Always positive (debit)
    fee_category: str | None = None           # "advisory", "management", "trading"
    annualized_rate: Decimal | None = None    # e.g., 0.01 = 1%
    currency: str = "USD"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source: SourceLocation | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> Decimal:
        return Decimal(str(v))


class Holding(BaseModel):
    """A security or asset held in an account at statement date."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    account_id: uuid.UUID
    statement_id: uuid.UUID
    symbol: str | None = None
    description: str
    quantity: Decimal | None = None
    price: Decimal | None = None
    market_value: Decimal
    cost_basis: Decimal | None = None
    unrealized_gain_loss: Decimal | None = None
    percent_of_portfolio: Decimal | None = None
    asset_class: str | None = None          # "equity", "fixed income", etc.
    currency: str = "USD"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source: SourceLocation | None = None

    @field_validator("market_value", mode="before")
    @classmethod
    def coerce_market_value(cls, v: Any) -> Decimal:
        return Decimal(str(v))


class CashFlow(BaseModel):
    """Summary cash flow for a statement period."""

    total_deposits: Decimal = Decimal("0")
    total_withdrawals: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    total_dividends: Decimal = Decimal("0")
    total_interest: Decimal = Decimal("0")
    net_cash_flow: Decimal = Decimal("0")


class StatementPeriod(BaseModel):
    """The date range covered by a statement."""

    start_date: date
    end_date: date


class Statement(BaseModel):
    """
    A parsed, normalized financial statement.

    This is the central domain entity that ties together all extracted data
    from a single uploaded document.

    bucket_type is denormalized here for the same reason as Account — so
    analytics services can query statements by bucket without an extra join.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    document_id: uuid.UUID               # Links to the raw StatementDocument
    institution_id: uuid.UUID
    institution_type: InstitutionType = InstitutionType.UNKNOWN
    account_id: uuid.UUID
    account_type: AccountType = AccountType.UNKNOWN
    bucket_type: BucketType | None = None
    statement_type: StatementType = StatementType.UNKNOWN
    period: StatementPeriod
    currency: str = "USD"

    # Extracted data collections
    balance_snapshots: list[BalanceSnapshot] = Field(default_factory=list)
    transactions: list[Transaction] = Field(default_factory=list)
    fees: list[Fee] = Field(default_factory=list)
    holdings: list[Holding] = Field(default_factory=list)
    cash_flow: CashFlow | None = None

    # Metadata
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    extraction_notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def model_post_init(self, __context: Any) -> None:
        if self.bucket_type is None:
            bt = get_bucket_for_account_type(self.account_type)
            if bt is None:
                bt = get_bucket_for_institution(self.institution_type)
            object.__setattr__(self, "bucket_type", bt)


class StatementDocument(BaseModel):
    """
    Represents the raw uploaded file before or during processing.

    Tracks the lifecycle of a document from upload through extraction.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    original_filename: str
    stored_filename: str                  # UUID-based to avoid collisions
    file_path: str                        # Absolute path on disk
    file_size_bytes: int
    mime_type: str
    institution_type: InstitutionType = InstitutionType.UNKNOWN
    document_status: DocumentStatus = DocumentStatus.UPLOADED
    page_count: int | None = None
    upload_timestamp: datetime = Field(default_factory=datetime.utcnow)
    processed_timestamp: datetime | None = None
    error_message: str | None = None


# ── Extraction result (returned by agents) ────────────────────────────────────

class FieldConfidence(BaseModel):
    """Per-field confidence tracking for extraction quality reporting."""

    field_name: str
    was_found: bool
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    extraction_method: str | None = None   # "llm", "regex", "table"
    notes: str | None = None


class ExtractionResult(BaseModel):
    """
    The output of an institution agent's extraction run.

    Includes the extracted statement plus a detailed confidence report
    so the supervisor can decide whether to accept, flag, or retry.
    """

    document_id: uuid.UUID
    institution_type: InstitutionType
    statement: Statement | None = None
    status: ExtractionStatus = ExtractionStatus.PENDING
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    field_confidences: list[FieldConfidence] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    processing_time_seconds: float | None = None


# ── Document confidence summary (computed by ConfidenceService) ───────────────

class DocumentConfidenceSummary(BaseModel):
    """
    Aggregated confidence score and tier for a processed document.

    Computed by ConfidenceService from field_confidences on ExtractionResult.
    Used to drive UI confidence badges (High / Medium / Low / Needs Review).
    """

    document_id: uuid.UUID
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    tier: ConfidenceTier = ConfidenceTier.NEEDS_REVIEW
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING

    # Field-level breakdown for detail view
    fields_found: int = 0
    fields_missing: int = 0
    fields_low_confidence: int = 0   # confidence < 0.5

    # Human-readable display label
    display_label: str = "Needs Review"
    display_color: str = "red"       # "green" | "yellow" | "red" | "gray"

    warnings: list[str] = Field(default_factory=list)


# ── Embedding record ──────────────────────────────────────────────────────────

class EmbeddingRecord(BaseModel):
    """Metadata about an embedded document chunk stored in Chroma."""

    id: str                              # Chroma document ID
    document_id: uuid.UUID
    statement_id: uuid.UUID | None = None
    chunk_index: int
    chunk_text: str
    page_number: int | None = None
    section: str | None = None
    institution_type: InstitutionType | None = None
    bucket_type: BucketType | None = None   # For bucket-scoped retrieval
    statement_period: str | None = None  # ISO date range string
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── API-facing response schemas ───────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    """Returned immediately after a successful document upload."""

    document_id: uuid.UUID
    original_filename: str
    file_size_bytes: int
    status: DocumentStatus
    message: str


class ChatMessage(BaseModel):
    """A single message in the chat interface."""

    role: str   # "user" | "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    """Incoming chat query from the frontend."""

    question: str = Field(min_length=1, max_length=2000)
    conversation_history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """Response from the RAG-powered chat endpoint."""

    answer: str
    sources: list[EmbeddingRecord] = Field(default_factory=list)
    sql_query_used: str | None = None
    processing_time_seconds: float | None = None
    # Phase 2.7: structured answer payload (None for backward-compat prose path)
    structured_answer: dict | None = None
    answer_type: str = "prose"
    confidence: float | None = None
    caveats: list[str] = Field(default_factory=list)
    # Phase 3: chat pipeline stage info
    fallback_used: bool = False
    fallback_reason: str | None = None


# ── Bucket entities ───────────────────────────────────────────────────────────

class Bucket(BaseModel):
    """
    A bucket is a product-level grouping (INVESTMENTS or BANKING) that owns
    a collection of documents, maintains its own retrieval scope, and drives
    the analytics and chat experience.

    The `bucket_type` field pins this to the taxonomy.  User-created buckets
    may have bucket_type=None for custom/free-form groupings.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    bucket_type: BucketType | None = None   # INVESTMENTS | BANKING | None (custom)
    institution_type: InstitutionType | None = None  # Optional: pin to one institution
    status: BucketStatus = BucketStatus.ACTIVE
    color: str = "#3b82f6"          # UI color tag (hex)
    icon: str | None = None         # Optional emoji or icon name
    document_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BucketCreateRequest(BaseModel):
    """Payload for creating a new bucket."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    bucket_type: BucketType | None = None
    institution_type: InstitutionType | None = None
    color: str = "#3b82f6"
    icon: str | None = None


class BucketDocumentLink(BaseModel):
    """Associates a document with a bucket (many-to-many)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    bucket_id: uuid.UUID
    document_id: uuid.UUID
    assigned_at: datetime = Field(default_factory=datetime.utcnow)


# ── Processing event entities ─────────────────────────────────────────────────

class ProcessingEvent(BaseModel):
    """
    A structured, safe execution trace event streamed to the frontend via SSE.

    These events describe what the system is doing without exposing raw LLM
    chain-of-thought or internal state.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    session_id: str                         # upload or chat session ID
    event_type: ProcessingEventType
    status: ProcessingEventStatus
    agent_name: str                         # e.g., "supervisor", "morgan_stanley_agent"
    step_name: str                          # e.g., "parse_pdf", "embed_chunks"
    message: str                            # Human-readable description
    bucket_id: uuid.UUID | None = None
    bucket_name: str | None = None
    document_id: uuid.UUID | None = None
    document_name: str | None = None
    progress: float | None = None           # 0.0–1.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Deletion audit ────────────────────────────────────────────────────────────

class DeletionRecord(BaseModel):
    """
    Audit trail for a document deletion.
    Records what was removed and from where, for auditability.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    document_id: uuid.UUID
    original_filename: str
    deleted_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_by: str = "user"                # future: user identity
    bucket_ids_removed: list[str] = Field(default_factory=list)
    embedding_ids_removed: int = 0
    sql_rows_removed: dict[str, int] = Field(default_factory=dict)


# ── Extended chat request (bucket-scoped) ────────────────────────────────────

class BucketScopedChatRequest(BaseModel):
    """Chat request with optional bucket scope filtering."""

    question: str = Field(min_length=1, max_length=2000)
    conversation_history: list[ChatMessage] = Field(default_factory=list)
    # None = all buckets, list of IDs = specific buckets
    bucket_ids: list[uuid.UUID] | None = None
    # Phase 3: explicit bucket type filter for analytics-driven chat
    bucket_type: BucketType | None = None
    session_id: str | None = None           # For SSE correlation
