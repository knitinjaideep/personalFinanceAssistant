"""
Chase statement parser.

Handles checking account and credit card statements.
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
    ExtractedFee,
    ExtractedTransaction,
    ParsedStatement,
)
from app.parsers.base import InstitutionParser, ParsedDocument

logger = structlog.get_logger(__name__)

_CHASE_RE = re.compile(
    r"chase|jpmorgan\s+chase|chase\.com|JPMorgan\s+Chase\s+Bank",
    re.IGNORECASE,
)
_PERIOD_RE = re.compile(
    r"(?:statement\s+period|billing\s+period)\s*[:\-]?\s*(.+?)\s+(?:to|through|-)\s+(.+?)(?:\n|$)",
    re.IGNORECASE,
)
_ACCOUNT_RE = re.compile(r"(?:account\s+(?:number|ending)\s*[:\-]?\s*)(\d{4})", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"\$?([\d,]+\.\d{2})")

_CATEGORY_KEYWORDS = {
    "groceries": ["grocery", "market", "whole foods", "trader joe", "safeway", "kroger"],
    "restaurants": ["restaurant", "cafe", "pizza", "burger", "starbucks", "mcdonald", "chipotle"],
    "gas": ["gas", "shell", "chevron", "exxon", "bp "],
    "travel": ["airline", "hotel", "airbnb", "uber", "lyft", "delta", "united"],
    "shopping": ["amazon", "target", "walmart", "costco", "best buy"],
    "subscriptions": ["netflix", "spotify", "hulu", "apple.com", "google *"],
    "utilities": ["electric", "water", "gas co", "internet", "comcast", "verizon"],
    "healthcare": ["pharmacy", "hospital", "medical", "dental", "cvs", "walgreens"],
}


class ChaseParser(InstitutionParser):

    @property
    def institution_type(self) -> str:
        return "chase"

    @property
    def institution_name(self) -> str:
        return "Chase"

    def can_handle(self, text: str, metadata: dict[str, Any] | None = None) -> float:
        matches = _CHASE_RE.findall(text[:3000])
        if len(matches) >= 2:
            return 0.95
        if len(matches) == 1:
            return 0.75
        return 0.0

    async def extract(self, document: ParsedDocument) -> ParsedStatement:
        first_pages = "\n".join(p.raw_text for p in document.pages[:3])
        full_text = document.full_text

        # Detect checking vs credit card
        is_credit = bool(re.search(r"credit\s+card|minimum\s+payment|apr|billing", first_pages, re.IGNORECASE))
        stmt_type = "credit_card" if is_credit else "bank"
        account_type = "credit_card" if is_credit else "checking"

        # Period
        period_start, period_end = None, None
        m = _PERIOD_RE.search(first_pages)
        if m:
            try:
                period_start = dateparser.parse(m.group(1).strip()).date()
                period_end = dateparser.parse(m.group(2).strip()).date()
            except (ValueError, TypeError):
                pass

        # Account
        acct_match = _ACCOUNT_RE.search(first_pages)
        account_masked = f"****{acct_match.group(1)}" if acct_match else ""

        # Extract data
        transactions = _extract_transactions(document, is_credit)
        balances = _extract_balances(document, period_end)

        # Institution details
        details = {}
        if is_credit:
            for field_name, pattern in [
                ("credit_limit", r"credit\s+limit\s*[:\-]?\s*\$?([\d,]+\.\d{2})"),
                ("available_credit", r"available\s+credit\s*[:\-]?\s*\$?([\d,]+\.\d{2})"),
                ("minimum_payment", r"minimum\s+payment\s*[:\-]?\s*\$?([\d,]+\.\d{2})"),
                ("apr_purchase", r"purchase\s+apr\s*[:\-]?\s*([\d.]+)%"),
            ]:
                fm = re.search(pattern, full_text, re.IGNORECASE)
                if fm:
                    details[field_name] = fm.group(1)

            # Rewards
            rewards_match = re.search(r"(?:points|rewards)\s+(?:earned|this\s+period)\s*[:\-]?\s*([\d,]+)", full_text, re.IGNORECASE)
            if rewards_match:
                details["rewards_earned"] = rewards_match.group(1).replace(",", "")

        return ParsedStatement(
            institution_type="chase",
            account_type=account_type,
            statement_type=stmt_type,
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


def _extract_transactions(doc: ParsedDocument, is_credit: bool) -> list[ExtractedTransaction]:
    transactions = []
    date_re = re.compile(r"(\d{2}/\d{2})")

    for page in doc.pages:
        # Try table extraction first
        for table in page.tables:
            if not table.header_row:
                continue
            header_lower = [h.lower() for h in table.header_row]
            if not any("date" in h for h in header_lower):
                continue

            date_col = next((i for i, h in enumerate(header_lower) if "date" in h), 0)
            desc_col = next((i for i, h in enumerate(header_lower) if "description" in h or "merchant" in h), 1)
            amt_col = next((i for i, h in enumerate(header_lower) if "amount" in h), len(header_lower) - 1)

            for row in table.rows:
                if len(row) <= max(date_col, amt_col):
                    continue
                try:
                    txn_date = dateparser.parse(str(row[date_col])).date()
                    raw_amt = str(row[amt_col]).replace(",", "").replace("$", "").strip()
                    if not raw_amt:
                        continue
                    amount = Decimal(raw_amt.replace("(", "-").replace(")", ""))
                    desc = str(row[desc_col]).strip() if desc_col < len(row) else ""

                    txn_type = "purchase" if is_credit and amount < 0 else "deposit" if amount > 0 else "withdrawal"
                    if "payment" in desc.lower():
                        txn_type = "payment"

                    transactions.append(ExtractedTransaction(
                        transaction_date=txn_date,
                        description=desc,
                        merchant_name=_clean_merchant(desc),
                        amount=amount,
                        transaction_type=txn_type,
                        category=_categorize(desc),
                        source_page=page.page_number,
                    ))
                except (ValueError, TypeError, InvalidOperation):
                    continue
    return transactions


def _extract_balances(doc: ParsedDocument, period_end: date | None) -> list[ExtractedBalance]:
    balances = []
    patterns = [
        r"(?:new|ending|closing)\s+balance\s*[:\-]?\s*\$?([\d,]+\.\d{2})",
        r"(?:total|account)\s+balance\s*[:\-]?\s*\$?([\d,]+\.\d{2})",
    ]
    for page in doc.pages[:3]:
        for pat in patterns:
            for m in re.finditer(pat, page.raw_text, re.IGNORECASE):
                try:
                    val = Decimal(m.group(1).replace(",", ""))
                    balances.append(ExtractedBalance(
                        snapshot_date=period_end or date.today(),
                        total_value=val,
                        source_page=page.page_number,
                    ))
                except InvalidOperation:
                    continue
    return balances


def _clean_merchant(description: str) -> str:
    """Clean up merchant name from transaction description."""
    name = re.sub(r"\s+\d{2}/\d{2}.*$", "", description)
    name = re.sub(r"\s+[A-Z]{2}\s*$", "", name)
    name = re.sub(r"#\d+", "", name)
    return name.strip()[:80]


def _categorize(description: str) -> str | None:
    desc_lower = description.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in desc_lower for kw in keywords):
            return category
    return "other"
