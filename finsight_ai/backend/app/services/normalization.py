"""
Normalization helpers for chatbot entity extraction.

Maps fuzzy / abbreviated user terms onto the canonical values the SQL layer
expects:

  - institutions  → display name + internal slug (matches InstitutionType)
  - categories     → canonical TransactionCategory value
  - time ranges    → explicit (start_date, end_date, label)

Typo-tolerant where it is cheap to be (substring + a few common misspellings).
Pure Python, no LLM calls.
"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, timedelta

# ── Institution normalization ─────────────────────────────────────────────────
# Each entry: canonical slug → (display_name, [aliases/substrings])
# Aliases are matched as case-insensitive substrings of the cleaned token.

_INSTITUTIONS: dict[str, tuple[str, list[str]]] = {
    "morgan_stanley":   ("Morgan Stanley", ["morgan stanley", "morgan", "morgon", "stanley", "ms", "msft_advisory"]),
    "chase":            ("Chase", ["chase", "jpmorgan chase", "jp morgan", "jpmorgan"]),
    "etrade":           ("E*TRADE", ["etrade", "e*trade", "e-trade", "e trade"]),
    "amex":             ("American Express", ["amex", "american express", "americanexpress", "am ex"]),
    "discover":         ("Discover", ["discover", "discvr", "discover card"]),
    "bank_of_america":  ("Bank of America", ["bank of america", "bofa", "boa", "bankofamerica", "bofamerica", "bof america", "bofa checking"]),
    "marcus":           ("Marcus by Goldman Sachs", ["marcus", "goldman sachs", "goldman", "marcus hysa", "marcus savings", "marcus high yield"]),
}

# Short standalone aliases that should only match as whole words (avoid "ms" in
# "transactions"). Everything else matches as a substring.
_WHOLE_WORD_ALIASES = {"ms", "am ex"}


def normalize_institution(value: str | None) -> tuple[str | None, str | None]:
    """Return (slug, display_name) for a fuzzy institution string.

    Returns (None, None) when nothing matches.
    """
    if not value:
        return None, None
    text = value.strip().lower()
    if not text:
        return None, None

    for slug, (display, aliases) in _INSTITUTIONS.items():
        for alias in aliases:
            if alias in _WHOLE_WORD_ALIASES:
                if re.search(rf"\b{re.escape(alias)}\b", text):
                    return slug, display
            elif alias in text:
                return slug, display
    return None, None


def institution_display_name(slug: str | None) -> str | None:
    """Display name for a known institution slug."""
    if not slug:
        return None
    entry = _INSTITUTIONS.get(slug.lower())
    if entry:
        return entry[0]
    return slug.replace("_", " ").title()


# ── Category normalization ────────────────────────────────────────────────────
# Canonical values match domain.enums.TransactionCategory.

_CATEGORIES: dict[str, list[str]] = {
    "groceries":     ["grocery", "groceries", "supermarket", "supermarkets", "whole foods", "trader joe", "safeway", "kroger", "costco"],
    "restaurants":   ["restaurant", "restaurants", "dining", "dine", "food delivery", "doordash", "uber eats", "grubhub", "cafe", "coffee", "eating out"],
    "gas":           ["gas", "fuel", "gasoline", "petrol", "shell", "chevron", "exxon"],
    "travel":        ["travel", "flight", "flights", "hotel", "hotels", "airbnb", "airline", "airfare"],
    "shopping":      ["shopping", "retail", "amazon", "target", "walmart"],
    "subscriptions": ["subscription", "subscriptions", "membership", "netflix", "spotify", "hulu", "disney"],
    "utilities":     ["utility", "utilities", "electric", "water bill", "internet", "cable"],
    "healthcare":    ["healthcare", "medical", "pharmacy", "doctor", "dental"],
    "entertainment": ["entertainment", "movie", "movies", "concert", "gym", "fitness"],
    "insurance":     ["insurance"],
    "transfers":     ["transfer", "transfers", "zelle", "venmo"],
    "fees":          ["fee", "fees", "penalty"],
}

# Display labels requested by spec (Groceries / Dining / Gas …)
_CATEGORY_DISPLAY: dict[str, str] = {
    "groceries": "Groceries",
    "restaurants": "Dining",
    "gas": "Gas",
    "travel": "Travel",
    "shopping": "Shopping",
    "subscriptions": "Subscriptions",
    "utilities": "Utilities",
    "healthcare": "Healthcare",
    "entertainment": "Entertainment",
    "insurance": "Insurance",
    "transfers": "Transfers",
    "fees": "Fees",
}


def normalize_category(value: str | None) -> str | None:
    """Map a fuzzy category string to a canonical TransactionCategory value."""
    if not value:
        return None
    text = value.strip().lower()
    if not text:
        return None
    for canonical, aliases in _CATEGORIES.items():
        if any(alias in text for alias in aliases):
            return canonical
    return None


def category_display_name(canonical: str | None) -> str | None:
    if not canonical:
        return None
    return _CATEGORY_DISPLAY.get(canonical.lower(), canonical.title())


# ── Account-name normalization ────────────────────────────────────────────────
# Account/card names are data-driven (set at upload via account_product), so we
# can't enumerate them. Instead we produce a clean search token that the SQL
# layer matches against accounts.account_name with LIKE. We strip generic filler
# words ("card", "account") and resolve a few well-known aliases.

_ACCOUNT_FILLER = {
    "card", "cards", "account", "acct", "the", "my", "credit", "statement",
    "visa", "mastercard", "amex",
}

# Known aliases → the canonical token most likely to appear in account_name.
_ACCOUNT_ALIASES: dict[str, str] = {
    "amazon prime": "prime",
    "amazon": "prime",              # the Amazon card is the Prime Visa
    "prime visa": "prime",
    "blue cash everyday": "blue cash",
    "blue cash preferred": "blue cash",
    "blue cash": "blue cash",
    "sapphire preferred": "sapphire",
    "sapphire reserve": "sapphire",
    "sapphire": "sapphire",
    "freedom unlimited": "freedom",
    "freedom flex": "freedom",
    "amex gold": "gold",
    "gold card": "gold",
    "roth ira": "roth",
    "roth": "roth",
    "traditional ira": "ira",
    "down payment": "down payment",
    "down payment savings": "down payment",
    "hysa": "savings",
    "high yield savings": "savings",
    "high yield": "savings",
    "marcus savings": "savings",
    "529": "529",
    "college savings": "529",
    "etrade ira": "ira",
    "morgan stanley ira": "ira",
    "investment account": "brokerage",
}


def normalize_account(value: str | None) -> str | None:
    """Return a lowercased search token for an account/card name, or None.

    The token is matched with LIKE against accounts.account_name, so partial
    names work ("prime" matches "Prime Visa").
    """
    if not value:
        return None
    text = value.strip().lower()
    if not text:
        return None

    # Resolve a known alias first (longest match wins).
    for alias in sorted(_ACCOUNT_ALIASES, key=len, reverse=True):
        if alias in text:
            return _ACCOUNT_ALIASES[alias]

    # Otherwise strip filler words and keep the distinctive remainder.
    tokens = [t for t in re.split(r"[\s_-]+", text) if t and t not in _ACCOUNT_FILLER]
    if not tokens:
        return None
    return " ".join(tokens)


# ── Time-range normalization ──────────────────────────────────────────────────

_MONTHS: dict[str, int] = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def normalize_timerange(
    value: str | None,
    today: date | None = None,
) -> tuple[date | None, date | None, str]:
    """Resolve a time-range token / phrase to (start_date, end_date, label).

    Handles: last_month, this_month, last_year, this_year, ytd,
    "last N months/weeks/days", "Q1 2025", "January", "Jan 2025", bare years.
    Returns (None, None, "") when nothing parses.
    """
    if not value:
        return None, None, ""
    today = today or date.today()
    q = value.strip().lower().replace("_", " ")

    if re.search(r"\b(last|previous|prior)\s+month\b", q):
        first = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        last = today.replace(day=1) - timedelta(days=1)
        return first, last, "last month"

    if re.search(r"\b(this|current)\s+month\b", q):
        first = today.replace(day=1)
        last = today.replace(day=monthrange(today.year, today.month)[1])
        return first, last, "this month"

    if re.search(r"\b(this|current)\s+year\b|\byt\s?d\b|\byear to date\b", q):
        return today.replace(month=1, day=1), today, f"{today.year} YTD"

    if re.search(r"\blast\s+year\b", q):
        y = today.year - 1
        return date(y, 1, 1), date(y, 12, 31), str(y)

    m = re.search(r"\b(?:last|past)\s+(\d+)\s+months?\b", q)
    if m:
        n = int(m.group(1))
        # Start at the first day of the month n months ago.
        month_idx = (today.year * 12 + today.month - 1) - n
        start = date(month_idx // 12, month_idx % 12 + 1, 1)
        return start, today, f"last {n} months"

    m = re.search(r"\b(?:last|past)\s+(\d+)\s+weeks?\b", q)
    if m:
        n = int(m.group(1))
        return today - timedelta(weeks=n), today, f"last {n} weeks"

    m = re.search(r"\b(?:last|past)\s+(\d+)\s+days?\b", q)
    if m:
        n = int(m.group(1))
        return today - timedelta(days=n), today, f"last {n} days"

    m = re.search(r"\bq([1-4])\s*(\d{4})?\b", q)
    if m:
        qn = int(m.group(1))
        year = int(m.group(2)) if m.group(2) else today.year
        ms, me = (qn - 1) * 3 + 1, qn * 3
        return date(year, ms, 1), date(year, me, monthrange(year, me)[1]), f"Q{qn} {year}"

    for name, num in _MONTHS.items():
        m = re.search(rf"\b{name}\b(?:\s+(\d{{4}}))?", q)
        if m:
            year = int(m.group(1)) if m.group(1) else today.year
            last_day = monthrange(year, num)[1]
            return date(year, num, 1), date(year, num, last_day), f"{name.capitalize()} {year}"

    m = re.search(r"\b(20\d{2})\b", q)
    if m:
        year = int(m.group(1))
        return date(year, 1, 1), date(year, 12, 31), str(year)

    return None, None, ""
