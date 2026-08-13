"""
Shared utilities for dashboard query modules.

All dashboard query functions return plain Python dicts/lists for direct JSON
serialization. These helpers handle Decimal parsing and formatting consistently
across banking_queries.py and investment_queries.py.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation


def dec(value: str | None) -> Decimal:
    """Safely parse a stored Decimal string; return 0 on failure."""
    if not value:
        return Decimal("0")
    try:
        return Decimal(value)
    except InvalidOperation:
        return Decimal("0")


def fmt(value: Decimal) -> str:
    """Format a Decimal as a US dollar string (no symbol)."""
    return f"{value:,.2f}"


def normalize_merchant(raw: str | None) -> str:
    """
    Strip trailing noise from raw merchant strings so 'NETFLIX.COM' and
    'NETFLIX *STREAMING' both collapse to 'NETFLIX'.

    Rules (applied in order):
      1. Uppercase and strip whitespace.
      2. Remove common URL suffixes (.COM, .NET, etc.).
      3. Remove everything after the first '*' or '#'.
      4. Remove trailing store-number digit sequences.
      5. Collapse internal whitespace.
    """
    if not raw:
        return "UNKNOWN"
    s = raw.upper().strip()
    s = re.sub(r"\.(COM|NET|ORG|IO|CO|APP)\b", "", s)
    s = re.sub(r"[*#].*$", "", s)
    s = re.sub(r"\s+\d{3,}\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or "UNKNOWN"


# ── Period / date-range filtering (PR 05 — Global Period Filter) ───────────
#
# The unified backend period contract for dashboard queries is an explicit
# `date_from`/`date_to` (inclusive) range, resolved client-side from the
# Current Month / 1M / 3M / 6M / YTD / 1Y / Custom selector — see
# frontend-next/lib/period.ts. These helpers build the SQL fragment; the
# functions in banking_queries.py / investment_queries.py stay in charge of
# which date column they filter on.

def date_range_clause(
    column: str, *, date_from: date | None, date_to: date | None,
) -> tuple[str | None, dict[str, str]]:
    """Inclusive `[date_from, date_to]` filter on `column`.

    Returns `(None, {})` when neither bound is given — callers should skip
    appending a WHERE fragment in that case, preserving today's "all time"
    behavior for endpoints that never had a date filter before PR 05.
    """
    if date_from is None and date_to is None:
        return None, {}
    if date_from is None or date_to is None:
        raise ValueError("date_from and date_to must both be provided together")
    return (
        f"{column} BETWEEN :date_from AND :date_to",
        {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )


def date_range_or_rolling_months_clause(
    column: str, *, date_from: date | None, date_to: date | None, months: int,
) -> tuple[str, dict[str, str]]:
    """Same as `date_range_clause`, but falls back to the legacy rolling
    `-N months`-from-today SQLite window (`date('now', '-N months')`) when no
    explicit range is given, preserving the exact prior behavior of the
    endpoints that already accepted a `months` query param before PR 05.
    """
    clause, params = date_range_clause(column, date_from=date_from, date_to=date_to)
    if clause is not None:
        return clause, params
    return f"{column} >= date('now', :offset)", {"offset": f"-{months} months"}
