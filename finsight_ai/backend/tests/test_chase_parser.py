"""
Tests for the Chase credit-card text-transaction extractor — regression test
for a real bug where sub-dollar amounts printed without a leading zero
("-.86", ".01" instead of "-0.86", "0.01") were silently dropped because the
amount regex required at least one digit before the decimal point.
"""

from __future__ import annotations

from decimal import Decimal

from app.parsers.base import ParsedDocument, ParsedPage
from app.parsers.chase.parser import ChaseParser


def _doc(*page_texts: str) -> ParsedDocument:
    pages = [
        ParsedPage(page_number=i + 1, raw_text=text, tables=[])
        for i, text in enumerate(page_texts)
    ]
    return ParsedDocument(file_path="chase.pdf", page_count=len(pages), pages=pages, metadata={})


_SUMMARY_PAGE = """\
CHASE FREEDOM UNLIMITED
Minimum Payment Due $0.00
Payment Due Date 03/26/26
"""

# Real text (via pdfplumber) from a Chase Freedom Unlimited statement whose
# only activity that month was a one-cent DoorDash charge and its refund —
# both printed without a leading zero.
_ACTIVITY_PAGE = """\
ACCOUNT ACTIVITY
Date of
Transaction Merchant Name or Transaction Description $ Amount
PAYMENTS AND OTHER CREDITS
02/09 Payment Thank You-Mobile -.01
PURCHASE
02/01 DD *DOORDASHDASHPASS DOORDASH.COM CA .01
2026 Totals Year-to-Date
Total fees charged in 2026 $0.00
"""

_SINGLE_CHARGE_PAGE = """\
ACCOUNT ACTIVITY
Date of
Transaction Merchant Name or Transaction Description $ Amount
PURCHASE
04/12 DD *DOORDASHDASHPASS SAN FRANCISCO CA -.86
"""

_CHECKING_APRIL_PAGE = """\
March 14, 2026throughApril 14, 2026
Chase Total Checking
CHECKING SUMMARY
TRANSACTION DETAIL
DATE DESCRIPTION AMOUNT BALANCE
03/16 Zelle Payment To Regina (Cleans) 28432574050 -90.00 26,301.55
03/31 JPMorgan Chase B Payroll Dd PPD ID: 1134994650 3,706.92 16,432.69
"""

_SAPPHIRE_PAGE_WITH_PHONE_FRAGMENT = """\
June 3, 2026throughJuly 2, 2026
CHASE SAPPHIRE PREFERRED
Minimum Payment Due $0.00
ACCOUNT ACTIVITY
Date of
Transaction Merchant Name or Transaction Description $ Amount
PAYMENTS AND OTHER CREDITS
06/03 Payment Thank You-Mobile -747.34
PURCHASE
06/02 SUNOCO PARAMUS PARAMUS NJ 56.28
07/02 D36179267 180-072-2008 FL 26.76
"""


class TestSubDollarAmounts:
    async def test_extracts_leading_zero_omitted_amounts(self):
        parser = ChaseParser()
        stmt = await parser.extract(_doc(_SUMMARY_PAGE, _ACTIVITY_PAGE))

        assert len(stmt.transactions) == 2
        by_desc = {t.description: t for t in stmt.transactions}

        payment = next(t for d, t in by_desc.items() if "Payment Thank You" in d)
        assert payment.amount == Decimal("0.01")

        purchase = next(t for d, t in by_desc.items() if "DOORDASH" in d)
        assert purchase.amount == Decimal("-0.01")

    async def test_single_sub_dollar_purchase(self):
        parser = ChaseParser()
        stmt = await parser.extract(_doc(_SUMMARY_PAGE, _SINGLE_CHARGE_PAGE))

        assert len(stmt.transactions) == 1
        # Raw statement prints this specific line as "-.86" under PURCHASE (a
        # credit against a purchase); _canonical_amount's credit-card sign
        # flip (unchanged by this fix) correctly turns that into +0.86.
        assert stmt.transactions[0].amount == Decimal("0.86")

    async def test_normal_amounts_still_parse(self):
        """Regression guard: the \\d* relaxation must not break ordinary amounts."""
        parser = ChaseParser()
        page = (
            "ACCOUNT ACTIVITY\n"
            "PURCHASE\n"
            "03/14 WHOLE FOODS MARKET NJ 1,234.56\n"
            "03/15 AMAZON.COM NJ 42.99\n"
        )
        stmt = await parser.extract(_doc(_SUMMARY_PAGE, page))

        amounts = {t.amount for t in stmt.transactions}
        assert Decimal("-1234.56") in amounts
        assert Decimal("-42.99") in amounts


class TestChaseCheckingStatements:
    async def test_april_checking_is_not_misclassified_as_apr_credit_card(self):
        parser = ChaseParser()
        stmt = await parser.extract(_doc(_CHECKING_APRIL_PAGE))

        assert stmt.account_type == "checking"
        assert stmt.statement_type == "bank"
        assert len(stmt.transactions) == 2
        by_desc = {t.description: t for t in stmt.transactions}
        assert by_desc["Zelle Payment To Regina (Cleans) 28432574050"].amount == Decimal("-90.00")
        payroll = by_desc["JPMorgan Chase B Payroll Dd PPD ID: 1134994650"]
        assert payroll.amount == Decimal("3706.92")


class TestChaseStatementPeriodDates:
    async def test_credit_card_dates_use_statement_period_not_phone_number_fragments(self):
        parser = ChaseParser()
        stmt = await parser.extract(_doc(_SAPPHIRE_PAGE_WITH_PHONE_FRAGMENT))

        assert stmt.account_type == "credit_card"
        assert {t.transaction_date.year for t in stmt.transactions} == {2026}
        by_desc = {t.description: t for t in stmt.transactions}
        assert by_desc["Payment Thank You-Mobile"].amount == Decimal("747.34")
        assert by_desc["D36179267 180-072-2008 FL"].transaction_date.year == 2026
