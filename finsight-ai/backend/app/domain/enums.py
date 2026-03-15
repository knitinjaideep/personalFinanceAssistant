"""
Domain enumerations.

All enums live here to avoid circular imports across the domain layer.
Includes taxonomy mappings (BucketType, TransactionCategory) introduced
in the Phase 3 refactor for bucket-aware analytics and banking normalization.
"""

from __future__ import annotations

from enum import Enum


# ── Top-level bucket taxonomy ─────────────────────────────────────────────────

class BucketType(str, Enum):
    """
    Top-level product buckets.

    INVESTMENTS — Morgan Stanley (IRA, Advisory, Brokerage) + E*TRADE (Brokerage).
    BANKING     — Chase (Checking, Credit Card) + Amex (Credit Card) + Discover (Credit Card).
    """

    INVESTMENTS = "investments"
    BANKING = "banking"


# ── Institutions ──────────────────────────────────────────────────────────────

class InstitutionType(str, Enum):
    """Supported financial institutions."""

    MORGAN_STANLEY = "morgan_stanley"
    CHASE = "chase"
    ETRADE = "etrade"
    AMEX = "amex"
    DISCOVER = "discover"
    UNKNOWN = "unknown"


# ── Account types ─────────────────────────────────────────────────────────────

class AccountType(str, Enum):
    """
    Specific account types within an institution.

    Investments group:
      IRA, ROTH_IRA, ADVISORY, INDIVIDUAL_BROKERAGE, FOUR_01K

    Banking group:
      CHECKING, CREDIT_CARD, SAVINGS
    """

    # Investments
    IRA = "ira"
    ROTH_IRA = "roth_ira"
    ADVISORY = "advisory"
    INDIVIDUAL_BROKERAGE = "individual_brokerage"
    FOUR_01K = "401k"

    # Banking
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"

    UNKNOWN = "unknown"


# ── Statement types ───────────────────────────────────────────────────────────

class StatementType(str, Enum):
    """Types of financial statements we can process."""

    BROKERAGE = "brokerage"          # Investments, holdings, trades
    BANK = "bank"                    # Checking/savings accounts
    CREDIT_CARD = "credit_card"      # Credit card statements
    RETIREMENT = "retirement"        # 401k, IRA statements
    ADVISORY = "advisory"            # Managed/advisory account statements
    UNKNOWN = "unknown"


# ── Transaction types ─────────────────────────────────────────────────────────

class TransactionType(str, Enum):
    """Transaction classifications."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    FEE = "fee"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    TRADE_BUY = "trade_buy"
    TRADE_SELL = "trade_sell"
    TAX_WITHHOLDING = "tax_withholding"
    ADVISORY_FEE = "advisory_fee"
    PAYMENT = "payment"              # Credit card payment
    PURCHASE = "purchase"            # Credit card / debit purchase
    REFUND = "refund"                # Merchant refund
    OTHER = "other"


# ── Transaction spending categories (banking) ─────────────────────────────────

class TransactionCategory(str, Enum):
    """
    Spending categories for banking transactions (Chase, Amex, Discover).

    Applied by the merchant normalizer using deterministic rules first;
    LLM fallback only when rule confidence is below threshold.
    """

    GROCERIES = "groceries"
    RESTAURANTS = "restaurants"
    SUBSCRIPTIONS = "subscriptions"
    TRAVEL = "travel"
    SHOPPING = "shopping"
    GAS = "gas"
    UTILITIES = "utilities"
    HEALTHCARE = "healthcare"
    ENTERTAINMENT = "entertainment"
    EDUCATION = "education"
    INSURANCE = "insurance"
    TRANSFERS = "transfers"
    FEES = "fees"
    ATM_CASH = "atm_cash"
    OTHER = "other"


# ── Confidence display tiers ───────────────────────────────────────────────────

class ConfidenceTier(str, Enum):
    """
    Human-readable confidence tier for UI display.

    Computed by ConfidenceService from a 0.0–1.0 float:
      HIGH         ≥ 0.80
      MEDIUM       ≥ 0.50
      LOW          ≥ 0.25
      NEEDS_REVIEW < 0.25 or ExtractionStatus.PARTIAL
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEEDS_REVIEW = "needs_review"


# ── Processing statuses ───────────────────────────────────────────────────────

class ExtractionStatus(str, Enum):
    """Processing status for a statement document."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    PARTIAL = "partial"       # Some fields extracted, some missing
    FAILED = "failed"


class DocumentStatus(str, Enum):
    """Upload/storage status of a raw document."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    PARSED = "parsed"
    PARTIALLY_PARSED = "partially_parsed"
    EMBEDDED = "embedded"
    PROCESSED = "processed"
    FAILED = "failed"
    DELETED = "deleted"


class BucketStatus(str, Enum):
    """Lifecycle status of a bucket."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


# ── Processing event types ────────────────────────────────────────────────────

class ProcessingEventType(str, Enum):
    """Types of structured processing events streamed to the frontend."""

    # ── Ingestion pipeline ─────────────────────────────────────────────────────

    # Phase 1 (legacy — kept for backwards compat)
    FILE_RECEIVED = "file_received"
    PARSING_STARTED = "parsing_started"
    PARSING_COMPLETE = "parsing_complete"
    CLASSIFICATION_STARTED = "classification_started"
    CLASSIFICATION_COMPLETE = "classification_complete"
    EXTRACTION_STARTED = "extraction_started"
    EXTRACTION_COMPLETE = "extraction_complete"
    NORMALIZATION_STARTED = "normalization_started"
    NORMALIZATION_COMPLETE = "normalization_complete"
    EMBEDDING_STARTED = "embedding_started"
    EMBEDDING_COMPLETE = "embedding_complete"
    PERSISTING = "persisting"
    INGESTION_COMPLETE = "ingestion_complete"
    INGESTION_FAILED = "ingestion_failed"

    # Phase 2.4 — Richer ingestion trace events
    DOCUMENT_RECEIVED = "document_received"
    """Document accepted, queued for processing."""
    PARSE_STARTED = "parse_started"
    """PDF parsing has begun."""
    TEXT_EXTRACTED = "text_extracted"
    """Raw text and structure extracted from PDF pages."""
    INSTITUTION_HYPOTHESES = "institution_hypotheses"
    """Classification scored against all known institution agents."""
    STATEMENT_TYPE_HYPOTHESES = "statement_type_hypotheses"
    """Statement type (brokerage/bank/credit_card/…) identified."""
    EXTRACTION_STARTED_V2 = "extraction_started_v2"
    """Field-level extraction running inside the institution agent."""
    FIELDS_DETECTED = "fields_detected"
    """Extraction complete — summary of detected records and confidence."""
    FIELDS_NEEDING_REVIEW = "fields_needing_review"
    """One or more fields/records require human review."""
    RECONCILIATION_STARTED = "reconciliation_started"
    """Reconciliation engine checking extracted facts against statement totals."""
    RECONCILIATION_COMPLETED = "reconciliation_completed"
    """Reconciliation finished — integrity score available."""
    PERSIST_STARTED = "persist_started"
    """Canonical DB write starting."""
    PERSIST_COMPLETED = "persist_completed"
    """Canonical DB write complete."""
    EMBEDDING_STARTED_V2 = "embedding_started_v2"
    """Vector embedding of document chunks starting."""
    EMBEDDING_COMPLETED = "embedding_completed"
    """Vector embedding complete — document searchable."""
    INGESTION_PIPELINE_COMPLETE = "ingestion_pipeline_complete"
    """All stages done — includes full summary."""

    # ── Chat / RAG pipeline ────────────────────────────────────────────────────

    # Phase 1 (legacy)
    SUPERVISOR_ROUTING = "supervisor_routing"
    BUCKET_SELECTED = "bucket_selected"
    RETRIEVAL_STARTED = "retrieval_started"
    RETRIEVAL_COMPLETE = "retrieval_complete"
    ANALYSIS_STARTED = "analysis_started"
    GENERATING_RESPONSE = "generating_response"
    RESPONSE_COMPLETE = "response_complete"

    # Phase 2.4 — Richer chat trace events
    RETRIEVAL_PLAN_SELECTED = "retrieval_plan_selected"
    """Strategy chosen: vector_only | sql_first | hybrid."""
    SQL_CANDIDATE_GENERATED = "sql_candidate_generated"
    """A SQL query was generated from an intent template."""
    SQL_VALIDATED = "sql_validated"
    """SQL passed safety checks (SELECT-only, whitelisted tables, LIMIT enforced)."""
    SOURCE_CHUNKS_RANKED = "source_chunks_ranked"
    """Vector chunks retrieved and re-ranked by relevance."""
    RESPONSE_DRAFT_STARTED = "response_draft_started"
    """LLM prompt submitted; generation in progress."""

    # Phase 3 — Chat reliability events
    CHAT_RETRIEVE_STARTED = "chat_retrieve_started"
    CHAT_RETRIEVE_DONE = "chat_retrieve_done"
    CHAT_GENERATE_STARTED = "chat_generate_started"
    CHAT_GENERATE_PROGRESS = "chat_generate_progress"
    CHAT_GENERATE_DONE = "chat_generate_done"
    CHAT_FALLBACK_TRIGGERED = "chat_fallback_triggered"
    CHAT_ANSWER_READY = "chat_answer_ready"

    # ── Generic ────────────────────────────────────────────────────────────────
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ProcessingEventStatus(str, Enum):
    """Status of an individual processing event."""

    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"
    WARNING = "warning"


# ── Phase 2 enums ─────────────────────────────────────────────────────────────

class IngestionJobStatus(str, Enum):
    """
    Lifecycle state of a durable ingestion job.

    Jobs are created when a document is accepted and advance through these
    states.  PAUSED is set when the process restarts mid-job so the runner
    can resume rather than restart.
    """

    PENDING = "pending"           # Created, not yet started
    RUNNING = "running"           # Actively processing
    PAUSED = "paused"             # Interrupted — eligible for resume
    AWAITING_REVIEW = "awaiting_review"  # Extraction done; review items outstanding
    COMPLETED = "completed"       # All stages done, promoted to canonical
    FAILED = "failed"             # Unrecoverable error


class IngestionStage(str, Enum):
    """
    Granular pipeline stage checkpointed inside an ingestion job.

    The runner writes the current stage before entering each step so that
    on resume it can skip already-completed stages.
    """

    RECEIVED = "received"
    PARSING = "parsing"
    PARSED = "parsed"
    CLASSIFYING = "classifying"
    CLASSIFIED = "classified"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    STAGING = "staging"
    STAGED = "staged"
    RECONCILING = "reconciling"
    RECONCILED = "reconciled"
    EMBEDDING = "embedding"
    EMBEDDED = "embedded"
    PROMOTING = "promoting"
    PROMOTED = "promoted"


class StagedRecordStatus(str, Enum):
    """
    Review lifecycle for an individual staged record (transaction, holding, etc.).

    These statuses are the source of truth for what a human has decided about
    each extracted record before it is promoted to the canonical tables.
    """

    EXTRACTED = "extracted"       # Fresh from the parser — not yet reviewed
    INFERRED = "inferred"         # Value was not literally on the page; model-derived
    NEEDS_REVIEW = "needs_review" # Low confidence or flagged by reconciliation
    APPROVED = "approved"         # User confirmed the record is correct
    CORRECTED = "corrected"       # User edited at least one field
    REJECTED = "rejected"         # User discarded — will not be promoted


class ReviewItemType(str, Enum):
    """The kind of thing a review item points at."""

    STAGED_STATEMENT = "staged_statement"
    STAGED_TRANSACTION = "staged_transaction"
    STAGED_FEE = "staged_fee"
    STAGED_HOLDING = "staged_holding"
    STAGED_BALANCE_SNAPSHOT = "staged_balance_snapshot"


class ReviewItemStatus(str, Enum):
    """Workflow state of a review queue item."""

    PENDING = "pending"       # Waiting for user action
    RESOLVED = "resolved"     # User approved, corrected, or rejected
    SKIPPED = "skipped"       # User chose to defer without a decision


class ReconciliationStatus(str, Enum):
    """Overall outcome of a reconciliation run against a staged statement."""

    PASSED = "passed"                              # All checks passed within tolerance
    PASSED_WITH_WARNINGS = "passed_with_warnings"  # Minor discrepancies only
    FAILED = "failed"                              # One or more critical checks failed
    SKIPPED = "skipped"                            # Insufficient data to evaluate


class CheckSeverity(str, Enum):
    """
    Severity of an individual reconciliation check result.

    CRITICAL — numbers are wrong; flags review items and blocks promotion.
    WARNING  — discrepancy within tolerance but worth surfacing to the user.
    INFO     — informational note only; no action required.
    """

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class CheckStatus(str, Enum):
    """Pass/fail state of an individual reconciliation check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"     # Could not evaluate (missing data)


# ── Taxonomy mapping constants ────────────────────────────────────────────────
# These dicts are the single source of truth for cross-cutting taxonomy lookups.
# Import from here; never hardcode institution→bucket mappings elsewhere.

INSTITUTION_BUCKET_MAP: dict[InstitutionType, BucketType] = {
    InstitutionType.MORGAN_STANLEY: BucketType.INVESTMENTS,
    InstitutionType.ETRADE: BucketType.INVESTMENTS,
    InstitutionType.CHASE: BucketType.BANKING,
    InstitutionType.AMEX: BucketType.BANKING,
    InstitutionType.DISCOVER: BucketType.BANKING,
}
"""Maps each institution to its top-level bucket. UNKNOWN is intentionally absent."""

INSTITUTION_ACCOUNT_TYPES: dict[InstitutionType, list[AccountType]] = {
    InstitutionType.MORGAN_STANLEY: [
        AccountType.IRA,
        AccountType.ROTH_IRA,
        AccountType.ADVISORY,
        AccountType.INDIVIDUAL_BROKERAGE,
    ],
    InstitutionType.ETRADE: [
        AccountType.INDIVIDUAL_BROKERAGE,
    ],
    InstitutionType.CHASE: [
        AccountType.CHECKING,
        AccountType.CREDIT_CARD,
    ],
    InstitutionType.AMEX: [
        AccountType.CREDIT_CARD,
    ],
    InstitutionType.DISCOVER: [
        AccountType.CREDIT_CARD,
    ],
}
"""Lists the account types each institution can produce. Used by agents and UI capability matrix."""

BUCKET_INSTITUTIONS: dict[BucketType, list[InstitutionType]] = {
    BucketType.INVESTMENTS: [InstitutionType.MORGAN_STANLEY, InstitutionType.ETRADE],
    BucketType.BANKING: [InstitutionType.CHASE, InstitutionType.AMEX, InstitutionType.DISCOVER],
}
"""Inverse of INSTITUTION_BUCKET_MAP — lists institutions per bucket."""

INVESTMENTS_ACCOUNT_TYPES: frozenset[AccountType] = frozenset({
    AccountType.IRA,
    AccountType.ROTH_IRA,
    AccountType.ADVISORY,
    AccountType.INDIVIDUAL_BROKERAGE,
    AccountType.FOUR_01K,
})
"""Account types that belong in the INVESTMENTS bucket."""

BANKING_ACCOUNT_TYPES: frozenset[AccountType] = frozenset({
    AccountType.CHECKING,
    AccountType.SAVINGS,
    AccountType.CREDIT_CARD,
})
"""Account types that belong in the BANKING bucket."""


def get_bucket_for_institution(institution: InstitutionType) -> BucketType | None:
    """Return the bucket for an institution, or None if unknown."""
    return INSTITUTION_BUCKET_MAP.get(institution)


def get_bucket_for_account_type(account_type: AccountType) -> BucketType | None:
    """Infer the bucket from an account type alone."""
    if account_type in INVESTMENTS_ACCOUNT_TYPES:
        return BucketType.INVESTMENTS
    if account_type in BANKING_ACCOUNT_TYPES:
        return BucketType.BANKING
    return None
