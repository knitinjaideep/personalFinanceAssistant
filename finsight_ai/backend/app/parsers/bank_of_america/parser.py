"""
Bank of America checking account statement parser.

Statement layout (Adv Plus Banking / Core Checking):
  - Page 1: account summary with beginning/ending balances
  - Page 2: legal/disclosures (skip)
  - Page 3+: transaction sections:
      "Deposits and other additions" — Date / Description / Amount
      "Withdrawals and other subtractions" — Date / Description / Amount
      "Checks" — rarely populated
      "Service fees" — rarely populated

Date format on transactions: MM/DD/YY (e.g. 12/31/24)
Period header: "for December 27, 2024 to January 28, 2025"
Account number: "Account number: 4460 3778 5392"
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
from app.parsers.categorize import categorize

logger = structlog.get_logger(__name__)

_BOFA_RE = re.compile(
    r"bank\s+of\s+america|bankofamerica\.com|bofa\.com|Bank\s+of\s+America,\s+N\.A\.",
    re.IGNORECASE,
)

# "for December 27, 2024 to January 28, 2025"
_PERIOD_RE = re.compile(
    r"for\s+(.+?)\s+to\s+(.+?)\s+Account\s+number",
    re.IGNORECASE,
)

# "Account number: 4460 3778 5392"
_ACCOUNT_RE = re.compile(
    r"Account\s+number\s*[:\-]?\s*([\d\s]{4,})",
    re.IGNORECASE,
)

# After continuation folding a BofA transaction line looks like:
#   "MM/DD/YY Description ... AMOUNT [ID:xxx PPD]"
# Strategy: match date at start, then find LAST dollar-amount token on the line
# (which sits just before the optional trailing ACH/ID noise).
# We use two passes:
#   1. _TX_DATE_RE: grab the date prefix to know where description starts
#   2. _AMOUNT_TAIL_RE: find the last numeric amount on the line
_TX_DATE_RE = re.compile(r"^(\d{2}/\d{2}/\d{2})\s+", re.MULTILINE)
_AMOUNT_TAIL_RE = re.compile(r"(-?[\d,]+\.\d{2})(?:\s+ID:\S+.*)?$")
# A line that starts with a date is definitely a new transaction, not a continuation.
_DATE_PREFIX_RE = re.compile(r"^\d{2}/\d{2}/\d{2}\s")

# Section headers — used to identify polarity
_SECTION_DEPOSIT = re.compile(
    r"Deposits\s+and\s+other\s+additions|Other\s+credits",
    re.IGNORECASE,
)
_SECTION_WITHDRAWAL = re.compile(
    r"Withdrawals\s+and\s+other\s+subtractions|Checks|Service\s+fees",
    re.IGNORECASE,
)
_SECTION_END = re.compile(
    r"^Total\s+(?:deposits|withdrawals|checks|service\s+fees)",
    re.IGNORECASE | re.MULTILINE,
)

# Balance extraction
_BALANCE_ENDING_RE = re.compile(
    r"Ending\s+balance\s+on\s+.+?\$\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)
_BALANCE_BEGINNING_RE = re.compile(
    r"Beginning\s+balance\s+on\s+.+?\$\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)


class BankOfAmericaParser(InstitutionParser):

    @property
    def institution_type(self) -> str:
        return "bofa"

    @property
    def institution_name(self) -> str:
        return "Bank of America"

    def can_handle(self, text: str, metadata: dict[str, Any] | None = None) -> float:
        matches = _BOFA_RE.findall(text[:3000])
        if len(matches) >= 2:
            return 0.95
        if len(matches) == 1:
            return 0.75
        return 0.0

    async def extract(self, document: ParsedDocument) -> ParsedStatement:
        first_page = document.pages[0].raw_text if document.pages else ""
        full_text = document.full_text

        # Period
        period_start, period_end = _extract_period(first_page)

        # Account number — last 4 digits of the masked account
        account_masked = ""
        acct_m = _ACCOUNT_RE.search(first_page)
        if acct_m:
            digits = re.sub(r"\s+", "", acct_m.group(1))
            account_masked = f"****{digits[-4:]}" if len(digits) >= 4 else digits

        transactions = _extract_transactions(document)
        balances = _extract_balances(full_text, period_end)

        return ParsedStatement(
            institution_type="bofa",
            account_type="checking",
            statement_type="bank",
            account_number_masked=account_masked,
            period_start=period_start,
            period_end=period_end,
            confidence=0.85 if transactions else 0.5,
            transactions=transactions,
            fees=[],
            holdings=[],
            balances=balances,
            institution_details={},
            page_count=document.page_count,
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_period(text: str) -> tuple[date | None, date | None]:
    m = _PERIOD_RE.search(text)
    if m:
        try:
            return (
                dateparser.parse(m.group(1).strip()).date(),
                dateparser.parse(m.group(2).strip()).date(),
            )
        except (ValueError, TypeError):
            pass

    # Fallback: look for "Month DD, YYYY to Month DD, YYYY" anywhere
    m2 = re.search(
        r"(\w+ \d{1,2},\s*\d{4})\s+to\s+(\w+ \d{1,2},\s*\d{4})",
        text, re.IGNORECASE,
    )
    if m2:
        try:
            return (
                dateparser.parse(m2.group(1).strip()).date(),
                dateparser.parse(m2.group(2).strip()).date(),
            )
        except (ValueError, TypeError):
            pass

    return None, None


def _extract_transactions(doc: ParsedDocument) -> list[ExtractedTransaction]:
    """
    Walk every page. Within each page text, detect section headers to determine
    whether upcoming transactions are deposits (positive) or withdrawals (negative),
    then regex-match each transaction line.
    """
    transactions: list[ExtractedTransaction] = []

    for page in doc.pages:
        text = page.raw_text
        if not text:
            continue

        # Split the page into labelled segments by section header
        segments = _split_into_segments(text)
        for is_deposit, segment_text in segments:
            folded = _fold_continuations(segment_text)
            for line in folded.splitlines():
                dm = _TX_DATE_RE.match(line)
                if not dm:
                    continue
                date_str = dm.group(1)
                rest = line[dm.end():]     # everything after the date
                am = _AMOUNT_TAIL_RE.search(rest)
                if not am:
                    continue
                raw_amt = am.group(1).replace(",", "")
                # Description is everything between the date and the last amount
                desc = rest[: am.start()].strip()
                if not desc:
                    continue

                try:
                    txn_date = _parse_date(date_str, segment_text)
                    amount_abs = Decimal(raw_amt.lstrip("-"))
                    # Canonical sign: deposits positive, withdrawals negative
                    amount = amount_abs if is_deposit else -amount_abs
                    txn_type = _classify_type(desc, is_deposit)

                    transactions.append(ExtractedTransaction(
                        transaction_date=txn_date,
                        description=desc,
                        merchant_name=_clean_merchant(desc),
                        amount=amount,
                        transaction_type=txn_type,
                        category=categorize(desc),
                        source_page=page.page_number,
                    ))
                except (ValueError, TypeError, InvalidOperation):
                    continue

    return transactions


def _fold_continuations(text: str) -> str:
    """
    BofA wraps long transaction descriptions onto the next line (no date prefix).
    Fold those continuation lines back onto the primary transaction line so the
    regex can match a single line: date … description … amount.

    A continuation line is one that does NOT start with a date (MM/DD/YY).
    We append it to the previous line, separated by a space.
    """
    lines = text.splitlines()
    folded: list[str] = []
    for line in lines:
        if not line.strip():
            folded.append(line)
        elif _DATE_PREFIX_RE.match(line) or not folded:
            folded.append(line)
        else:
            # Continuation — join onto previous line
            folded[-1] = folded[-1].rstrip() + " " + line.strip()
    return "\n".join(folded)


def _split_into_segments(text: str) -> list[tuple[bool, str]]:
    """
    Return a list of (is_deposit, segment_text) tuples.
    Segments are delimited by section header lines.
    """
    lines = text.splitlines()
    segments: list[tuple[bool, str]] = []
    current_lines: list[str] = []
    is_deposit: bool = True  # default — overwritten on first header match

    in_section = False

    for line in lines:
        if _SECTION_DEPOSIT.search(line):
            if in_section and current_lines:
                segments.append((is_deposit, "\n".join(current_lines)))
            is_deposit = True
            in_section = True
            current_lines = []
            continue

        if _SECTION_WITHDRAWAL.search(line):
            if in_section and current_lines:
                segments.append((is_deposit, "\n".join(current_lines)))
            is_deposit = False
            in_section = True
            current_lines = []
            continue

        if in_section:
            if _SECTION_END.match(line.strip()):
                # "Total deposits ..." — flush and stop this segment
                segments.append((is_deposit, "\n".join(current_lines)))
                in_section = False
                current_lines = []
                continue
            current_lines.append(line)

    # Flush any trailing segment
    if in_section and current_lines:
        segments.append((is_deposit, "\n".join(current_lines)))

    return segments


def _parse_date(date_str: str, context_text: str) -> date:
    """Parse MM/DD/YY using the statement year from surrounding context."""
    # Try to pull the 4-digit year from the page text
    stmt_year: int | None = None
    for m in re.finditer(r"\b(20\d{2})\b", context_text):
        stmt_year = int(m.group(1))
        break  # use first match

    if stmt_year is None:
        stmt_year = date.today().year

    month = int(date_str[:2])
    day = int(date_str[3:5])
    yr2 = int(date_str[6:8])
    year = 2000 + yr2

    # When the 2-digit year conflicts with the inferred stmt_year, trust the
    # explicit 2-digit year since BofA always encodes it on the transaction line.
    try:
        return date(year, month, day)
    except ValueError:
        return date(stmt_year, month, day)


def _classify_type(desc: str, is_deposit: bool) -> str:
    d = desc.lower()
    if re.search(r"zelle|transfer|trnsfr|wire", d):
        return "transfer"
    if re.search(r"payroll|direct\s*dep|dir\s*dep|ach\s*credit", d):
        return "deposit"
    if "payment" in d or "epay" in d:
        return "payment"
    if re.search(r"atm|cash\s+withdrawal", d):
        return "withdrawal"
    return "deposit" if is_deposit else "withdrawal"


def _clean_merchant(description: str) -> str:
    # Strip ACH boilerplate: "DES:Ext Trnsfr ID:... INDN:... CO ID:... PPD"
    name = re.sub(r"\s+DES:.+$", "", description, flags=re.IGNORECASE)
    name = re.sub(r"\s+ID:\S+", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+INDN:\S+.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+(?:PPD|WEB|CCD)$", "", name, flags=re.IGNORECASE)
    return name.strip()[:80]


def _extract_balances(text: str, period_end: date | None) -> list[ExtractedBalance]:
    balances = []
    snap_date = period_end or date.today()

    m = _BALANCE_ENDING_RE.search(text)
    if m:
        try:
            balances.append(ExtractedBalance(
                snapshot_date=snap_date,
                total_value=Decimal(m.group(1).replace(",", "")),
                source_page=1,
            ))
        except InvalidOperation:
            pass

    return balances
