"""
MCP tool contracts — typed request/response boundaries.

Every tool that crosses the supervisor ↔ institution-agent boundary is
represented here as a pair of Pydantic models (Request / Response).
Using explicit contracts instead of raw dicts provides:
  - compile-time type checking via mypy / pyright
  - self-documenting tool interfaces
  - easy schema generation for LangGraph tool binding

All monetary values are represented as strings (Decimal serialised form)
to avoid float precision loss when crossing the boundary.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.mcp_tools.registry import ToolInput, ToolOutput


# ── Document Classification ────────────────────────────────────────────────────

class ClassifyDocumentRequest(ToolInput):
    """
    Request to identify which institution and statement type a document belongs to.

    ``document_text_sample`` should be the joined raw text of the first three
    pages of the document — enough context for keyword-based heuristics without
    sending the entire document payload.
    """

    document_text_sample: str = Field(
        description="Joined raw text from the first 3 pages of the document"
    )
    filename: str = Field(
        description="Original filename as uploaded by the user (used as a secondary signal)"
    )


class ClassifyDocumentResponse(ToolOutput):
    """Result of institution / statement-type classification."""

    institution_type: str = Field(
        description="Matched InstitutionType enum value, e.g. 'morgan_stanley'"
    )
    statement_type: str = Field(
        description="Matched StatementType enum value, e.g. 'brokerage'"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str | None = Field(
        default=None,
        description="Optional human-readable explanation of why this institution was chosen",
    )


# ── Document Extraction ────────────────────────────────────────────────────────

class ExtractDocumentRequest(ToolInput):
    """
    Request to extract structured financial data from a parsed document.

    The ``document_id`` is used to look up the in-flight ``ParsedDocument``
    from ``InFlightDocumentStore``; the parsed document is stored there by
    ``parse_node`` immediately after parsing so we avoid re-parsing the PDF.

    ``institution_type`` must match a value registered in
    ``INSTITUTION_AGENT_REGISTRY`` (e.g. ``"morgan_stanley"``).
    """

    document_id: str = Field(
        description="UUID string of the document being processed"
    )
    institution_type: str = Field(
        description="InstitutionType enum value identifying the target agent"
    )


class ExtractDocumentResponse(ToolOutput):
    """Outcome of running an institution agent's extract() method."""

    extraction_status: str = Field(
        description="ExtractionStatus enum value: success | partial | failed"
    )
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    transaction_count: int = 0
    fee_count: int = 0
    holding_count: int = 0
    balance_snapshot_count: int = 0
    statement_id: str | None = Field(
        default=None,
        description="UUID string of the Statement domain entity if extraction succeeded",
    )
    errors: list[str] = Field(default_factory=list)


# ── Fee Analysis ───────────────────────────────────────────────────────────────

class FeeAnalysisRequest(ToolInput):
    """
    Filters for the fee aggregation query.

    All filters are optional; omitting all of them returns fees across all
    statements and accounts in the database.
    """

    statement_id: str | None = Field(
        default=None,
        description="Restrict to fees linked to a specific statement UUID",
    )
    account_id: str | None = Field(
        default=None,
        description="Restrict to fees linked to a specific account UUID",
    )
    start_date: str | None = Field(
        default=None,
        description="ISO-format date string — inclusive lower bound on fee date",
    )
    end_date: str | None = Field(
        default=None,
        description="ISO-format date string — inclusive upper bound on fee date",
    )


class FeeAnalysisResponse(ToolOutput):
    """Aggregated fee statistics for the requested filters."""

    total_fees: str = Field(
        default="0.00",
        description="Total fee amount as a Decimal string (e.g. '1234.56')",
    )
    fee_count: int = 0
    by_category: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of fee category label → total amount as Decimal string",
    )
    anomalies: list[str] = Field(
        default_factory=list,
        description="Human-readable descriptions of fee anomalies (unusually large, duplicates, …)",
    )


# ── Holdings Analysis ──────────────────────────────────────────────────────────

class HoldingsAnalysisRequest(ToolInput):
    """Request to summarise holdings recorded against a specific statement."""

    statement_id: str = Field(
        description="UUID string of the statement whose holdings should be analysed"
    )


class HoldingsAnalysisResponse(ToolOutput):
    """Summary of holdings for a statement."""

    total_market_value: str = Field(
        default="0.00",
        description="Total market value as a Decimal string",
    )
    holding_count: int = 0
    top_holdings: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Top holdings sorted by market value, each a dict with keys: "
            "symbol, name, market_value, pct_of_portfolio"
        ),
    )
    asset_class_breakdown: dict[str, str] = Field(
        default_factory=dict,
        description="Asset class label → total market value as Decimal string",
    )


# ── Transaction Search ─────────────────────────────────────────────────────────

class TransactionSearchRequest(ToolInput):
    """
    Criteria for searching the transactions table.

    ``query`` is the primary free-text search term.  All other fields narrow
    the result set further.
    """

    query: str = Field(description="Free-text search term applied to description/notes")
    statement_id: str | None = Field(
        default=None,
        description="Restrict to transactions belonging to this statement UUID",
    )
    account_id: str | None = Field(
        default=None,
        description="Restrict to transactions belonging to this account UUID",
    )
    start_date: str | None = Field(
        default=None,
        description="ISO-format date string — inclusive lower bound on transaction date",
    )
    end_date: str | None = Field(
        default=None,
        description="ISO-format date string — inclusive upper bound on transaction date",
    )
    transaction_type: str | None = Field(
        default=None,
        description="TransactionType enum value to filter by (e.g. 'fee', 'dividend')",
    )
    limit: int = Field(default=20, ge=1, le=500)


class TransactionSearchResponse(ToolOutput):
    """Results of a transaction search."""

    transactions: list[dict[str, Any]] = Field(default_factory=list)
    total_found: int = 0


# ── Hybrid RAG Retrieval ───────────────────────────────────────────────────────

class HybridRetrievalRequest(ToolInput):
    """
    Request to run the hybrid vector + SQL retriever.

    ``bucket_ids`` scopes the vector search to specific Chroma buckets
    (document groups).  Pass ``None`` to search all buckets.
    ``include_sql`` controls whether the SQL path is attempted at all;
    set to ``False`` for questions that are clearly unstructured in nature.
    """

    question: str = Field(description="The natural language financial question")
    bucket_ids: list[str] | None = Field(
        default=None,
        description="Optional list of bucket UUIDs to scope vector search",
    )
    top_k: int = Field(default=6, ge=1, le=50)
    include_sql: bool = Field(
        default=True,
        description="Whether to attempt a SQL query in addition to vector retrieval",
    )


class HybridRetrievalResponse(ToolOutput):
    """Combined retrieval result from vector store and/or SQL."""

    context_text: str = Field(
        description="Concatenated text ready for insertion into an LLM prompt"
    )
    vector_chunks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Raw Chroma chunk records with id, text, and metadata",
    )
    sql_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rows returned by the SQL query (each row is a dict)",
    )
    sql_query: str | None = Field(
        default=None,
        description="The SQL query that was executed, for audit / UI display",
    )
    data_source: str = Field(
        default="none",
        description="Strategy used: 'sql' | 'vector' | 'hybrid' | 'none'",
    )


# ── Answer Rendering ───────────────────────────────────────────────────────────

class AnswerRenderRequest(ToolInput):
    """
    Request to build a structured financial answer from RAG retrieval results.

    The tool combines ``prose_answer``, ``vector_chunks``, and ``sql_results``
    into a typed ``StructuredAnswer`` (or compatible dict) that the frontend can
    render as cards, tables, and evidence drawers.

    ``intent_override`` allows callers to force a specific answer layout (e.g.
    ``"fee_summary"`` or ``"holdings_breakdown"``); if omitted the tool infers
    intent from the question.
    """

    question: str = Field(description="The original user question")
    prose_answer: str = Field(description="LLM-generated prose answer to the question")
    vector_chunks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Vector chunks used to generate the answer (for evidence display)",
    )
    sql_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="SQL result rows used in the answer (for structured display)",
    )
    sql_query: str | None = Field(
        default=None,
        description="SQL query that produced sql_results",
    )
    intent_override: str | None = Field(
        default=None,
        description=(
            "Force a specific answer intent/layout. "
            "Valid values: fee_summary | holdings_breakdown | transaction_list | "
            "balance_snapshot | general"
        ),
    )


class AnswerRenderResponse(ToolOutput):
    """Fully rendered structured answer ready for the frontend."""

    answer_type: str = Field(
        description=(
            "The answer layout type: fee_summary | holdings_breakdown | "
            "transaction_list | balance_snapshot | general"
        )
    )
    structured_answer: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Serialised StructuredAnswer payload. "
            "Shape depends on answer_type; always includes 'prose' and 'confidence'."
        ),
    )
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    caveats: list[str] = Field(
        default_factory=list,
        description="Warnings or caveats about the answer quality or data completeness",
    )
