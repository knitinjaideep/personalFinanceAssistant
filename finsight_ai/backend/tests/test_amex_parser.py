"""
Tests for the Amex text-based transaction extractor — the root-cause fix for the
empty transactions table. Amex statements lay transactions out as plain text
lines (not ruled tables), so the parser must read those lines.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.parsers.amex.parser import AmexParser
from app.parsers.base import ParsedDocument, ParsedPage
from app.parsers.categorize import categorize


def _doc(text: str) -> ParsedDocument:
    return ParsedDocument(
        file_path="amex.pdf", page_count=1,
        pages=[ParsedPage(page_number=1, raw_text=text, tables=[])],
        metadata={},
    )


_SAMPLE = """\
Blue Cash Everyday from American Express
Closing Date 01/09/26
Account Ending 7-91002
New Balance $78.47
12/22/25* MOBILE PAYMENT - THANK YOU -$6.85
12/23/25 JACK'S SUPER FOODTOWN OF BLOOMFIELD NJ $13.21
01/03/26 PATEL BROTHERS EDISON NJ $53.66
01/06/26 SHELL OIL 12345 FL $40.10
01/07/26 NETFLIX.COM $15.49
Purchases 04/28/2023 17.49% (v) $0.00
"""


@pytest.mark.asyncio
async def test_amex_extracts_text_transactions():
    parser = AmexParser()
    stmt = await parser.extract(_doc(_SAMPLE))

    # 5 real transactions; the APR "Purchases ... %" line must be excluded.
    assert len(stmt.transactions) == 5
    descs = [t.description for t in stmt.transactions]
    assert any("FOODTOWN" in d for d in descs)
    assert not any("17.49%" in d for d in descs)


@pytest.mark.asyncio
async def test_amex_signs_and_categories():
    parser = AmexParser()
    stmt = await parser.extract(_doc(_SAMPLE))
    by_desc = {t.description: t for t in stmt.transactions}

    # Charges are negative (outflow); the payment is positive (credit).
    foodtown = next(t for d, t in by_desc.items() if "FOODTOWN" in d)
    assert foodtown.amount == Decimal("-13.21")
    assert foodtown.category == "groceries"

    payment = next(t for d, t in by_desc.items() if "MOBILE PAYMENT" in d)
    assert payment.amount == Decimal("-6.85") or payment.amount == Decimal("6.85")
    assert payment.transaction_type == "payment"

    shell = next(t for d, t in by_desc.items() if "SHELL" in d)
    assert shell.category == "gas"


@pytest.mark.asyncio
async def test_amex_closing_date_becomes_period_end():
    parser = AmexParser()
    stmt = await parser.extract(_doc(_SAMPLE))
    assert stmt.period_end is not None
    assert stmt.period_end.year == 2026 and stmt.period_end.month == 1


@pytest.mark.asyncio
async def test_amex_empty_when_no_transaction_lines():
    parser = AmexParser()
    stmt = await parser.extract(_doc("Blue Cash Everyday from American Express\nNew Balance $0.00\n"))
    assert stmt.transactions == []


def test_shared_categorizer_groceries():
    assert categorize("PATEL BROTHERS EDISON NJ") == "groceries"
    assert categorize("JACK'S SUPER FOODTOWN") == "groceries"
    assert categorize("SHELL OIL 12345") == "gas"
    assert categorize("NETFLIX.COM") == "subscriptions"
    assert categorize("SOME RANDOM MERCHANT") == "other"


def test_payments_are_not_categorized_as_spending():
    # Regression: "Payment Thank You-Mobile" used to match "mobil" → gas.
    assert categorize("Payment Thank You-Mobile") == "other"
    assert categorize("AUTOPAY PAYMENT RECEIVED - THANK YOU") == "other"
    assert categorize("Online Payment Thank You") == "other"
    # But a real mobile-carrier bill is still a utility, and Exxon is still gas.
    assert categorize("T-Mobile monthly bill") == "utilities"
    assert categorize("EXXONMOBIL 4521") == "gas"


# ── Morgan Stanley advisory-fee text extraction ──────────────────────────────

@pytest.mark.asyncio
async def test_morgan_stanley_extracts_advisory_fee_from_text():
    from app.parsers.morgan_stanley.parser import MorganStanleyParser

    text = (
        "Morgan Stanley Account Statement\n"
        "Statement Period: 05/01/25 to 05/31/25\n"
        "5/7 Service Fee ADV FEE 05/01-05/31 (166.15)\n"
        "Total Account Value $123,456.00\n"
    )
    doc = ParsedDocument(
        file_path="ms.pdf", page_count=1,
        pages=[ParsedPage(page_number=1, raw_text=text, tables=[])],
        metadata={},
    )
    stmt = await MorganStanleyParser().extract(doc)
    assert len(stmt.fees) == 1
    assert stmt.fees[0].amount == Decimal("166.15")
    assert stmt.fees[0].fee_category == "advisory_fee"


@pytest.mark.asyncio
async def test_morgan_stanley_ignores_fee_disclosure_text():
    from app.parsers.morgan_stanley.parser import MorganStanleyParser

    text = (
        "Morgan Stanley Account Statement\n"
        "You may be charged a fee of up to $50.00 for wire transfers.\n"
    )
    doc = ParsedDocument(
        file_path="ms.pdf", page_count=1,
        pages=[ParsedPage(page_number=1, raw_text=text, tables=[])],
        metadata={},
    )
    stmt = await MorganStanleyParser().extract(doc)
    assert stmt.fees == []


def test_account_name_from_product():
    from app.services.ingestion import _account_name_from_product
    assert _account_name_from_product("Chase — Prime Visa") == "Prime Visa"
    assert _account_name_from_product("American Express — Blue Cash") == "Blue Cash"
    assert _account_name_from_product("Chase - Freedom Unlimited") == "Freedom Unlimited"
    assert _account_name_from_product("Sapphire Preferred") == "Sapphire Preferred"
    assert _account_name_from_product(None) is None
    assert _account_name_from_product("") is None


# ── Chase canonical sign convention ───────────────────────────────────────────

def test_chase_canonical_amount_flips_credit_card():
    from decimal import Decimal
    from app.parsers.chase.parser import _canonical_amount
    # Credit card: statement-positive purchase → stored negative (money out).
    assert _canonical_amount(Decimal("94.22"), is_credit=True) == Decimal("-94.22")
    # Credit card: statement-negative payment → stored positive (money in).
    assert _canonical_amount(Decimal("-57.75"), is_credit=True) == Decimal("57.75")
    # Checking/bank rows are left as-is (already canonical).
    assert _canonical_amount(Decimal("-30.00"), is_credit=False) == Decimal("-30.00")
    assert _canonical_amount(Decimal("1500.00"), is_credit=False) == Decimal("1500.00")
