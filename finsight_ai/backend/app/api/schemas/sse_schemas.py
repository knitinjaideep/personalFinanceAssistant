"""
Typed SSE (Server-Sent Events) envelope schemas for Phase 2.4.

All streaming endpoints emit events that conform to one of the typed
payloads below.  Every event shares the ``SSEEvent`` envelope; the
``payload`` field is discriminated by ``event_type``.

Design goals:
- Frontend receives a typed contract it can switch on ``event_type``.
- Every event carries enough context to render without additional fetches.
- Metadata fields are explicit — never a free-form blob.
- Duration fields allow the UI to surface performance timings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ── Shared base ────────────────────────────────────────────────────────────────

class SSEEvent(BaseModel):
    """
    Envelope for every Server-Sent Event emitted by Coral.

    The ``event_type`` field drives frontend dispatch.
    The ``payload`` field carries event-specific structured data.
    """

    session_id: str
    """Identifies which upload or chat session this event belongs to."""

    event_type: str
    """Discriminator — maps to a ``ProcessingEventType`` value."""

    status: str
    """One of: started | in_progress | complete | failed | warning."""

    agent_name: str
    """Which component emitted the event (e.g. 'supervisor', 'morgan_stanley_agent')."""

    stage: str
    """Human-readable pipeline stage label (e.g. 'parse_pdf', 'embed_chunks')."""

    message: str
    """Short, user-facing description of what is happening."""

    progress: float | None = None
    """Optional 0.0–1.0 completion fraction for the current stage."""

    document_id: str | None = None
    """Set for ingestion events; null for pure chat events."""

    duration_ms: int | None = None
    """Wall-clock time spent in this step, if known."""

    warnings: list[str] = Field(default_factory=list)
    """Non-fatal issues discovered at this step."""

    payload: dict[str, Any] = Field(default_factory=dict)
    """Structured, event-specific data — see payload schemas below."""

    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
    )

    def to_sse(self) -> str:
        """Serialize to the ``data: <json>\\n\\n`` wire format."""
        import json
        return f"data: {json.dumps(self.model_dump())}\n\n"


# ── Terminal sentinel ──────────────────────────────────────────────────────────

class StreamDoneEvent(BaseModel):
    """Sent as the final event in any SSE stream to signal completion."""

    type: str = "stream_done"
    session_id: str
    total_duration_ms: int | None = None
    error: str | None = None

    def to_sse(self) -> str:
        import json
        return f"data: {json.dumps(self.model_dump())}\n\n"


# ── Ingestion payload schemas ──────────────────────────────────────────────────

class DocumentReceivedPayload(BaseModel):
    """Emitted when a document is accepted and queued."""
    filename: str
    file_size_bytes: int
    document_id: str


class ParseStartedPayload(BaseModel):
    """Emitted when PDF parsing begins."""
    document_id: str
    file_path: str


class TextExtractedPayload(BaseModel):
    """Emitted after PDF text extraction is complete."""
    document_id: str
    page_count: int
    char_count: int
    has_tables: bool


class InstitutionHypothesesPayload(BaseModel):
    """Emitted after classification scoring runs across all agents."""
    document_id: str
    hypotheses: list[dict[str, Any]]
    """List of {institution, confidence, matched_signals} dicts."""
    selected_institution: str
    selected_confidence: float


class StatementTypeHypothesesPayload(BaseModel):
    """Emitted when the statement type is determined."""
    document_id: str
    statement_type: str
    confidence: float


class ExtractionStartedPayload(BaseModel):
    """Emitted when field extraction begins for a specific institution."""
    document_id: str
    institution: str
    agent: str


class FieldsDetectedPayload(BaseModel):
    """Emitted after extraction completes with field-level summary."""
    document_id: str
    institution: str
    transaction_count: int
    fee_count: int
    holding_count: int
    balance_snapshot_count: int
    overall_confidence: float
    low_confidence_fields: list[str]
    """Field names that fell below the confidence threshold."""


class FieldsNeedingReviewPayload(BaseModel):
    """
    Emitted when extraction finds records that require human review.

    This is a separate event from ``FieldsDetectedPayload`` so the
    frontend can immediately activate the review badge.
    """
    document_id: str
    review_item_count: int
    reasons: list[str]
    """Short descriptions of why review was flagged."""


class ReconciliationStartedPayload(BaseModel):
    """Emitted when the reconciliation engine begins checking a statement."""
    document_id: str
    staged_statement_id: str
    check_count: int


class ReconciliationCompletedPayload(BaseModel):
    """Emitted when reconciliation finishes with its integrity score."""
    document_id: str
    staged_statement_id: str
    status: str
    """ReconciliationStatus value."""
    integrity_score: float
    checks_passed: int
    checks_failed: int
    checks_critical: int
    checks_warning: int
    review_items_created: int


class PersistStartedPayload(BaseModel):
    """Emitted when canonical DB persistence begins."""
    document_id: str
    record_counts: dict[str, int]
    """e.g. {transactions: 42, fees: 3, holdings: 15}"""


class PersistCompletedPayload(BaseModel):
    """Emitted when canonical DB persistence succeeds."""
    document_id: str
    statement_id: str
    promoted_counts: dict[str, int]


class EmbeddingStartedPayload(BaseModel):
    """Emitted when Chroma embedding begins."""
    document_id: str
    chunk_count: int


class EmbeddingCompletedPayload(BaseModel):
    """Emitted when Chroma embedding finishes."""
    document_id: str
    embedded_count: int
    skipped_count: int


class IngestionCompletePayload(BaseModel):
    """Final ingestion event — summary of the full pipeline run."""
    document_id: str
    institution: str
    statement_type: str
    overall_status: str
    overall_confidence: float
    error_count: int
    warning_count: int
    review_item_count: int
    duration_ms: int | None = None


# ── Chat / RAG payload schemas ─────────────────────────────────────────────────

class RetrievalPlanSelectedPayload(BaseModel):
    """Emitted when the retrieval strategy is selected."""
    session_id: str
    strategy: str
    """e.g. 'vector_only', 'sql_first', 'hybrid'"""
    scope_label: str
    bucket_ids: list[str]


class SQLCandidateGeneratedPayload(BaseModel):
    """Emitted when a candidate SQL query is generated from a template."""
    session_id: str
    intent: str
    sql: str
    template_name: str | None = None


class SQLValidatedPayload(BaseModel):
    """Emitted when a SQL query passes safety validation."""
    session_id: str
    sql: str
    tables_referenced: list[str]
    rows_returned: int | None = None
    duration_ms: int | None = None


class SourceChunksRankedPayload(BaseModel):
    """Emitted after vector retrieval and re-ranking."""
    session_id: str
    chunk_count: int
    top_sources: list[dict[str, Any]]
    """[{document_id, institution, section, page_number, score}]"""


class ResponseDraftStartedPayload(BaseModel):
    """Emitted when the LLM begins generating the answer."""
    session_id: str
    model: str
    prompt_token_estimate: int | None = None


class ResponseCompletePayload(BaseModel):
    """
    Final chat event — carries the full answer and all evidence.

    This is the payload the frontend renders as the answer card.
    """
    session_id: str
    answer: str
    answer_type: str = "prose"
    """prose | table | numeric | comparison — for structured rendering."""

    sources: list[dict[str, Any]]
    """[{id, document_id, chunk_text, page_number, section, institution, statement_period}]"""

    sql_query_used: str | None = None
    confidence: float | None = None
    caveats: list[str] = Field(default_factory=list)
    processing_time_seconds: float | None = None
