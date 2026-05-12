"""
Shared utilities for dashboard query modules.

All dashboard query functions return plain Python dicts/lists for direct JSON
serialization. These helpers handle Decimal parsing and formatting consistently
across banking_queries.py and investment_queries.py.
"""

from __future__ import annotations

import re
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
