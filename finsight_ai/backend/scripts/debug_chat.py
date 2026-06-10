#!/usr/bin/env python3
"""
Debug a single chat question through the full Coral pipeline.

Usage:
    python scripts/debug_chat.py --question "How much did I spend on Amex Gold last month?"
    python scripts/debug_chat.py -q "What fees did Morgan Stanley charge me?" --verbose

Output (all to stdout):
    1. Classified intent + confidence + data source
    2. Extracted entities (institution, category, merchant, account, date range)
    3. Selected route (sql / fts / hybrid / fallback)
    4. SQL tool result (row count, summary, first 3 rows)
    5. RAG chunk count
    6. Final answer (summary)
    7. Any errors / caveats
    8. Timing breakdown (ms)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# ── Bootstrap Python path ─────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
os.chdir(ROOT)  # make relative DB paths work


async def _run(question: str, verbose: bool) -> None:
    # Import after path setup
    from app.core.logger import configure_logging
    configure_logging(level="WARNING")  # suppress noise during debug run

    from app.db.engine import init_db
    from app.services.intent_classifier import classify
    from app.services.intent_mapping import to_query_intent
    from app.services import sql_query, text_search, vector_search
    from app.services.normalization import (
        normalize_account,
        normalize_category,
        normalize_institution,
        normalize_timerange,
    )
    from app.domain.entities import QueryContext
    from app.domain.enums import QueryPath
    from app.domain.classification import DataSource
    from datetime import date as _date

    await init_db()

    print()
    print("=" * 70)
    print(f"  CORAL DEBUG — {question!r}")
    print("=" * 70)

    total_start = time.perf_counter()

    # ── 1. Classify ───────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    classification = await classify(question)
    intent_ms = round((time.perf_counter() - t0) * 1000, 1)

    print(f"\n[1] INTENT CLASSIFICATION ({intent_ms} ms)")
    print(f"    intent     : {classification.intent.value}")
    print(f"    data_source: {classification.data_source.value}")
    print(f"    confidence : {round(classification.confidence * 100, 1)}%")
    print(f"    source     : {classification.source}")
    if classification.needs_clarification:
        print(f"    CLARIFY    : {classification.clarifying_question}")

    # ── 2. Extract entities ───────────────────────────────────────────────────
    ents = classification.entities
    print(f"\n[2] EXTRACTED ENTITIES")
    print(f"    institution: {ents.institution!r}")
    print(f"    account    : {ents.account!r}")
    print(f"    category   : {ents.category!r}")
    print(f"    merchant   : {ents.merchant!r}")
    print(f"    time_range : {ents.time_range.type} / {ents.time_range.value!r}")
    if ents.time_range.start_date or ents.time_range.end_date:
        print(f"    dates      : {ents.time_range.start_date} → {ents.time_range.end_date}")

    # ── 3. Normalize ─────────────────────────────────────────────────────────
    inst_slug, inst_display = normalize_institution(ents.institution)
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

    ctx = QueryContext(
        date_from=date_from,
        date_to=date_to,
        timeframe_label=label,
        category=category,
        merchant=merchant,
        institution=inst_slug,
        account_type=None,
        account_name=account_name,
    )

    print(f"\n[3] NORMALIZED CONTEXT")
    print(f"    institution: {inst_slug!r} ({inst_display!r})")
    print(f"    account    : {account_name!r}")
    print(f"    category   : {category!r}")
    print(f"    merchant   : {merchant!r}")
    print(f"    date_from  : {date_from}")
    print(f"    date_to    : {date_to}")
    print(f"    label      : {label!r}")

    # ── 4. Route + SQL ────────────────────────────────────────────────────────
    query_intent = to_query_intent(classification.intent)
    ds = classification.data_source

    if ds == DataSource.SQL:
        path = QueryPath.SQL
    elif ds == DataSource.RAG:
        path = QueryPath.FTS
    elif ds == DataSource.HYBRID:
        path = QueryPath.HYBRID
    else:
        path = QueryPath.HYBRID

    print(f"\n[4] ROUTING")
    print(f"    query_intent: {query_intent.value}")
    print(f"    path        : {path.value}")

    # ── 5. SQL execution ──────────────────────────────────────────────────────
    sql_result = None
    sql_rows = 0
    if path in (QueryPath.SQL, QueryPath.HYBRID):
        t0 = time.perf_counter()
        sql_result = await sql_query.execute_for_intent(query_intent, question, ctx)
        sql_ms = round((time.perf_counter() - t0) * 1000, 1)
        sql_rows = len(sql_result.get("rows", []))

        print(f"\n[5] SQL TOOL RESULT ({sql_ms} ms)")
        print(f"    tool       : sql_query / {query_intent.value}")
        print(f"    row_count  : {sql_rows}")
        print(f"    summary    : {sql_result.get('summary', '')}")

        if verbose and sql_result.get("sql_used"):
            print(f"    sql_used   :\n{sql_result['sql_used'][:800]}")

        if sql_rows == 0:
            print("    ⚠️  No SQL rows — trying relaxed filters…")
            # Try relaxed
            if ctx.category or ctx.merchant:
                relaxed = ctx.model_copy(update={"category": None, "merchant": None})
                sql_result2 = await sql_query.execute_for_intent(query_intent, question, relaxed)
                if sql_result2.get("rows"):
                    sql_result = sql_result2
                    sql_rows = len(sql_result["rows"])
                    print(f"    ✓ Relaxed hit: {sql_rows} rows (dropped category/merchant)")
            # Try date fallback
            if not sql_rows and (ctx.date_from or ctx.date_to):
                no_date = ctx.model_copy(update={"date_from": None, "date_to": None, "timeframe_label": "", "category": None, "merchant": None})
                sql_result3 = await sql_query.execute_for_intent(query_intent, question, no_date)
                if sql_result3.get("rows"):
                    sql_result = sql_result3
                    sql_rows = len(sql_result["rows"])
                    print(f"    ✓ Date fallback hit: {sql_rows} rows (dropped date filter)")

        if verbose and sql_rows > 0:
            print(f"    first rows :")
            for r in (sql_result.get("rows") or [])[:3]:
                print(f"      {json.dumps(r, default=str)}")
    else:
        print(f"\n[5] SQL TOOL — skipped (path={path.value})")

    # ── 6. RAG ───────────────────────────────────────────────────────────────
    rag_count = 0
    if path in (QueryPath.FTS, QueryPath.VECTOR, QueryPath.HYBRID) or sql_rows == 0:
        t0 = time.perf_counter()
        try:
            text_chunks = await text_search.search(question)
            rag_count = len(text_chunks)
            rag_ms = round((time.perf_counter() - t0) * 1000, 1)
            print(f"\n[6] RAG ({rag_ms} ms)")
            print(f"    fts_chunks : {rag_count}")
            if verbose and text_chunks:
                print(f"    first chunk: {text_chunks[0].get('snippet', text_chunks[0].get('content', ''))[:200]}")
        except Exception as exc:
            print(f"\n[6] RAG — error: {exc}")

    # ── 7. Summary ────────────────────────────────────────────────────────────
    total_ms = round((time.perf_counter() - total_start) * 1000, 1)

    print(f"\n[7] SUMMARY")
    print(f"    sql_rows   : {sql_rows}")
    print(f"    rag_chunks : {rag_count}")
    print(f"    total_ms   : {total_ms}")

    if sql_rows == 0 and rag_count == 0:
        print("\n  ⚠️  NO DATA FOUND — chatbot would show helpful fallback")
    elif sql_rows > 0:
        print(f"\n  ✓ Would answer from SQL: {sql_result.get('summary', '')}")
    elif rag_count > 0:
        print(f"\n  ✓ Would answer from RAG ({rag_count} chunks)")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Debug a Coral chat question through the full pipeline."
    )
    parser.add_argument(
        "-q", "--question",
        required=True,
        help="The question to debug, e.g. \"How much did I spend last month?\""
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show SQL query, first rows, and first RAG chunk"
    )
    args = parser.parse_args()
    asyncio.run(_run(args.question, args.verbose))


if __name__ == "__main__":
    main()
