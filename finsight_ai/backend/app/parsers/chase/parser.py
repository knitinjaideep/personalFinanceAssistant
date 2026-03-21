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
    r"(?:statement\s+period|billing\s+period|opening/closing\s+date)\s*[:\-]?\s*(.+?)\s+(?:to|through|-)\s+(.+?)(?:\n|$)",
    re.IGNORECASE,
)
# Matches "January 16, 2026throughFebruary 13, 2026" (no space) or with spaces
_PERIOD_RE2 = re.compile(
    r"(\w+ \d{1,2},\s*\d{4})\s*through\s*(\w+ \d{1,2},\s*\d{4})",
    re.IGNORECASE,
)
# Matches "12/03/25 - 01/02/26" style
_PERIOD_RE3 = re.compile(
    r"(\d{2}/\d{2}/\d{2,4})\s*[-–]\s*(\d{2}/\d{2}/\d{2,4})",
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

        # Period — try multiple regex patterns
        period_start, period_end = None, None
        for pattern in [_PERIOD_RE, _PERIOD_RE2, _PERIOD_RE3]:
            m = pattern.search(first_pages)
            if m:
                try:
                    period_start = dateparser.parse(m.group(1).strip()).date()
                    period_end = dateparser.parse(m.group(2).strip()).date()
                    break
                except (ValueError, TypeError):
                    continue

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

                    txn_type = _classify_type(desc, amount, is_credit)
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

        # Text-based fallback (handles Chase PDFs without structured tables)
        if not transactions:
            txns = _extract_transactions_from_text(page.raw_text, page.page_number, is_credit)
            transactions.extend(txns)

    return transactions


# Matches: "01/16 Description -1,234.56 14,297.86" (checking: date desc amount balance)
# Matches: "01/16 01/15 Description -1,234.56 14,297.86" (checking: date settle desc amount balance)
# Matches: "12/01 MERCHANT NAME NJ 16.96" (credit: date desc amount)
_CHECKING_TX_RE = re.compile(
    r"^(\d{2}/\d{2})"            # transaction date
    r"(?:\s+\d{2}/\d{2})?"       # optional settlement date
    r"\s+(.+?)"                   # description (non-greedy)
    r"\s+([-]?\d{1,3}(?:,\d{3})*\.\d{2})"  # amount
    r"(?:\s+[\d,]+\.\d{2})?$",   # optional balance
    re.MULTILINE,
)

_CREDIT_TX_RE = re.compile(
    r"^(\d{2}/\d{2})"            # transaction date
    r"\s+(.+?)"                   # description
    r"\s+([-]?\d{1,3}(?:,\d{3})*\.\d{2})$",  # amount at end of line
    re.MULTILINE,
)


def _extract_transactions_from_text(
    text: str, page_number: int, is_credit: bool
) -> list[ExtractedTransaction]:
    """Extract transactions from raw PDF text using regex line matching."""
    if not text:
        return []

    transactions = []
    # Infer statement year from text — look for dates in "Month DD, YYYY" or "/YYYY" format
    stmt_year = date.today().year
    year_match = re.search(r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s*(20\d{2})", text, re.IGNORECASE)
    if not year_match:
        year_match = re.search(r"\d{2}/\d{2}/(20\d{2})", text)
    if not year_match:
        year_match = re.search(r"(?:through|to|-)\s*(?:\w+ \d+,\s*)?(20\d{2})", text, re.IGNORECASE)
    if year_match:
        stmt_year = int(year_match.group(1))

    # Only process lines within transaction sections
    in_transactions = False
    pattern = _CREDIT_TX_RE if is_credit else _CHECKING_TX_RE

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Section markers (Chase uses *start*/*end* tags and section headers)
        if re.search(
            r"\*start\*transaction|TRANSACTION DETAIL|ACCOUNT ACTIVITY|"
            r"PAYMENTS AND OTHER CREDITS|^PURCHASE$|^PURCHASES$|"
            r"Date of\s*$|Merchant Name or Transaction",
            line, re.IGNORECASE
        ):
            in_transactions = True
            continue
        if re.search(r"\*end\*transaction|Ending Balance\s*\$", line, re.IGNORECASE):
            in_transactions = False
            continue
        # Skip pure header/label lines that aren't transactions
        if re.match(r"^(DATE|DESCRIPTION|AMOUNT|BALANCE|Transaction\s*#:)", line, re.IGNORECASE):
            continue

        if not in_transactions:
            continue

        m = pattern.match(line)
        if not m:
            continue

        try:
            date_str = m.group(1)  # MM/DD
            desc = m.group(2).strip()
            raw_amt = m.group(3).replace(",", "")
            amount = Decimal(raw_amt)

            # Parse date — use stmt_year, watch for year rollover
            month, day = int(date_str[:2]), int(date_str[3:5])
            # Handle year rollover: if month is Dec but stmt_year ends in Jan+, use prior year
            try:
                txn_date = date(stmt_year, month, day)
            except ValueError:
                continue
            # If date is in the future (>90 days), assume it's the prior year
            from datetime import date as date_cls
            if (txn_date - date_cls.today()).days > 90:
                txn_date = date(stmt_year - 1, month, day)

            txn_type = _classify_type(desc, amount, is_credit)
            transactions.append(ExtractedTransaction(
                transaction_date=txn_date,
                description=desc,
                merchant_name=_clean_merchant(desc),
                amount=amount,
                transaction_type=txn_type,
                category=_categorize(desc),
                source_page=page_number,
            ))
        except (ValueError, TypeError, InvalidOperation):
            continue

    return transactions


def _classify_type(desc: str, amount: Decimal, is_credit: bool) -> str:
    desc_lower = desc.lower()
    if "payment" in desc_lower:
        return "payment"
    if re.search(r"transfer|zelle|venmo|paypal", desc_lower):
        return "transfer"
    if re.search(r"payroll|direct dep|dir dep|deposit", desc_lower):
        return "deposit"
    if is_credit:
        return "purchase" if amount > 0 else "payment"
    return "withdrawal" if amount < 0 else "deposit"


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
