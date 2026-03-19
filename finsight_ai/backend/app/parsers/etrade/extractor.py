"""
E*TRADE statement extractor.

Extracts from individual brokerage statements:
- Account number (masked)
- Statement period
- Portfolio value / balance snapshots
- Holdings (securities with quantity, price, market value)
- Transactions (trades, dividends, transfers, fees)
- Fees (commissions, account fees)
- Cash flow summary
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import structlog

from app.domain.entities import (
    Account,
    BalanceSnapshot,
    CashFlow,
    Fee,
    FieldConfidence,
    FinancialInstitution,
    Holding,
    SourceLocation,
    Statement,
    StatementPeriod,
    Transaction,
)
from app.domain.enums import (
    AccountType,
    ExtractionStatus,
    InstitutionType,
    StatementType,
    TransactionType,
)
from app.parsers.base import ParsedDocument, ParsedTable

logger = structlog.get_logger(__name__)

# ── Regex patterns ─────────────────────────────────────────────────────────────

_AMOUNT_RE = re.compile(r"\(?\$?\s*([\d,]+\.\d{2})\)?")
_ACCOUNT_RE = re.compile(
    r"account\s*(?:number|#)?\s*[:\-]?\s*(?:ending\s+in\s+)?([xX*\d\-]{4,})",
    re.IGNORECASE,
)
_PERIOD_RE = re.compile(
    r"(?:statement\s+period|for\s+the\s+period|portfolio\s+as\s+of)\s*[:\-]?\s*"
    r"(\w[\w\s,]+?)\s+(?:through|to|-)\s+(\w[\w\s,]+?)(?:\n|$)",
    re.IGNORECASE,
)
_PORTFOLIO_VALUE_RE = re.compile(
    r"(?:total\s+(?:account\s+)?(?:value|portfolio)|portfolio\s+value|net\s+asset\s+value|"
    r"total\s+market\s+value)\s*[:\-]?\s*\$?\s*([\d,]+\.?\d*)",
    re.IGNORECASE,
)
_CASH_BALANCE_RE = re.compile(
    r"(?:cash\s+(?:balance|available)|money\s+market|cash\s+equivalent)\s*[:\-]?\s*"
    r"\$?\s*([\d,]+\.?\d*)",
    re.IGNORECASE,
)

_SECTION_HEADERS = {
    "holdings": re.compile(
        r"portfolio\s+detail|holdings|positions|securities\s+held|equity\s+positions",
        re.IGNORECASE,
    ),
    "transactions": re.compile(
        r"transaction\s+(history|detail|summary)|activity\s+detail|trade\s+history",
        re.IGNORECASE,
    ),
    "fees": re.compile(
        r"fee\s+(detail|schedule)|commissions?|charges?\s+and\s+fees?",
        re.IGNORECASE,
    ),
}


def _parse_decimal(text: str) -> Decimal | None:
    if not text:
        return None
    negative = "(" in text or text.strip().startswith("-")
    cleaned = re.sub(r"[^\d.]", "", text)
    if not cleaned:
        return None
    try:
        val = Decimal(cleaned)
        return -val if negative else val
    except InvalidOperation:
        return None


def _parse_date(text: str) -> date | None:
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y",
                "%B %d %Y", "%b %d %Y"):
        try:
            parsed = datetime.strptime(text.strip(), fmt)
            if parsed.year == 1900:
                parsed = parsed.replace(year=datetime.today().year)
            return parsed.date()
        except ValueError:
            continue
    try:
        from dateutil import parser as du
        return du.parse(text.strip(), fuzzy=True).date()
    except Exception:
        return None


@dataclass
class _Ctx:
    document: ParsedDocument
    institution_id: uuid.UUID
    account_id: uuid.UUID
    statement_id: uuid.UUID
    field_confidences: list[FieldConfidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_fc(self, name: str, found: bool, conf: float, method: str = "regex") -> None:
        self.field_confidences.append(
            FieldConfidence(field_name=name, was_found=found,
                            confidence=conf, extraction_method=method)
        )


ETRADE_INSTITUTION = FinancialInstitution(
    name="E*TRADE",
    institution_type=InstitutionType.ETRADE,
    website="https://us.etrade.com",
)


class ETradeExtractor:
    """Extracts structured financial data from E*TRADE brokerage statements."""

    async def extract(
        self,
        document: ParsedDocument,
        account_type: AccountType = AccountType.INDIVIDUAL_BROKERAGE,
        statement_type: StatementType = StatementType.BROKERAGE,
    ) -> Statement:
        account = self._extract_account(document, account_type)
        ctx = _Ctx(
            document=document,
            institution_id=ETRADE_INSTITUTION.id,
            account_id=account.id,
            statement_id=uuid.uuid4(),
        )

        period = self._extract_period(document, ctx)
        balance_snapshots = self._extract_balances(document, ctx, period)
        holdings = self._extract_holdings(document, ctx)
        transactions = self._extract_transactions(document, ctx)
        fees = self._extract_fees(document, ctx)
        cash_flow = self._compute_cash_flow(transactions, fees)

        found_fc = [f for f in ctx.field_confidences if f.was_found]
        overall = (
            sum(f.confidence for f in found_fc) / len(ctx.field_confidences)
            if ctx.field_confidences else 0.0
        )

        status = ExtractionStatus.SUCCESS
        if overall < 0.4 or (not holdings and not balance_snapshots):
            status = ExtractionStatus.PARTIAL
            ctx.warnings.append("Limited fields extracted from E*TRADE document")

        stmt = Statement(
            id=ctx.statement_id,
            document_id=uuid.uuid4(),  # overwritten by agent
            institution_id=ETRADE_INSTITUTION.id,
            institution_type=InstitutionType.ETRADE,
            account_id=account.id,
            account_type=account_type,
            statement_type=statement_type,
            period=period,
            balance_snapshots=balance_snapshots,
            transactions=transactions,
            fees=fees,
            holdings=holdings,
            cash_flow=cash_flow,
            extraction_status=status,
            overall_confidence=round(overall, 3),
            extraction_notes=ctx.warnings,
        )
        logger.info(
            "etrade_extractor.done",
            holdings=len(holdings),
            transactions=len(transactions),
            confidence=overall,
        )
        return stmt

    def _extract_account(
        self, document: ParsedDocument, account_type: AccountType
    ) -> Account:
        sample = "\n".join(p.raw_text for p in document.pages[:2])
        account_number = "****0000"
        m = _ACCOUNT_RE.search(sample)
        if m:
            raw = re.sub(r"[^\d]", "", m.group(1))
            account_number = f"****{raw[-4:]}" if len(raw) >= 4 else "****" + raw
        return Account(
            institution_id=ETRADE_INSTITUTION.id,
            institution_type=InstitutionType.ETRADE,
            account_number_masked=account_number,
            account_name="E*TRADE Brokerage",
            account_type=account_type,
        )

    def _extract_period(
        self, document: ParsedDocument, ctx: _Ctx
    ) -> StatementPeriod:
        sample = "\n".join(p.raw_text for p in document.pages[:3])
        m = _PERIOD_RE.search(sample)
        if m:
            start = _parse_date(m.group(1))
            end = _parse_date(m.group(2))
            if start and end:
                ctx.add_fc("period", True, 0.90)
                return StatementPeriod(start_date=start, end_date=end)

        # Fallback: scan for dates
        date_re = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b|"
                              r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s*\d{4})\b",
                              re.IGNORECASE)
        dates: list[date] = []
        for dm in date_re.finditer(sample):
            ds = next((g for g in dm.groups() if g), None)
            if ds:
                d = _parse_date(ds)
                if d:
                    dates.append(d)
        if len(dates) >= 2:
            dates.sort()
            ctx.add_fc("period", True, 0.55, "inferred")
            return StatementPeriod(start_date=dates[0], end_date=dates[-1])

        today = date.today()
        ctx.add_fc("period", False, 0.10)
        ctx.warnings.append("Statement period not found; using current month")
        return StatementPeriod(start_date=today.replace(day=1), end_date=today)

    def _extract_balances(
        self,
        document: ParsedDocument,
        ctx: _Ctx,
        period: StatementPeriod,
    ) -> list[BalanceSnapshot]:
        snapshots: list[BalanceSnapshot] = []
        full = "\n".join(p.raw_text for p in document.pages[:4])

        m = _PORTFOLIO_VALUE_RE.search(full)
        if m:
            amt = _parse_decimal(m.group(1))
            if amt is not None and amt > 0:
                cash_m = _CASH_BALANCE_RE.search(full)
                cash = _parse_decimal(cash_m.group(1)) if cash_m else None
                snapshots.append(BalanceSnapshot(
                    account_id=ctx.account_id,
                    statement_id=ctx.statement_id,
                    snapshot_date=period.end_date,
                    total_value=amt,
                    cash_value=cash,
                    invested_value=(amt - cash) if cash else None,
                    confidence=0.85,
                    source=SourceLocation(section="Portfolio Summary", raw_text=m.group(0)),
                ))
                ctx.add_fc("balance", True, 0.85)
                return snapshots

        ctx.add_fc("balance", False, 0.0)
        ctx.warnings.append("No portfolio value found")
        return snapshots

    def _extract_holdings(
        self, document: ParsedDocument, ctx: _Ctx
    ) -> list[Holding]:
        holdings: list[Holding] = []
        pattern = _SECTION_HEADERS["holdings"]
        holding_pages = [p for p in document.pages if pattern.search(p.raw_text)]

        for page in holding_pages:
            for table in page.tables:
                holdings.extend(self._parse_holding_table(table, ctx))

        ctx.add_fc("holdings", bool(holdings), 0.75 if holdings else 0.0, "table")
        return holdings

    def _parse_holding_table(
        self, table: ParsedTable, ctx: _Ctx
    ) -> list[Holding]:
        holdings: list[Holding] = []
        headers = [str(h or "").lower().strip() for h in (table.header_row or [])]

        symbol_col = _col(headers, ["symbol", "ticker"])
        desc_col = _col(headers, ["description", "security", "name"])
        qty_col = _col(headers, ["quantity", "shares", "units"])
        price_col = _col(headers, ["price", "unit price", "last price"])
        value_col = _col(headers, ["market value", "value", "total value"])
        cost_col = _col(headers, ["cost basis", "cost", "total cost"])
        gain_col = _col(headers, ["unrealized", "gain/loss", "gain loss"])

        for row in table.rows:
            if not row or all((c or "").strip() == "" for c in row):
                continue
            try:
                symbol = _cell(row, symbol_col) or None
                desc = _cell(row, desc_col)
                value_str = _cell(row, value_col)
                market_value = _parse_decimal(value_str)

                if market_value is None or market_value <= 0:
                    continue

                holdings.append(Holding(
                    account_id=ctx.account_id,
                    statement_id=ctx.statement_id,
                    symbol=symbol,
                    description=desc or symbol or "Unknown",
                    quantity=_parse_decimal(_cell(row, qty_col)),
                    price=_parse_decimal(_cell(row, price_col)),
                    market_value=market_value,
                    cost_basis=_parse_decimal(_cell(row, cost_col)),
                    unrealized_gain_loss=_parse_decimal(_cell(row, gain_col)),
                    confidence=0.78,
                    source=SourceLocation(page=table.page_number, section="Holdings"),
                ))
            except Exception as exc:
                logger.debug("etrade.holding.row.skip", error=str(exc))

        return holdings

    def _extract_transactions(
        self, document: ParsedDocument, ctx: _Ctx
    ) -> list[Transaction]:
        transactions: list[Transaction] = []
        pattern = _SECTION_HEADERS["transactions"]
        tx_pages = [p for p in document.pages if pattern.search(p.raw_text)]

        for page in tx_pages:
            for table in page.tables:
                transactions.extend(self._parse_transaction_table(table, ctx))

        ctx.add_fc(
            "transactions",
            bool(transactions),
            0.78 if transactions else 0.0,
            "table",
        )
        return transactions

    def _parse_transaction_table(
        self, table: ParsedTable, ctx: _Ctx
    ) -> list[Transaction]:
        txns: list[Transaction] = []
        headers = [str(h or "").lower().strip() for h in (table.header_row or [])]
        date_col = _col(headers, ["date", "trade date", "transaction date"])
        desc_col = _col(headers, ["description", "activity", "transaction"])
        amount_col = _col(headers, ["amount", "net amount", "value"])
        symbol_col = _col(headers, ["symbol", "ticker"])
        qty_col = _col(headers, ["quantity", "shares"])
        price_col = _col(headers, ["price", "per share"])

        if date_col is None:
            return []

        for row in table.rows:
            if not row or all((c or "").strip() == "" for c in row):
                continue
            try:
                date_str = _cell(row, date_col)
                desc = _cell(row, desc_col)
                tx_date = _parse_date(date_str)
                amount = _parse_decimal(_cell(row, amount_col))

                if not tx_date or not desc or amount is None:
                    continue

                tx_type = _classify_etrade_txn_type(desc, amount)
                txns.append(Transaction(
                    account_id=ctx.account_id,
                    statement_id=ctx.statement_id,
                    transaction_date=tx_date,
                    description=desc,
                    transaction_type=tx_type,
                    amount=amount,
                    symbol=_cell(row, symbol_col) or None,
                    quantity=_parse_decimal(_cell(row, qty_col)),
                    price_per_unit=_parse_decimal(_cell(row, price_col)),
                    confidence=0.80,
                    source=SourceLocation(page=table.page_number, section="Transactions"),
                ))
            except Exception as exc:
                logger.debug("etrade.txn.row.skip", error=str(exc))

        return txns

    def _extract_fees(
        self, document: ParsedDocument, ctx: _Ctx
    ) -> list[Fee]:
        fees: list[Fee] = []
        # Promote fee-type transactions
        pattern = _SECTION_HEADERS["fees"]
        fee_re = re.compile(
            r"(?:commission|account\s+fee|transfer\s+fee|trading\s+fee)\s*[:\-]?\s*"
            r"\$?\s*([\d,]+\.\d{2})",
            re.IGNORECASE,
        )
        for page in document.pages:
            for m in fee_re.finditer(page.raw_text):
                amt = _parse_decimal(m.group(1))
                if amt and amt > 0:
                    fees.append(Fee(
                        account_id=ctx.account_id,
                        statement_id=ctx.statement_id,
                        fee_date=date.today(),
                        description=m.group(0).split(":")[0].strip(),
                        amount=amt,
                        fee_category="trading",
                        confidence=0.72,
                        source=SourceLocation(page=page.page_number, section="Fees"),
                    ))
        ctx.add_fc("fees", bool(fees), 0.72 if fees else 0.30, "regex")
        return fees

    def _compute_cash_flow(
        self, transactions: list[Transaction], fees: list[Fee]
    ) -> CashFlow:
        deposits = sum(t.amount for t in transactions
                       if t.transaction_type in (TransactionType.DEPOSIT, TransactionType.DIVIDEND,
                                                  TransactionType.INTEREST) and t.amount > 0)
        withdrawals = abs(sum(t.amount for t in transactions
                              if t.transaction_type == TransactionType.WITHDRAWAL and t.amount < 0))
        fee_total = sum(f.amount for f in fees)
        dividends = sum(t.amount for t in transactions if t.transaction_type == TransactionType.DIVIDEND)
        interest = sum(t.amount for t in transactions if t.transaction_type == TransactionType.INTEREST)
        return CashFlow(
            total_deposits=deposits,
            total_withdrawals=withdrawals,
            total_fees=fee_total,
            total_dividends=dividends,
            total_interest=interest,
            net_cash_flow=deposits - withdrawals - fee_total,
        )


# ── Utilities ─────────────────────────────────────────────────────────────────

def _col(headers: list[str], candidates: list[str]) -> int | None:
    for c in candidates:
        for i, h in enumerate(headers):
            if c in h:
                return i
    return None


def _cell(row: list, idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return str(row[idx] or "").strip()


def _classify_etrade_txn_type(desc: str, amount: Decimal) -> TransactionType:
    lower = desc.lower()
    if any(w in lower for w in ["bought", "buy", "purchase"]):
        return TransactionType.TRADE_BUY
    if any(w in lower for w in ["sold", "sell", "sale"]):
        return TransactionType.TRADE_SELL
    if any(w in lower for w in ["dividend", "div"]):
        return TransactionType.DIVIDEND
    if any(w in lower for w in ["interest"]):
        return TransactionType.INTEREST
    if any(w in lower for w in ["commission", "fee"]):
        return TransactionType.FEE
    if any(w in lower for w in ["deposit", "contribution", "transfer in"]):
        return TransactionType.DEPOSIT
    if any(w in lower for w in ["withdrawal", "transfer out"]):
        return TransactionType.WITHDRAWAL
    if "tax" in lower:
        return TransactionType.TAX_WITHHOLDING
    if amount > 0:
        return TransactionType.DEPOSIT
    return TransactionType.OTHER
