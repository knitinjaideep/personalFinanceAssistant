"""
Pure domain entities (Pydantic models, no DB coupling).

These are the contracts between parsers, services, and API layer.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _to_decimal(v: Any) -> Decimal:
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


class ParsedStatement(BaseModel):
    """Result of parsing a financial statement — the canonical extraction output.

    This is what every parser returns. The ingestion service maps it to DB models.
    """

    institution_type: str
    account_type: str = "unknown"
    statement_type: str = "unknown"
    account_number_masked: str = ""
    account_name: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    currency: str = "USD"
    confidence: float = 0.0

    # Extracted records
    transactions: list[ExtractedTransaction] = Field(default_factory=list)
    fees: list[ExtractedFee] = Field(default_factory=list)
    holdings: list[ExtractedHolding] = Field(default_factory=list)
    balances: list[ExtractedBalance] = Field(default_factory=list)

    # Bank-specific raw details (preserved as-is for bank detail tables)
    institution_details: dict[str, Any] = Field(default_factory=dict)

    # Extraction metadata
    warnings: list[str] = Field(default_factory=list)
    page_count: int = 0


class ExtractedTransaction(BaseModel):
    transaction_date: date
    settlement_date: date | None = None
    description: str
    merchant_name: str | None = None
    transaction_type: str = "other"
    category: str | None = None
    amount: Decimal
    currency: str = "USD"
    quantity: Decimal | None = None
    price_per_unit: Decimal | None = None
    symbol: str | None = None
    confidence: float = 1.0
    source_page: int | None = None

    _normalize_amount = field_validator("amount", mode="before")(_to_decimal)


class ExtractedFee(BaseModel):
    fee_date: date
    description: str
    amount: Decimal
    fee_category: str | None = None
    annualized_rate: Decimal | None = None
    currency: str = "USD"
    confidence: float = 1.0
    source_page: int | None = None

    _normalize_amount = field_validator("amount", mode="before")(_to_decimal)


class ExtractedHolding(BaseModel):
    symbol: str | None = None
    description: str
    quantity: Decimal | None = None
    price: Decimal | None = None
    market_value: Decimal
    cost_basis: Decimal | None = None
    unrealized_gain_loss: Decimal | None = None
    percent_of_portfolio: Decimal | None = None
    asset_class: str | None = None
    currency: str = "USD"
    confidence: float = 1.0
    source_page: int | None = None

    _normalize_market_value = field_validator("market_value", mode="before")(_to_decimal)


class ExtractedBalance(BaseModel):
    snapshot_date: date
    total_value: Decimal
    cash_value: Decimal | None = None
    invested_value: Decimal | None = None
    unrealized_gain_loss: Decimal | None = None
    currency: str = "USD"
    confidence: float = 1.0
    source_page: int | None = None

    _normalize_total = field_validator("total_value", mode="before")(_to_decimal)


# ── API schemas ──────────────────────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    message: str | None = None


class ChatRequest(BaseModel):
    question: str
    history: list[dict[str, str]] = Field(default_factory=list)
    conversation_id: str | None = None  # client-managed; backend generates one if omitted


class QueryContext(BaseModel):
    """Structured parameters extracted from the user's natural-language question."""
    # Timeframe
    date_from: date | None = None
    date_to: date | None = None
    timeframe_label: str = ""          # e.g. "last month", "2024", "Q1 2025"

    # Filters extracted from question text
    category: str | None = None        # TransactionCategory value or None
    merchant: str | None = None        # raw merchant keyword (lowercased)
    institution: str | None = None     # institution name keyword (lowercased)
    account_type: str | None = None    # AccountType value or None
    account_name: str | None = None    # specific account/card name, e.g. "Prime Visa" (matched LIKE)

    # Amount filters (from user phrases like "over $100", "under $50")
    amount_min: float | None = None
    amount_max: float | None = None

    # Flags
    is_recurring_only: bool = False
    limit: int = 50

    # Routing metadata (populated by chat_router; used by answer_builder)
    route_risk: str = "safe"


class AnswerTimings(BaseModel):
    """Per-stage duration breakdown (all values in milliseconds, None = stage not run)."""
    intent_ms: float | None = None
    parse_ms: float | None = None
    sql_ms: float | None = None
    rag_ms: float | None = None
    llm_ms: float | None = None
    total_ms: float | None = None


class StructuredAnswer(BaseModel):
    """The standard answer format returned by the query system."""
    answer_type: str = "prose"  # prose, numeric, table, comparison, no_data
    title: str = ""
    summary: str = ""
    primary_value: str | None = None
    highlights: list[dict[str, str]] = Field(default_factory=list)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, str]] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    query_path: str = "sql"
    intent: str = ""
    confidence: float = 0.0

    # Filter transparency — what the query actually searched for
    searched_filters: dict[str, Any] = Field(default_factory=dict)
    exact_match: bool = True          # False when exact filters returned no rows
    suggestions_used: bool = False    # True when suggestions section is populated

    # Transparency / debugging
    sql_used: list[str] = Field(default_factory=list)   # parameterized SQL strings shown to user
    rows_used: int = 0
    chart_payload: dict[str, Any] | None = None         # {type, labels, datasets} for frontend chart

    # Retrieval provenance — shown in "Based on" bar in the UI
    based_on: str = ""   # e.g. "Chase Freedom transactions, Mar–Apr 2026, 42 rows"

    # Phase 5/6: answer strategy and LLM call tracking
    answer_strategy: str = "llm_narrative"  # template_only | llm_narrative | hybrid_template_plus_llm
    llm_called: bool = True                 # False when template_only path was used

    # Observability — surfaced to frontend
    request_id: str = ""
    timings: AnswerTimings = Field(default_factory=AnswerTimings)
    follow_up_suggestions: list[str] = Field(default_factory=list)  # alias kept for API compat

    # Populated by answer_builder; consumed by debug_payload assembly in chat.py.
    # Not serialized to the standard API response — excluded from model_dump by chat API.
    verifier_passed: bool = True
    verifier_repaired: bool = False
    verifier_warnings: list[str] = Field(default_factory=list)


class ChatDebugPayload(BaseModel):
    """Developer-only pipeline metadata. Returned when DEBUG_CHAT=true."""
    route_type: str = ""
    route_risk: str = ""
    query_plan_task: str = ""
    query_plan_source: str = ""
    sql_queries_executed: list[str] = Field(default_factory=list)
    row_count: int = 0
    retrieval_count: int = 0
    answer_strategy: str = ""
    llm_called: bool = False
    verifier_passed: bool = True
    verifier_repaired: bool = False
    verifier_warnings: list[str] = Field(default_factory=list)
    fallback_steps: list[str] = Field(default_factory=list)
    timings: dict[str, float | None] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    answer: StructuredAnswer
    raw_text: str = ""
    request_id: str = ""
    debug: ChatDebugPayload | None = None


class DocumentSummary(BaseModel):
    id: str
    filename: str
    institution: str
    status: str
    page_count: int | None = None
    statement_count: int = 0
    upload_time: datetime | None = None
    processed_time: datetime | None = None
    error: str | None = None

    # Enrichment for the Documents dashboard grouping (best-effort, may be null).
    account_product: str | None = None   # e.g. "American Express — Blue Cash"
    account_type: str | None = None      # from the parsed statement, e.g. "credit_card"
    period_start: date | None = None     # earliest statement period for this doc
    period_end: date | None = None       # latest statement period for this doc
    statement_year: int | None = None    # year derived from period_end
    statement_month: int | None = None   # month derived from period_end


class DocumentStats(BaseModel):
    """Aggregated, status-normalized document counts for the dashboard cards."""
    total: int = 0
    parsed: int = 0
    processing: int = 0
    uploaded: int = 0
    failed: int = 0


class AnalyticsSummary(BaseModel):
    total_documents: int = 0
    total_statements: int = 0
    total_transactions: int = 0
    total_fees: int = 0
    total_holdings: int = 0
    institutions: list[str] = Field(default_factory=list)
    date_range: dict[str, str | None] = Field(default_factory=dict)


class BulkUploadFileResult(BaseModel):
    """Per-file result from the bulk upload endpoint."""
    filename: str
    outcome: str  # saved | duplicate_skipped | failed
    document_id: str | None = None
    destination_path: str | None = None
    parsed: bool = False
    partial_parse: bool = False
    error_message: str | None = None


class BulkUploadSummary(BaseModel):
    uploaded: int = 0
    duplicates_skipped: int = 0
    successfully_ingested: int = 0
    failed: int = 0
    partial_parses: int = 0
    results: list[BulkUploadFileResult] = Field(default_factory=list)
