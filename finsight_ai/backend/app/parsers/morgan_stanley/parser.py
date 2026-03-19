"""
Morgan Stanley statement parser.

Handles brokerage, advisory, IRA, and retirement account statements.
Uses regex-heavy extraction for structured fields (dates, amounts, account numbers),
with LLM assist for semi-structured narrative sections.
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
    ExtractedHolding,
    ExtractedTransaction,
    ParsedStatement,
)
from app.parsers.base import InstitutionParser, ParsedDocument

logger = structlog.get_logger(__name__)

# ── Detection patterns ───────────────────────────────────────────────────────

_MS_INDICATORS = [
    r"morgan\s+stanley",
    r"morganstanley\.com",
    r"MS\s+Smith\s+Barney",
]
_MS_RE = re.compile("|".join(_MS_INDICATORS), re.IGNORECASE)

_PERIOD_RE = re.compile(
    r"(?:for\s+the\s+period|statement\s+period)\s+(.+?)\s+(?:to|through)\s+(.+?)(?:\n|$)",
    re.IGNORECASE,
)
_ACCOUNT_RE = re.compile(
    r"(?:account\s+(?:number|#|no\.?)\s*[:\-]?\s*)([X*\d]{4,}[-\s]?[X*\d]+)",
    re.IGNORECASE,
)
_AMOUNT_RE = re.compile(r"\$?([\d,]+\.\d{2})")

_STATEMENT_TYPE_PATTERNS = {
    "brokerage": [r"brokerage\s+account", r"individual\s+account", r"portfolio\s+summary"],
    "advisory": [r"advisory\s+(fee|account|service)", r"managed\s+account"],
    "retirement": [r"traditional\s+ira", r"roth\s+ira", r"rollover\s+ira", r"401\s*\(?k\)?"],
}


class MorganStanleyParser(InstitutionParser):

    @property
    def institution_type(self) -> str:
        return "morgan_stanley"

    @property
    def institution_name(self) -> str:
        return "Morgan Stanley"

    def can_handle(self, text: str, metadata: dict[str, Any] | None = None) -> float:
        matches = _MS_RE.findall(text[:3000])
        if len(matches) >= 2:
            return 0.95
        if len(matches) == 1:
            return 0.75
        return 0.0

    async def extract(self, document: ParsedDocument) -> ParsedStatement:
        full_text = document.full_text
        first_pages = "\n".join(p.raw_text for p in document.pages[:3])

        # Detect statement type
        stmt_type = "brokerage"
        for stype, patterns in _STATEMENT_TYPE_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, first_pages, re.IGNORECASE):
                    stmt_type = stype
                    break

        # Account type mapping
        account_type_map = {
            "brokerage": "individual_brokerage",
            "advisory": "advisory",
            "retirement": "ira",
        }

        # Extract period
        period_start, period_end = _extract_period(first_pages)

        # Extract account number
        acct_match = _ACCOUNT_RE.search(first_pages)
        account_masked = acct_match.group(1) if acct_match else ""

        # Extract financial data from all pages
        transactions = _extract_transactions(document)
        fees = _extract_fees(document)
        holdings = _extract_holdings(document)
        balances = _extract_balances(document, period_end)

        # Institution-specific details
        details = {}
        advisor_match = re.search(r"(?:financial\s+advisor|fa)\s*[:\-]?\s*(.+)", first_pages, re.IGNORECASE)
        if advisor_match:
            details["financial_advisor"] = advisor_match.group(1).strip()

        fee_rate_match = re.search(r"(?:annual|annualized)\s+(?:fee|rate)\s*[:\-]?\s*([\d.]+)%", full_text, re.IGNORECASE)
        if fee_rate_match:
            details["management_fee_rate"] = fee_rate_match.group(1)

        return ParsedStatement(
            institution_type="morgan_stanley",
            account_type=account_type_map.get(stmt_type, "unknown"),
            statement_type=stmt_type,
            account_number_masked=account_masked,
            period_start=period_start,
            period_end=period_end,
            confidence=0.8 if transactions or holdings else 0.5,
            transactions=transactions,
            fees=fees,
            holdings=holdings,
            balances=balances,
            institution_details=details,
            warnings=[],
            page_count=document.page_count,
        )


def _extract_period(text: str) -> tuple[date | None, date | None]:
    match = _PERIOD_RE.search(text)
    if match:
        try:
            start = dateparser.parse(match.group(1).strip()).date()
            end = dateparser.parse(match.group(2).strip()).date()
            return start, end
        except (ValueError, TypeError):
            pass
    return None, None


def _parse_amount(text: str) -> Decimal | None:
    match = _AMOUNT_RE.search(text)
    if match:
        try:
            return Decimal(match.group(1).replace(",", ""))
        except InvalidOperation:
            pass
    return None


def _extract_transactions(doc: ParsedDocument) -> list[ExtractedTransaction]:
    """Extract transactions from tables that look like transaction history."""
    transactions = []
    for page in doc.pages:
        for table in page.tables:
            if not table.header_row:
                continue
            header_lower = [h.lower() for h in table.header_row]
            # Look for date + description + amount columns
            if not any("date" in h for h in header_lower):
                continue
            if not any("amount" in h or "value" in h or "price" in h for h in header_lower):
                continue

            date_col = next((i for i, h in enumerate(header_lower) if "date" in h), None)
            desc_col = next((i for i, h in enumerate(header_lower) if "description" in h or "activity" in h), None)
            amt_col = next((i for i, h in enumerate(header_lower) if "amount" in h or "value" in h or "net" in h), None)

            if date_col is None or amt_col is None:
                continue

            for row in table.rows:
                if len(row) <= max(date_col, amt_col):
                    continue
                try:
                    txn_date = dateparser.parse(str(row[date_col])).date()
                    amount = _parse_amount(str(row[amt_col]))
                    if amount is None:
                        continue
                    desc = str(row[desc_col]) if desc_col is not None and desc_col < len(row) else ""
                    transactions.append(ExtractedTransaction(
                        transaction_date=txn_date,
                        description=desc.strip(),
                        amount=amount,
                        transaction_type=_classify_transaction(desc),
                        source_page=page.page_number,
                    ))
                except (ValueError, TypeError):
                    continue
    return transactions


def _extract_fees(doc: ParsedDocument) -> list[ExtractedFee]:
    """Extract fees from fee-related sections."""
    fees = []
    fee_section_re = re.compile(r"(?:fee|charge|commission)", re.IGNORECASE)

    for page in doc.pages:
        for table in page.tables:
            if not table.header_row:
                continue
            header_text = " ".join(table.header_row).lower()
            if not fee_section_re.search(header_text):
                continue

            for row in table.rows:
                if len(row) < 2:
                    continue
                amount = _parse_amount(" ".join(str(c) for c in row))
                if amount and amount > 0:
                    desc = str(row[0]) if row[0] else "Fee"
                    fees.append(ExtractedFee(
                        fee_date=date.today(),  # Will be refined by period
                        description=desc.strip(),
                        amount=amount,
                        source_page=page.page_number,
                    ))
    return fees


def _extract_holdings(doc: ParsedDocument) -> list[ExtractedHolding]:
    """Extract holdings from portfolio/holdings tables."""
    holdings = []
    for page in doc.pages:
        for table in page.tables:
            if not table.header_row:
                continue
            header_lower = [h.lower() for h in table.header_row]
            if not any("symbol" in h or "security" in h or "holding" in h or "description" in h for h in header_lower):
                continue
            if not any("value" in h or "market" in h for h in header_lower):
                continue

            desc_col = next((i for i, h in enumerate(header_lower) if "description" in h or "security" in h), 0)
            sym_col = next((i for i, h in enumerate(header_lower) if "symbol" in h or "ticker" in h), None)
            val_col = next((i for i, h in enumerate(header_lower) if "market" in h or "value" in h), None)
            qty_col = next((i for i, h in enumerate(header_lower) if "quantity" in h or "shares" in h), None)
            price_col = next((i for i, h in enumerate(header_lower) if "price" in h), None)

            if val_col is None:
                continue

            for row in table.rows:
                if len(row) <= val_col:
                    continue
                market_val = _parse_amount(str(row[val_col]))
                if market_val is None or market_val == 0:
                    continue

                holdings.append(ExtractedHolding(
                    symbol=str(row[sym_col]).strip() if sym_col and sym_col < len(row) else None,
                    description=str(row[desc_col]).strip() if desc_col < len(row) else "",
                    quantity=_parse_amount(str(row[qty_col])) if qty_col and qty_col < len(row) else None,
                    price=_parse_amount(str(row[price_col])) if price_col and price_col < len(row) else None,
                    market_value=market_val,
                    source_page=page.page_number,
                ))
    return holdings


def _extract_balances(doc: ParsedDocument, period_end: date | None) -> list[ExtractedBalance]:
    """Extract balance snapshot from account summary section."""
    balances = []
    balance_re = re.compile(r"(?:total\s+(?:account\s+)?value|total\s+assets|account\s+balance)\s*[:\-]?\s*\$?([\d,]+\.\d{2})", re.IGNORECASE)

    for page in doc.pages[:3]:  # Usually in first few pages
        for match in balance_re.finditer(page.raw_text):
            try:
                value = Decimal(match.group(1).replace(",", ""))
                balances.append(ExtractedBalance(
                    snapshot_date=period_end or date.today(),
                    total_value=value,
                    source_page=page.page_number,
                ))
            except InvalidOperation:
                continue
    return balances


def _classify_transaction(description: str) -> str:
    """Classify transaction type from description text."""
    desc_lower = description.lower()
    if any(w in desc_lower for w in ["dividend", "div"]):
        return "dividend"
    if any(w in desc_lower for w in ["interest"]):
        return "interest"
    if any(w in desc_lower for w in ["fee", "commission", "advisory"]):
        return "fee"
    if any(w in desc_lower for w in ["bought", "buy", "purchase"]):
        return "trade_buy"
    if any(w in desc_lower for w in ["sold", "sell", "sale"]):
        return "trade_sell"
    if any(w in desc_lower for w in ["deposit", "contribution"]):
        return "deposit"
    if any(w in desc_lower for w in ["withdrawal", "distribution"]):
        return "withdrawal"
    if any(w in desc_lower for w in ["transfer"]):
        return "transfer"
    return "other"
