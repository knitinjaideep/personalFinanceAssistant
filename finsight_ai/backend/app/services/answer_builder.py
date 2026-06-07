"""
Answer builder — composes structured, UI-friendly answers from retrieval results.

The LLM's role is to format and explain results, not to discover facts.
SQL data is authoritative. Text chunks provide context and explanation.
"""

from __future__ import annotations

import os
import time
from typing import Any

from app.core.logger import get_logger, get_request_id
from app.domain.entities import AnswerTimings, QueryContext, StructuredAnswer
from app.domain.enums import QueryIntent, QueryPath
from app.services import llm, sql_query, text_search, vector_search
from app.services.chart_builder import build_chart

logger = get_logger(__name__)

_DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")


async def build_answer(
    question: str,
    intent: QueryIntent,
    path: QueryPath,
    confidence: float,
    ctx: QueryContext,
    *,
    req_id: str = "",
) -> StructuredAnswer:
    """Build a structured answer for a user question."""
    if not req_id:
        req_id = get_request_id()

    sql_result: dict[str, Any] | None = None
    text_results: list[dict] = []
    vector_results: list[dict] = []
    timings = AnswerTimings()

    # ── Gather data ───────────────────────────────────────────────────────────
    if path in (QueryPath.SQL, QueryPath.HYBRID):
        t0 = time.perf_counter()
        sql_result = await sql_query.execute_for_intent(intent, question, ctx)
        timings.sql_ms = sql_result.pop("_sql_duration_ms", None) or round(
            (time.perf_counter() - t0) * 1000, 1
        )

    if path in (QueryPath.FTS, QueryPath.HYBRID):
        t0 = time.perf_counter()
        text_results = await text_search.search(question)
        timings.rag_ms = round((time.perf_counter() - t0) * 1000, 1)

    if path == QueryPath.VECTOR:
        t0 = time.perf_counter()
        vector_results = await vector_search.search(question)
        timings.rag_ms = round((time.perf_counter() - t0) * 1000, 1)

    chunks_retrieved = len(text_results) + len(vector_results)
    logger.info(
        "rag_retrieval_completed",
        extra={
            "stage": "rag_retrieval_completed",
            "request_id": req_id,
            "chunks_retrieved": chunks_retrieved,
            "sources": [c.get("document_id", "") for c in (text_results + vector_results)[:5]],
            "duration_ms": timings.rag_ms,
        },
    )

    # ── Check data ────────────────────────────────────────────────────────────
    has_sql_data  = bool(sql_result and sql_result.get("rows"))
    has_text_data = bool(text_results) or bool(vector_results)

    if not has_sql_data and not has_text_data:
        logger.info(
            "response_generation_completed",
            extra={
                "stage": "response_generation_completed",
                "request_id": req_id,
                "answer_type": "no_data",
                "result_count": 0,
            },
        )
        return _no_data_answer(question, intent)

    # ── Determine answer type ─────────────────────────────────────────────────
    answer_type = _determine_answer_type(intent, sql_result)

    # ── Build LLM context ─────────────────────────────────────────────────────
    context = _build_context(sql_result, text_results, vector_results, ctx)

    # ── Generate narrative ────────────────────────────────────────────────────
    t0 = time.perf_counter()
    narrative = await _generate_narrative(question, intent, context, answer_type, ctx)
    timings.llm_ms = round((time.perf_counter() - t0) * 1000, 1)

    # ── Assemble answer ───────────────────────────────────────────────────────
    answer = StructuredAnswer(
        answer_type=answer_type,
        title=_title_for_intent(intent, ctx),
        summary=narrative,
        intent=intent.value,
        query_path=path.value,
        confidence=confidence,
        rows_used=len(sql_result["rows"]) if sql_result else 0,
        sql_used=[sql_result["sql_used"]] if sql_result and sql_result.get("sql_used") else [],
        timings=timings,
        request_id=req_id,
    )

    # ── Add chart payload ─────────────────────────────────────────────────────
    if sql_result and sql_result.get("rows"):
        answer.chart_payload = build_chart(intent, sql_result["rows"], ctx.timeframe_label)

    # ── Add structured sections / highlights ──────────────────────────────────
    if sql_result and sql_result.get("rows"):
        rows = sql_result["rows"]
        answer.primary_value = sql_result.get("summary", "")

        if answer_type == "table":
            answer.sections.append({
                "type": "table",
                "columns": sql_result.get("columns", []),
                "rows": rows[:20],
            })
        elif answer_type == "numeric":
            for row in rows[:6]:
                for key, value in row.items():
                    if value is None or key in ("earliest", "latest", "id", "sql_used"):
                        continue
                    answer.highlights.append({
                        "label": _friendly_label(key),
                        "value": _format_value(key, value),
                    })

    # ── Citations from text search ────────────────────────────────────────────
    for chunk in (text_results + vector_results)[:5]:
        answer.citations.append({
            "source": f"Page {chunk.get('page_number', '?')}",
            "text": chunk.get("snippet", chunk.get("content", ""))[:200],
            "document_id": chunk.get("document_id", ""),
        })

    # ── Caveats ───────────────────────────────────────────────────────────────
    if ctx.timeframe_label:
        answer.caveats.append(f"Results filtered to: {ctx.timeframe_label}.")
    # Only flag "text-only" when the intent was SQL-routed but returned no rows,
    # meaning we fell back to FTS. Don't show it for HYBRID or TEXT_EXPLANATION
    # since those legitimately use document text.
    _SQL_ONLY_INTENTS = {
        QueryIntent.SPENDING_BY_CATEGORY,
        QueryIntent.FEE_SUMMARY,
        QueryIntent.TRANSACTION_LOOKUP,
        QueryIntent.BALANCE_LOOKUP,
        QueryIntent.HOLDINGS_TOTAL,
        QueryIntent.HOLDINGS_LOOKUP,
        QueryIntent.CASH_FLOW_SUMMARY,
        QueryIntent.SUBSCRIPTION_LOOKUP,
        QueryIntent.DOCUMENT_AVAILABILITY,
        QueryIntent.INSTITUTION_COVERAGE,
        QueryIntent.STATEMENT_COVERAGE,
    }
    if not has_sql_data and has_text_data and intent in _SQL_ONLY_INTENTS:
        answer.caveats.append("Based on document text — structured data not available for this query.")

    # ── Follow-ups ────────────────────────────────────────────────────────────
    answer.suggested_followups = _suggest_followups(intent, ctx)

    logger.info(
        "response_generation_completed",
        extra={
            "stage": "response_generation_completed",
            "request_id": req_id,
            "answer_type": answer_type,
            "intent": intent.value,
            "route": path.value,
            "result_count": answer.rows_used,
            "chunks_retrieved": chunks_retrieved,
            "confidence": round(confidence, 3),
            "sql_ms": timings.sql_ms,
            "rag_ms": timings.rag_ms,
            "llm_ms": timings.llm_ms,
        },
    )

    if _DEBUG and sql_result and sql_result.get("rows"):
        logger.debug(
            "debug.sql_rows_preview",
            extra={
                "request_id": req_id,
                "sql_used": sql_result.get("sql_used", ""),
                "rows_preview": sql_result["rows"][:3],
            },
        )

    return answer


# ── No-data fallback ──────────────────────────────────────────────────────────

def _no_data_answer(question: str, intent: QueryIntent) -> StructuredAnswer:
    return StructuredAnswer(
        answer_type="no_data",
        title="No Data Available",
        summary=(
            "I don't have data to answer this question yet. "
            "Upload your statements using the Upload button, then ask again."
        ),
        intent=intent.value,
        query_path="none",
        confidence=1.0,
        caveats=["No statements have been ingested for this query."],
        suggested_followups=[
            "What documents have been uploaded?",
            "Which institutions are covered?",
            "Show me my account balances",
        ],
    )


# ── Answer-type routing ───────────────────────────────────────────────────────

def _determine_answer_type(intent: QueryIntent, sql_result: dict | None) -> str:
    _NUMERIC = {
        QueryIntent.FEE_SUMMARY,
        QueryIntent.CASH_FLOW_SUMMARY,
        QueryIntent.BALANCE_LOOKUP,
        QueryIntent.HOLDINGS_TOTAL,
    }
    _TABLE = {
        QueryIntent.TRANSACTION_LOOKUP,
        QueryIntent.HOLDINGS_LOOKUP,
        QueryIntent.STATEMENT_COVERAGE,
        QueryIntent.DOCUMENT_AVAILABILITY,
        QueryIntent.INSTITUTION_COVERAGE,
        QueryIntent.SUBSCRIPTION_LOOKUP,
        QueryIntent.SPENDING_BY_CATEGORY,
    }
    if intent in _NUMERIC:
        return "numeric"
    if intent in _TABLE:
        return "table"
    if intent == QueryIntent.TEXT_EXPLANATION:
        return "prose"
    return "prose"


# ── Context string for LLM ────────────────────────────────────────────────────

def _build_context(
    sql_result: dict | None,
    text_results: list,
    vector_results: list,
    ctx: QueryContext,
) -> str:
    parts: list[str] = []

    if ctx.timeframe_label:
        parts.append(f"Time period: {ctx.timeframe_label}")
    if ctx.category:
        parts.append(f"Category filter: {ctx.category}")
    if ctx.institution:
        parts.append(f"Institution filter: {ctx.institution.replace('_', ' ').title()}")

    if sql_result and sql_result.get("rows"):
        parts.append(f"\nSQL summary: {sql_result.get('summary', '')}")
        for i, row in enumerate(sql_result["rows"][:12]):
            row_str = ", ".join(
                f"{k}: {v}" for k, v in row.items()
                if v is not None and k not in ("sql_used",)
            )
            parts.append(f"  Row {i+1}: {row_str}")

    if text_results:
        parts.append("\nDocument excerpts:")
        for chunk in text_results[:4]:
            parts.append(f"  - {chunk.get('snippet', chunk.get('content', ''))[:200]}")

    if vector_results:
        parts.append("\nRelated passages:")
        for chunk in vector_results[:3]:
            parts.append(f"  - {chunk.get('content', '')[:200]}")

    return "\n".join(parts)


# ── LLM narrative generation ──────────────────────────────────────────────────

async def _generate_narrative(
    question: str,
    intent: QueryIntent,
    context: str,
    answer_type: str,
    ctx: QueryContext,
) -> str:
    if not context:
        return "No data available to answer this question."

    period_hint = f" The data is filtered to {ctx.timeframe_label}." if ctx.timeframe_label else ""

    system_prompt = (
        "You are a personal finance assistant. Answer in plain English using only the data provided.\n"
        "Rules:\n"
        "- Format dollar amounts with $ and commas, e.g. $5,701\n"
        "- Never show raw column names like fee_category or total_amount\n"
        "- Never show SQL field names, underscores, or technical identifiers\n"
        "- Be direct and concise — 1-3 sentences maximum\n"
        "- Summarize totals and key figures naturally\n"
        "- Mention institution or account names when relevant\n"
        f"- {period_hint}\n"
        "- Do not speculate beyond the provided data. Never invent numbers."
    )

    prompt = f"""Question: {question}

Data:
{context}

Answer concisely in plain English."""

    try:
        response = await llm.generate(prompt, system=system_prompt)
        return response.strip()
    except Exception as exc:
        logger.warning(
            "answer_builder.llm_failed",
            extra={"request_id": get_request_id(), "error": str(exc)},
        )
        if context:
            first_meaningful = next(
                (line for line in context.splitlines() if line.strip() and not line.startswith("  ")),
                "",
            )
            return first_meaningful or "Unable to generate answer."
        return "Unable to generate answer."


# ── Formatting helpers ────────────────────────────────────────────────────────

_LABEL_MAP: dict[str, str] = {
    "fee_category":        "Category",
    "total_amount":        "Total",
    "total":               "Total",
    "amount":              "Amount",
    "count":               "Count",
    "fee_count":           "Fees",
    "transaction_count":   "Transactions",
    "institution":         "Institution",
    "institution_type":    "Institution",
    "account_type":        "Account Type",
    "account_name":        "Account",
    "transaction_type":    "Type",
    "merchant_name":       "Merchant",
    "merchant":            "Merchant",
    "transaction_date":    "Date",
    "description":         "Description",
    "symbol":              "Symbol",
    "market_value":        "Market Value",
    "percent_of_portfolio": "Portfolio %",
    "period_start":        "From",
    "period_end":          "To",
    "total_value":         "Total Value",
    "total_spent":         "Total Spent",
    "avg_per_txn":         "Avg per Transaction",
    "monthly_amount":      "Monthly Amount",
    "unrealized_gain_loss": "Unrealized G/L",
    "total_inflow":        "Total Inflow",
    "total_outflow":       "Total Outflow",
    "net_flow":            "Net Flow",
    "doc_count":           "Documents",
}

_MONEY_COLS: frozenset[str] = frozenset({
    "total_amount", "total", "amount", "market_value", "total_value",
    "unrealized_gain_loss", "cash_value", "invested_value", "fee_total",
    "total_spent", "monthly_amount", "avg_per_txn", "total_inflow",
    "total_outflow", "net_flow", "avg_amount",
})


def _friendly_label(col: str) -> str:
    return _LABEL_MAP.get(col, col.replace("_", " ").title())


def _format_value(col: str, value: Any) -> str:
    if value is None:
        return "—"
    val_str = str(value)
    if col in _MONEY_COLS:
        try:
            num = float(val_str)
            return f"${num:,.2f}"
        except (ValueError, TypeError):
            pass
    return val_str


# ── Title & follow-up helpers ─────────────────────────────────────────────────

def _title_for_intent(intent: QueryIntent, ctx: QueryContext) -> str:
    base = {
        QueryIntent.FEE_SUMMARY:           "Fee Summary",
        QueryIntent.SPENDING_BY_CATEGORY:  "Spending Breakdown",
        QueryIntent.SUBSCRIPTION_LOOKUP:   "Recurring Charges",
        QueryIntent.TRANSACTION_LOOKUP:    "Transactions",
        QueryIntent.BALANCE_LOOKUP:        "Account Balances",
        QueryIntent.HOLDINGS_LOOKUP:       "Portfolio Holdings",
        QueryIntent.HOLDINGS_TOTAL:        "Total Invested",
        QueryIntent.CASH_FLOW_SUMMARY:     "Cash Flow",
        QueryIntent.DOCUMENT_AVAILABILITY: "Document Status",
        QueryIntent.INSTITUTION_COVERAGE:  "Institution Coverage",
        QueryIntent.STATEMENT_COVERAGE:    "Statement Coverage",
        QueryIntent.TEXT_EXPLANATION:      "Document Excerpt",
        QueryIntent.HYBRID_FINANCIAL_QUESTION: "Financial Analysis",
    }.get(intent, "Answer")

    suffix_parts: list[str] = []
    if ctx.institution:
        suffix_parts.append(ctx.institution.replace("_", " ").title())
    if ctx.timeframe_label:
        suffix_parts.append(ctx.timeframe_label)
    if suffix_parts:
        return f"{base} — {', '.join(suffix_parts)}"
    return base


def _suggest_followups(intent: QueryIntent, ctx: QueryContext) -> list[str]:
    base = {
        QueryIntent.FEE_SUMMARY: [
            "Which account has the highest fees?",
            "Show me all fee transactions",
            "What are my advisory fees this year?",
        ],
        QueryIntent.SPENDING_BY_CATEGORY: [
            "Show me my grocery transactions",
            "What subscriptions am I paying?",
            "How does this compare to last month?",
        ],
        QueryIntent.SUBSCRIPTION_LOOKUP: [
            "How much did I spend on subscriptions last year?",
            "Show me my Netflix charges",
            "What are my top recurring expenses?",
        ],
        QueryIntent.TRANSACTION_LOOKUP: [
            "Show me transactions over $500",
            "What's my spending by category?",
            "Show me recent deposits",
        ],
        QueryIntent.BALANCE_LOOKUP: [
            "How has my balance changed over time?",
            "What's my total invested amount?",
            "Show me my holdings breakdown",
        ],
        QueryIntent.HOLDINGS_TOTAL: [
            "Show me my top holdings",
            "What's my asset allocation?",
            "How much have I gained or lost?",
        ],
        QueryIntent.HOLDINGS_LOOKUP: [
            "What's my asset allocation?",
            "What's my largest holding?",
            "Show me my portfolio balance",
        ],
        QueryIntent.CASH_FLOW_SUMMARY: [
            "Show me my spending by category",
            "What are my recurring expenses?",
            "What was my net cash flow last month?",
        ],
    }.get(intent, [
        "Show me my account balances",
        "What fees have I been charged?",
        "What is my total invested amount?",
    ])

    if ctx.institution and intent == QueryIntent.FEE_SUMMARY:
        name = ctx.institution.replace("_", " ").title()
        base = [f"Show me all {name} transactions", f"What's my {name} balance?"] + base[:2]

    return base[:4]
