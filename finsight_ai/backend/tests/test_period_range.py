"""
PR 05 — Global Period Filter: pure, deterministic tests for the period model.

Covers:
  - `Period.for_range` (app.domain.plan_vs_actual) — validation, label
    defaults, equivalence with `Period.for_month` for a whole-month range.
  - `_resolve_period` (app.api.plan_vs_actual) — the unified
    start_date/end_date vs legacy year/month query-contract precedence and
    error handling.

DB-integration coverage (custom ranges flowing through the real Plan vs
Actual engine against a temp SQLite DB) lives in
backend/tests/test_plan_vs_actual.py.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from app.api.plan_vs_actual import _resolve_period
from app.domain.plan_vs_actual import Period


# ── Period.for_range ────────────────────────────────────────────────────────

def test_for_range_basic():
    p = Period.for_range(date(2026, 8, 5), date(2026, 8, 20))
    assert p.start == date(2026, 8, 5)
    assert p.end == date(2026, 8, 20)
    assert p.label == "2026-08-05..2026-08-20"


def test_for_range_custom_label():
    p = Period.for_range(date(2026, 8, 5), date(2026, 8, 20), label="Custom")
    assert p.label == "Custom"


def test_for_range_single_day_is_valid():
    p = Period.for_range(date(2026, 8, 5), date(2026, 8, 5))
    assert p.start == p.end == date(2026, 8, 5)


def test_for_range_end_before_start_raises():
    with pytest.raises(ValueError):
        Period.for_range(date(2026, 8, 20), date(2026, 8, 5))


def test_for_range_spans_year_boundary():
    p = Period.for_range(date(2025, 12, 20), date(2026, 1, 5))
    assert p.start.year == 2025
    assert p.end.year == 2026


def test_for_range_whole_month_matches_for_month():
    """A for_range() call spanning exactly one calendar month must resolve
    to the same [start, end] as for_month() — for_range is a strict
    superset, not a different rule, so PR 04's month-based call sites and
    PR 05's range-based call sites agree on whole-month periods."""
    via_month = Period.for_month(2026, 8)
    via_range = Period.for_range(date(2026, 8, 1), date(2026, 8, 31))
    assert via_month.start == via_range.start
    assert via_month.end == via_range.end


# ── _resolve_period precedence (app.api.plan_vs_actual) ────────────────────

def test_resolve_period_start_end_takes_precedence_over_year_month():
    period = _resolve_period(2026, 8, date(2026, 8, 5), date(2026, 8, 10))
    assert period.start == date(2026, 8, 5)
    assert period.end == date(2026, 8, 10)


def test_resolve_period_falls_back_to_year_month():
    period = _resolve_period(2026, 8, None, None)
    assert period.start == date(2026, 8, 1)
    assert period.end == date(2026, 8, 31)


def test_resolve_period_requires_something():
    with pytest.raises(HTTPException) as exc:
        _resolve_period(None, None, None, None)
    assert exc.value.status_code == 422


def test_resolve_period_rejects_partial_range():
    with pytest.raises(HTTPException) as exc:
        _resolve_period(None, None, date(2026, 8, 5), None)
    assert exc.value.status_code == 422


def test_resolve_period_rejects_inverted_range():
    with pytest.raises(HTTPException) as exc:
        _resolve_period(None, None, date(2026, 8, 20), date(2026, 8, 5))
    assert exc.value.status_code == 422
