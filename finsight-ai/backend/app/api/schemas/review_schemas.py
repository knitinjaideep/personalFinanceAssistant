"""
Pydantic request/response schemas for the review queue API.

These schemas decouple the HTTP contract from the ORM layer.
The frontend consumes these shapes directly — keep field names stable.

Design conventions:
- Response models use Optional for nullable fields (never omit them).
- Monetary amounts are returned as strings to preserve Decimal precision.
- field_flags is a dict of field_name → human-readable reason string so
  the UI can highlight exactly which fields need attention.
- Timestamps are ISO-8601 strings for JSON compatibility.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Shared primitives ─────────────────────────────────────────────────────────

class FieldFlag(BaseModel):
    """A single field-level annotation attached to a staged record."""

    field: str = Field(..., description="The field name that has an issue")
    reason: str = Field(..., description="Human-readable explanation of the flag")


# ── Review item ───────────────────────────────────────────────────────────────

class ReviewItemResponse(BaseModel):
    """Lightweight summary of a review queue item — returned in list views."""

    id: str
    ingestion_job_id: str
    record_type: str           # ReviewItemType value
    record_id: str
    status: str                # ReviewItemStatus value
    reason: str
    priority: int
    confidence: float
    resolved_at: Optional[datetime]
    resolution_action: Optional[str]
    resolution_notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# ── Staged record detail shapes ───────────────────────────────────────────────

class StagedStatementDetail(BaseModel):
    """Full detail of a staged statement header, for the review drawer."""

    id: str
    ingestion_job_id: str
    document_id: str
    institution_type: str
    account_number_masked: Optional[str]
    account_name: Optional[str]
    account_type: str
    statement_type: str
    period_start: Optional[date]
    period_end: Optional[date]
    currency: str
    status: str
    overall_confidence: float
    field_flags: Dict[str, str]      # {field_name: reason}
    reviewer_notes: Optional[str]
    reviewed_at: Optional[datetime]
    extraction_notes: List[str]
    source_pages: List[int]
    canonical_statement_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class StagedTransactionDetail(BaseModel):
    """Full detail of a staged transaction, for the review drawer."""

    id: str
    ingestion_job_id: str
    staged_statement_id: str
    transaction_date: Optional[date]
    settlement_date: Optional[date]
    description: str
    transaction_type: str
    amount: str                      # Decimal string
    currency: str
    quantity: Optional[str]
    price_per_unit: Optional[str]
    symbol: Optional[str]
    status: str
    confidence: float
    field_flags: Dict[str, str]
    reviewer_notes: Optional[str]
    reviewed_at: Optional[datetime]
    source_page: Optional[int]
    source_section: Optional[str]
    canonical_transaction_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class StagedFeeDetail(BaseModel):
    id: str
    ingestion_job_id: str
    staged_statement_id: str
    fee_date: Optional[date]
    description: str
    amount: str
    fee_category: Optional[str]
    annualized_rate: Optional[str]
    currency: str
    status: str
    confidence: float
    field_flags: Dict[str, str]
    reviewer_notes: Optional[str]
    reviewed_at: Optional[datetime]
    source_page: Optional[int]
    source_section: Optional[str]
    canonical_fee_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class StagedHoldingDetail(BaseModel):
    id: str
    ingestion_job_id: str
    staged_statement_id: str
    symbol: Optional[str]
    description: str
    quantity: Optional[str]
    price: Optional[str]
    market_value: str
    cost_basis: Optional[str]
    unrealized_gain_loss: Optional[str]
    percent_of_portfolio: Optional[str]
    asset_class: Optional[str]
    currency: str
    status: str
    confidence: float
    field_flags: Dict[str, str]
    reviewer_notes: Optional[str]
    reviewed_at: Optional[datetime]
    source_page: Optional[int]
    source_section: Optional[str]
    canonical_holding_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class StagedBalanceSnapshotDetail(BaseModel):
    id: str
    ingestion_job_id: str
    staged_statement_id: str
    snapshot_date: Optional[date]
    total_value: str
    cash_value: Optional[str]
    invested_value: Optional[str]
    unrealized_gain_loss: Optional[str]
    currency: str
    status: str
    confidence: float
    field_flags: Dict[str, str]
    reviewer_notes: Optional[str]
    reviewed_at: Optional[datetime]
    source_page: Optional[int]
    source_section: Optional[str]
    canonical_balance_snapshot_id: Optional[str]
    created_at: datetime
    updated_at: datetime


# ── Review queue response ─────────────────────────────────────────────────────

class ReviewQueueResponse(BaseModel):
    """
    Paginated review queue result.

    Each item in ``items`` is a ReviewItemResponse.  The detail payload for
    the highlighted record is fetched separately via GET /review/records/{type}/{id}.
    """

    items: List[ReviewItemResponse]
    total_pending: int
    job_id: Optional[str] = None     # Set when scoped to a single job


# ── Action request bodies ─────────────────────────────────────────────────────

class ApproveRequest(BaseModel):
    """Approve a staged record as-is."""

    review_item_id: str
    notes: Optional[str] = Field(
        default=None, description="Optional reviewer notes"
    )


class CorrectRequest(BaseModel):
    """
    Submit a field-level correction for a staged record.

    ``field_updates`` contains only the fields the user has changed.
    Unknown fields are silently ignored by the service.
    """

    review_item_id: str
    field_updates: Dict[str, Any] = Field(
        ..., description="Map of field_name → new_value"
    )
    notes: Optional[str] = None


class RejectRequest(BaseModel):
    """Reject a staged record — it will not be promoted to canonical."""

    review_item_id: str
    notes: Optional[str] = None


class SkipRequest(BaseModel):
    """Defer a review item without making a decision."""

    review_item_id: str


class BulkApproveRequest(BaseModel):
    """Approve all records for a given ingestion job in one action."""

    job_id: str
    notes: Optional[str] = None


# ── Promotion response ────────────────────────────────────────────────────────

class PromotionResult(BaseModel):
    """
    Result of promoting all approved staged records to canonical tables.

    Returned after the review gate is cleared (all items resolved) and
    promotion runs.
    """

    job_id: str
    statements_promoted: int
    transactions_promoted: int
    fees_promoted: int
    holdings_promoted: int
    balance_snapshots_promoted: int
    records_rejected: int
    warnings: List[str]


# ── Job review summary ────────────────────────────────────────────────────────

class JobReviewSummary(BaseModel):
    """
    High-level review status for a single ingestion job.

    Used by the document detail panel and the upload confirmation flow.
    """

    job_id: str
    document_id: str
    job_status: str                  # IngestionJobStatus value
    current_stage: str               # IngestionStage value
    pending_review_count: int
    total_review_count: int
    staged_statements: int
    staged_transactions: int
    staged_fees: int
    staged_holdings: int
    staged_balance_snapshots: int
    warnings: List[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
