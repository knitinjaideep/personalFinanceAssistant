"""
Domain enumerations.

All enums live here to avoid circular imports across the domain layer.
"""

from __future__ import annotations

from enum import Enum


class InstitutionType(str, Enum):
    """Supported financial institutions."""

    MORGAN_STANLEY = "morgan_stanley"
    CHASE = "chase"
    ETRADE = "etrade"
    UNKNOWN = "unknown"


class StatementType(str, Enum):
    """Types of financial statements we can process."""

    BROKERAGE = "brokerage"          # Investments, holdings, trades
    BANK = "bank"                    # Checking/savings accounts
    CREDIT_CARD = "credit_card"      # Credit card statements
    RETIREMENT = "retirement"        # 401k, IRA statements
    ADVISORY = "advisory"            # Managed/advisory account statements
    UNKNOWN = "unknown"


class AccountType(str, Enum):
    """Types of financial accounts."""

    BROKERAGE = "brokerage"
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    IRA = "ira"
    ROTH_IRA = "roth_ira"
    FOUR_01K = "401k"
    ADVISORY = "advisory"
    UNKNOWN = "unknown"


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
    OTHER = "other"


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
