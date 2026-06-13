"""
Answer builder — composes structured, UI-friendly answers from retrieval results.

Phase 5/6/7/8 principles:
  - Python (FactBundle) is the source of truth for ALL calculations.
  - LLM only narrates pre-computed facts; it never sees raw rows.
  - Simple SQL answers use deterministic templates (no LLM, no latency).
  - The LLM is called only for hybrid/narrative/analysis paths.
  - LLM output is grounded: JSON schema, strict no-hallucination instructions.
  - Every LLM answer passes the answer verifier before leaving the pipeline.

Path decision (AnswerStrategy):
  template_only         → render_template() → immediate response
  hybrid_template_plus_llm → render_template() summary + LLM commentary on facts
  llm_narrative         → LLM receives FactBundle context (not raw rows)
"""

from __future__ import annotations

import os
import time
from typing import Any

from app.chat.answer_templates import (
    AnswerStrategy,
    build_llm_context_from_facts,
    choose_strategy,
    render_template,
)
from app.chat.answer_verifier import VerifierResult, verify_answer
from app.chat.fact_builder import FactBundle, build_facts
from app.chat.retrieval import RetrievalChunk, chunks_to_citations, retrieve
from app.core.logger import get_logger, get_request_id
from app.domain.entities import AnswerTimings, QueryContext, StructuredAnswer
from app.domain.enums import QueryIntent, QueryPath
from app.services import llm, sql_query, text_search
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
    route_risk: str | None = None,
) -> StructuredAnswer:
    """Build a structured answer for a user question."""
    if not req_id:
        req_id = get_request_id()
    # route_risk may be passed explicitly or read from ctx (set by chat_router).
    if route_risk is None:
        route_risk = getattr(ctx, "route_risk", "safe") or "safe"

    sql_result: dict[str, Any] | None = None
    retrieval_chunks: list[RetrievalChunk] = []
    # Legacy text_results kept for FactBundle signature compatibility
    text_results: list[dict] = []
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
        retrieval_mode = "hybrid" if path == QueryPath.HYBRID else "fts_only"
        retrieval_chunks = await retrieve(
            question,
            mode=retrieval_mode,
            top_k=6,
            institution=ctx.institution,
        )
        # Provide legacy text_results format for FactBundle (text only, no rich metadata needed)
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
        timings.rag_ms = round((time.perf_counter() - t0) * 1000, 1)

    chunks_retrieved = len(retrieval_chunks)
    logger.info(
        "rag_retrieval_completed",
        extra={
            "stage": "rag_retrieval_completed",
            "request_id": req_id,
            "chunks_retrieved": chunks_retrieved,
            "sources": [c.document_id for c in retrieval_chunks[:5]],
            "duration_ms": timings.rag_ms,
        },
    )

    # ── Check data ────────────────────────────────────────────────────────────
    has_sql_data  = bool(sql_result and sql_result.get("rows"))
    has_text_data = bool(text_results)
    exact_match   = sql_result.get("exact_match", True) if sql_result else True
    suggestions   = sql_result.get("suggestions", []) if sql_result else []
    searched_filters = sql_result.get("searched_filters", {}) if sql_result else {}

    if not has_sql_data and not has_text_data:
        logger.info(
            "response_generation_completed",
            extra={
                "stage": "response_generation_completed",
                "request_id": req_id,
                "answer_type": "no_data",
                "result_count": 0,
                "answer_strategy": AnswerStrategy.TEMPLATE_ONLY.value,
                "llm_called": False,
            },
        )
        return _no_data_answer(question, intent, searched_filters, suggestions, ctx)

    # ── Phase 5: build FactBundle (all Python calculations) ───────────────────
    fact_bundle = build_facts(intent, sql_result, text_results, ctx_filters=searched_filters)

    logger.info(
        "fact_builder_completed",
        extra={
            "stage": "fact_builder_completed",
            "request_id": req_id,
            "rows_used": fact_bundle.rows_used,
            "total_spend": fact_bundle.total_spend,
            "total_fees": fact_bundle.total_fees,
            "balance": fact_bundle.balance,
            "holdings_value": fact_bundle.holdings_value,
            "transaction_count": fact_bundle.transaction_count,
            "top_category_count": len(fact_bundle.top_categories),
            "has_comparison": fact_bundle.comparison is not None,
            "caveat_count": len(fact_bundle.caveats),
        },
    )

    # ── Phase 6: choose answer strategy ───────────────────────────────────────
    strategy = choose_strategy(
        intent,
        question,
        fact_bundle,
        has_rag=has_text_data,
        route_risk=route_risk,
    )

    answer_type = _determine_answer_type(intent, sql_result)

    # ── Generate narrative ────────────────────────────────────────────────────
    llm_called = False
    t0 = time.perf_counter()

    if strategy == AnswerStrategy.TEMPLATE_ONLY:
        narrative = render_template(intent, fact_bundle, question)
        if not narrative:
            # Template returned empty — fall back to a safe LLM call
            strategy = AnswerStrategy.HYBRID_TEMPLATE_PLUS_LLM

    if strategy == AnswerStrategy.HYBRID_TEMPLATE_PLUS_LLM:
        template_summary = render_template(intent, fact_bundle, question)
        llm_context = build_llm_context_from_facts(fact_bundle, template_summary)
        narrative = await _generate_narrative_from_facts(question, intent, llm_context, ctx, fact_bundle)
        llm_called = True

    elif strategy == AnswerStrategy.LLM_NARRATIVE:
        # LLM gets FactBundle context, not raw rows
        llm_context = build_llm_context_from_facts(fact_bundle)
        # Include document excerpts for RAG paths (use rich retrieval chunks)
        if retrieval_chunks:
            llm_context += "\n\nDocument excerpts (from statements):\n"
            for chunk in retrieval_chunks[:4]:
                excerpt = (chunk.snippet or chunk.text)[:200]
                source_label = chunk.document_name or chunk.institution_type or "document"
                llm_context += f"  [{source_label}] {excerpt}\n"
        elif text_results:
            llm_context += "\n\nDocument excerpts:\n"
            for chunk in text_results[:4]:
                llm_context += f"  - {chunk.get('snippet', chunk.get('content', ''))[:200]}\n"
        narrative = await _generate_narrative_from_facts(question, intent, llm_context, ctx, fact_bundle)
        llm_called = True

    timings.llm_ms = round((time.perf_counter() - t0) * 1000, 1) if llm_called else None

    # ── Assemble answer ───────────────────────────────────────────────────────
    answer = StructuredAnswer(
        answer_type=answer_type,
        title=_title_for_intent(intent, ctx),
        summary=narrative,
        intent=intent.value,
        query_path=path.value,
        confidence=confidence,
        rows_used=fact_bundle.rows_used,
        sql_used=[sql_result["sql_used"]] if sql_result and sql_result.get("sql_used") else [],
        timings=timings,
        request_id=req_id,
        exact_match=exact_match,
        searched_filters=searched_filters,
        suggestions_used=bool(suggestions),
        answer_strategy=strategy.value,
        llm_called=llm_called,
        based_on=_build_based_on(fact_bundle, ctx, retrieval_chunks),
    )

    # ── Add chart payload ─────────────────────────────────────────────────────
    if sql_result and sql_result.get("rows"):
        answer.chart_payload = build_chart(intent, sql_result["rows"], ctx.timeframe_label)
        # Prefer chart_ready_data from FactBundle when chart_payload is absent
        if not answer.chart_payload and fact_bundle.chart_ready_data:
            answer.chart_payload = {"type": "bar", "data": fact_bundle.chart_ready_data}

    # ── Structured sections / highlights ──────────────────────────────────────
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
            # Build highlights from FactBundle metrics (not raw rows)
            for label, value in _highlights_from_facts(fact_bundle):
                answer.highlights.append({"label": label, "value": value})

            # Fallback: if no fact highlights, use rows as before
            if not answer.highlights:
                for row in rows[:6]:
                    for key, value in row.items():
                        if value is None or key in ("earliest", "latest", "id", "sql_used"):
                            continue
                        answer.highlights.append({
                            "label": _friendly_label(key),
                            "value": _format_value(key, value),
                        })

    # ── Suggestion sections (only when exact query found nothing) ─────────────
    if suggestions and not has_sql_data:
        for sug in suggestions:
            answer.sections.append({
                "type": "suggestion_table",
                "label": sug.get("label", "Related data"),
                "columns": sug.get("columns", []),
                "rows": sug.get("rows", [])[:10],
                "summary": sug.get("summary", ""),
            })

    # ── Citations from hybrid retrieval ──────────────────────────────────────
    if retrieval_chunks:
        answer.citations.extend(chunks_to_citations(retrieval_chunks[:5]))

    # ── Phase 8: verify the answer before returning ───────────────────────────
    verifier_result = verify_answer(question, fact_bundle, answer)
    if verifier_result.repaired:
        answer.summary = verifier_result.repaired_summary or answer.summary
    # Carry verifier state on the answer for debug_payload assembly upstream.
    answer.verifier_passed = verifier_result.passed
    answer.verifier_repaired = verifier_result.repaired
    answer.verifier_warnings = verifier_result.warnings
    if verifier_result.warnings:
        logger.warning(
            "answer_verifier.warnings",
            extra={
                "request_id": req_id,
                "passed": verifier_result.passed,
                "repaired": verifier_result.repaired,
                "warnings": verifier_result.warnings,
            },
        )

    # ── Caveats (from FactBundle) ─────────────────────────────────────────────
    answer.caveats.extend(fact_bundle.caveats)
    if verifier_result.warnings and not verifier_result.passed:
        answer.caveats.append("Some details in this answer could not be fully verified.")

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

    if suggestions and not has_sql_data:
        answer.caveats.append(
            "The suggestion tables below show related data — "
            "they are not answers to your original question."
        )

    # ── Follow-ups (from FactBundle) ──────────────────────────────────────────
    answer.suggested_followups = fact_bundle.suggested_followups or _suggest_followups(intent, ctx)

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
            "answer_strategy": strategy.value,
            "llm_called": llm_called,
            "verifier_passed": verifier_result.passed,
            "verifier_repaired": verifier_result.repaired,
            "verifier_warning_count": len(verifier_result.warnings),
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

def _no_data_answer(
    question: str,
    intent: QueryIntent,
    searched_filters: dict | None = None,
    suggestions: list | None = None,
    ctx: "QueryContext | None" = None,
) -> StructuredAnswer:
    searched_filters = searched_filters or {}
    suggestions = suggestions or []

    filter_parts: list[str] = []
    if searched_filters.get("merchant"):
        filter_parts.append(f"merchant '{searched_filters['merchant']}'")
    if searched_filters.get("category"):
        filter_parts.append(f"category '{searched_filters['category']}'")
    if searched_filters.get("period"):
        filter_parts.append(f"period '{searched_filters['period']}'")
    elif searched_filters.get("date_from") or searched_filters.get("date_to"):
        df = searched_filters.get("date_from", "")
        dt = searched_filters.get("date_to", "")
        filter_parts.append(f"dates {df}–{dt}")
    if searched_filters.get("institution"):
        filter_parts.append(f"institution '{searched_filters['institution']}'")
    if searched_filters.get("account"):
        filter_parts.append(f"account '{searched_filters['account']}'")

    if filter_parts:
        filter_desc = ", ".join(filter_parts)
        summary = f"I searched for {filter_desc} but found no matching transactions."
    else:
        summary = (
            "I don't have data to answer this question yet. "
            "Upload your statements using the Upload button, then ask again."
        )

    caveats: list[str] = []
    if filter_parts:
        caveats.append(f"Searched for: {', '.join(filter_parts)}. No exact matches found.")
    else:
        caveats.append("No statements have been ingested for this query.")

    sections: list[dict] = []
    if suggestions:
        for sug in suggestions:
            sections.append({
                "type": "suggestion_table",
                "label": sug.get("label", "Related data"),
                "columns": sug.get("columns", []),
                "rows": sug.get("rows", [])[:10],
                "summary": sug.get("summary", ""),
            })
        caveats.append(
            "The tables below show related data — they are suggestions only, "
            "not an answer to your original question."
        )

    return StructuredAnswer(
        answer_type="no_data",
        title="No Matching Data",
        summary=summary,
        intent=intent.value,
        query_path="none",
        confidence=1.0,
        caveats=caveats,
        sections=sections,
        exact_match=False,
        searched_filters=searched_filters,
        suggestions_used=bool(suggestions),
        suggested_followups=[
            "What documents have been uploaded?",
            "Which institutions are covered?",
            "Show me my account balances",
        ],
        answer_strategy=AnswerStrategy.TEMPLATE_ONLY.value,
        llm_called=False,
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


# ── LLM narrative from FactBundle context (Phase 7 — grounded) ───────────────

_LLM_SYSTEM_PROMPT = """\
You are a personal finance assistant. Your job is to explain pre-computed facts \
in plain English. You must never invent, calculate, or change numbers.

RULES (non-negotiable):
1. Use ONLY the facts provided in the user message. Do not add numbers not listed there.
2. Do not recalculate totals, averages, deltas, or percentages — they are already computed.
3. Do not infer causes unless a cause is explicitly stated in the facts.
4. Do not claim a trend or change unless comparison facts are provided.
5. If data is missing or partial, say so briefly (e.g. "Data covers only March 2026.").
6. Format dollar amounts as $X,XXX.XX. Never show raw field names or underscores.
7. Keep the response concise: 1-3 sentences unless sections are genuinely needed.
8. Mention caveats when they are listed in the facts.

Output ONLY valid JSON — no markdown, no prose outside the JSON:
{
  "summary": "<1-3 sentence plain-English answer>",
  "highlights": [],
  "caveats": ["<caveat if any>"],
  "suggested_followups": ["<follow-up question>"]
}
If you cannot produce valid JSON, output a single plain sentence starting with "PLAIN:".
"""


def _build_grounded_prompt(
    question: str,
    context: str,
    fact_bundle: "FactBundle",
    timeframe_label: str = "",
) -> str:
    """Build a tight, grounded prompt for the LLM (Phase 7)."""
    lines: list[str] = [
        f"Question: {question}",
        "",
        "Pre-computed facts (do not recalculate, do not change):",
        context,
    ]
    if fact_bundle.caveats:
        lines.append("\nCaveats (must be acknowledged if relevant):")
        for c in fact_bundle.caveats:
            lines.append(f"  - {c}")
    if timeframe_label:
        lines.append(f"\nTime period in scope: {timeframe_label}")
    lines.append(
        "\nAnswer using ONLY the facts above. "
        "Return valid JSON as specified in the system prompt."
    )
    return "\n".join(lines)


def _extract_summary_from_llm_json(raw: str, fallback: str) -> str:
    """Parse LLM JSON output and extract the summary field. Returns fallback on failure."""
    import json, re

    text = raw.strip()

    # Plain-text fallback signal
    if text.startswith("PLAIN:"):
        return text[len("PLAIN:"):].strip()

    # Strip markdown fences
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"```$", "", text.strip())

    # Find first JSON object
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        logger.warning(
            "answer_builder.llm_no_json",
            extra={"request_id": get_request_id(), "raw_preview": text[:200]},
        )
        return fallback

    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "answer_builder.llm_json_parse_failed",
            extra={"request_id": get_request_id(), "error": str(exc), "raw_preview": text[:200]},
        )
        return fallback

    summary = data.get("summary", "")
    if not summary or not isinstance(summary, str):
        return fallback
    return summary.strip()


async def _generate_narrative_from_facts(
    question: str,
    intent: QueryIntent,
    context: str,
    ctx: QueryContext,
    fact_bundle: "FactBundle | None" = None,
) -> str:
    """LLM receives pre-computed facts only. Strict grounded JSON prompt (Phase 7).

    Falls back to the deterministic template summary if:
    - LLM call fails
    - LLM returns no valid JSON
    - LLM summary field is empty
    """
    if not context:
        return "No data available to answer this question."

    # Build deterministic fallback from context first line (cheap, always available)
    fallback_summary = next(
        (line for line in context.splitlines() if line.strip() and not line.startswith("  ")),
        "",
    ) or "Unable to generate answer."

    prompt = _build_grounded_prompt(
        question,
        context,
        fact_bundle or FactBundle(),
        timeframe_label=ctx.timeframe_label or "",
    )

    try:
        raw = await llm.generate(
            prompt,
            system=_LLM_SYSTEM_PROMPT,
            format_json=True,
        )
        summary = _extract_summary_from_llm_json(raw, fallback_summary)
        logger.info(
            "answer_builder.llm_narrative_generated",
            extra={
                "request_id": get_request_id(),
                "intent": intent.value,
                "json_parse": "ok" if summary != fallback_summary else "fallback",
            },
        )
        return summary
    except Exception as exc:
        logger.warning(
            "answer_builder.llm_failed",
            extra={"request_id": get_request_id(), "error": str(exc)},
        )
        return fallback_summary


# ── Highlights from FactBundle ────────────────────────────────────────────────

def _highlights_from_facts(b: FactBundle) -> list[tuple[str, str]]:
    """Build (label, value) pairs from pre-computed FactBundle metrics."""
    out: list[tuple[str, str]] = []

    if b.total_spend is not None:
        out.append(("Total Spend", f"${b.total_spend:,.2f}"))
    if b.total_income is not None:
        out.append(("Total Income", f"${b.total_income:,.2f}"))
    if b.net_cash_flow is not None:
        out.append(("Net Cash Flow", f"${b.net_cash_flow:,.2f}"))
    if b.total_fees is not None:
        out.append(("Total Fees", f"${b.total_fees:,.2f}"))
    if b.balance is not None:
        out.append(("Balance", f"${b.balance:,.2f}"))
    if b.holdings_value is not None:
        out.append(("Holdings Value", f"${b.holdings_value:,.2f}"))
    if b.transaction_count:
        out.append(("Transactions", str(b.transaction_count)))
    if b.average_transaction is not None:
        out.append(("Avg per Transaction", f"${b.average_transaction:,.2f}"))

    return out[:6]


# ── Formatting helpers (kept for table-type answers) ─────────────────────────

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


# ── Based-on provenance string ────────────────────────────────────────────────

def _build_based_on(
    bundle: "FactBundle",
    ctx: "QueryContext",
    retrieval_chunks: "list[RetrievalChunk]",
) -> str:
    """Build a short human-readable provenance string for the 'Based on' bar."""
    parts: list[str] = []

    # Institution / account
    if bundle.institution:
        parts.append(bundle.institution.replace("_", " ").title())
    elif ctx.institution:
        parts.append(ctx.institution.replace("_", " ").title())
    if bundle.account_name:
        parts.append(bundle.account_name)

    # Time range
    if bundle.date_range:
        parts.append(bundle.date_range)
    elif ctx.timeframe_label:
        parts.append(ctx.timeframe_label)

    # Row count (SQL) or chunk count (RAG)
    if bundle.rows_used:
        parts.append(f"{bundle.rows_used} transaction{'s' if bundle.rows_used != 1 else ''}")
    elif retrieval_chunks:
        parts.append(f"{len(retrieval_chunks)} document chunk{'s' if len(retrieval_chunks) != 1 else ''}")

    return ", ".join(parts) if parts else ""


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
