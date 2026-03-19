"""
E*TRADE statement parser.

Handles individual brokerage account statements.
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

_ETRADE_RE = re.compile(
    r"e\*?trade|etrade\.com|morgan\s+stanley\s+(?:at\s+)?e\*?trade",
    re.IGNORECASE,
)
_PERIOD_RE = re.compile(
    r"(?:statement\s+period|for\s+the\s+period)\s*[:\-]?\s*(.+?)\s+(?:to|through|-)\s+(.+?)(?:\n|$)",
    re.IGNORECASE,
)
_ACCOUNT_RE = re.compile(r"(?:account\s*#?\s*[:\-]?\s*)(\d{4}[-\s]?\d{4})", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"\$?([\d,]+\.\d{2})")


class ETradeParser(InstitutionParser):

    @property
    def institution_type(self) -> str:
        return "etrade"

    @property
    def institution_name(self) -> str:
        return "E*TRADE"

    def can_handle(self, text: str, metadata: dict[str, Any] | None = None) -> float:
        matches = _ETRADE_RE.findall(text[:3000])
        if len(matches) >= 2:
            return 0.95
        if len(matches) == 1:
            return 0.75
        return 0.0

    async def extract(self, document: ParsedDocument) -> ParsedStatement:
        first_pages = "\n".join(p.raw_text for p in document.pages[:3])

        period_start, period_end = None, None
        m = _PERIOD_RE.search(first_pages)
        if m:
            try:
                period_start = dateparser.parse(m.group(1).strip()).date()
                period_end = dateparser.parse(m.group(2).strip()).date()
            except (ValueError, TypeError):
                pass

        acct_match = _ACCOUNT_RE.search(first_pages)
        account_masked = f"****{acct_match.group(1)[-4:]}" if acct_match else ""

        transactions = _extract_transactions(document)
        holdings = _extract_holdings(document)
        balances = _extract_balances(document, period_end)

        # E*TRADE-specific details
        details = {}
        for field_name, pattern in [
            ("margin_buying_power", r"margin\s+buying\s+power\s*[:\-]?\s*\$?([\d,]+\.\d{2})"),
            ("option_buying_power", r"option\s+buying\s+power\s*[:\-]?\s*\$?([\d,]+\.\d{2})"),
            ("realized_gain_loss_ytd", r"(?:realized|net)\s+(?:gain|loss)\s+(?:ytd|year)\s*[:\-]?\s*\(?\$?([\d,]+\.\d{2})\)?"),
        ]:
            fm = re.search(pattern, document.full_text, re.IGNORECASE)
            if fm:
                details[field_name] = fm.group(1).replace(",", "")

        return ParsedStatement(
            institution_type="etrade",
            account_type="individual_brokerage",
            statement_type="brokerage",
            account_number_masked=account_masked,
            period_start=period_start,
            period_end=period_end,
            confidence=0.8 if transactions or holdings else 0.5,
            transactions=transactions,
            fees=[],
            holdings=holdings,
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
            if not any("amount" in h or "value" in h or "price" in h for h in header_lower):
                continue

            date_col = next((i for i, h in enumerate(header_lower) if "date" in h), 0)
            desc_col = next((i for i, h in enumerate(header_lower) if "description" in h or "action" in h), 1)
            amt_col = next((i for i, h in enumerate(header_lower) if "amount" in h or "net" in h), None)
            sym_col = next((i for i, h in enumerate(header_lower) if "symbol" in h), None)
            qty_col = next((i for i, h in enumerate(header_lower) if "quantity" in h or "shares" in h), None)

            if amt_col is None:
                continue

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
                    symbol = str(row[sym_col]).strip() if sym_col and sym_col < len(row) else None

                    transactions.append(ExtractedTransaction(
                        transaction_date=txn_date,
                        description=desc,
                        amount=amount,
                        symbol=symbol,
                        quantity=Decimal(str(row[qty_col]).replace(",", "")) if qty_col and qty_col < len(row) and row[qty_col] else None,
                        transaction_type=_classify(desc),
                        source_page=page.page_number,
                    ))
                except (ValueError, TypeError, InvalidOperation):
                    continue
    return transactions


def _extract_holdings(doc: ParsedDocument) -> list[ExtractedHolding]:
    holdings = []
    for page in doc.pages:
        for table in page.tables:
            if not table.header_row:
                continue
            header_lower = [h.lower() for h in table.header_row]
            if not any("symbol" in h or "security" in h for h in header_lower):
                continue
            if not any("value" in h or "market" in h for h in header_lower):
                continue

            sym_col = next((i for i, h in enumerate(header_lower) if "symbol" in h), 0)
            desc_col = next((i for i, h in enumerate(header_lower) if "description" in h or "security" in h), 1)
            val_col = next((i for i, h in enumerate(header_lower) if "market" in h or "value" in h), None)
            qty_col = next((i for i, h in enumerate(header_lower) if "quantity" in h or "shares" in h), None)

            if val_col is None:
                continue

            for row in table.rows:
                if len(row) <= val_col:
                    continue
                try:
                    raw = str(row[val_col]).replace(",", "").replace("$", "").strip()
                    if not raw:
                        continue
                    mkt_val = Decimal(raw)
                    if mkt_val == 0:
                        continue
                    holdings.append(ExtractedHolding(
                        symbol=str(row[sym_col]).strip() if sym_col < len(row) else None,
                        description=str(row[desc_col]).strip() if desc_col < len(row) else "",
                        market_value=mkt_val,
                        quantity=Decimal(str(row[qty_col]).replace(",", "")) if qty_col and qty_col < len(row) and row[qty_col] else None,
                        source_page=page.page_number,
                    ))
                except (ValueError, TypeError, InvalidOperation):
                    continue
    return holdings


def _extract_balances(doc: ParsedDocument, period_end: date | None) -> list[ExtractedBalance]:
    balances = []
    pattern = re.compile(r"(?:total\s+(?:account|portfolio)\s+value|account\s+balance)\s*[:\-]?\s*\$?([\d,]+\.\d{2})", re.IGNORECASE)
    for page in doc.pages[:3]:
        for m in pattern.finditer(page.raw_text):
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


def _classify(desc: str) -> str:
    d = desc.lower()
    if any(w in d for w in ["bought", "buy"]):
        return "trade_buy"
    if any(w in d for w in ["sold", "sell"]):
        return "trade_sell"
    if "dividend" in d:
        return "dividend"
    if "interest" in d:
        return "interest"
    if "fee" in d:
        return "fee"
    if any(w in d for w in ["deposit", "transfer in"]):
        return "deposit"
    if any(w in d for w in ["withdrawal", "transfer out"]):
        return "withdrawal"
    return "other"
