"""
Tests for the Morgan Stanley text-based transaction/holdings extractor — the
root-cause fix for zero transactions and zero holdings ever being extracted
from Morgan Stanley statements. Morgan Stanley lays out "CASH FLOW ACTIVITY BY
DATE" and "HOLDINGS" as plain text (no ruled tables), so the parser must read
those lines. Fixture text below is copied verbatim from real statements
(via pdfplumber, x_tolerance=3/y_tolerance=3 — the same settings production
parsing uses).
"""

from __future__ import annotations

from decimal import Decimal

from app.parsers.base import ParsedDocument, ParsedPage
from app.parsers.morgan_stanley.parser import MorganStanleyParser


def _doc(*page_texts: str) -> ParsedDocument:
    pages = [
        ParsedPage(page_number=i + 1, raw_text=text, tables=[])
        for i, text in enumerate(page_texts)
    ]
    return ParsedDocument(file_path="ms.pdf", page_count=len(pages), pages=pages, metadata={})


# A simple single-holding account (real text from a House Downpayment statement).
_HOLDINGS_PAGE = """\
CLIENT STATEMENT For the Period June 1-30, 2026 Page 6 of 8
Active Assets Account NITIN KOTCHERLAKOTA &
Account Detail 427-075198-701 PAVANI L AVVA JT TEN
HOLDINGS
Current
Security Description Quantity Unit Cost Share Price Total Cost Market Value Est Ann Income Yield %
MSILF MMKT WEALTH CLASS (MWMXX) 36,291.500 N/A $1.0000 N/A $36,291.50 $1,365.65 3.76
Enrolled In Dividend Reinvestment; Capital Gains Reinvest; Asset Class: Cash
Percentage Unrealized Current
of Holdings Total Cost Market Value Gain/(Loss) Est Ann Income Yield %
MUTUAL FUNDS 100.00% — $36,291.50 N/A $1,365.65 3.76%
"""

_ACTIVITY_PAGE = """\
CLIENT STATEMENT For the Period June 1-30, 2026 Page 7 of 8
ACTIVITY
CASH FLOW ACTIVITY BY DATE
Activity Settlement
Date Date Activity Type Description Comments Quantity Price Credits/(Debits)
6/26 Cash Transfer FUNDS TRANSFERRED Confirmation - #DXOGL01E4 $5,000.00
From 427-XXX805
6/26 Cash Transfer FUNDS TRANSFERRED Confirmation - #D5WKSMRFV 1,000.00
From 427-XXX587
6/26 6/26 Bought MSILF MMKT WEALTH CLASS UNSOLICITED TRADE 6,000.000 1.0000 (6,000.00)
6/30 Dividend MSILF MMKT WEALTH CLASS 95.09
6/30 Dividend Reinvestment MSILF MMKT WEALTH CLASS REINVESTMENT 95.090 1.0000 (95.09)
NET CREDITS/(DEBITS) $0.00
"""

# A more complex multi-security account (real text from Joint Investments) —
# mix of $-prefixed and bare numbers, a "Sold" trade, a fee, and a "Total"
# rollup line that must NOT be captured as its own holding.
_STOCK_HOLDINGS_PAGE = """\
HOLDINGS
Security Description Trade Date Quantity Unit Cost Share Price Total Cost Market Value Gain/(Loss) Est Ann Income Yield %
3M CO (MMM) 7/16/24 4.000 $103.310 $153.160 $413.24 $612.64 $199.40 LT $11.68 1.91
Next Dividend Payable 03/2026; Asset Class: Equities
A O SMITH CORP (AOS) 3/13/25 1.000 65.450 73.490 65.45 73.49 8.04ST 1.44 1.96
Next Dividend Payable 02/17/26; Asset Class: Equities
BLACKSTONE INC (BX) 4/14/25 3.000 128.867 142.420 386.60 427.26 40.66ST R
10/31/25 1.000 146.010 142.420 146.01 142.42 (3.59)ST R
Total 4.000 532.61 569.68 37.07 ST 13.26 2.33
Next Dividend Payable 02/2026; Asset Class: Equities
"""

_STOCK_ACTIVITY_PAGE = """\
ACTIVITY
CASH FLOW ACTIVITY BY DATE
Activity Settlement
Date Date Activity Type Description Comments Quantity Price Credits/(Debits)
1/2 Qualified Dividend AUTOMATIC DATA PROCESSING INC $3.85
1/2 Qualified Dividend HP INC COM 3.60
1/8 Service Fee ADV FEE 01/01-01/31 (211.68)
1/26 1/27 Sold STRYKER CORP ACTED AS AGENT 1.770 356.9800 631.85
UNSOLICITED TRADE
VSP BY DATE 20241018
PRC 369.56160QTY 1
1/26 1/27 Bought PAYCHEX INC ACTED AS AGENT 6.000 106.1900 (637.14)
UNSOLICITED TRADE
NET CREDITS/(DEBITS) $33.58
"""


class TestTransactions:
    async def test_extracts_all_activity_lines(self):
        parser = MorganStanleyParser()
        stmt = await parser.extract(_doc(_HOLDINGS_PAGE, _ACTIVITY_PAGE))

        assert len(stmt.transactions) == 5
        descs = [t.description for t in stmt.transactions]
        assert any("Cash Transfer" in d for d in descs)
        assert any("Bought" in d for d in descs)
        assert any(d.startswith("Dividend Reinvestment") for d in descs)
        # A plain "Dividend" and "Dividend Reinvestment" line must not collide.
        assert sum(1 for d in descs if d == "Dividend MSILF MMKT WEALTH CLASS") == 1

    async def test_signs_and_amounts(self):
        parser = MorganStanleyParser()
        stmt = await parser.extract(_doc(_ACTIVITY_PAGE))

        by_desc = {t.description: t for t in stmt.transactions}
        bought = next(t for d, t in by_desc.items() if d.startswith("Bought"))
        assert bought.amount == Decimal("-6000.00")
        assert bought.transaction_type == "trade_buy"

        transfer = next(t for d, t in by_desc.items() if "DXOGL01E4" in d)
        assert transfer.amount == Decimal("5000.00")

        # Net of all 5 lines is $0.00, matching the statement's own
        # "NET CREDITS/(DEBITS) $0.00" total — a strong end-to-end sanity check.
        assert sum(t.amount for t in stmt.transactions) == Decimal("0.00")

    async def test_multiline_trade_comments_dont_leak_into_next_row(self):
        parser = MorganStanleyParser()
        stmt = await parser.extract(_doc(_STOCK_ACTIVITY_PAGE))

        descs = [t.description for t in stmt.transactions]
        assert any(d.startswith("Sold STRYKER") for d in descs)
        assert any(d.startswith("Bought PAYCHEX") for d in descs)
        # Continuation lines ("UNSOLICITED TRADE", "VSP BY DATE...") aren't
        # date-prefixed and must not be picked up as their own transactions.
        assert not any(d == "UNSOLICITED TRADE" for d in descs)
        assert not any("VSP BY DATE" in d for d in descs)
        assert len(stmt.transactions) == 5  # 2 dividends, 1 fee-looking activity, sold, bought


class TestHoldings:
    async def test_extracts_single_mmf_holding(self):
        parser = MorganStanleyParser()
        stmt = await parser.extract(_doc(_HOLDINGS_PAGE))

        assert len(stmt.holdings) == 1
        h = stmt.holdings[0]
        assert h.symbol == "MWMXX"
        assert h.description == "MSILF MMKT WEALTH CLASS"
        assert h.market_value == Decimal("36291.50")
        assert h.quantity == Decimal("36291.500")

    async def test_extracts_stock_holdings_and_skips_total_rollup(self):
        parser = MorganStanleyParser()
        stmt = await parser.extract(_doc(_STOCK_HOLDINGS_PAGE))

        by_symbol: dict[str, list] = {}
        for h in stmt.holdings:
            by_symbol.setdefault(h.symbol, []).append(h)

        assert by_symbol["MMM"][0].market_value == Decimal("612.64")
        assert by_symbol["AOS"][0].market_value == Decimal("73.49")
        # BX has TWO lots printed across two lines: the first carries the
        # "(BX)" ticker, the second is a bare continuation line (just the
        # trade date + numeric columns, no ticker repeated) that must still
        # be attributed to BX — this was the root cause of a real ~35% portfolio
        # under-count on multi-lot statements. The "Total ..." rollup line that
        # follows must never appear as its own row.
        assert len(by_symbol["BX"]) == 2
        assert {h.market_value for h in by_symbol["BX"]} == {Decimal("427.26"), Decimal("142.42")}
        assert not any(h.description.lower().startswith("total") for h in stmt.holdings)
        assert len(stmt.holdings) == 4

    async def test_ticker_disambiguated_from_earlier_parenthetical(self):
        """"COMCAST CORP (NEW) CLASS A (CMCSA) ..." — the real ticker is the
        LAST parenthetical group, not "(NEW)" (a reissue/class marker)."""
        parser = MorganStanleyParser()
        line = (
            "COMCAST CORP (NEW) CLASS A (CMCSA) 6/17/26 5.000 22.690 23.960 "
            "113.45 119.80 6.35ST 6.60 5.51"
        )
        stmt = await parser.extract(_doc(f"HOLDINGS\n{line}\n"))

        assert len(stmt.holdings) == 1
        h = stmt.holdings[0]
        assert h.symbol == "CMCSA"
        assert h.description == "COMCAST CORP (NEW) CLASS A"
        assert h.market_value == Decimal("119.80")
