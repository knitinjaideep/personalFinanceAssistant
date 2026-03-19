"""
Discover statement parser.

Handles Discover credit card statements.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from dateutil import parser as dateparser

from app.domain.entities import (
    ExtractedBalance,
    ExtractedTransaction,
    ParsedStatement,
)
from app.parsers.base import InstitutionParser, ParsedDocument

logger = structlog.get_logger(__name__)

_DISCOVER_RE = re.compile(
    r"discover|discover\.com|discover\s+(?:card|bank|financial)",
    re.IGNORECASE,
)
_PERIOD_RE = re.compile(
    r"(?:statement\s+(?:closing|period)|billing\s+period)\s*[:\-]?\s*(.+?)\s+(?:to|through|-)\s+(.+?)(?:\n|$)",
    re.IGNORECASE,
)


class DiscoverParser(InstitutionParser):

    @property
    def institution_type(self) -> str:
        return "discover"

    @property
    def institution_name(self) -> str:
        return "Discover"

    def can_handle(self, text: str, metadata: dict[str, Any] | None = None) -> float:
        matches = _DISCOVER_RE.findall(text[:3000])
        if len(matches) >= 2:
            return 0.95
        if len(matches) == 1:
            return 0.70
        return 0.0

    async def extract(self, document: ParsedDocument) -> ParsedStatement:
        first_pages = "\n".join(p.raw_text for p in document.pages[:3])
        full_text = document.full_text

        period_start, period_end = None, None
        m = _PERIOD_RE.search(first_pages)
        if m:
            try:
                period_start = dateparser.parse(m.group(1).strip()).date()
                period_end = dateparser.parse(m.group(2).strip()).date()
            except (ValueError, TypeError):
                pass

        acct_match = re.search(r"(?:account\s+(?:ending|number))\s*[:\-]?\s*(\d{4})", first_pages, re.IGNORECASE)
        account_masked = f"****{acct_match.group(1)}" if acct_match else ""

        transactions = _extract_transactions(document)
        balances = _extract_balances(first_pages, period_end)

        details = {}
        for field_name, pattern in [
            ("cashback_earned", r"cashback\s+(?:earned|bonus)\s*[:\-]?\s*\$?([\d,]+\.\d{2})"),
            ("cashback_balance", r"cashback\s+balance\s*[:\-]?\s*\$?([\d,]+\.\d{2})"),
            ("credit_limit", r"credit\s+limit\s*[:\-]?\s*\$?([\d,]+)"),
            ("minimum_payment", r"minimum\s+payment\s*[:\-]?\s*\$?([\d,]+\.\d{2})"),
            ("apr_purchase", r"(?:purchase\s+)?apr\s*[:\-]?\s*([\d.]+)%"),
        ]:
            fm = re.search(pattern, full_text, re.IGNORECASE)
            if fm:
                details[field_name] = fm.group(1).replace(",", "")

        return ParsedStatement(
            institution_type="discover",
            account_type="credit_card",
            statement_type="credit_card",
            account_number_masked=account_masked,
            period_start=period_start,
            period_end=period_end,
            confidence=0.8 if transactions else 0.5,
            transactions=transactions,
            fees=[],
            holdings=[],
            balances=balances,
            institution_details=details,
            page_count=document.page_count,
        )


def _extract_transactions(doc: ParsedDocument) -> list[ExtractedTransaction]:
    transactions = []
    for page in doc.pages:
        for table in page.tables:
            if not table.header_row:
                continue
            header_lower = [h.lower() for h in table.header_row]
            if not any("date" in h for h in header_lower):
                continue

            date_col = next((i for i, h in enumerate(header_lower) if "date" in h), 0)
            desc_col = next((i for i, h in enumerate(header_lower) if "description" in h), 1)
            amt_col = next((i for i, h in enumerate(header_lower) if "amount" in h), len(header_lower) - 1)

            for row in table.rows:
                if len(row) <= max(date_col, amt_col):
                    continue
                try:
                    txn_date = dateparser.parse(str(row[date_col])).date()
                    raw = str(row[amt_col]).replace(",", "").replace("$", "").strip()
                    if not raw:
                        continue
                    amount = Decimal(raw.replace("(", "-").replace(")", ""))
                    desc = str(row[desc_col]).strip() if desc_col < len(row) else ""

                    txn_type = "payment" if "payment" in desc.lower() else "purchase"
                    transactions.append(ExtractedTransaction(
                        transaction_date=txn_date,
                        description=desc,
                        merchant_name=desc[:80].strip(),
                        amount=amount,
                        transaction_type=txn_type,
                        category=_categorize(desc),
                        source_page=page.page_number,
                    ))
                except (ValueError, TypeError, InvalidOperation):
                    continue
    return transactions


def _extract_balances(text: str, period_end: date | None) -> list[ExtractedBalance]:
    balances = []
    for pat in [
        r"(?:new|total|closing)\s+balance\s*[:\-]?\s*\$?([\d,]+\.\d{2})",
    ]:
        for m in re.finditer(pat, text, re.IGNORECASE):
            try:
                val = Decimal(m.group(1).replace(",", ""))
                balances.append(ExtractedBalance(
                    snapshot_date=period_end or date.today(),
                    total_value=val,
                ))
            except InvalidOperation:
                continue
    return balances


def _categorize(desc: str) -> str:
    d = desc.lower()
    categories = {
        "restaurants": ["restaurant", "cafe", "starbucks", "mcdonald"],
        "travel": ["airline", "hotel", "uber", "lyft"],
        "shopping": ["amazon", "target", "walmart"],
        "groceries": ["grocery", "whole foods", "trader joe"],
        "gas": ["shell", "chevron", "exxon", "gas"],
        "subscriptions": ["netflix", "spotify", "hulu"],
    }
    for cat, keywords in categories.items():
        if any(kw in d for kw in keywords):
            return cat
    return "other"
