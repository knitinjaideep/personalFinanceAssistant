"""
Answer builder — composes structured, UI-friendly answers from retrieval results.

The LLM's role is to format and explain results, not to discover facts.
SQL data is authoritative. Text chunks provide context and explanation.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.domain.entities import StructuredAnswer
from app.domain.enums import QueryIntent, QueryPath
from app.services import llm, sql_query, text_search, vector_search

logger = structlog.get_logger(__name__)


async def build_answer(
    question: str,
    intent: QueryIntent,
    path: QueryPath,
    confidence: float,
) -> StructuredAnswer:
    """Build a structured answer for a user question.

    Routes to the appropriate data sources based on intent and path,
    then uses the LLM to compose a coherent answer.
    """
    sql_result: dict[str, Any] | None = None
    text_results: list[dict] = []
    vector_results: list[dict] = []

    # Step 1: Gather data based on path
    if path in (QueryPath.SQL, QueryPath.HYBRID):
        sql_result = await sql_query.execute_for_intent(intent, question)

    if path in (QueryPath.FTS, QueryPath.HYBRID):
        text_results = await text_search.search(question)

    if path == QueryPath.VECTOR:
        vector_results = await vector_search.search(question)

    # Step 2: Check if we have any data
    has_sql_data = sql_result and sql_result.get("rows")
    has_text_data = bool(text_results) or bool(vector_results)

    if not has_sql_data and not has_text_data:
        return _no_data_answer(question, intent)

    # Step 3: Determine answer type
    answer_type = _determine_answer_type(intent, sql_result)

    # Step 4: Build context for LLM
    context = _build_context(sql_result, text_results, vector_results)

    # Step 5: Generate narrative using LLM
    narrative = await _generate_narrative(question, intent, context, answer_type)

    # Step 6: Assemble structured answer
    answer = StructuredAnswer(
        answer_type=answer_type,
        title=_title_for_intent(intent),
        summary=narrative,
        intent=intent.value,
        query_path=path.value,
        confidence=confidence,
    )

    # Add structured data
    if sql_result and sql_result.get("rows"):
        answer.primary_value = sql_result.get("summary", "")
        if answer_type == "table":
            answer.sections.append({
                "type": "table",
                "columns": sql_result.get("columns", []),
                "rows": sql_result["rows"][:20],
            })
        elif answer_type == "numeric":
            rows = sql_result["rows"]
            for row in rows[:5]:
                for key, value in row.items():
                    if value is not None and key not in ("earliest", "latest"):
                        answer.highlights.append({"label": key.replace("_", " ").title(), "value": str(value)})

    # Add citations from text search
    for chunk in (text_results + vector_results)[:5]:
        answer.citations.append({
            "source": f"Page {chunk.get('page_number', '?')}",
            "text": chunk.get("snippet", chunk.get("content", ""))[:200],
            "document_id": chunk.get("document_id", ""),
        })

    # Add follow-up suggestions
    answer.suggested_followups = _suggest_followups(intent)

    return answer


def _no_data_answer(question: str, intent: QueryIntent) -> StructuredAnswer:
    return StructuredAnswer(
        answer_type="no_data",
        title="No Data Available",
        summary="I don't have data to answer this question yet. Upload some financial statements first, and I'll be able to help.",
        intent=intent.value,
        query_path="none",
        confidence=1.0,
        caveats=["No financial documents have been uploaded or the data needed hasn't been extracted."],
        suggested_followups=[
            "What documents have I uploaded?",
            "Which institutions are covered?",
        ],
    )


def _determine_answer_type(intent: QueryIntent, sql_result: dict | None) -> str:
    if intent in (QueryIntent.FEE_SUMMARY, QueryIntent.CASH_FLOW_SUMMARY, QueryIntent.BALANCE_LOOKUP):
        return "numeric"
    if intent in (QueryIntent.TRANSACTION_LOOKUP, QueryIntent.HOLDINGS_LOOKUP,
                  QueryIntent.STATEMENT_COVERAGE, QueryIntent.DOCUMENT_AVAILABILITY,
                  QueryIntent.INSTITUTION_COVERAGE):
        return "table"
    if intent == QueryIntent.TEXT_EXPLANATION:
        return "prose"
    return "prose"


def _build_context(sql_result: dict | None, text_results: list, vector_results: list) -> str:
    parts = []
    if sql_result and sql_result.get("rows"):
        parts.append(f"SQL result: {sql_result.get('summary', '')}")
        for i, row in enumerate(sql_result["rows"][:10]):
            row_str = ", ".join(f"{k}: {v}" for k, v in row.items() if v is not None)
            parts.append(f"  Row {i+1}: {row_str}")

    if text_results:
        parts.append("\nDocument excerpts:")
        for chunk in text_results[:5]:
            parts.append(f"  - {chunk.get('snippet', chunk.get('content', ''))[:200]}")

    if vector_results:
        parts.append("\nRelated passages:")
        for chunk in vector_results[:3]:
            parts.append(f"  - {chunk.get('content', '')[:200]}")

    return "\n".join(parts)


async def _generate_narrative(question: str, intent: QueryIntent, context: str, answer_type: str) -> str:
    if not context:
        return "No data available to answer this question."

    system_prompt = """You are a financial analyst assistant. Answer based ONLY on the provided data.
Be concise, specific, and factual. Use dollar amounts with commas. Don't speculate beyond the data.
If data is incomplete, say so. Never invent numbers."""

    prompt = f"""Question: {question}

Data:
{context}

Provide a clear, concise answer in 1-3 paragraphs."""

    try:
        response = await llm.generate(prompt, system=system_prompt)
        return response.strip()
    except Exception as exc:
        logger.warning("answer_builder.llm_failed", error=str(exc))
        return context.split("\n")[0] if context else "Unable to generate answer."


def _title_for_intent(intent: QueryIntent) -> str:
    titles = {
        QueryIntent.FEE_SUMMARY: "Fee Summary",
        QueryIntent.TRANSACTION_LOOKUP: "Transactions",
        QueryIntent.BALANCE_LOOKUP: "Account Balances",
        QueryIntent.HOLDINGS_LOOKUP: "Portfolio Holdings",
        QueryIntent.CASH_FLOW_SUMMARY: "Cash Flow Summary",
        QueryIntent.DOCUMENT_AVAILABILITY: "Document Status",
        QueryIntent.INSTITUTION_COVERAGE: "Institution Coverage",
        QueryIntent.STATEMENT_COVERAGE: "Statement Coverage",
        QueryIntent.TEXT_EXPLANATION: "Document Excerpt",
        QueryIntent.HYBRID_FINANCIAL_QUESTION: "Financial Analysis",
    }
    return titles.get(intent, "Answer")


def _suggest_followups(intent: QueryIntent) -> list[str]:
    followups = {
        QueryIntent.FEE_SUMMARY: [
            "What are my advisory fees by quarter?",
            "Which account has the highest fees?",
            "Show me all fee transactions",
        ],
        QueryIntent.TRANSACTION_LOOKUP: [
            "Show me transactions over $1,000",
            "What's my spending by category?",
            "Show me recent deposits",
        ],
        QueryIntent.BALANCE_LOOKUP: [
            "How has my balance changed over time?",
            "What's my total across all accounts?",
            "Show me my holdings breakdown",
        ],
        QueryIntent.HOLDINGS_LOOKUP: [
            "What's my asset allocation?",
            "What's my largest holding?",
            "Show me my portfolio balance",
        ],
        QueryIntent.CASH_FLOW_SUMMARY: [
            "Show me my monthly spending",
            "What are my recurring expenses?",
            "What was my net cash flow last month?",
        ],
    }
    return followups.get(intent, [
        "Show me my account balances",
        "What fees have I been charged?",
        "List my recent transactions",
    ])
