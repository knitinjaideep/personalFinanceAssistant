"""
Typed schema for the chatbot intent-classification pipeline.

These models are the strict contract between the LLM classifier and the chat
router. Every raw LLM classifier response is validated through
``IntentClassificationResult`` before any routing decision is made.

The taxonomy here (``ChatIntent``) is the *user-facing* intent set requested for
the chatbot. It is mapped onto the existing internal ``QueryIntent`` handlers in
``app.services.intent_mapping`` so the SQL/RAG layers stay untouched.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatIntent(str, Enum):
    """User-facing chatbot intents."""

    TRANSACTION_SEARCH = "transaction_search"
    SPENDING_SUMMARY = "spending_summary"
    INCOME_SUMMARY = "income_summary"
    BALANCE_SUMMARY = "balance_summary"
    INVESTMENT_SUMMARY = "investment_summary"
    FEES_SUMMARY = "fees_summary"
    DOCUMENT_LOOKUP = "document_lookup"
    ACCOUNT_SUMMARY = "account_summary"
    COMPARISON = "comparison"
    UNKNOWN = "unknown"


class DataSource(str, Enum):
    """Which retrieval path the classifier recommends."""

    SQL = "sql"
    RAG = "rag"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class TimeRange(BaseModel):
    """Extracted time scope for a question.

    ``type`` is "relative" (e.g. last_month), "absolute" (explicit dates), or
    "none" when the question carries no time scope.
    """

    type: Literal["relative", "absolute", "none"] = "none"
    value: str | None = None          # e.g. "last_month", "january_2025", "q1_2025"
    start_date: str | None = None     # ISO date string, resolved when known
    end_date: str | None = None       # ISO date string, resolved when known

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: object) -> str:
        if v is None or v == "":
            return "none"
        return str(v)


class ExtractedEntities(BaseModel):
    """Entities pulled out of the user's question."""

    category: str | None = None
    merchant: str | None = None
    institution: str | None = None
    account: str | None = None
    # second institution/time scope for comparison questions
    compare_to: str | None = None
    time_range: TimeRange = Field(default_factory=TimeRange)


class IntentClassificationResult(BaseModel):
    """Validated output of the intent classifier."""

    intent: ChatIntent = ChatIntent.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    data_source: DataSource = DataSource.UNKNOWN
    needs_clarification: bool = False
    clarifying_question: str | None = None

    # not part of the LLM contract — populated by the classifier service to
    # record how the result was produced (llm / rule_fallback / invalid).
    source: str = "llm"

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: object) -> float:
        try:
            f = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, f))

    @field_validator("intent", mode="before")
    @classmethod
    def _coerce_intent(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                return ChatIntent(v.strip().lower())
            except ValueError:
                return ChatIntent.UNKNOWN
        return v

    @field_validator("data_source", mode="before")
    @classmethod
    def _coerce_source(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                return DataSource(v.strip().lower())
            except ValueError:
                return DataSource.UNKNOWN
        return v

    @classmethod
    def unknown_fallback(cls, *, source: str = "invalid") -> IntentClassificationResult:
        """A safe zero-confidence result used when classification fails."""
        return cls(
            intent=ChatIntent.UNKNOWN,
            confidence=0.0,
            entities=ExtractedEntities(),
            data_source=DataSource.UNKNOWN,
            needs_clarification=False,
            clarifying_question=None,
            source=source,
        )
