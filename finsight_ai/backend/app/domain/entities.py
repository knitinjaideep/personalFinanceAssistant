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


class ChatResponse(BaseModel):
    answer: StructuredAnswer
    raw_text: str = ""


class DocumentSummary(BaseModel):
    id: str
    filename: str
    institution: str
    status: str
    page_count: int | None = None
    statement_count: int = 0
    upload_time: datetime | None = None
    error: str | None = None


class AnalyticsSummary(BaseModel):
    total_documents: int = 0
    total_statements: int = 0
    total_transactions: int = 0
    total_fees: int = 0
    total_holdings: int = 0
    institutions: list[str] = Field(default_factory=list)
    date_range: dict[str, str | None] = Field(default_factory=dict)
