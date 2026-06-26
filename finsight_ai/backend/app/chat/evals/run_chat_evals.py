#!/usr/bin/env python3
"""
Coral chatbot eval runner — golden question test suite.

Usage:
    python app/chat/evals/run_chat_evals.py
    python app/chat/evals/run_chat_evals.py --filter banking
    python app/chat/evals/run_chat_evals.py --id banking_spend_001
    python app/chat/evals/run_chat_evals.py --fail-fast

Output:
    PASS/FAIL per question, then a summary table.
    Failing questions show which stage failed: classification, entity, route, answer.

The eval checks:
  - Intent was correctly classified (or is in the expected list)
  - Data source (domain) matches expected
  - Required entities were extracted
  - Answer text includes required substrings
  - Answer text excludes forbidden substrings
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── Bootstrap ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

import os
os.chdir(ROOT)

# ── Dataclass for a single eval result ────────────────────────────────────────

@dataclass
class EvalResult:
    eval_id: str
    question: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    actual_intent: str = ""
    actual_domain: str = ""
    actual_route_type: str = ""
    actual_task_type: str = ""
    actual_answer: str = ""
    actual_semantic_parser_called: bool = False
    actual_semantic_scenario_type: str = ""
    duration_ms: float = 0.0


# ── Eval logic ────────────────────────────────────────────────────────────────

async def run_one_eval(case: dict[str, Any]) -> EvalResult:
    from app.services.intent_classifier import classify
    from app.services.intent_mapping import build_route_decision, to_query_intent
    from app.services import sql_query, text_search
    from app.services.normalization import (
        normalize_account,
        normalize_category,
        normalize_institution,
        normalize_timerange,
    )
    from app.domain.entities import QueryContext
    from app.domain.enums import QueryPath
    from app.domain.classification import DataSource, RouteType
    from app.chat.query_planner import plan as build_query_plan
    from datetime import date as _date

    eval_id = case["id"]
    question = case["question"]
    expected = case.get("expected", {})
    failures: list[str] = []

    t0 = time.perf_counter()

    # 1. Classify
    classification = await classify(question)
    actual_intent = classification.intent.value
    actual_domain = classification.data_source.value

    # Check intent
    exp_intent = expected.get("intent")
    if exp_intent:
        allowed = [exp_intent] if isinstance(exp_intent, str) else exp_intent
        if not any(actual_intent == i for i in allowed):
            failures.append(f"intent: got {actual_intent!r}, expected one of {allowed}")

    # Check domain/data_source
    exp_domain = expected.get("domain")
    if exp_domain:
        allowed_domains = [exp_domain] if isinstance(exp_domain, str) else exp_domain
        if not any(actual_domain == d for d in allowed_domains):
            failures.append(f"domain: got {actual_domain!r}, expected one of {allowed_domains}")

    # 2. Normalize entities
    ents = classification.entities
    inst_slug, _ = normalize_institution(ents.institution)
    category = normalize_category(ents.category)
    account_name = normalize_account(ents.account)
    merchant = ents.merchant.lower() if ents.merchant else None

    # Check required entities
    req_ents = expected.get("required_entities", {})
    for ent_key, allowed_values in req_ents.items():
        if isinstance(allowed_values, str):
            allowed_values = [allowed_values]
        if ent_key == "institution":
            actual_val = inst_slug or (ents.institution or "")
        elif ent_key == "category":
            actual_val = category or (ents.category or "")
        elif ent_key == "account":
            actual_val = account_name or (ents.account or "")
        elif ent_key == "merchant":
            actual_val = merchant or (ents.merchant or "")
        else:
            actual_val = ""
        # Check if any allowed value is a substring of the actual value
        if not any(v in (actual_val or "") for v in allowed_values):
            failures.append(f"entity[{ent_key}]: got {actual_val!r}, expected one of {allowed_values}")

    # 2b. Build route decision + query plan for route_type / task_type checks
    decision = build_route_decision(classification, question=question)
    actual_route_type = decision.route_type.value

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

    if account_name and merchant and account_name in merchant:
        merchant = None

    ctx = QueryContext(
        date_from=date_from, date_to=date_to, timeframe_label=label,
        category=category, merchant=merchant, institution=inst_slug,
        account_type=None, account_name=account_name,
    )

    query_plan = await build_query_plan(classification, decision, question=question, ctx=ctx)
    actual_task_type = query_plan.task_type

    # Check route_type
    exp_route_type = expected.get("route_type")
    if exp_route_type:
        allowed_rt = [exp_route_type] if isinstance(exp_route_type, str) else exp_route_type
        if not any(actual_route_type == rt for rt in allowed_rt):
            failures.append(f"route_type: got {actual_route_type!r}, expected one of {allowed_rt}")

    # Check task_type
    exp_task_type = expected.get("task_type")
    if exp_task_type:
        allowed_tt = [exp_task_type] if isinstance(exp_task_type, str) else exp_task_type
        if not any(actual_task_type == tt for tt in allowed_tt):
            failures.append(f"task_type: got {actual_task_type!r}, expected one of {allowed_tt}")

    # Check purchase_price extraction (affordability evals)
    exp_price = expected.get("purchase_price")
    if exp_price is not None and query_plan.affordability is not None:
        actual_price = query_plan.affordability.purchase_price
        if actual_price is None or abs(actual_price - float(exp_price)) > 1.0:
            failures.append(
                f"purchase_price: got {actual_price!r}, expected ~{exp_price}"
            )

    # Check semantic_parser_called (semantic scenario evals)
    exp_semantic = expected.get("semantic_parser_called")
    if exp_semantic is not None and query_plan.affordability is not None:
        actual_semantic = query_plan.affordability.semantic_parser_called
        if actual_semantic != bool(exp_semantic):
            failures.append(
                f"semantic_parser_called: got {actual_semantic!r}, expected {bool(exp_semantic)!r}"
            )

    # 3. Run pipeline to get answer text
    # For affordability, use the affordability analyzer directly
    actual_answer = ""
    try:
        if decision.route_type == RouteType.AFFORDABILITY and query_plan.affordability is not None:
            from app.chat.affordability import analyze as analyze_affordability
            aff = query_plan.affordability
            ans = await analyze_affordability(
                task_type=aff.task_type,
                purchase_price=aff.purchase_price,
                purchase_item=aff.purchase_item,
                purchase_category=aff.purchase_category,
                question=question,
            )
            actual_answer = ans.summary or ""
        else:
            query_intent = to_query_intent(classification.intent)
            ds = classification.data_source
            if ds == DataSource.SQL:
                path = QueryPath.SQL
            elif ds == DataSource.RAG:
                path = QueryPath.FTS
            else:
                path = QueryPath.HYBRID

            if path in (QueryPath.SQL, QueryPath.HYBRID):
                sql_result = await sql_query.execute_for_intent(query_intent, question, ctx)
                actual_answer = sql_result.get("summary", "")
                if not sql_result.get("rows") and (ctx.category or ctx.merchant):
                    relaxed = ctx.model_copy(update={"category": None, "merchant": None})
                    sql_result2 = await sql_query.execute_for_intent(query_intent, question, relaxed)
                    if sql_result2.get("rows"):
                        actual_answer = sql_result2.get("summary", actual_answer)

            if not actual_answer and path in (QueryPath.FTS, QueryPath.HYBRID):
                chunks = await text_search.search(question)
                if chunks:
                    actual_answer = chunks[0].get("snippet", chunks[0].get("content", ""))[:200]
    except Exception as exc:
        failures.append(f"pipeline error: {exc}")

    # 4. Check answer constraints
    must_include = expected.get("answer_must_include", [])
    for token in must_include:
        if token not in actual_answer:
            failures.append(f"answer_must_include: {token!r} not in answer ({actual_answer[:100]!r})")

    must_not_include = expected.get("answer_must_not_include", [])
    for token in must_not_include:
        if token.lower() in actual_answer.lower():
            failures.append(f"answer_must_not_include: {token!r} found in answer")

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)

    actual_semantic_parser_called = False
    actual_semantic_scenario_type = ""
    if query_plan.affordability is not None:
        actual_semantic_parser_called = query_plan.affordability.semantic_parser_called
        actual_semantic_scenario_type = query_plan.affordability.semantic_scenario_type

    return EvalResult(
        eval_id=eval_id,
        question=question,
        passed=len(failures) == 0,
        failures=failures,
        actual_intent=actual_intent,
        actual_domain=actual_domain,
        actual_route_type=actual_route_type,
        actual_task_type=actual_task_type,
        actual_answer=actual_answer[:150],
        actual_semantic_parser_called=actual_semantic_parser_called,
        actual_semantic_scenario_type=actual_semantic_scenario_type,
        duration_ms=duration_ms,
    )


# ── Runner ────────────────────────────────────────────────────────────────────

async def run_evals(
    cases: list[dict],
    fail_fast: bool = False,
) -> list[EvalResult]:
    import os
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    from app.db.engine import init_db
    from app.core.logger import configure_logging
    configure_logging()
    await init_db()

    results: list[EvalResult] = []
    total = len(cases)
    for i, case in enumerate(cases, 1):
        sys.stdout.write(f"\r  [{i:3d}/{total}] {case['id']:<35} ", )
        sys.stdout.flush()
        result = await run_one_eval(case)
        results.append(result)
        status = "✓ PASS" if result.passed else "✗ FAIL"
        sys.stdout.write(f"{status} ({result.duration_ms}ms)\n")
        if not result.passed and fail_fast:
            break
    return results


def load_cases(yaml_path: Path, filter_prefix: str | None, single_id: str | None) -> list[dict]:
    with open(yaml_path) as f:
        cases = yaml.safe_load(f)
    if single_id:
        cases = [c for c in cases if c["id"] == single_id]
    elif filter_prefix:
        cases = [c for c in cases if c["id"].startswith(filter_prefix)]
    return cases


def print_summary(results: list[EvalResult]) -> None:
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)
    avg_ms = round(sum(r.duration_ms for r in results) / max(total, 1), 1)

    print()
    print("=" * 70)
    print(f"  EVAL SUMMARY: {passed}/{total} passed   {failed} failed   avg {avg_ms}ms/q")
    print("=" * 70)

    if failed > 0:
        print("\nFAILURES:")
        for r in results:
            if not r.passed:
                print(f"\n  [{r.eval_id}]")
                print(f"    Q: {r.question!r}")
                print(f"    intent={r.actual_intent}  domain={r.actual_domain}  route={r.actual_route_type}  task={r.actual_task_type}")
                if r.actual_semantic_parser_called or r.actual_semantic_scenario_type:
                    print(f"    semantic_called={r.actual_semantic_parser_called}  semantic_type={r.actual_semantic_scenario_type!r}")
                print(f"    answer={r.actual_answer!r}")
                for f in r.failures:
                    print(f"    ✗ {f}")

    if passed == total:
        print("\n  All evals passed! 🎉")
    print()


def main():
    parser = argparse.ArgumentParser(description="Run Coral golden question evals")
    parser.add_argument("--filter", "-f", help="Run only evals with IDs starting with this prefix (e.g. 'banking')")
    parser.add_argument("--id", help="Run a single eval by ID")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after first failure")
    parser.add_argument("--yaml", default=str(Path(__file__).parent / "golden_questions.yaml"), help="Path to golden questions YAML")
    args = parser.parse_args()

    yaml_path = Path(args.yaml)
    if not yaml_path.exists():
        print(f"Error: {yaml_path} not found")
        sys.exit(1)

    cases = load_cases(yaml_path, args.filter, args.id)
    if not cases:
        print("No matching cases found.")
        sys.exit(0)

    print(f"\nRunning {len(cases)} golden question eval(s)…\n")
    results = asyncio.run(run_evals(cases, fail_fast=args.fail_fast))
    print_summary(results)

    if any(not r.passed for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
