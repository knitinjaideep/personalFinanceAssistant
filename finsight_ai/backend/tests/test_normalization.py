"""Unit tests for entity normalization helpers."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.normalization import (
    category_display_name,
    institution_display_name,
    normalize_category,
    normalize_institution,
    normalize_timerange,
)


@pytest.mark.parametrize(
    "raw,expected_slug,expected_display",
    [
        ("amex", "amex", "American Express"),
        ("American Express", "amex", "American Express"),
        ("ms", "morgan_stanley", "Morgan Stanley"),
        ("morgan", "morgan_stanley", "Morgan Stanley"),
        ("Morgan Stanley", "morgan_stanley", "Morgan Stanley"),
        ("morgan stanly", "morgan_stanley", "Morgan Stanley"),  # typo
        ("chase", "chase", "Chase"),
        ("etrade", "etrade", "E*TRADE"),
        ("e-trade", "etrade", "E*TRADE"),
        ("discover", "discover", "Discover"),
        ("unknown bank", None, None),
    ],
)
def test_normalize_institution(raw, expected_slug, expected_display):
    slug, display = normalize_institution(raw)
    assert slug == expected_slug
    assert display == expected_display


def test_institution_ms_is_whole_word_only():
    # "ms" must not match inside "transactions"
    slug, _ = normalize_institution("show me my transactions")
    assert slug is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("grocery", "groceries"),
        ("groceries", "groceries"),
        ("supermarket", "groceries"),
        ("restaurant", "restaurants"),
        ("dining", "restaurants"),
        ("food delivery", "restaurants"),
        ("gas", "gas"),
        ("fuel", "gas"),
        ("nonsense", None),
    ],
)
def test_normalize_category(raw, expected):
    assert normalize_category(raw) == expected


def test_category_display_names():
    assert category_display_name("groceries") == "Groceries"
    assert category_display_name("restaurants") == "Dining"
    assert category_display_name("gas") == "Gas"


class TestTimeRange:
    TODAY = date(2026, 6, 2)

    def test_last_month(self):
        start, end, label = normalize_timerange("last_month", today=self.TODAY)
        assert start == date(2026, 5, 1)
        assert end == date(2026, 5, 31)
        assert label == "last month"

    def test_this_month(self):
        start, end, label = normalize_timerange("this month", today=self.TODAY)
        assert start == date(2026, 6, 1)
        assert end == date(2026, 6, 30)

    def test_january(self):
        start, end, label = normalize_timerange("January", today=self.TODAY)
        assert start == date(2026, 1, 1)
        assert end == date(2026, 1, 31)

    def test_jan_2025(self):
        start, end, _ = normalize_timerange("Jan 2025", today=self.TODAY)
        assert start == date(2025, 1, 1)
        assert end == date(2025, 1, 31)

    def test_q1_2025(self):
        start, end, label = normalize_timerange("Q1 2025", today=self.TODAY)
        assert start == date(2025, 1, 1)
        assert end == date(2025, 3, 31)
        assert label == "Q1 2025"

    def test_last_3_months(self):
        start, end, label = normalize_timerange("last_3_months", today=self.TODAY)
        assert start == date(2026, 3, 1)
        assert end == self.TODAY
        assert label == "last 3 months"

    def test_empty(self):
        assert normalize_timerange(None) == (None, None, "")
        assert normalize_timerange("whatever") == (None, None, "")


# ── Account normalization ─────────────────────────────────────────────────────

def test_normalize_account_aliases_and_filler():
    from app.services.normalization import normalize_account
    assert normalize_account("amazon prime card") == "prime"
    assert normalize_account("amazon") == "prime"
    assert normalize_account("prime visa") == "prime"
    assert normalize_account("blue cash") == "blue cash"
    assert normalize_account("sapphire preferred") == "sapphire"
    assert normalize_account("my chase card") == "chase"
    assert normalize_account("the account") is None
    assert normalize_account(None) is None
    assert normalize_account("") is None
