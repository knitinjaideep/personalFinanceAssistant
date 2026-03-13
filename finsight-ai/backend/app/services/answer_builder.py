"""
Answer builder — Phase 2.7 structured answer construction.

Converts raw RAG results (vector chunks + SQL rows) into typed answer objects
that the frontend can render as metric cards, tables, or comparison views.

Design:
- Intent classification is heuristic (regex + SQL presence) so it is fast and
  fully local.  Phase 2.6 query planner will eventually feed a richer intent
  signal; the builder accepts it as an optional override.
- SQL results are the primary numeric truth source when present.
- Vector chunks provide provenance, narrative context, and confidence signal.
- Confidence is derived from: extraction confidence of contributing records,
  vector retrieval scores (when available), and presence/absence of SQL data.

All builders are pure functions that return Pydantic models.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

from app.api.schemas.answer_schemas import (
    AnswerEvidence,
    ComparisonAnswer,
    ComparisonItem,
    EvidenceChunk,
    NumericAnswer,
    ProseAnswer,
    StructuredAnswer,
    TableAnswer,
    TableRow,
)
from app.rag.retriever import RetrievalResult

logger = structlog.get_logger(__name__)


# ── Intent patterns ────────────────────────────────────────────────────────────

_NUMERIC_PATTERNS = re.compile(
    r"(how much|total fees?|total amount|sum of|net worth|total balance|"
    r"overall balance|total value|portfolio value|amount paid|total paid|"
    r"total (deposits?|withdrawals?|transactions?)|average fee)",
    re.IGNORECASE,
)

_TABLE_PATTERNS = re.compile(
    r"(list|show me|all (fees?|transactions?|holdings?)|break(down| it down)|"
    r"itemize|detail|what are (my|the)|transactions? (in|for|this|last))",
    re.IGNORECASE,
)

_COMPARISON_PATTERNS = re.compile(
    r"(compar[ei]|month.over.month|year.over.year|highest|lowest|most|least|"
    r"which (account|month|institution)|rank|vs\.?|versus|better|worse|"
    r"across (accounts?|institutions?))",
    re.IGNORECASE,
)


def _infer_intent(question: str, sql_results: list[dict]) -> str:
    """
    Heuristically classify intent from question text and SQL result shape.

    Returns one of: 'numeric', 'table', 'comparison', 'prose'.
    """
    # Comparison: multiple rows with a label + metric pattern
    if sql_results and len(sql_results) > 1 and _COMPARISON_PATTERNS.search(question):
        return "comparison"

    # Table: explicit list/detail request or many rows
    if sql_results and len(sql_results) > 3 and _TABLE_PATTERNS.search(question):
        return "table"

    # Numeric: aggregation question with 1 SQL row (or 0 SQL rows but numeric intent)
    if _NUMERIC_PATTERNS.search(question) and len(sql_results) <= 1:
        return "numeric"

    # Fallback to table when we have structured rows
    if sql_results and len(sql_results) > 1:
        return "table"

    # Single SQL row → numeric
    if len(sql_results) == 1:
        return "numeric"

    return "prose"


def _build_evidence(retrieval: RetrievalResult) -> AnswerEvidence:
    """Convert a RetrievalResult into an AnswerEvidence object."""
    chunks = []
    for chunk in retrieval.vector_chunks[:8]:
        meta = chunk.get("metadata", {})
        chunks.append(
            EvidenceChunk(
                id=chunk.get("id", ""),
                document_id=meta.get("document_id", ""),
                chunk_text=chunk.get("text", ""),
                page_number=meta.get("page_number"),
                section=meta.get("section"),
                institution_type=meta.get("institution_type"),
                statement_period=meta.get("statement_period"),
                relevance_score=chunk.get("score"),
            )
        )

    data_source: str
    if retrieval.sql_query and retrieval.vector_chunks:
        data_source = "hybrid"
    elif retrieval.sql_query:
        data_source = "sql"
    elif retrieval.vector_chunks:
        data_source = "vector"
    else:
        data_source = "none"

    return AnswerEvidence(
        chunks=chunks,
        sql_query=retrieval.sql_query,
        sql_row_count=len(retrieval.sql_results) if retrieval.sql_results else None,
        data_source=data_source,  # type: ignore[arg-type]
    )


def _estimate_confidence(retrieval: RetrievalResult) -> float:
    """
    Derive an answer confidence estimate from retrieval quality signals.

    Rules:
    - SQL with results → high base (0.85)
    - Vector-only with several chunks → moderate (0.65)
    - Few or no chunks → low (0.40)
    - Capped at 0.95 — we never claim certainty without user review.
    """
    if retrieval.sql_results:
        base = 0.85
    elif len(retrieval.vector_chunks) >= 4:
        base = 0.65
    elif len(retrieval.vector_chunks) >= 1:
        base = 0.50
    else:
        base = 0.30

    # Slight boost if both SQL and vector are present
    if retrieval.sql_results and retrieval.vector_chunks:
        base = min(base + 0.05, 0.95)

    return round(base, 2)


def _format_currency(value: Any) -> tuple[str, float | None]:
    """
    Format a value as USD currency string.

    Returns (formatted_string, raw_float).
    """
    try:
        d = Decimal(str(value))
        raw = float(d)
        formatted = f"${d:,.2f}"
        return formatted, raw
    except (InvalidOperation, TypeError, ValueError):
        return str(value), None


def _build_numeric_answer(
    question: str,
    sql_results: list[dict],
    prose_answer: str,
    evidence: AnswerEvidence,
    confidence: float,
) -> NumericAnswer:
    """Build a NumericAnswer from a single-row SQL result or prose extraction."""
    label = question.strip().rstrip("?")

    value_str = "N/A"
    raw_value = None
    unit = None
    period = None

    if sql_results:
        row = sql_results[0]
        # Look for the most likely numeric column
        for col, val in row.items():
            if val is not None and str(col).lower() not in ("id", "account_id", "statement_id"):
                formatted, raw = _format_currency(val)
                if raw is not None:
                    value_str = formatted
                    raw_value = raw
                    unit = "USD"
                    break
                elif str(val).strip():
                    value_str = str(val)
                    break

        # Look for a period column
        for col in ("period", "period_start", "period_end", "month", "fee_date", "transaction_date"):
            if col in row and row[col]:
                period = str(row[col])
                break

    caveats: list[str] = []
    if evidence.data_source == "vector":
        caveats.append(
            "This value was derived from document text, not structured database records. "
            "Verify against your original statements."
        )
    if confidence < 0.5:
        caveats.append("Low confidence — limited data available for this question.")

    return NumericAnswer(
        label=label,
        value=value_str,
        raw_value=raw_value,
        unit=unit,
        period=period,
        summary_text=prose_answer[:200] if prose_answer else None,
        confidence=confidence,
        caveats=caveats,
        evidence=evidence,
    )


def _build_table_answer(
    question: str,
    sql_results: list[dict],
    prose_answer: str,
    evidence: AnswerEvidence,
    confidence: float,
) -> TableAnswer:
    """Build a TableAnswer from multi-row SQL results."""
    if not sql_results:
        return TableAnswer(
            title=question.strip().rstrip("?"),
            columns=[],
            rows=[],
            row_count=0,
            summary_text=prose_answer[:200] if prose_answer else None,
            confidence=confidence,
            evidence=evidence,
        )

    columns = list(sql_results[0].keys())
    MAX_DISPLAY = 50
    display_rows = sql_results[:MAX_DISPLAY]
    rows = [TableRow(cells=dict(row)) for row in display_rows]

    caveats: list[str] = []
    if len(sql_results) > MAX_DISPLAY:
        caveats.append(f"Showing {MAX_DISPLAY} of {len(sql_results)} results.")

    return TableAnswer(
        title=question.strip().rstrip("?"),
        columns=columns,
        rows=rows,
        row_count=len(sql_results),
        truncated=len(sql_results) > MAX_DISPLAY,
        summary_text=prose_answer[:200] if prose_answer else None,
        confidence=confidence,
        caveats=caveats,
        evidence=evidence,
    )


def _build_comparison_answer(
    question: str,
    sql_results: list[dict],
    prose_answer: str,
    evidence: AnswerEvidence,
    confidence: float,
) -> ComparisonAnswer:
    """Build a ComparisonAnswer from multi-row SQL results."""
    if not sql_results:
        return ComparisonAnswer(
            title=question.strip().rstrip("?"),
            dimension="unknown",
            metric="value",
            items=[],
            summary_text=prose_answer[:200] if prose_answer else None,
            confidence=confidence,
            evidence=evidence,
        )

    cols = list(sql_results[0].keys())

    # Heuristic: first non-numeric column is the label, first numeric is the value
    label_col = cols[0]
    value_col = cols[-1] if len(cols) > 1 else cols[0]
    for col in cols:
        if any(kw in col.lower() for kw in ("amount", "value", "total", "sum", "fee", "balance")):
            value_col = col
            break

    metric = value_col.replace("_", " ").title()
    dimension = label_col.replace("_", " ").title()

    items: list[ComparisonItem] = []
    for row in sql_results:
        label = str(row.get(label_col, ""))
        raw_val = row.get(value_col)
        formatted, raw_float = _format_currency(raw_val) if raw_val is not None else ("N/A", None)
        items.append(
            ComparisonItem(
                label=label,
                value=formatted,
                raw_value=raw_float,
            )
        )

    # Mark the highest-value item
    numeric_items = [(i, item) for i, item in enumerate(items) if item.raw_value is not None]
    if numeric_items:
        max_idx = max(numeric_items, key=lambda x: x[1].raw_value or 0)[0]
        items[max_idx] = items[max_idx].model_copy(update={"is_baseline": True})

    return ComparisonAnswer(
        title=question.strip().rstrip("?"),
        dimension=dimension,
        metric=metric,
        unit="USD",
        items=items,
        summary_text=prose_answer[:200] if prose_answer else None,
        confidence=confidence,
        evidence=evidence,
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def build_structured_answer(
    question: str,
    prose_answer: str,
    retrieval: RetrievalResult,
    intent_override: str | None = None,
) -> StructuredAnswer:
    """
    Build a typed structured answer from RAG results.

    Args:
        question:        The user's original question.
        prose_answer:    The LLM-generated narrative answer (always available).
        retrieval:       Full RetrievalResult (vector chunks + SQL rows).
        intent_override: Optional pre-classified intent from query planner.

    Returns:
        A discriminated-union StructuredAnswer (Prose / Numeric / Table / Comparison).
    """
    evidence = _build_evidence(retrieval)
    confidence = _estimate_confidence(retrieval)

    intent = intent_override or _infer_intent(question, retrieval.sql_results)
    logger.debug(
        "answer_builder.intent",
        question_prefix=question[:60],
        intent=intent,
        sql_rows=len(retrieval.sql_results),
        vector_chunks=len(retrieval.vector_chunks),
    )

    if intent == "numeric":
        return _build_numeric_answer(
            question, retrieval.sql_results, prose_answer, evidence, confidence
        )
    elif intent == "table":
        return _build_table_answer(
            question, retrieval.sql_results, prose_answer, evidence, confidence
        )
    elif intent == "comparison":
        return _build_comparison_answer(
            question, retrieval.sql_results, prose_answer, evidence, confidence
        )
    else:
        caveats: list[str] = []
        if not retrieval.vector_chunks and not retrieval.sql_results:
            caveats.append("No relevant data was found. Upload financial statements to enable analysis.")
        elif confidence < 0.5:
            caveats.append("Limited data available — answer may be incomplete.")

        return ProseAnswer(
            text=prose_answer,
            confidence=confidence,
            caveats=caveats,
            evidence=evidence,
        )
