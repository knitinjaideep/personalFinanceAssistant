"""
Staged persistence models — Phase 2.1.

Staged records are the buffer between raw extraction and canonical data.
Nothing in this module writes to the canonical tables (statements, transactions,
holdings, fees, balance_snapshots).  Promotion to canonical is a deliberate
service-layer action that happens AFTER a human approves records via the
review queue.

Design decisions:
- Every staged table mirrors its canonical counterpart plus:
    - ``status`` (StagedRecordStatus) — tracks review lifecycle
    - ``confidence`` — already present on most canonical models; required here
    - ``source_page`` / ``source_section`` — provenance for the reviewer
    - ``field_flags_json`` — JSON dict of field_name → flag reason for inline
      annotations shown in the review UI
    - ``reviewer_notes`` — free-text from the user during review
    - ``reviewed_at`` / ``reviewed_by`` — audit trail
- ``ingestion_job_id`` links every staged record back to the job that produced it.
- Monetary values follow the same Decimal-as-string convention as canonical models.
- UUIDs are strings (SQLite has no native UUID type).
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ── Ingestion Job ──────────────────────────────────────────────────────────────

class IngestionJobModel(SQLModel, table=True):
    """
    Durable ingestion job record.

    Created when a document is accepted.  The runner checkpoints ``current_stage``
    before entering each pipeline step so that a restart can resume rather than
    reprocess from scratch.

    ``error_detail`` is written on failure and preserved across retries so the
    user can understand what went wrong without digging through logs.
    """

    __tablename__ = "ingestion_jobs"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    document_id: str = Field(index=True)            # FK to statement_documents.id
    bucket_id: Optional[str] = Field(default=None, index=True)  # FK to buckets.id

    status: str = "pending"                         # IngestionJobStatus enum value
    current_stage: str = "received"                 # IngestionStage enum value

    # Timing
    created_at: datetime = Field(default_factory=_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None       # Updated by runner to detect stalls

    # Outcome metadata
    attempt_count: int = 0
    error_detail: Optional[str] = None              # Last error message if failed/paused
    stage_timings_json: str = "{}"                  # JSON: stage → duration_ms
    warnings_json: str = "[]"                       # JSON array of warning strings

    # Relationships
    staged_statements: List["StagedStatementModel"] = Relationship(
        back_populates="ingestion_job"
    )
    staged_transactions: List["StagedTransactionModel"] = Relationship(
        back_populates="ingestion_job"
    )
    staged_fees: List["StagedFeeModel"] = Relationship(
        back_populates="ingestion_job"
    )
    staged_holdings: List["StagedHoldingModel"] = Relationship(
        back_populates="ingestion_job"
    )
    staged_balance_snapshots: List["StagedBalanceSnapshotModel"] = Relationship(
        back_populates="ingestion_job"
    )
    review_items: List["ReviewItemModel"] = Relationship(
        back_populates="ingestion_job"
    )


# ── Staged Statement ───────────────────────────────────────────────────────────

class StagedStatementModel(SQLModel, table=True):
    """
    Staged version of a parsed statement header.

    Mirrors StatementModel but does not write to ``statements``.
    Promoted to canonical only after approval.
    """

    __tablename__ = "staged_statements"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    ingestion_job_id: str = Field(foreign_key="ingestion_jobs.id", index=True)

    # Document linkage
    document_id: str = Field(index=True)            # FK to statement_documents.id

    # Extracted values (mirrors StatementModel)
    institution_type: str = "unknown"
    account_number_masked: Optional[str] = None
    account_name: Optional[str] = None
    account_type: str = "unknown"
    statement_type: str = "unknown"
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    currency: str = "USD"

    # Review lifecycle
    status: str = "extracted"                       # StagedRecordStatus enum value
    overall_confidence: float = 0.0
    field_flags_json: str = "{}"                    # {field_name: reason_string}
    reviewer_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: str = "user"

    # Provenance
    extraction_notes_json: str = "[]"               # JSON array of strings
    source_pages_json: str = "[]"                   # JSON array of page ints

    # Timestamps
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    # Canonical link — populated after promotion
    canonical_statement_id: Optional[str] = None    # FK to statements.id

    # Relationships
    ingestion_job: Optional[IngestionJobModel] = Relationship(
        back_populates="staged_statements"
    )


# ── Staged Transaction ─────────────────────────────────────────────────────────

class StagedTransactionModel(SQLModel, table=True):
    """
    Staged version of an extracted transaction row.

    Mirrors TransactionModel.  Each row carries its own review status so the
    user can approve/correct/reject at per-transaction granularity.
    """

    __tablename__ = "staged_transactions"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    ingestion_job_id: str = Field(foreign_key="ingestion_jobs.id", index=True)
    staged_statement_id: str = Field(foreign_key="staged_statements.id", index=True)

    # Extracted values
    transaction_date: Optional[date] = None
    settlement_date: Optional[date] = None
    description: str = ""
    transaction_type: str = "other"
    amount: str = "0"                               # Decimal as string
    currency: str = "USD"
    quantity: Optional[str] = None
    price_per_unit: Optional[str] = None
    symbol: Optional[str] = None

    # Review lifecycle
    status: str = "extracted"                       # StagedRecordStatus enum value
    confidence: float = 1.0
    field_flags_json: str = "{}"
    reviewer_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: str = "user"

    # Provenance
    source_page: Optional[int] = None
    source_section: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    # Canonical link — populated after promotion
    canonical_transaction_id: Optional[str] = None  # FK to transactions.id

    # Relationships
    ingestion_job: Optional[IngestionJobModel] = Relationship(
        back_populates="staged_transactions"
    )


# ── Staged Fee ────────────────────────────────────────────────────────────────

class StagedFeeModel(SQLModel, table=True):
    """Staged version of an extracted fee record."""

    __tablename__ = "staged_fees"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    ingestion_job_id: str = Field(foreign_key="ingestion_jobs.id", index=True)
    staged_statement_id: str = Field(foreign_key="staged_statements.id", index=True)

    # Extracted values
    fee_date: Optional[date] = None
    description: str = ""
    amount: str = "0"                               # Always positive Decimal string
    fee_category: Optional[str] = None
    annualized_rate: Optional[str] = None
    currency: str = "USD"

    # Review lifecycle
    status: str = "extracted"                       # StagedRecordStatus enum value
    confidence: float = 1.0
    field_flags_json: str = "{}"
    reviewer_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: str = "user"

    # Provenance
    source_page: Optional[int] = None
    source_section: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    # Canonical link
    canonical_fee_id: Optional[str] = None          # FK to fees.id

    # Relationships
    ingestion_job: Optional[IngestionJobModel] = Relationship(
        back_populates="staged_fees"
    )


# ── Staged Holding ────────────────────────────────────────────────────────────

class StagedHoldingModel(SQLModel, table=True):
    """Staged version of an extracted portfolio holding."""

    __tablename__ = "staged_holdings"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    ingestion_job_id: str = Field(foreign_key="ingestion_jobs.id", index=True)
    staged_statement_id: str = Field(foreign_key="staged_statements.id", index=True)

    # Extracted values
    symbol: Optional[str] = None
    description: str = ""
    quantity: Optional[str] = None
    price: Optional[str] = None
    market_value: str = "0"                         # Decimal as string
    cost_basis: Optional[str] = None
    unrealized_gain_loss: Optional[str] = None
    percent_of_portfolio: Optional[str] = None
    asset_class: Optional[str] = None
    currency: str = "USD"

    # Review lifecycle
    status: str = "extracted"                       # StagedRecordStatus enum value
    confidence: float = 1.0
    field_flags_json: str = "{}"
    reviewer_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: str = "user"

    # Provenance
    source_page: Optional[int] = None
    source_section: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    # Canonical link
    canonical_holding_id: Optional[str] = None      # FK to holdings.id

    # Relationships
    ingestion_job: Optional[IngestionJobModel] = Relationship(
        back_populates="staged_holdings"
    )


# ── Staged Balance Snapshot ────────────────────────────────────────────────────

class StagedBalanceSnapshotModel(SQLModel, table=True):
    """Staged version of an extracted account balance snapshot."""

    __tablename__ = "staged_balance_snapshots"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    ingestion_job_id: str = Field(foreign_key="ingestion_jobs.id", index=True)
    staged_statement_id: str = Field(foreign_key="staged_statements.id", index=True)

    # Extracted values
    snapshot_date: Optional[date] = None
    total_value: str = "0"                          # Decimal as string
    cash_value: Optional[str] = None
    invested_value: Optional[str] = None
    unrealized_gain_loss: Optional[str] = None
    currency: str = "USD"

    # Review lifecycle
    status: str = "extracted"                       # StagedRecordStatus enum value
    confidence: float = 1.0
    field_flags_json: str = "{}"
    reviewer_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: str = "user"

    # Provenance
    source_page: Optional[int] = None
    source_section: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    # Canonical link
    canonical_balance_snapshot_id: Optional[str] = None  # FK to balance_snapshots.id

    # Relationships
    ingestion_job: Optional[IngestionJobModel] = Relationship(
        back_populates="staged_balance_snapshots"
    )


# ── Review Item ───────────────────────────────────────────────────────────────

class ReviewItemModel(SQLModel, table=True):
    """
    A single item in the human review queue.

    Each ReviewItem points to exactly one staged record via
    (``record_type``, ``record_id``).  Multiple review items can exist for
    the same staged record if it is re-queued after a correction.

    ``reason`` explains why the item entered the queue (e.g. "confidence < 0.7",
    "reconciliation mismatch", "amount sign ambiguous").

    ``priority`` is an integer where lower = more urgent.  The service layer
    assigns priority based on confidence and reconciliation severity.
    """

    __tablename__ = "review_items"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    ingestion_job_id: str = Field(foreign_key="ingestion_jobs.id", index=True)

    # What this item points at
    record_type: str = Field(index=True)            # ReviewItemType enum value
    record_id: str = Field(index=True)              # PK of the staged record

    # Queue metadata
    status: str = "pending"                         # ReviewItemStatus enum value
    reason: str = ""                                # Human-readable flag reason
    priority: int = 50                              # 0 (highest) – 100 (lowest)
    confidence: float = 1.0                         # Confidence of the flagged record

    # Resolution
    resolved_at: Optional[datetime] = None
    resolved_by: str = "user"
    resolution_action: Optional[str] = None         # "approved" | "corrected" | "rejected"
    resolution_notes: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    # Relationships
    ingestion_job: Optional[IngestionJobModel] = Relationship(
        back_populates="review_items"
    )


# ── Reconciliation Result ──────────────────────────────────────────────────────

class ReconciliationResultModel(SQLModel, table=True):
    """
    Persisted result of a reconciliation run for a staged statement.

    One row per run — if reconciliation is re-run (e.g. after corrections),
    a new row is inserted with ``run_number`` incremented.

    ``checks_json`` stores the full list of individual check results as a
    JSON array so the UI can render per-check detail without extra queries.
    Each element has the shape:
        {
            "check_id": str,
            "name": str,
            "status": "passed"|"failed"|"skipped",
            "severity": "critical"|"warning"|"info",
            "message": str,
            "expected": str|null,
            "actual": str|null,
            "delta": str|null,
            "tolerance": str|null
        }

    ``integrity_score`` is a 0.0–1.0 float derived from the weighted check
    results.  It is surfaced in the UI as a trust indicator.

    ``review_items_created`` records how many new review items were added to
    the queue as a result of CRITICAL/WARNING check failures.
    """

    __tablename__ = "statement_reconciliation_results"

    id: str = Field(default_factory=_new_uuid, primary_key=True)
    ingestion_job_id: str = Field(index=True)               # FK to ingestion_jobs.id
    staged_statement_id: str = Field(index=True)            # FK to staged_statements.id

    # Overall outcome
    status: str = "skipped"                                 # ReconciliationStatus value
    integrity_score: float = 0.0                            # 0.0 (no trust) – 1.0 (full trust)
    run_number: int = 1

    # Full per-check detail (JSON array — see docstring)
    checks_json: str = "[]"

    # Summary counts
    checks_total: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    checks_skipped: int = 0
    checks_critical: int = 0
    checks_warning: int = 0

    # Review items raised by this run
    review_items_created: int = 0

    # Timing
    ran_at: datetime = Field(default_factory=_now)
    duration_ms: Optional[int] = None


# ── Field Correction ───────────────────────────────────────────────────────────

class FieldCorrectionModel(SQLModel, table=True):
    """
    Immutable journal of every field-level correction made during review.

    Each row records a single field edit: what the extractor produced
    (``original_value``), what the user changed it to (``corrected_value``),
    which record it came from, and which institution + record type it belongs to.

    This table is the source of truth for the correction learning loop:
    - ``CorrectionService.get_hints()`` reads it to surface prior corrections
      as few-shot examples for the extraction prompt on future documents.
    - ``CorrectionService.get_calibration()`` counts corrections per
      (institution, record_type, field_name) to adjust base confidence scores.

    Design decisions:
    - Rows are never mutated after creation (append-only journal).
    - ``original_value`` and ``corrected_value`` are stored as JSON strings so
      any Python primitive (str, int, float, date, Decimal) can round-trip
      without losing fidelity.
    - (institution_type, record_type, field_name) form the lookup key for
      hints and calibration; they are individually indexed.
    - ``reviewed_by`` defaults to "user" and can be extended with session IDs
      if multi-user support is added later.
    """

    __tablename__ = "field_corrections"

    id: str = Field(default_factory=_new_uuid, primary_key=True)

    # ── Provenance ─────────────────────────────────────────────────────────────
    institution_type: str = Field(index=True)
    """InstitutionType enum value — e.g. 'morgan_stanley'."""

    record_type: str = Field(index=True)
    """ReviewItemType enum value — e.g. 'staged_transaction'."""

    field_name: str = Field(index=True)
    """The name of the corrected field — e.g. 'amount', 'description'."""

    # ── Source record linkage ──────────────────────────────────────────────────
    staged_record_id: str = Field(index=True)
    """PK of the staged record that was corrected."""

    ingestion_job_id: str = Field(index=True)
    """FK to ingestion_jobs.id — groups corrections per document."""

    # ── Correction payload ─────────────────────────────────────────────────────
    original_value: str = "null"
    """JSON-encoded value before correction."""

    corrected_value: str = "null"
    """JSON-encoded value after correction."""

    correction_reason: Optional[str] = None
    """Free-text explanation from the reviewer (maps to reviewer_notes)."""

    # ── Confidence context ─────────────────────────────────────────────────────
    original_confidence: float = 1.0
    """Extraction confidence score at the time of correction."""

    # ── Audit ──────────────────────────────────────────────────────────────────
    reviewed_by: str = "user"
    corrected_at: datetime = Field(default_factory=_now)
