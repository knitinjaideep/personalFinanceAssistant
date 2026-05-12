"""
query_context.py — extract structured parameters from a natural-language question.

Parses:
  - Timeframe  : "last month", "in January", "this year", "Q2 2024", "last 3 months"
  - Category   : TransactionCategory keyword matching
  - Merchant   : free-form merchant keyword
  - Institution: institution name keyword
  - Flags      : recurring/subscription only

All extraction is pure-Python, zero LLM calls — fast and deterministic.
"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, timedelta
from typing import Any

from app.domain.entities import QueryContext
from app.domain.enums import TransactionCategory

# ── Month name maps ───────────────────────────────────────────────────────────

_MONTH_NAMES: dict[str, int] = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# ── Category keyword mapping ──────────────────────────────────────────────────

_CATEGORY_KEYWORDS: list[tuple[TransactionCategory, list[str]]] = [
    (TransactionCategory.GROCERIES,     ["grocer", "grocery", "supermarket", "whole foods", "trader joe", "safeway", "kroger", "costco"]),
    (TransactionCategory.RESTAURANTS,   ["restaurant", "dining", "eat out", "food", "lunch", "dinner", "breakfast", "cafe", "coffee", "doordash", "uber eats", "grubhub"]),
    (TransactionCategory.SUBSCRIPTIONS, ["subscription", "subscribe", "recurring", "membership", "netflix", "spotify", "hulu", "apple", "amazon prime", "disney"]),
    (TransactionCategory.TRAVEL,        ["travel", "flight", "hotel", "airbnb", "airline", "uber", "lyft", "transit", "airfare"]),
    (TransactionCategory.SHOPPING,      ["shopping", "amazon", "target", "walmart", "retail", "purchase"]),
    (TransactionCategory.GAS,           ["gas", "fuel", "gasoline", "shell", "chevron", "bp", "exxon"]),
    (TransactionCategory.UTILITIES,     ["utility", "utilities", "electric", "water", "internet", "cable", "phone", "cell"]),
    (TransactionCategory.HEALTHCARE,    ["healthcare", "medical", "pharmacy", "doctor", "hospital", "dental", "cvs", "walgreens"]),
    (TransactionCategory.ENTERTAINMENT, ["entertainment", "movie", "theater", "concert", "sport", "gym", "fitness"]),
    (TransactionCategory.INSURANCE,     ["insurance", "insur"]),
    (TransactionCategory.TRANSFERS,     ["transfer", "zelle", "venmo", "paypal"]),
    (TransactionCategory.FEES,          ["fee", "charge", "penalty"]),
]

# ── Institution keyword mapping ───────────────────────────────────────────────

_INSTITUTION_KEYWORDS: list[tuple[str, list[str]]] = [
    ("morgan_stanley", ["morgan stanley", "morgan", "ms "]),
    ("chase",          ["chase"]),
    ("etrade",         ["etrade", "e*trade", "e-trade"]),
    ("amex",           ["amex", "american express"]),
    ("discover",       ["discover"]),
]

# ── Account-type keyword mapping ─────────────────────────────────────────────

_ACCOUNT_TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("credit_card",          ["credit card", "card spending", "card charges"]),
    ("checking",             ["checking", "bank account", "debit"]),
    ("ira",                  ["ira", "traditional ira"]),
    ("roth_ira",             ["roth ira", "roth"]),
    ("individual_brokerage", ["brokerage", "individual account", "taxable"]),
    ("advisory",             ["advisory", "managed account", "wealth management"]),
]


# ── Public API ────────────────────────────────────────────────────────────────

def extract_context(question: str, today: date | None = None) -> QueryContext:
    """Return a QueryContext with all extractable parameters filled in."""
    today = today or date.today()
    q = question.lower().strip()

    date_from, date_to, label = _parse_timeframe(q, today)
    category    = _parse_category(q)
    merchant    = _parse_merchant(q)
    institution = _parse_institution(q)
    account_type = _parse_account_type(q)
    is_recurring = _parse_recurring_flag(q)

    return QueryContext(
        date_from=date_from,
        date_to=date_to,
        timeframe_label=label,
        category=category,
        merchant=merchant,
        institution=institution,
        account_type=account_type,
        is_recurring_only=is_recurring,
    )


# ── Timeframe parser ──────────────────────────────────────────────────────────

def _parse_timeframe(q: str, today: date) -> tuple[date | None, date | None, str]:
    """Return (date_from, date_to, human_label) or (None, None, "")."""

    # "last month" / "previous month"
    if re.search(r"\blast\s+month\b|\bprevious\s+month\b", q):
        first = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        last  = today.replace(day=1) - timedelta(days=1)
        return first, last, "last month"

    # "this month" / "current month"
    if re.search(r"\bthis\s+month\b|\bcurrent\s+month\b", q):
        first = today.replace(day=1)
        last  = today.replace(day=monthrange(today.year, today.month)[1])
        return first, last, "this month"

    # "this year" / "current year" / "ytd" / "year to date"
    if re.search(r"\bthis\s+year\b|\bcurrent\s+year\b|\byt[d]\b|\byear[\s-]to[\s-]date\b", q):
        return today.replace(month=1, day=1), today, f"{today.year} YTD"

    # "last year"
    if re.search(r"\blast\s+year\b", q):
        y = today.year - 1
        return date(y, 1, 1), date(y, 12, 31), str(y)

    # "last N months"  e.g. "last 3 months", "past 6 months"
    m = re.search(r"\b(?:last|past)\s+(\d+)\s+months?\b", q)
    if m:
        n = int(m.group(1))
        return today - timedelta(days=30 * n), today, f"last {n} months"

    # "last N weeks"
    m = re.search(r"\b(?:last|past)\s+(\d+)\s+weeks?\b", q)
    if m:
        n = int(m.group(1))
        return today - timedelta(weeks=n), today, f"last {n} weeks"

    # "last N days"
    m = re.search(r"\b(?:last|past)\s+(\d+)\s+days?\b", q)
    if m:
        n = int(m.group(1))
        return today - timedelta(days=n), today, f"last {n} days"

    # "Q1 2024" / "Q3" (current year assumed)
    m = re.search(r"\bq([1-4])\s*(\d{4})?\b", q)
    if m:
        qnum = int(m.group(1))
        year = int(m.group(2)) if m.group(2) else today.year
        month_start = (qnum - 1) * 3 + 1
        month_end   = qnum * 3
        last_day    = monthrange(year, month_end)[1]
        label = f"Q{qnum} {year}"
        return date(year, month_start, 1), date(year, month_end, last_day), label

    # "in January" / "January 2024" / "last January"
    for name, num in _MONTH_NAMES.items():
        pattern = rf"\b(?:in\s+|last\s+|this\s+)?{name}(?:\s+(\d{{4}}))?\b"
        m = re.search(pattern, q)
        if m:
            year = int(m.group(1)) if m.group(1) else today.year
            # "last January" — if the named month hasn't happened yet this year use last year
            if not m.group(1) and re.search(r"\blast\s+" + name, q):
                year = today.year - 1 if num >= today.month else today.year
            last_day = monthrange(year, num)[1]
            label = f"{name.capitalize()} {year}"
            return date(year, num, 1), date(year, num, last_day), label

    # Bare 4-digit year  e.g. "in 2023", "during 2024"
    m = re.search(r"\b(20\d{2})\b", q)
    if m:
        year = int(m.group(1))
        return date(year, 1, 1), date(year, 12, 31), str(year)

    return None, None, ""


# ── Category / merchant / institution / account-type parsers ──────────────────

def _parse_category(q: str) -> str | None:
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(kw in q for kw in keywords):
            return category.value
    return None


def _parse_merchant(q: str) -> str | None:
    """Extract a merchant name from patterns like 'at Starbucks', 'from Amazon', 'to Netflix'."""
    m = re.search(r"\b(?:at|from|to|with|for)\s+([A-Za-z][A-Za-z0-9 &'.-]{1,30}?)(?:\s+(?:in|on|last|this|during|between|since)|$|\?|,)", q)
    if m:
        candidate = m.group(1).strip()
        # Skip timeframe words that leak through
        _SKIP = {"the", "my", "a", "an", "all", "each", "every", "any"}
        if candidate.lower() not in _SKIP and len(candidate) > 2:
            return candidate.lower()
    return None


def _parse_institution(q: str) -> str | None:
    for slug, keywords in _INSTITUTION_KEYWORDS:
        if any(kw in q for kw in keywords):
            return slug
    return None


def _parse_account_type(q: str) -> str | None:
    for atype, keywords in _ACCOUNT_TYPE_KEYWORDS:
        if any(kw in q for kw in keywords):
            return atype
    return None


def _parse_recurring_flag(q: str) -> bool:
    return bool(re.search(
        r"\b(?:subscription|subscribe|recurring|repeat|monthly\s+charge|regular\s+payment)\b",
        q,
    ))
