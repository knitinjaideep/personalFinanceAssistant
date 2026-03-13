"""
Structured answer schemas for Phase 2.7.

FinSight AI distinguishes four answer types that the frontend renders differently:

- ``prose``       — Free-form narrative. Rendered as a formatted text block.
- ``numeric``     — A single computed value (e.g. total fees, net worth). Rendered
                    as a highlighted metric card with provenance details.
- ``table``       — Tabular data (e.g. fee breakdown by category). Rendered as an
                    interactive table with sort/filter.
- ``comparison``  — Side-by-side values across dimensions (accounts, periods).
                    Rendered as a comparison card or small chart.

Every answer carries:
- ``confidence``  — 0.0–1.0 signal derived from retrieval quality.
- ``caveats``     — warnings surfaced to the user (e.g. "Only 3 of 6 months have data").
- ``evidence``    — source chunks and SQL used, for the evidence drawer.
- ``data_source`` — whether the numeric truth came from SQL or vector retrieval.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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
    """Descriptive title for the table."""

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
    """Descriptive title for the comparison."""

    dimension: str
    """What is being compared — 'account', 'period', 'institution', 'category'."""

    metric: str
    """The metric being compared — e.g. 'total_fees', 'balance', 'transactions'."""

    unit: str | None = None

    items: list[ComparisonItem]
    """The items being compared, ordered by label or value."""

    summary_text: str | None = None

    confidence: float | None = None
    caveats: list[str] = Field(default_factory=list)
    evidence: AnswerEvidence = Field(default_factory=AnswerEvidence)


# ── Union type ────────────────────────────────────────────────────────────────

StructuredAnswer = ProseAnswer | NumericAnswer | TableAnswer | ComparisonAnswer


# ── Extended ResponseComplete payload ─────────────────────────────────────────

class StructuredResponseCompletePayload(BaseModel):
    """
    Phase 2.7 upgrade to ``ResponseCompletePayload``.

    Replaces the flat ``answer: str`` + ``answer_type: str`` pair with a
    fully-typed ``structured_answer`` discriminated union.  The ``answer``
    field is retained for backward-compatible prose rendering.
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
