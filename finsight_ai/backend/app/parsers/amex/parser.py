"""
American Express statement parser.

Handles Amex credit card statements.
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
from app.parsers.categorize import categorize

logger = structlog.get_logger(__name__)

_AMEX_RE = re.compile(
    r"american\s+express|amex|americanexpress\.com|member\s+since",
    re.IGNORECASE,
)
_PERIOD_RE = re.compile(
    r"(?:statement\s+(?:closing|period)|billing\s+period)\s*[:\-]?\s*(.+?)\s+(?:to|through|-)\s+(.+?)(?:\n|$)",
    re.IGNORECASE,
)
_CLOSING_DATE_RE = re.compile(r"closing\s+date\s*[:\-]?\s*(\d{2}/\d{2}/\d{2,4})", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"\$?([\d,]+\.\d{2})")

# A transaction text line:  MM/DD/YY[*]  DESCRIPTION  [-]$AMOUNT
# - leading date (2-digit year as Amex prints it)
# - optional "*" marker (payments/credits)
# - greedy description
# - trailing signed dollar amount (last money token on the line)
_TXN_LINE_RE = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{2,4})\*?\s+"
    r"(?P<desc>.+?)\s+"
    r"(?P<sign>-?)\$(?P<amount>[\d,]+\.\d{2})\s*$"
)

# Lines from the interest-charge / APR summary table that look transaction-like
# but are NOT real transactions (e.g. "Purchases 04/28/2023 17.49% (v) $0.00").
_NON_TXN_HINTS = re.compile(
    r"\b(apr|annual\s+percentage|interest\s+charge|balance\s+subject|"
    r"\(v\)|%\s*\(|cash\s+advance\s+limit|credit\s+limit|available\s+credit)\b",
    re.IGNORECASE,
)

# Fee lines, e.g. "Late Fee $39.00", "Foreign Transaction Fee $1.20"
_FEE_LINE_RE = re.compile(
    r"^(?P<desc>.*?\bfee\b.*?)\s+\$(?P<amount>[\d,]+\.\d{2})\s*$",
    re.IGNORECASE,
)
_TOTAL_FEES_RE = re.compile(
    r"total\s+fees?\s+(?:for\s+this\s+period)?\s*[:\-]?\s*\$?([\d,]+\.\d{2})",
    re.IGNORECASE,
)


class AmexParser(InstitutionParser):

    @property
    def institution_type(self) -> str:
        return "amex"

    @property
    def institution_name(self) -> str:
        return "American Express"

    def can_handle(self, text: str, metadata: dict[str, Any] | None = None) -> float:
        matches = _AMEX_RE.findall(text[:3000])
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

        # Amex statements usually print only a "Closing Date" — use it as period_end
        # when an explicit billing period wasn't found.
        if period_end is None:
            cm = _CLOSING_DATE_RE.search(first_pages)
            if cm:
                try:
                    period_end = dateparser.parse(cm.group(1).strip()).date()
                except (ValueError, TypeError):
                    pass

        acct_match = re.search(r"(?:account\s+ending|xxxx-?)\s*(\d{4,5})", first_pages, re.IGNORECASE)
        account_masked = f"****{acct_match.group(1)}" if acct_match else ""

        transactions = _extract_transactions(document)
        fees = _extract_fees(document, period_end)
        balances = _extract_balances(first_pages, period_end)

        # period_start fallback: first day of the closing month.
        if period_start is None and period_end is not None:
            period_start = period_end.replace(day=1)

        logger.info(
            "amex.extract.done",
            transactions=len(transactions), fees=len(fees), balances=len(balances),
            period_end=str(period_end) if period_end else None,
        )

        details = {}
        for field_name, pattern in [
            ("membership_rewards_earned", r"(?:rewards?|points?)\s+(?:earned|this\s+period)\s*[:\-]?\s*([\d,]+)"),
            ("membership_rewards_balance", r"(?:rewards?|points?)\s+balance\s*[:\-]?\s*([\d,]+)"),
            ("apr", r"(?:purchase\s+)?apr\s*[:\-]?\s*([\d.]+)%"),
            ("credit_limit", r"credit\s+limit\s*[:\-]?\s*\$?([\d,]+)"),
            ("minimum_payment", r"minimum\s+(?:payment|due)\s*[:\-]?\s*\$?([\d,]+\.\d{2})"),
            ("payment_due_date", r"(?:payment|due)\s+date\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})"),
        ]:
            fm = re.search(pattern, full_text, re.IGNORECASE)
            if fm:
                details[field_name] = fm.group(1).replace(",", "")

        return ParsedStatement(
            institution_type="amex",
            account_type="credit_card",
            statement_type="credit_card",
            account_number_masked=account_masked,
            period_start=period_start,
            period_end=period_end,
            confidence=0.85 if transactions else 0.5,
            transactions=transactions,
            fees=fees,
            holdings=[],
            balances=balances,
            institution_details=details,
            page_count=document.page_count,
        )


def _extract_transactions(doc: ParsedDocument) -> list[ExtractedTransaction]:
    """Extract Amex transactions.

    Amex statements lay transactions out as plain TEXT lines (not ruled tables),
    so text-line parsing is the primary strategy. Table parsing is kept as a
    fallback for the rare statement that does export ruled tables.
    """
    transactions = _extract_transactions_from_text(doc)
    if transactions:
        return transactions
    return _extract_transactions_from_tables(doc)


def _extract_transactions_from_text(doc: ParsedDocument) -> list[ExtractedTransaction]:
    transactions: list[ExtractedTransaction] = []
    seen: set[tuple[str, str, str]] = set()  # (date, desc, amount) dedup

    for page in doc.pages:
        for raw_line in page.raw_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            m = _TXN_LINE_RE.match(line)
            if not m:
                continue
            # Skip APR / interest-charge summary rows that resemble transactions.
            if _NON_TXN_HINTS.search(line):
                continue

            desc = m.group("desc").strip()
            if not desc:
                continue

            raw_amount = m.group("amount").replace(",", "")
            try:
                amount = Decimal(raw_amount)
            except InvalidOperation:
                continue

            # On a credit-card statement, a charge increases what you owe.
            # Represent charges as negative (outflow) and payments/credits as
            # positive — consistent with the rest of the canonical model where
            # spending is negative.
            is_credit = bool(m.group("sign")) or _looks_like_payment(desc)
            signed = amount if is_credit else -amount

            txn_date = _parse_amex_date(m.group("date"))
            if txn_date is None:
                continue

            key = (str(txn_date), desc.lower(), raw_amount)
            if key in seen:
                continue
            seen.add(key)

            transactions.append(ExtractedTransaction(
                transaction_date=txn_date,
                description=desc,
                merchant_name=desc[:80].strip(),
                amount=signed,
                transaction_type="payment" if is_credit else "purchase",
                category=_categorize(desc),
                source_page=page.page_number,
            ))

    return transactions


def _extract_transactions_from_tables(doc: ParsedDocument) -> list[ExtractedTransaction]:
    transactions = []
    for page in doc.pages:
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


def _extract_fees(doc: ParsedDocument, period_end: date | None) -> list[ExtractedFee]:
    """Extract individual fee lines (late fee, foreign-transaction fee, etc.)."""
    fees: list[ExtractedFee] = []
    seen: set[str] = set()
    fee_date = period_end or date.today()

    for page in doc.pages:
        for raw_line in page.raw_text.splitlines():
            line = raw_line.strip()
            if not line or "fee" not in line.lower():
                continue
            # Skip explanatory / threat text ("...you may have to pay a late fee of up to...")
            if any(w in line.lower() for w in ("may have to", "up to", "if we do not", "could be")):
                continue
            m = _FEE_LINE_RE.match(line)
            if not m:
                continue
            desc = m.group("desc").strip()
            try:
                amount = Decimal(m.group("amount").replace(",", ""))
            except InvalidOperation:
                continue
            if amount == 0:
                continue
            key = f"{desc.lower()}|{amount}"
            if key in seen:
                continue
            seen.add(key)
            fees.append(ExtractedFee(
                fee_date=fee_date,
                description=desc,
                amount=amount,
                fee_category=_fee_category(desc),
                source_page=page.page_number,
            ))
    return fees


def _fee_category(desc: str) -> str:
    d = desc.lower()
    if "late" in d:
        return "late_fee"
    if "foreign" in d or "transaction fee" in d:
        return "foreign_transaction_fee"
    if "annual" in d:
        return "annual_fee"
    if "interest" in d:
        return "interest"
    return "other"


def _looks_like_payment(desc: str) -> bool:
    d = desc.lower()
    return any(w in d for w in ("payment", "thank you", "autopay", "credit", "refund", "return"))


def _parse_amex_date(raw: str) -> date | None:
    try:
        return dateparser.parse(raw, dayfirst=False).date()
    except (ValueError, TypeError, OverflowError):
        return None


def _extract_balances(text: str, period_end: date | None) -> list[ExtractedBalance]:
    balances = []
    for pat in [
        r"(?:new|total)\s+balance\s*[:\-]?\s*\$?([\d,]+\.\d{2})",
        r"(?:statement|closing)\s+balance\s*[:\-]?\s*\$?([\d,]+\.\d{2})",
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
    # Uses the shared, comprehensive categorizer (groceries/dining/gas-aware).
    return categorize(desc)
