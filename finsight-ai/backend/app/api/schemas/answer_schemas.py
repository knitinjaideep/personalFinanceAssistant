"""
Structured answer schemas for Phase 2.7+.

FinSight AI distinguishes answer types that the frontend renders differently:

- ``prose``         — Free-form narrative.
- ``numeric``       — A single computed value (e.g. total fees, net worth).
- ``table``         — Tabular data (e.g. fee breakdown by category).
- ``comparison``    — Side-by-side values across dimensions (accounts, periods).
- ``no_data``       — Deterministic "nothing found" answer. Never calls the LLM.
                      Includes bucket/institution context so the message is grounded.
- ``partial_data``  — Some context found but not enough to answer precisely.

Every answer carries:
- ``confidence``  — 0.0–1.0 signal derived from retrieval quality.
- ``caveats``     — warnings surfaced to the user (e.g. "Only 3 of 6 months have data").
- ``evidence``    — source chunks and SQL used, for the evidence drawer.
- ``data_source`` — whether the numeric truth came from SQL or vector retrieval.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── New Phase 2 enrichment models ─────────────────────────────────────────────

class AnswerHighlight(BaseModel):
    """A key metric or stat chip to show prominently above the main answer."""

    label: str
    """Human-readable label for the stat chip, e.g. 'Total Fees'."""

    value: str
    """Formatted value string, e.g. '$1,234.56'."""

    unit: str | None = None
    """Optional unit label, e.g. 'USD', '%'."""

    trend: Literal["up", "down", "neutral"] | None = None
    """Direction indicator for trend display."""

    trend_label: str | None = None
    """Human-readable trend annotation, e.g. '+12% vs last month'."""


class AnswerSection(BaseModel):
    """An expandable section of the answer for long prose or sub-analysis."""

    heading: str
    """Section heading shown in the accordion trigger."""

    content: str
    """The section body text, rendered as prose."""

    expanded_by_default: bool = False
    """Whether the accordion section should be open on first render."""


# ── Evidence ──────────────────────────────────────────────────────────────────

class EvidenceChunk(BaseModel):
    """A single piece of evidence supporting an answer."""

    id: str
    document_id: str
    chunk_text: str
    page_number: int | None = None
    section: str | None = None
    institution_type: str | None = None
    statement_period: str | None = None
    relevance_score: float | None = None


class AnswerEvidence(BaseModel):
    """All evidence attached to a structured answer."""

    chunks: list[EvidenceChunk] = Field(default_factory=list)
    """Vector-retrieved document chunks."""

    sql_query: str | None = None
    """SQL used to compute structured data (if any)."""

    sql_row_count: int | None = None
    """How many rows the SQL query returned."""

    data_source: Literal["sql", "vector", "hybrid", "none"] = "none"
    """Primary source of numeric truth in this answer."""


# ── Answer types ──────────────────────────────────────────────────────────────

class ProseAnswer(BaseModel):
    """
    Free-form narrative answer.

    Used for open-ended questions, explanations, and comparisons that
    don't reduce to a single number or table.
    """

    answer_type: Literal["prose"] = "prose"
    text: str
    """The generated narrative answer."""

    title: str | None = None
    """Optional display title derived from the user's question."""

    highlights: list[AnswerHighlight] = Field(default_factory=list)
    """Stat chips shown prominently above the answer (empty for most prose answers)."""

    sections: list[AnswerSection] = Field(default_factory=list)
    """Expandable accordion sections for sub-analysis or lengthy prose."""

    suggested_followups: list[str] = Field(default_factory=list)
    """Contextually relevant follow-up question suggestions."""

    confidence: float | None = None
    caveats: list[str] = Field(default_factory=list)
    evidence: AnswerEvidence = Field(default_factory=AnswerEvidence)


class NumericAnswer(BaseModel):
    """
    A single key metric with provenance.

    Used for questions like "How much did I pay in fees?" or
    "What is my current account balance?".
    """

    answer_type: Literal["numeric"] = "numeric"

    title: str | None = None
    """Optional display title derived from the user's question."""

    label: str
    """Human-readable label, e.g. 'Total fees paid (Jan–Jun 2026)'."""

    value: str
    """Formatted value as a string, e.g. '$1,234.56' or '42 transactions'."""

    raw_value: float | None = None
    """Unformatted numeric value for frontend formatting/charting."""

    unit: str | None = None
    """Unit label, e.g. 'USD', '%', 'transactions'."""

    period: str | None = None
    """Date range this value covers, e.g. '2026-01-01 to 2026-06-30'."""

    institution: str | None = None
    """Institution this value belongs to, if scoped."""

    account: str | None = None
    """Account this value belongs to, if scoped."""

    summary_text: str | None = None
    """One-sentence narrative summary for context."""

    highlights: list[AnswerHighlight] = Field(default_factory=list)
    """Stat chips shown prominently above the answer."""

    sections: list[AnswerSection] = Field(default_factory=list)
    """Expandable accordion sections for sub-analysis."""

    suggested_followups: list[str] = Field(default_factory=list)
    """Contextually relevant follow-up question suggestions."""

    confidence: float | None = None
    caveats: list[str] = Field(default_factory=list)
    evidence: AnswerEvidence = Field(default_factory=AnswerEvidence)


class TableRow(BaseModel):
    """A single row in a table answer."""
    cells: dict[str, Any]
    """Column name → value mapping."""


class TableAnswer(BaseModel):
    """
    Tabular data answer.

    Used for breakdowns, lists of transactions, fee summaries by category,
    holdings, etc.
    """

    answer_type: Literal["table"] = "table"

    title: str
    """Descriptive title for the table (also serves as the unified display title)."""

    columns: list[str]
    """Ordered list of column names."""

    rows: list[TableRow]
    """Data rows."""

    row_count: int
    """Total rows (may exceed what is returned if truncated)."""

    truncated: bool = False
    """True if the full result set exceeded the display limit."""

    summary_text: str | None = None
    """One-sentence summary of what the table shows."""

    highlights: list[AnswerHighlight] = Field(default_factory=list)
    """Stat chips shown above the table (e.g. row count, total)."""

    sections: list[AnswerSection] = Field(default_factory=list)
    """Expandable accordion sections for additional context."""

    suggested_followups: list[str] = Field(default_factory=list)
    """Contextually relevant follow-up question suggestions."""

    confidence: float | None = None
    caveats: list[str] = Field(default_factory=list)
    evidence: AnswerEvidence = Field(default_factory=AnswerEvidence)


class ComparisonItem(BaseModel):
    """A single dimension in a comparison answer."""
    label: str
    """The dimension label, e.g. account name or period."""
    value: str
    """Formatted value."""
    raw_value: float | None = None
    delta_pct: float | None = None
    """Percentage change vs. a baseline, if available."""
    is_baseline: bool = False
    """True if this is the reference item."""


class ComparisonAnswer(BaseModel):
    """
    Side-by-side comparison across accounts, periods, or institutions.

    Used for questions like "Compare my balances month over month" or
    "Which account paid the most in fees?".
    """

    answer_type: Literal["comparison"] = "comparison"

    title: str
    """Descriptive title for the comparison (also serves as the unified display title)."""

    dimension: str
    """What is being compared — 'account', 'period', 'institution', 'category'."""

    metric: str
    """The metric being compared — e.g. 'total_fees', 'balance', 'transactions'."""

    unit: str | None = None

    items: list[ComparisonItem]
    """The items being compared, ordered by label or value."""

    summary_text: str | None = None

    highlights: list[AnswerHighlight] = Field(default_factory=list)
    """Stat chips for the max/min items in the comparison."""

    sections: list[AnswerSection] = Field(default_factory=list)
    """Expandable accordion sections for additional context."""

    suggested_followups: list[str] = Field(default_factory=list)
    """Contextually relevant follow-up question suggestions."""

    confidence: float | None = None
    caveats: list[str] = Field(default_factory=list)
    evidence: AnswerEvidence = Field(default_factory=AnswerEvidence)


# ── No-data answer ────────────────────────────────────────────────────────────

class NoDataAnswer(BaseModel):
    """
    Deterministic structured answer for queries with zero retrieval results.

    Built without calling the LLM.  Includes bucket/institution context so the
    message feels grounded ("I couldn't find Chase transaction data in the Banking
    bucket") rather than generic ("No relevant data was found").
    """

    answer_type: Literal["no_data"] = "no_data"

    title: str
    """Short headline, e.g. 'No recent transactions found'."""

    summary: str
    """One-to-two sentence explanation of what was searched and found nothing."""

    what_was_checked: list[str] = Field(default_factory=list)
    """Bullet list of what the system actually searched (documents, SQL, etc.)."""

    possible_reasons: list[str] = Field(default_factory=list)
    """Why this might have returned nothing (not uploaded, wrong period, etc.)."""

    suggested_followups: list[str] = Field(default_factory=list)
    """Next questions the user could ask that are more likely to succeed."""

    confidence: float = 0.0
    caveats: list[str] = Field(default_factory=list)
    evidence: AnswerEvidence = Field(default_factory=AnswerEvidence)

    # Bucket / institution context for grounded messaging
    bucket_label: str | None = None
    """Human-readable bucket name, e.g. 'Banking', 'Investments'."""

    institution_labels: list[str] = Field(default_factory=list)
    """Institution names that were searched, e.g. ['Chase', 'Morgan Stanley']."""


class PartialDataAnswer(BaseModel):
    """
    Answer for queries where some relevant context was found but not enough
    to answer precisely.

    Renders a brief explanation of what was found and what is missing.
    """

    answer_type: Literal["partial_data"] = "partial_data"

    title: str
    summary: str
    """What was found and why it's insufficient."""

    what_was_found: list[str] = Field(default_factory=list)
    """Brief description of the partial data available."""

    what_is_missing: list[str] = Field(default_factory=list)
    """What additional data would enable a complete answer."""

    suggested_followups: list[str] = Field(default_factory=list)

    confidence: float | None = None
    caveats: list[str] = Field(default_factory=list)
    evidence: AnswerEvidence = Field(default_factory=AnswerEvidence)

    bucket_label: str | None = None
    institution_labels: list[str] = Field(default_factory=list)


# ── Union type ────────────────────────────────────────────────────────────────

StructuredAnswer = (
    ProseAnswer
    | NumericAnswer
    | TableAnswer
    | ComparisonAnswer
    | NoDataAnswer
    | PartialDataAnswer
)

__all__ = [
    "AnswerHighlight",
    "AnswerSection",
    "AnswerEvidence",
    "EvidenceChunk",
    "ProseAnswer",
    "NumericAnswer",
    "TableRow",
    "TableAnswer",
    "ComparisonItem",
    "ComparisonAnswer",
    "NoDataAnswer",
    "PartialDataAnswer",
    "StructuredAnswer",
    "PipelineMeta",
    "StructuredResponseCompletePayload",
]


# ── Extended ResponseComplete payload ─────────────────────────────────────────

class PipelineMeta(BaseModel):
    """
    Metadata about how the answer was produced by the chat pipeline.

    Carried alongside the structured answer so the frontend can render
    fallback badges, warning callouts, and trust indicators without
    having to inspect event payloads.
    """

    pipeline_stage: str = "llm"
    """Which stage produced the answer: 'llm' | 'retrieval_only' | 'safe_error'."""

    fallback_triggered: bool = False
    """True when LLM generation failed and a fallback answer was used."""

    fallback_reason: str | None = None
    """Machine-readable reason for fallback: 'timeout' | 'stall' | 'connection' | 'error'."""

    warnings: list[str] = Field(default_factory=list)
    """Human-readable warning messages to surface to the user."""


class StructuredResponseCompletePayload(BaseModel):
    """
    Phase 2.7 upgrade to ``ResponseCompletePayload``.

    Replaces the flat ``answer: str`` + ``answer_type: str`` pair with a
    fully-typed ``structured_answer`` discriminated union.  The ``answer``
    field is retained for backward-compatible prose rendering.

    ``pipeline_meta`` carries fallback/warning context that was previously
    scattered across event payloads, ensuring a single clean terminal event.
    """

    session_id: str
    answer: str
    """Backward-compatible prose fallback — always present."""

    answer_type: str = "prose"
    """Discriminator string for frontend switch — mirrors structured_answer.answer_type."""

    structured_answer: StructuredAnswer | None = None
    """Fully-typed answer payload.  None when answer_type is 'prose' (simple fallback)."""

    sources: list[dict[str, Any]] = Field(default_factory=list)
    sql_query_used: str | None = None
    confidence: float | None = None
    caveats: list[str] = Field(default_factory=list)
    processing_time_seconds: float | None = None

    pipeline_meta: PipelineMeta = Field(default_factory=PipelineMeta)
    """Pipeline execution metadata: stage, fallback flag, warnings."""
