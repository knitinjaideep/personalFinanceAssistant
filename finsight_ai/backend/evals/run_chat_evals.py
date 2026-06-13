#!/usr/bin/env python3
"""
Coral chat pipeline eval runner.

Runs each case in chat_eval_cases.yaml through the full chat_router.route()
pipeline — the same code path the API endpoint uses — then writes a terminal
summary and backend/evals/eval_report.md.

─── Quick-start ────────────────────────────────────────────────────────────────
  # From the backend/ directory:
  python evals/run_chat_evals.py

  # Filter to cases tagged or id-prefixed with "spending":
  python evals/run_chat_evals.py --filter spending

  # Run a single case by ID:
  python evals/run_chat_evals.py --id merchant_001

  # Stop on first failure:
  python evals/run_chat_evals.py --fail-fast

  # Suppress report file write:
  python evals/run_chat_evals.py --no-report

  # Show full answer text in the failure block:
  python evals/run_chat_evals.py --verbose
────────────────────────────────────────────────────────────────────────────────

Checks performed for each case
  1. intent   — ChatIntent produced by the classifier matches expected value(s)
  2. domain   — DataSource matches expected value(s)
  3. entities — named entity fields (institution, category, merchant, account)
                contain at least one of the allowed substrings
  4. answer   — final answer summary does NOT contain forbidden strings
                (answer_must_not_include)

answer_must_include is intentionally soft: it is only checked when the SQL
layer returns at least one row (to avoid false failures on empty databases).

Exit codes:
  0 — all cases passed
  1 — one or more cases failed
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ── Path bootstrap ─────────────────────────────────────────────────────────────
# This file lives at backend/evals/run_chat_evals.py.
# We need backend/ on sys.path so `app.*` imports resolve.
_EVALS_DIR = Path(__file__).resolve().parent          # backend/evals/
_BACKEND_DIR = _EVALS_DIR.parent                      # backend/
sys.path.insert(0, str(_BACKEND_DIR))

import os
os.chdir(_BACKEND_DIR)   # relative DB / config paths work from here

_CASES_YAML = _EVALS_DIR / "chat_eval_cases.yaml"
_REPORT_PATH = _EVALS_DIR / "eval_report.md"


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class CaseResult:
    case_id: str
    question: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    # What the pipeline actually produced
    actual_intent: str = ""
    actual_domain: str = ""
    actual_route: str = ""
    actual_route_type: str = ""
    actual_route_risk: str = ""
    actual_complexity_signals: list[str] = field(default_factory=list)
    actual_llm_called: bool = False
    actual_answer: str = ""
    # QueryPlan fields captured from RoutingOutcome
    actual_plan_task_type: str = ""
    actual_plan_metric: str = ""
    actual_plan_group_by: str = ""
    actual_plan_source: str = ""
    # Phase 5/6: answer strategy + LLM gate
    actual_answer_strategy: str = ""
    actual_answer_llm_called: bool = True
    # What the case expected (for the report)
    expected_intent: str = ""
    expected_domain: str = ""
    expected_route_type: str = ""
    expected_route_risk: str = ""
    expected_plan_task_type: str = ""
    expected_answer_strategy: str = ""
    duration_ms: float = 0.0
    tags: list[str] = field(default_factory=list)
    error: str = ""


# ── Single-case runner ─────────────────────────────────────────────────────────

async def run_one(case: dict[str, Any]) -> CaseResult:
    from app.services.chat_router import route   # full pipeline entry point

    case_id = case["id"]
    question = case["question"]
    expected = case.get("expected", {})
    tags = case.get("tags", [])

    result = CaseResult(
        case_id=case_id,
        question=question,
        passed=True,
        tags=tags,
        expected_intent=_as_list_str(expected.get("intent")),
        expected_domain=_as_list_str(expected.get("domain")),
        expected_route_type=_as_list_str(expected.get("route_type")),
        expected_route_risk=_as_list_str(expected.get("route_risk")),
        expected_plan_task_type=_as_list_str(expected.get("plan_task_type")),
        expected_answer_strategy=_as_list_str(expected.get("answer_strategy")),
    )

    t0 = time.perf_counter()
    try:
        outcome = await route(question, req_id=f"eval_{case_id}")
    except Exception as exc:
        result.passed = False
        result.error = str(exc)
        result.failures.append(f"pipeline_error: {exc}")
        result.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        return result

    result.duration_ms = round((time.perf_counter() - t0) * 1000, 1)

    # Capture actuals
    cls = outcome.classification
    result.actual_intent = cls.intent.value
    result.actual_domain = cls.data_source.value
    result.actual_route = outcome.route
    result.actual_answer = (outcome.answer.summary or "")[:300]

    dec = outcome.route_decision
    if dec is not None:
        result.actual_route_type = dec.route_type.value
        result.actual_route_risk = dec.route_risk.value
        result.actual_complexity_signals = dec.complexity_signals
        result.actual_llm_called = dec.llm_called

    qp = outcome.query_plan
    if qp is not None:
        pm = qp.primary_metric()
        result.actual_plan_task_type = qp.task_type
        result.actual_plan_metric = pm.name
        result.actual_plan_group_by = pm.group_by or ""
        result.actual_plan_source = qp.plan_source

    # Phase 5/6: answer strategy + LLM gate
    result.actual_answer_strategy = getattr(outcome.answer, "answer_strategy", "")
    result.actual_answer_llm_called = getattr(outcome.answer, "llm_called", True)

    # ── Check 1: intent ───────────────────────────────────────────────────────
    exp_intent = expected.get("intent")
    if exp_intent is not None:
        allowed = _as_list(exp_intent)
        if result.actual_intent not in allowed:
            result.failures.append(
                f"intent: got {result.actual_intent!r}, expected one of {allowed}"
            )

    # ── Check 2: domain ───────────────────────────────────────────────────────
    exp_domain = expected.get("domain")
    if exp_domain is not None:
        allowed = _as_list(exp_domain)
        if result.actual_domain not in allowed:
            result.failures.append(
                f"domain: got {result.actual_domain!r}, expected one of {allowed}"
            )

    # ── Check 3: route_type ───────────────────────────────────────────────────
    exp_route_type = expected.get("route_type")
    if exp_route_type is not None and result.actual_route_type:
        allowed = _as_list(exp_route_type)
        if result.actual_route_type not in allowed:
            result.failures.append(
                f"route_type: got {result.actual_route_type!r}, expected one of {allowed}"
            )

    # ── Check 4: route_risk ───────────────────────────────────────────────────
    exp_route_risk = expected.get("route_risk")
    if exp_route_risk is not None and result.actual_route_risk:
        allowed = _as_list(exp_route_risk)
        if result.actual_route_risk not in allowed:
            result.failures.append(
                f"route_risk: got {result.actual_route_risk!r}, expected one of {allowed}"
            )

    # ── Check 5: plan_task_type ───────────────────────────────────────────────
    exp_plan_task = expected.get("plan_task_type")
    if exp_plan_task is not None and result.actual_plan_task_type:
        allowed = _as_list(exp_plan_task)
        if result.actual_plan_task_type not in allowed:
            result.failures.append(
                f"plan_task_type: got {result.actual_plan_task_type!r}, expected one of {allowed}"
            )

    # ── Check 6: required entities ────────────────────────────────────────────
    req_ents = expected.get("required_entities", {})
    ents = cls.entities
    for ent_key, allowed_values in req_ents.items():
        allowed_values = _as_list(allowed_values)
        actual_val = _entity_value(ents, ent_key)
        if not any(v in (actual_val or "") for v in allowed_values):
            result.failures.append(
                f"entity[{ent_key}]: got {actual_val!r}, expected one of {allowed_values}"
            )

    # ── Check 6b: answer_strategy ─────────────────────────────────────────────
    exp_strategy = expected.get("answer_strategy")
    if exp_strategy is not None and result.actual_answer_strategy:
        allowed = _as_list(exp_strategy)
        if result.actual_answer_strategy not in allowed:
            result.failures.append(
                f"answer_strategy: got {result.actual_answer_strategy!r}, expected one of {allowed}"
            )

    # ── Check 7: answer must NOT include ─────────────────────────────────────
    answer_lower = result.actual_answer.lower()
    for forbidden in expected.get("answer_must_not_include", []):
        if forbidden.lower() in answer_lower:
            result.failures.append(
                f"answer_must_not_include: {forbidden!r} found in answer"
            )

    # ── Check 8: answer must include (soft — only when SQL rows exist) ────────
    if outcome.sql_rows > 0:
        for required in expected.get("answer_must_include", []):
            if required not in result.actual_answer:
                result.failures.append(
                    f"answer_must_include: {required!r} not in answer"
                )

    result.passed = len(result.failures) == 0
    return result


# ── Helpers ────────────────────────────────────────────────────────────────────

def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _as_list_str(value: Any) -> str:
    parts = _as_list(value)
    if not parts:
        return ""
    return " | ".join(parts)


def _entity_value(ents: Any, key: str) -> str | None:
    from app.services.normalization import (
        normalize_account,
        normalize_category,
        normalize_institution,
    )
    if key == "institution":
        slug, _ = normalize_institution(ents.institution)
        return slug or (ents.institution or "").lower()
    if key == "category":
        return normalize_category(ents.category) or (ents.category or "").lower()
    if key == "account":
        return normalize_account(ents.account) or (ents.account or "").lower()
    if key == "merchant":
        return (ents.merchant or "").lower()
    return None


# ── Batch runner ───────────────────────────────────────────────────────────────

async def run_all(cases: list[dict], *, fail_fast: bool, verbose: bool) -> list[CaseResult]:
    from app.db.engine import init_db
    from app.core.logger import configure_logging

    configure_logging()   # suppress pipeline noise during evals
    await init_db()

    results: list[CaseResult] = []
    total = len(cases)

    for i, case in enumerate(cases, 1):
        label = f"[{i:3d}/{total}] {case['id']:<35}"
        sys.stdout.write(f"  {label}")
        sys.stdout.flush()

        r = await run_one(case)
        results.append(r)

        status = "PASS" if r.passed else "FAIL"
        sys.stdout.write(f"{status}  ({r.duration_ms:.0f}ms)\n")

        if verbose and not r.passed:
            for f in r.failures:
                sys.stdout.write(f"         x {f}\n")
            if r.actual_route_type:
                sys.stdout.write(f"         route_type={r.actual_route_type}  route_risk={r.actual_route_risk}  llm_called={r.actual_llm_called}\n")
            if r.actual_plan_task_type:
                sys.stdout.write(f"         plan_task={r.actual_plan_task_type}  metric={r.actual_plan_metric}  group_by={r.actual_plan_group_by or '—'}  source={r.actual_plan_source}\n")
            if r.actual_answer_strategy:
                sys.stdout.write(f"         answer_strategy={r.actual_answer_strategy}  answer_llm_called={r.actual_answer_llm_called}\n")
            sys.stdout.write(f"         answer: {r.actual_answer[:120]!r}\n")

        if fail_fast and not r.passed:
            print("  (--fail-fast: stopping after first failure)")
            break

    return results


# ── Terminal summary ───────────────────────────────────────────────────────────

def print_summary(results: list[CaseResult]) -> None:
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)
    avg_ms = round(sum(r.duration_ms for r in results) / max(total, 1), 1)

    print()
    print("=" * 72)
    print(f"  CORAL EVAL SUMMARY — {passed}/{total} passed   {failed} failed   avg {avg_ms}ms/q")
    print("=" * 72)

    if failed:
        print("\nFAILED CASES:")
        for r in results:
            if r.passed:
                continue
            print(f"\n  [{r.case_id}]")
            print(f"    Q          : {r.question!r}")
            print(f"    intent     : actual={r.actual_intent!r}  expected={r.expected_intent!r}")
            print(f"    domain     : actual={r.actual_domain!r}  expected={r.expected_domain!r}")
            if r.actual_route_type:
                print(f"    route_type : actual={r.actual_route_type!r}  expected={r.expected_route_type!r}")
                print(f"    route_risk : actual={r.actual_route_risk!r}  expected={r.expected_route_risk!r}")
                print(f"    llm_called : {r.actual_llm_called}  signals={r.actual_complexity_signals}")
            if r.actual_answer_strategy:
                print(f"    strategy   : actual={r.actual_answer_strategy!r}  expected={r.expected_answer_strategy!r}  answer_llm={r.actual_answer_llm_called}")
            if r.actual_answer:
                print(f"    answer     : {r.actual_answer[:160]!r}")
            for f in r.failures:
                print(f"    x {f}")
            if r.error:
                print(f"    ERROR      : {r.error}")

    if passed == total:
        print("\n  All cases passed.")
    print()


# ── Markdown report ────────────────────────────────────────────────────────────

def write_report(results: list[CaseResult], path: Path) -> None:
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)
    avg_ms = round(sum(r.duration_ms for r in results) / max(total, 1), 1)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        "# Coral Chat Eval Report",
        "",
        f"**Generated:** {now}",
        f"**Cases:** {total}  |  **Passed:** {passed}  |  **Failed:** {failed}  |  **Avg latency:** {avg_ms}ms",
        "",
        "---",
        "",
        "## Results by case",
        "",
        "| ID | Tags | Intent | Domain | Route Type | Route Risk | Plan Task | Plan Src | Classifier LLM | Answer Strategy | Answer LLM | ms | Status |",
        "|----|------|--------|--------|------------|------------|-----------|----------|----------------|-----------------|------------|----|--------|",
    ]

    for r in results:
        status = "PASS" if r.passed else "**FAIL**"
        tag_str = ", ".join(r.tags) if r.tags else "—"
        llm_marker = "Y" if r.actual_llm_called else "N"
        plan_task = r.actual_plan_task_type or "—"
        plan_src = r.actual_plan_source or "—"
        strategy = r.actual_answer_strategy or "—"
        answer_llm = "Y" if r.actual_answer_llm_called else "N"
        lines.append(
            f"| {r.case_id} | {tag_str} | {r.actual_intent} | {r.actual_domain}"
            f" | {r.actual_route_type} | {r.actual_route_risk}"
            f" | {plan_task} | {plan_src} | {llm_marker}"
            f" | {strategy} | {answer_llm}"
            f" | {r.duration_ms:.0f} | {status} |"
        )

    if failed:
        lines += [
            "",
            "---",
            "",
            "## Failure details",
            "",
        ]
        for r in results:
            if r.passed:
                continue
            lines += [
                f"### `{r.case_id}`",
                "",
                f"**Question:** {r.question}",
                "",
                f"**Expected:** intent={r.expected_intent}  domain={r.expected_domain}  route_type={r.expected_route_type}  route_risk={r.expected_route_risk}  plan_task_type={r.expected_plan_task_type or '—'}  answer_strategy={r.expected_answer_strategy or '—'}",
                f"**Actual:**   intent={r.actual_intent}  domain={r.actual_domain}  route_type={r.actual_route_type}  route_risk={r.actual_route_risk}  llm_called={r.actual_llm_called}",
                f"**Plan:**     task_type={r.actual_plan_task_type or '—'}  metric={r.actual_plan_metric or '—'}  group_by={r.actual_plan_group_by or '—'}  source={r.actual_plan_source or '—'}",
                f"**Answer:**   strategy={r.actual_answer_strategy or '—'}  llm_called={r.actual_answer_llm_called}",
            ]
            if r.actual_complexity_signals:
                lines.append(f"**Complexity signals:** {', '.join(r.actual_complexity_signals)}")
            lines += [
                "",
                "**Failures:**",
            ]
            for f in r.failures:
                lines.append(f"- {f}")
            if r.actual_answer:
                lines.append(f"\n**Answer excerpt:** `{r.actual_answer[:200]}`")
            if r.error:
                lines.append(f"\n**Pipeline error:** `{r.error}`")
            lines.append("")

    lines += [
        "---",
        "",
        "## How to re-run",
        "",
        "```bash",
        "# From the backend/ directory:",
        "python evals/run_chat_evals.py",
        "",
        "# Filter to a tag or id prefix:",
        "python evals/run_chat_evals.py --filter spending",
        "",
        "# Single case:",
        "python evals/run_chat_evals.py --id merchant_001",
        "```",
        "",
        "_This file is auto-generated by `evals/run_chat_evals.py`. Do not edit manually._",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  Report written → {path.relative_to(_BACKEND_DIR)}")


# ── Case loading + filtering ───────────────────────────────────────────────────

def load_cases(
    yaml_path: Path,
    filter_prefix: str | None,
    single_id: str | None,
) -> list[dict]:
    with open(yaml_path, encoding="utf-8") as fh:
        cases: list[dict] = yaml.safe_load(fh)

    if single_id:
        cases = [c for c in cases if c["id"] == single_id]
    elif filter_prefix:
        # Match against id prefix OR any tag
        cases = [
            c for c in cases
            if c["id"].startswith(filter_prefix)
            or filter_prefix in (c.get("tags") or [])
        ]

    return cases


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            Run Coral chat eval cases against the live pipeline.
            Cases are defined in evals/chat_eval_cases.yaml.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--filter", "-f", metavar="PREFIX_OR_TAG",
        help="Run only cases whose id starts with this prefix or whose tags include it",
    )
    parser.add_argument(
        "--id",
        help="Run a single case by exact id (e.g. merchant_001)",
    )
    parser.add_argument(
        "--fail-fast", action="store_true",
        help="Stop after the first failing case",
    )
    parser.add_argument(
        "--yaml", default=str(_CASES_YAML),
        help=f"Path to eval cases YAML (default: {_CASES_YAML})",
    )
    parser.add_argument(
        "--no-report", action="store_true",
        help="Skip writing eval_report.md",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print failure details inline as each case runs",
    )
    args = parser.parse_args()

    yaml_path = Path(args.yaml)
    if not yaml_path.exists():
        print(f"Error: cases file not found: {yaml_path}")
        sys.exit(1)

    cases = load_cases(yaml_path, args.filter, args.id)
    if not cases:
        print("No matching cases found.")
        sys.exit(0)

    print(f"\n  Coral chat eval — {len(cases)} case(s)\n")
    results = asyncio.run(run_all(cases, fail_fast=args.fail_fast, verbose=args.verbose))
    print_summary(results)

    if not args.no_report:
        write_report(results, _REPORT_PATH)

    sys.exit(0 if all(r.passed for r in results) else 1)


if __name__ == "__main__":
    main()
