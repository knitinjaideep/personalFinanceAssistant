"""
SSE streaming pipeline for chat.

Runs the same classify → route → SQL → answer pipeline as the batch endpoint,
but emits Server-Sent Events at each stage so the UI can show progressive
status rather than a blank spinner.

Event protocol:
  status       {"message": str}
  intent       {"domain": str, "intent": str, "confidence": float}
  tool_start   {"tool": str, "intent": str}
  tool_result  {"row_count": int, "summary": str}
  answer_token {"text": str}
  table        {"columns": list, "rows": list}
  chart        {"type": str, ...}
  error        {"message": str}
  done         {"request_id": str}
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from app.chat.guardrails import apply_guardrails_to_answer, safe_error_message
from app.chat.retrieval import RetrievalChunk, chunks_to_citations, retrieve
from app.chat.services.conversation_context import conversation_context
from app.config import settings
from app.core.logger import get_logger, get_request_id
from app.domain.classification import ChatIntent, DataSource, IntentClassificationResult
from app.domain.entities import AnswerTimings, QueryContext, StructuredAnswer
from app.domain.enums import QueryIntent, QueryPath
from app.services import availability, llm, sql_query, text_search
from app.services.chart_builder import build_chart
from app.services.intent_classifier import classify
from app.services.intent_mapping import to_query_intent
from app.services.normalization import (
    category_display_name,
    institution_display_name,
    normalize_account,
    normalize_category,
    normalize_institution,
    normalize_timerange,
)

logger = get_logger(__name__)

# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ── Context builder (mirrors chat_router._build_context) ─────────────────────

def _build_context(result: IntentClassificationResult) -> QueryContext:
    from datetime import date as _date
    ents = result.entities
    inst_slug, _ = normalize_institution(ents.institution)
    category = normalize_category(ents.category)
    account_name = normalize_account(ents.account)

    tr = ents.time_range
    date_from = date_to = None
    label = ""
    if tr.start_date or tr.end_date:
        try:
            date_from = _date.fromisoformat(tr.start_date[:10]) if tr.start_date else None
            date_to   = _date.fromisoformat(tr.end_date[:10])   if tr.end_date   else None
        except (ValueError, TypeError):
            pass
        label = tr.value or ""
    elif tr.value:
        date_from, date_to, label = normalize_timerange(tr.value)

    merchant = ents.merchant.lower() if ents.merchant else None
    if account_name and merchant and account_name in merchant:
        merchant = None

    return QueryContext(
        date_from=date_from,
        date_to=date_to,
        timeframe_label=label,
        category=category,
        merchant=merchant,
        institution=inst_slug,
        account_type=None,
        account_name=account_name,
        amount_min=result.entities.amount_min,
        amount_max=result.entities.amount_max,
    )


def _resolve_path(data_source: DataSource, query_intent: QueryIntent) -> QueryPath:
    if data_source == DataSource.SQL:
        return QueryPath.SQL
    if data_source == DataSource.RAG:
        return QueryPath.FTS
    if data_source == DataSource.HYBRID:
        return QueryPath.HYBRID
    return QueryPath.HYBRID


# ── SQL fallback (mirrors chat_router._sql_with_fallbacks) ───────────────────

async def _sql_with_fallbacks(
    query_intent: QueryIntent,
    question: str,
    ctx: QueryContext,
) -> tuple[dict[str, Any] | None, QueryContext]:
    result = await sql_query.execute_for_intent(query_intent, question, ctx)
    if result.get("rows"):
        return result, ctx

    if ctx.category or ctx.merchant:
        relaxed = ctx.model_copy(update={"category": None, "merchant": None})
        result = await sql_query.execute_for_intent(query_intent, question, relaxed)
        if result.get("rows"):
            return result, relaxed

    if ctx.date_from or ctx.date_to:
        no_date = ctx.model_copy(update={
            "date_from": None, "date_to": None, "timeframe_label": "",
            "category": None, "merchant": None,
        })
        result = await sql_query.execute_for_intent(query_intent, question, no_date)
        if result.get("rows"):
            return result, no_date

    return result, ctx


# ── LLM context builder (mirrors answer_builder._build_context) ───────────────

def _build_llm_context(
    sql_result: dict | None,
    text_results: list,
    _unused_vector_results: list,
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
            row_str = ", ".join(f"{k}: {v}" for k, v in row.items() if v is not None and k != "sql_used")
            parts.append(f"  Row {i+1}: {row_str}")

    if text_results:
        parts.append("\nDocument excerpts:")
        for chunk in text_results[:4]:
            parts.append(f"  - {chunk.get('snippet', chunk.get('content', ''))[:200]}")

    return "\n".join(parts)


# ── Structured answer assembly (mirrors answer_builder logic) ─────────────────

_NUMERIC_INTENTS = {
    QueryIntent.FEE_SUMMARY,
    QueryIntent.CASH_FLOW_SUMMARY,
    QueryIntent.BALANCE_LOOKUP,
    QueryIntent.HOLDINGS_TOTAL,
}
_TABLE_INTENTS = {
    QueryIntent.TRANSACTION_LOOKUP,
    QueryIntent.HOLDINGS_LOOKUP,
    QueryIntent.STATEMENT_COVERAGE,
    QueryIntent.DOCUMENT_AVAILABILITY,
    QueryIntent.INSTITUTION_COVERAGE,
    QueryIntent.SUBSCRIPTION_LOOKUP,
    QueryIntent.SPENDING_BY_CATEGORY,
}
_SQL_ROUTED_INTENTS = _NUMERIC_INTENTS | _TABLE_INTENTS | {
    QueryIntent.CASH_FLOW_SUMMARY,
}

_MONEY_COLS: frozenset[str] = frozenset({
    "total_amount", "total", "amount", "market_value", "total_value",
    "unrealized_gain_loss", "cash_value", "invested_value", "fee_total",
    "total_spent", "monthly_amount", "avg_per_txn", "total_inflow",
    "total_outflow", "net_flow", "avg_amount",
})

_LABEL_MAP: dict[str, str] = {
    "fee_category": "Category", "total_amount": "Total", "total": "Total",
    "amount": "Amount", "count": "Count", "fee_count": "Fees",
    "transaction_count": "Transactions", "institution": "Institution",
    "institution_type": "Institution", "account_type": "Account Type",
    "account_name": "Account", "transaction_type": "Type",
    "merchant_name": "Merchant", "merchant": "Merchant",
    "transaction_date": "Date", "description": "Description",
    "symbol": "Symbol", "market_value": "Market Value",
    "percent_of_portfolio": "Portfolio %", "period_start": "From",
    "period_end": "To", "total_value": "Total Value",
    "total_spent": "Total Spent", "avg_per_txn": "Avg per Transaction",
    "monthly_amount": "Monthly Amount", "unrealized_gain_loss": "Unrealized G/L",
    "total_inflow": "Total Inflow", "total_outflow": "Total Outflow",
    "net_flow": "Net Flow", "doc_count": "Documents",
}

_FOLLOWUPS: dict[QueryIntent, list[str]] = {
    QueryIntent.FEE_SUMMARY: ["Which account has the highest fees?", "Show me all fee transactions", "What are my advisory fees this year?"],
    QueryIntent.SPENDING_BY_CATEGORY: ["Show me my grocery transactions", "What subscriptions am I paying?", "How does this compare to last month?"],
    QueryIntent.SUBSCRIPTION_LOOKUP: ["How much did I spend on subscriptions last year?", "Show me my Netflix charges", "What are my top recurring expenses?"],
    QueryIntent.TRANSACTION_LOOKUP: ["Show me transactions over $500", "What's my spending by category?", "Show me recent deposits"],
    QueryIntent.BALANCE_LOOKUP: ["How has my balance changed over time?", "What's my total invested amount?", "Show me my holdings breakdown"],
    QueryIntent.HOLDINGS_TOTAL: ["Show me my top holdings", "What's my asset allocation?", "How much have I gained or lost?"],
    QueryIntent.HOLDINGS_LOOKUP: ["What's my asset allocation?", "What's my largest holding?", "Show me my portfolio balance"],
    QueryIntent.CASH_FLOW_SUMMARY: ["Show me my spending by category", "What are my recurring expenses?", "What was my net cash flow last month?"],
}
_DEFAULT_FOLLOWUPS = ["Show me my account balances", "What fees have I been charged?", "What is my total invested amount?"]


def _friendly_label(col: str) -> str:
    return _LABEL_MAP.get(col, col.replace("_", " ").title())


def _format_value(col: str, value: object) -> str:
    if value is None:
        return "—"
    val_str = str(value)
    if col in _MONEY_COLS:
        try:
            return f"${float(val_str):,.2f}"
        except (ValueError, TypeError):
            pass
    return val_str


def _intent_title(intent: QueryIntent, ctx: QueryContext) -> str:
    base = {
        QueryIntent.FEE_SUMMARY: "Fee Summary",
        QueryIntent.SPENDING_BY_CATEGORY: "Spending Breakdown",
        QueryIntent.SUBSCRIPTION_LOOKUP: "Recurring Charges",
        QueryIntent.TRANSACTION_LOOKUP: "Transactions",
        QueryIntent.BALANCE_LOOKUP: "Account Balances",
        QueryIntent.HOLDINGS_LOOKUP: "Portfolio Holdings",
        QueryIntent.HOLDINGS_TOTAL: "Total Invested",
        QueryIntent.CASH_FLOW_SUMMARY: "Cash Flow",
        QueryIntent.DOCUMENT_AVAILABILITY: "Document Status",
        QueryIntent.INSTITUTION_COVERAGE: "Institution Coverage",
        QueryIntent.STATEMENT_COVERAGE: "Statement Coverage",
        QueryIntent.TEXT_EXPLANATION: "Document Excerpt",
        QueryIntent.HYBRID_FINANCIAL_QUESTION: "Financial Analysis",
    }.get(intent, "Answer")
    parts: list[str] = []
    if ctx.institution:
        parts.append(ctx.institution.replace("_", " ").title())
    if ctx.timeframe_label:
        parts.append(ctx.timeframe_label)
    return f"{base} — {', '.join(parts)}" if parts else base


def _build_structured_answer(
    *,
    narrative: str,
    question: str,
    query_intent: QueryIntent,
    path: QueryPath,
    confidence: float,
    sql_result: dict[str, Any] | None,
    text_results: list[dict],
    retrieval_chunks: list[RetrievalChunk],
    used_ctx: QueryContext,
    has_sql: bool,
    req_id: str,
    llm_ms: float,
    total_ms: float,
) -> StructuredAnswer:
    if query_intent in _NUMERIC_INTENTS:
        answer_type = "numeric"
    elif query_intent in _TABLE_INTENTS:
        answer_type = "table"
    else:
        answer_type = "prose"

    timings = AnswerTimings(llm_ms=llm_ms)

    answer = StructuredAnswer(
        answer_type=answer_type,
        title=_intent_title(query_intent, used_ctx),
        summary=narrative,
        intent=query_intent.value,
        query_path=path.value,
        confidence=round(confidence, 3),
        rows_used=len(sql_result["rows"]) if sql_result and sql_result.get("rows") else 0,
        sql_used=[sql_result["sql_used"]] if sql_result and sql_result.get("sql_used") else [],
        timings=timings,
        request_id=req_id,
    )

    if sql_result and sql_result.get("rows"):
        rows = sql_result["rows"]
        cols = sql_result.get("columns", [])
        answer.primary_value = sql_result.get("summary", "")
        answer.chart_payload = build_chart(query_intent, rows, used_ctx.timeframe_label)

        if answer_type == "table":
            answer.sections.append({"type": "table", "columns": cols, "rows": rows[:20]})
        elif answer_type == "numeric":
            for row in rows[:6]:
                for key, value in row.items():
                    if value is None or key in ("earliest", "latest", "id", "sql_used"):
                        continue
                    answer.highlights.append({
                        "label": _friendly_label(key),
                        "value": _format_value(key, value),
                    })

    if retrieval_chunks:
        answer.citations.extend(chunks_to_citations(retrieval_chunks[:5]))
    elif text_results:
        for chunk in text_results[:5]:
            answer.citations.append({
                "source": f"Page {chunk.get('page_number', '?')}",
                "text": chunk.get("snippet", chunk.get("content", ""))[:200],
                "document_id": chunk.get("document_id", ""),
            })

    # Based-on provenance
    based_on_parts: list[str] = []
    if used_ctx.institution:
        based_on_parts.append(used_ctx.institution.replace("_", " ").title())
    if used_ctx.timeframe_label:
        based_on_parts.append(used_ctx.timeframe_label)
    if sql_result and sql_result.get("rows"):
        n = len(sql_result["rows"])
        based_on_parts.append(f"{n} row{'s' if n != 1 else ''}")
    elif retrieval_chunks:
        n = len(retrieval_chunks)
        based_on_parts.append(f"{n} chunk{'s' if n != 1 else ''}")
    answer.based_on = ", ".join(based_on_parts) if based_on_parts else ""

    if used_ctx.timeframe_label:
        answer.caveats.append(f"Results filtered to: {used_ctx.timeframe_label}.")
    if not has_sql and text_results and query_intent in _SQL_ROUTED_INTENTS:
        answer.caveats.append("Based on document text — structured data not available for this query.")

    answer.suggested_followups = _FOLLOWUPS.get(query_intent, _DEFAULT_FOLLOWUPS)[:4]

    return answer


# ── Main streaming generator ──────────────────────────────────────────────────

async def stream_chat(
    question: str,
    *,
    req_id: str = "",
    conversation_id: str = "",
) -> AsyncIterator[str]:
    """Async generator that yields SSE-formatted strings for a chat question."""
    req_id = req_id or get_request_id()
    total_start = time.perf_counter()

    logger.info(
        "stream_chat.start",
        extra={
            "stage": "stream_start",
            "request_id": req_id,
            "conversation_id": conversation_id or "none",
            "question": question[:200],
        },
    )

    try:
        # ── 1. Status ────────────────────────────────────────────────────────
        yield _sse("status", {"message": "Understanding your question…"})

        # ── 2. Classify ──────────────────────────────────────────────────────
        classification = await classify(question)

        # ── 2b. Merge prior conversation context ─────────────────────────────
        if conversation_id:
            classification = await conversation_context.resolve_followup(
                conversation_id, classification
            )

        query_intent = to_query_intent(classification.intent)
        ctx = _build_context(classification)

        yield _sse("intent", {
            "domain": classification.data_source.value,
            "intent": classification.intent.value,
            "confidence": round(classification.confidence, 3),
        })

        logger.info(
            "stream_chat.classified",
            extra={
                "stage": "stream_classified",
                "request_id": req_id,
                "intent": classification.intent.value,
                "data_source": classification.data_source.value,
                "confidence": round(classification.confidence, 3),
                "route_type": "simple_sql" if classification.data_source.value == "sql" else classification.data_source.value,
            },
        )

        # ── 3. Clarification short-circuit ───────────────────────────────────
        if classification.needs_clarification and classification.intent == ChatIntent.UNKNOWN:
            q = classification.clarifying_question or (
                "Could you tell me which account, institution, or time period you mean?"
            )
            yield _sse("answer_token", {"text": q})
            yield _sse("done", {"request_id": req_id})
            return

        # ── 4. Resolve path and run SQL ──────────────────────────────────────
        path = _resolve_path(classification.data_source, query_intent)
        sql_result: dict[str, Any] | None = None
        used_ctx = ctx

        if path in (QueryPath.SQL, QueryPath.HYBRID):
            yield _sse("status", {"message": "Querying your financial data…"})
            yield _sse("tool_start", {
                "tool": "sql_query",
                "intent": query_intent.value,
            })
            t0 = time.perf_counter()
            sql_result, used_ctx = await _sql_with_fallbacks(query_intent, question, ctx)
            sql_ms = round((time.perf_counter() - t0) * 1000, 1)
            sql_rows = len(sql_result.get("rows", [])) if sql_result else 0

            yield _sse("tool_result", {
                "row_count": sql_rows,
                "summary": sql_result.get("summary", "") if sql_result else "",
                "duration_ms": sql_ms,
            })

            logger.info(
                "stream_chat.sql_done",
                extra={"stage": "stream_sql", "request_id": req_id,
                       "row_count": sql_rows, "duration_ms": sql_ms},
            )
        else:
            sql_rows = 0

        has_sql = sql_rows > 0

        # ── 5. Hybrid retrieval (FTS5 + vector) ─────────────────────────────
        retrieval_chunks: list[RetrievalChunk] = []
        text_results: list[dict] = []  # legacy compat
        force_rag = path in (QueryPath.FTS, QueryPath.VECTOR, QueryPath.HYBRID)
        rag_fallback = (not has_sql) and path == QueryPath.SQL

        if force_rag or rag_fallback:
            yield _sse("status", {"message": "Searching document text…"})
            try:
                retrieval_mode = "hybrid" if path == QueryPath.HYBRID else "fts_only"
                retrieval_chunks = await retrieve(
                    question,
                    mode=retrieval_mode,
                    top_k=6,
                    institution=used_ctx.institution,
                )
                text_results = [
                    {
                        "chunk_id": c.chunk_id,
                        "document_id": c.document_id,
                        "snippet": c.snippet or c.text[:200],
                        "content": c.text,
                        "page_number": c.page_number,
                        "institution_type": c.institution_type,
                    }
                    for c in retrieval_chunks
                ]
            except Exception as exc:
                logger.warning("stream_chat.retrieval_failed", extra={"error": str(exc)})

        rag_count = len(retrieval_chunks)

        # ── 6. Emit citations if retrieval found document evidence ───────────
        if retrieval_chunks:
            yield _sse("citations", {
                "chunks": [
                    {
                        "chunk_id": c.chunk_id,
                        "document_name": c.document_name,
                        "page_number": c.page_number,
                        "snippet": (c.snippet or c.text)[:150],
                        "score": c.score,
                        "retrieval_method": c.retrieval_method,
                    }
                    for c in retrieval_chunks[:5]
                ]
            })

        # ── 6b. Emit table/chart if data exists ──────────────────────────────
        if has_sql and sql_result:
            rows = sql_result.get("rows", [])
            cols = sql_result.get("columns", [])
            if rows and cols:
                yield _sse("table", {"columns": cols, "rows": rows[:20]})

            chart = build_chart(query_intent, rows, used_ctx.timeframe_label)
            if chart:
                yield _sse("chart", chart)

        # ── 7. No data fallback ──────────────────────────────────────────────
        if not has_sql and rag_count == 0:
            inst_display = institution_display_name(ctx.institution)
            cat_display = category_display_name(ctx.category)
            searched_bits: list[str] = []
            if cat_display:
                searched_bits.append(f"{cat_display} transactions")
            if inst_display:
                searched_bits.append(f"at {inst_display}")
            if ctx.timeframe_label:
                searched_bits.append(f"for {ctx.timeframe_label}")
            searched = " ".join(searched_bits) or "your statements"

            cats = await availability.available_categories(ctx.institution)
            insts = await availability.available_institutions()
            lines = [f"I couldn't find {searched}."]
            if cats:
                pretty = ", ".join(category_display_name(c) or c for c in cats[:8])
                lines.append(f"Categories I have: {pretty}.")
            if insts:
                lines.append(f"Institutions with data: {', '.join(insts[:8])}.")
            clarify = classification.clarifying_question or "Could you mention an account, institution, or time period?"
            lines.append(clarify)

            fallback_text = " ".join(lines)
            yield _sse("answer_token", {"text": fallback_text})
            yield _sse("done", {"request_id": req_id, "duration_ms": round((time.perf_counter() - total_start) * 1000, 1)})
            return

        # ── 8. Build and stream verified answer ──────────────────────────────
        yield _sse("status", {"message": "Building answer…"})

        llm_context = _build_llm_context(sql_result, text_results, [], used_ctx)
        period_hint = f" The data is filtered to {used_ctx.timeframe_label}." if used_ctx.timeframe_label else ""

        system_prompt = (
            "You are Coral, a personal finance assistant. Answer in plain English using only the data provided.\n"
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
        prompt = f"Question: {question}\n\nData:\n{llm_context}\n\nAnswer concisely in plain English."

        t0 = time.perf_counter()
        token_count = 0
        narrative = ""
        try:
            # Buffer all tokens so guardrails can be applied to the full answer
            # before emission. This prevents account numbers leaking mid-stream.
            tokens: list[str] = []
            async for token in llm.generate_stream(prompt, system=system_prompt):
                tokens.append(token)
                token_count += 1
            narrative = apply_guardrails_to_answer("".join(tokens))
            yield _sse("answer_token", {"text": narrative})
        except Exception as exc:
            logger.warning("stream_chat.llm_stream_failed", extra={"error": str(exc), "request_id": req_id})
            try:
                fallback_text = await llm.generate(prompt, system=system_prompt)
                narrative = apply_guardrails_to_answer(fallback_text.strip())
                yield _sse("answer_token", {"text": narrative})
            except Exception:
                narrative = sql_result.get("summary", "Unable to generate answer.") if sql_result else "Unable to generate answer."
                yield _sse("answer_token", {"text": narrative})

        llm_ms = round((time.perf_counter() - t0) * 1000, 1)
        total_ms = round((time.perf_counter() - total_start) * 1000, 1)

        # ── Build full StructuredAnswer for the frontend ──────────────────────
        structured = _build_structured_answer(
            narrative=narrative,
            question=question,
            query_intent=query_intent,
            path=path,
            confidence=classification.confidence,
            sql_result=sql_result,
            text_results=text_results,
            retrieval_chunks=retrieval_chunks,
            used_ctx=used_ctx,
            has_sql=has_sql,
            req_id=req_id,
            llm_ms=llm_ms,
            total_ms=total_ms,
        )

        # Record turn for follow-up resolution
        if conversation_id:
            try:
                await conversation_context.record_turn(
                    conversation_id,
                    classification=classification,
                    institution=used_ctx.institution,
                    account_name=used_ctx.account_name,
                    category=used_ctx.category,
                    merchant=used_ctx.merchant,
                    date_from=used_ctx.date_from.isoformat() if used_ctx.date_from else None,
                    date_to=used_ctx.date_to.isoformat() if used_ctx.date_to else None,
                    timeframe_label=used_ctx.timeframe_label,
                    amount_min=used_ctx.amount_min,
                    amount_max=used_ctx.amount_max,
                    answer_summary=sql_result.get("summary", "") if sql_result else "",
                )
            except Exception:
                pass  # never let context recording break the stream

        logger.info(
            "stream_chat.done",
            extra={
                "stage": "stream_done",
                "request_id": req_id,
                "conversation_id": conversation_id or "none",
                "intent": classification.intent.value,
                "route": path.value,
                "sql_rows": sql_rows,
                "rag_chunks": rag_count,
                "token_count": token_count,
                "llm_ms": llm_ms,
                "total_ms": total_ms,
            },
        )

        yield _sse("done", {
            "request_id": req_id,
            "conversation_id": conversation_id or "",
            "duration_ms": total_ms,
            "answer": structured.model_dump(),
        })

    except Exception as exc:
        logger.error(
            "stream_chat.error",
            extra={"stage": "stream_error", "request_id": req_id, "error": str(exc)},
            exc_info=True,
        )
        yield _sse("error", {"message": safe_error_message(exc)})
        yield _sse("done", {"request_id": req_id})
