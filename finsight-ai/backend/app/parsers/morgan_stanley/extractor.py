"""
Morgan Stanley statement structured data extractor.

Architecture:
- Section-based extraction: identify logical sections of the statement
  (Account Summary, Holdings, Transaction History, Fee Detail, etc.)
  then apply targeted extraction to each section.
- Hybrid approach: regex for structured fields (dates, dollar amounts,
  account numbers), LLM for narrative/semi-structured sections.
- Each extracted value carries a SourceLocation so the UI can show
  users exactly where data came from.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

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
from app.ollama.model_router import ModelRouter, TaskType, get_model_router
from app.parsers.base import ParsedDocument, ParsedPage, ParsedTable

logger = structlog.get_logger(__name__)

# ── Regex patterns ─────────────────────────────────────────────────────────────

# Date patterns: "January 31, 2026", "01/31/2026", "2026-01-31"
_DATE_PATTERNS = [
    r"(\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b)",
    r"(\b\d{1,2}/\d{1,2}/\d{4}\b)",
    r"(\b\d{4}-\d{2}-\d{2}\b)",
]
_DATE_RE = re.compile("|".join(_DATE_PATTERNS), re.IGNORECASE)

# Dollar amounts: "$1,234,567.89", "($1,234.56)", "1,234.56"
_AMOUNT_RE = re.compile(
    r"\(?\$?\s*([\d,]+\.?\d*)\)?",
    re.IGNORECASE,
)

# Account number patterns
_ACCOUNT_RE = re.compile(
    r"(?:account\s+(?:number|#|no\.?)\s*[:\-]?\s*)([X*\d]{4,}[-\s]?[X*\d]+)",
    re.IGNORECASE,
)

# Statement period: "For the period January 1, 2026 to January 31, 2026"
_PERIOD_RE = re.compile(
    r"(?:for\s+the\s+period|statement\s+period)\s+"
    r"(.+?)\s+(?:to|through)\s+(.+?)(?:\n|$)",
    re.IGNORECASE,
)

# Advisory fee patterns
_FEE_RE = re.compile(
    r"(?:advisory|management|portfolio|investment)\s+fee[s]?\s*[:\-]?\s*"
    r"\(?\$?\s*([\d,]+\.?\d*)\)?",
    re.IGNORECASE,
)

# Balance/value patterns
_BALANCE_RE = re.compile(
    r"(?:total\s+(?:account\s+)?(?:value|balance|assets)|"
    r"net\s+(?:asset\s+)?value|portfolio\s+(?:value|balance))\s*[:\-]?\s*"
    r"\(?\$?\s*([\d,]+\.?\d*)\)?",
    re.IGNORECASE,
)

# Section headers common in Morgan Stanley statements
_SECTION_HEADERS = {
    "account_summary": re.compile(
        r"account\s+summary|portfolio\s+overview|account\s+overview", re.IGNORECASE
    ),
    "holdings": re.compile(
        r"portfolio\s+detail|holdings|positions|securities\s+held", re.IGNORECASE
    ),
    "transactions": re.compile(
        r"transaction\s+(history|detail|summary)|activity\s+detail", re.IGNORECASE
    ),
    "fees": re.compile(
        r"fee\s+(detail|schedule|summary)|advisory\s+fee|charges?\s+and\s+fees?",
        re.IGNORECASE,
    ),
    "cash_flow": re.compile(
        r"cash\s+(flow|activity)|money\s+movement", re.IGNORECASE
    ),
}


def _parse_decimal(text: str) -> Decimal | None:
    """Parse a currency string to Decimal, handling parentheses as negative."""
    if not text:
        return None
    is_negative = text.strip().startswith("(") or text.strip().startswith("-")
    cleaned = re.sub(r"[^\d.]", "", text)
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
        return -value if is_negative else value
    except InvalidOperation:
        return None


def _parse_date_str(text: str) -> date | None:
    """Parse a date string into a date object."""
    from dateutil import parser as dateutil_parser
    try:
        return dateutil_parser.parse(text.strip(), fuzzy=True).date()
    except Exception:
        return None


@dataclass
class ExtractionContext:
    """Shared state for a single extraction run."""

    document: ParsedDocument
    institution_id: uuid.UUID
    account_id: uuid.UUID
    statement_id: uuid.UUID
    statement_type: StatementType
    field_confidences: list[FieldConfidence]
    warnings: list[str]

    def add_confidence(
        self,
        field_name: str,
        was_found: bool,
        confidence: float,
        method: str = "regex",
        notes: str | None = None,
    ) -> None:
        self.field_confidences.append(
            FieldConfidence(
                field_name=field_name,
                was_found=was_found,
                confidence=confidence,
                extraction_method=method,
                notes=notes,
            )
        )


class MorganStanleyExtractor:
    """
    Extracts structured financial data from Morgan Stanley statements.

    Implements a section-aware hybrid extraction strategy.
    """

    MS_INSTITUTION = FinancialInstitution(
        name="Morgan Stanley",
        institution_type=InstitutionType.MORGAN_STANLEY,
        website="https://www.morganstanley.com",
    )

    def __init__(self, model_router: ModelRouter | None = None) -> None:
        self._router = model_router or get_model_router()

    async def extract(
        self,
        document: ParsedDocument,
        statement_type: StatementType,
    ) -> Statement:
        """
        Extract a complete Statement from a parsed document.

        Args:
            document: The parsed PDF document
            statement_type: Pre-classified statement type

        Returns:
            A Statement domain entity populated with extracted data.
        """
        institution = self.MS_INSTITUTION
        account = self._extract_account(document)
        ctx = ExtractionContext(
            document=document,
            institution_id=institution.id,
            account_id=account.id,
            statement_id=uuid.uuid4(),
            statement_type=statement_type,
            field_confidences=[],
            warnings=[],
        )

        period = await self._extract_period(document, ctx)
        balance_snapshots = self._extract_balances(document, ctx, period)
        transactions = self._extract_transactions(document, ctx)
        fees = self._extract_fees(document, ctx)
        holdings = self._extract_holdings(document, ctx)
        cash_flow = self._compute_cash_flow(transactions, fees)

        # Determine overall extraction status and confidence
        found_fields = [fc for fc in ctx.field_confidences if fc.was_found]
        overall_confidence = (
            sum(fc.confidence for fc in found_fields) / len(ctx.field_confidences)
            if ctx.field_confidences
            else 0.0
        )

        status = ExtractionStatus.SUCCESS
        if overall_confidence < 0.4:
            status = ExtractionStatus.PARTIAL
        if not transactions and not balance_snapshots:
            status = ExtractionStatus.PARTIAL
            ctx.warnings.append("No transactions or balances found — check document quality")

        statement = Statement(
            id=ctx.statement_id,
            document_id=uuid.uuid4(),  # Will be set by the agent with the real document_id
            institution_id=institution.id,
            institution_type=InstitutionType.MORGAN_STANLEY,
            account_id=account.id,
            account_type=account.account_type,
            statement_type=statement_type,
            period=period,
            balance_snapshots=balance_snapshots,
            transactions=transactions,
            fees=fees,
            holdings=holdings,
            cash_flow=cash_flow,
            extraction_status=status,
            overall_confidence=round(overall_confidence, 3),
            extraction_notes=ctx.warnings,
        )

        logger.info(
            "extractor.done",
            statement_id=str(ctx.statement_id),
            transactions=len(transactions),
            fees=len(fees),
            holdings=len(holdings),
            confidence=overall_confidence,
        )
        return statement

    # Account type detection patterns
    _IRA_RE = re.compile(r"\b(?:traditional|rollover|inherited)?\s*ira\b", re.IGNORECASE)
    _ROTH_RE = re.compile(r"\broth\s+ira\b", re.IGNORECASE)
    _ADVISORY_RE = re.compile(r"\b(?:advisory|managed|discretionary|portfolio\s+management)\b", re.IGNORECASE)

    def _extract_account(self, document: ParsedDocument) -> Account:
        """Extract account number and type from first page header."""
        account_number = "****0000"  # Default masked fallback

        # Sample first two pages for account detection
        sample = "\n".join(p.raw_text for p in document.pages[:2])

        for page in document.pages[:2]:
            match = _ACCOUNT_RE.search(page.raw_text)
            if match:
                raw_num = match.group(1).strip()
                digits_only = re.sub(r"[^\d]", "", raw_num)
                account_number = f"****{digits_only[-4:]}" if len(digits_only) >= 4 else raw_num
                break

        # Detect account type in priority order: Roth IRA > IRA > Advisory > Brokerage
        if self._ROTH_RE.search(sample):
            account_type = AccountType.ROTH_IRA
            account_name = "Morgan Stanley Roth IRA"
        elif self._IRA_RE.search(sample):
            account_type = AccountType.IRA
            account_name = "Morgan Stanley IRA"
        elif self._ADVISORY_RE.search(sample):
            account_type = AccountType.ADVISORY
            account_name = "Morgan Stanley Advisory Account"
        else:
            account_type = AccountType.INDIVIDUAL_BROKERAGE
            account_name = "Morgan Stanley Brokerage Account"

        return Account(
            institution_id=self.MS_INSTITUTION.id,
            institution_type=InstitutionType.MORGAN_STANLEY,
            account_number_masked=account_number,
            account_type=account_type,
            account_name=account_name,
        )

    async def _extract_period(
        self, document: ParsedDocument, ctx: ExtractionContext
    ) -> StatementPeriod:
        """Extract the statement date range."""
        first_pages_text = "\n".join(p.raw_text for p in document.pages[:3])

        match = _PERIOD_RE.search(first_pages_text)
        if match:
            start_str, end_str = match.group(1), match.group(2)
            start_date = _parse_date_str(start_str)
            end_date = _parse_date_str(end_str)
            if start_date and end_date:
                ctx.add_confidence("period", True, 0.9, "regex")
                return StatementPeriod(start_date=start_date, end_date=end_date)

        # Find any dates in the first page and use them
        all_dates = []
        for match in _DATE_RE.finditer(first_pages_text):
            date_str = next(g for g in match.groups() if g)
            parsed = _parse_date_str(date_str)
            if parsed:
                all_dates.append(parsed)

        if len(all_dates) >= 2:
            all_dates.sort()
            ctx.add_confidence("period", True, 0.6, "regex", "inferred from date mentions")
            return StatementPeriod(start_date=all_dates[0], end_date=all_dates[-1])

        # Fallback: use today
        from datetime import date as dt_date
        today = dt_date.today()
        ctx.add_confidence("period", False, 0.1, "fallback")
        ctx.warnings.append("Statement period could not be determined; using current month")
        return StatementPeriod(
            start_date=today.replace(day=1),
            end_date=today,
        )

    def _extract_balances(
        self,
        document: ParsedDocument,
        ctx: ExtractionContext,
        period: StatementPeriod,
    ) -> list[BalanceSnapshot]:
        """Extract account balance/value snapshots."""
        snapshots: list[BalanceSnapshot] = []

        for page in document.pages:
            match = _BALANCE_RE.search(page.raw_text)
            if match:
                amount = _parse_decimal(match.group(1))
                if amount and amount > 0:
                    snapshot = BalanceSnapshot(
                        account_id=ctx.account_id,
                        statement_id=ctx.statement_id,
                        snapshot_date=period.end_date,
                        total_value=amount,
                        currency="USD",
                        confidence=0.8,
                        source=SourceLocation(
                            page=page.page_number,
                            section="Account Summary",
                            raw_text=match.group(0),
                        ),
                    )
                    snapshots.append(snapshot)
                    ctx.add_confidence("balance", True, 0.8, "regex")
                    break  # Take first match only

        if not snapshots:
            ctx.add_confidence("balance", False, 0.0)
            ctx.warnings.append("No account balance found")

        return snapshots

    def _extract_transactions(
        self, document: ParsedDocument, ctx: ExtractionContext
    ) -> list[Transaction]:
        """Extract transactions from table-formatted transaction sections."""
        transactions: list[Transaction] = []
        transaction_pages = self._find_section_pages(document, "transactions")

        for page in transaction_pages:
            for table in page.tables:
                extracted = self._parse_transaction_table(table, ctx)
                transactions.extend(extracted)

        ctx.add_confidence(
            "transactions",
            len(transactions) > 0,
            0.75 if transactions else 0.0,
            "table",
        )
        return transactions

    def _extract_fees(
        self, document: ParsedDocument, ctx: ExtractionContext
    ) -> list[Fee]:
        """Extract fees from both regex matches and fee-specific tables."""
        fees: list[Fee] = []

        for page in document.pages:
            # Regex-based fee extraction
            for match in _FEE_RE.finditer(page.raw_text):
                amount = _parse_decimal(match.group(1))
                if amount and amount > 0:
                    # Find the date nearest to this fee mention
                    fee_date = ctx.document.pages[0].raw_text  # placeholder
                    from datetime import date as dt_date
                    fee = Fee(
                        account_id=ctx.account_id,
                        statement_id=ctx.statement_id,
                        fee_date=dt_date.today(),  # Will be improved with date extraction
                        description=match.group(0).split(":")[0].strip(),
                        amount=amount,
                        fee_category="advisory",
                        currency="USD",
                        confidence=0.75,
                        source=SourceLocation(
                            page=page.page_number,
                            section="Fee Detail",
                            raw_text=match.group(0),
                        ),
                    )
                    fees.append(fee)

            # Table-based fee extraction
            for table in page.tables:
                if self._looks_like_fee_table(table):
                    extracted = self._parse_fee_table(table, ctx, page.page_number)
                    fees.extend(extracted)

        ctx.add_confidence("fees", len(fees) > 0, 0.75 if fees else 0.3, "hybrid")
        return fees

    def _extract_holdings(
        self, document: ParsedDocument, ctx: ExtractionContext
    ) -> list[Holding]:
        """Extract security holdings from portfolio detail tables."""
        holdings: list[Holding] = []
        holding_pages = self._find_section_pages(document, "holdings")

        for page in holding_pages:
            for table in page.tables:
                extracted = self._parse_holding_table(table, ctx)
                holdings.extend(extracted)

        ctx.add_confidence("holdings", len(holdings) > 0, 0.7 if holdings else 0.0, "table")
        return holdings

    def _compute_cash_flow(
        self, transactions: list[Transaction], fees: list[Fee]
    ) -> CashFlow:
        """Aggregate cash flow totals from transactions."""
        deposits = sum(
            t.amount for t in transactions
            if t.transaction_type in (TransactionType.DEPOSIT, TransactionType.DIVIDEND,
                                       TransactionType.INTEREST)
            and t.amount > 0
        )
        withdrawals = abs(sum(
            t.amount for t in transactions
            if t.transaction_type == TransactionType.WITHDRAWAL
            and t.amount < 0
        ))
        fee_total = sum(f.amount for f in fees)
        dividends = sum(
            t.amount for t in transactions
            if t.transaction_type == TransactionType.DIVIDEND
        )
        interest = sum(
            t.amount for t in transactions
            if t.transaction_type == TransactionType.INTEREST
        )

        return CashFlow(
            total_deposits=deposits,
            total_withdrawals=withdrawals,
            total_fees=fee_total,
            total_dividends=dividends,
            total_interest=interest,
            net_cash_flow=deposits - withdrawals - fee_total,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _find_section_pages(
        self, document: ParsedDocument, section_key: str
    ) -> list[ParsedPage]:
        """Return pages that appear to belong to a logical statement section."""
        pattern = _SECTION_HEADERS.get(section_key)
        if not pattern:
            return []
        return [p for p in document.pages if pattern.search(p.raw_text)]

    def _parse_transaction_table(
        self, table: ParsedTable, ctx: ExtractionContext
    ) -> list[Transaction]:
        """Parse a table that looks like a transaction listing."""
        transactions: list[Transaction] = []
        headers = [h.lower() for h in (table.header_row or [])]

        # Try to identify column positions
        date_col = self._find_col(headers, ["date", "trade date", "transaction date"])
        desc_col = self._find_col(headers, ["description", "activity", "transaction"])
        amount_col = self._find_col(headers, ["amount", "debit", "credit", "value"])
        type_col = self._find_col(headers, ["type", "transaction type"])

        if date_col is None and amount_col is None:
            return []  # Can't identify columns

        for row in table.rows:
            if not row or all(cell == "" for cell in row):
                continue

            try:
                date_str = row[date_col] if date_col is not None and date_col < len(row) else ""
                desc = row[desc_col] if desc_col is not None and desc_col < len(row) else ""
                amount_str = row[amount_col] if amount_col is not None and amount_col < len(row) else ""

                tx_date = _parse_date_str(date_str)
                amount = _parse_decimal(amount_str)

                if tx_date is None or amount is None or desc == "":
                    continue

                tx_type = self._classify_transaction_type(desc)

                transactions.append(
                    Transaction(
                        account_id=ctx.account_id,
                        statement_id=ctx.statement_id,
                        transaction_date=tx_date,
                        description=desc,
                        transaction_type=tx_type,
                        amount=amount,
                        confidence=0.8,
                        source=SourceLocation(
                            page=table.page_number,
                            section="Transaction History",
                        ),
                    )
                )
            except Exception as exc:
                logger.debug("transaction.row.skip", error=str(exc))
                continue

        return transactions

    def _parse_fee_table(
        self, table: ParsedTable, ctx: ExtractionContext, page_number: int
    ) -> list[Fee]:
        """Parse a table that contains fee line items."""
        fees: list[Fee] = []
        from datetime import date as dt_date

        for row in table.rows:
            if not row or all(cell == "" for cell in row):
                continue
            # Look for any amount in the row
            for i, cell in enumerate(row):
                amount = _parse_decimal(cell)
                if amount and amount > 0 and amount < Decimal("100000"):
                    desc_cells = [c for j, c in enumerate(row) if j != i and c]
                    desc = " ".join(desc_cells[:2]) if desc_cells else "Fee"
                    fees.append(
                        Fee(
                            account_id=ctx.account_id,
                            statement_id=ctx.statement_id,
                            fee_date=dt_date.today(),
                            description=desc,
                            amount=amount,
                            fee_category="advisory",
                            confidence=0.65,
                            source=SourceLocation(page=page_number, section="Fee Detail"),
                        )
                    )
                    break

        return fees

    def _parse_holding_table(
        self, table: ParsedTable, ctx: ExtractionContext
    ) -> list[Holding]:
        """Parse a portfolio holdings table."""
        holdings: list[Holding] = []
        headers = [h.lower() for h in (table.header_row or [])]

        symbol_col = self._find_col(headers, ["symbol", "ticker", "cusip"])
        desc_col = self._find_col(headers, ["description", "security", "name"])
        qty_col = self._find_col(headers, ["quantity", "shares", "units"])
        price_col = self._find_col(headers, ["price", "unit price", "market price"])
        value_col = self._find_col(
            headers, ["market value", "value", "total value", "current value"]
        )

        for row in table.rows:
            if not row or all(cell == "" for cell in row):
                continue
            try:
                symbol = row[symbol_col].strip() if symbol_col is not None and symbol_col < len(row) else None
                desc = row[desc_col].strip() if desc_col is not None and desc_col < len(row) else ""
                qty_str = row[qty_col] if qty_col is not None and qty_col < len(row) else ""
                price_str = row[price_col] if price_col is not None and price_col < len(row) else ""
                value_str = row[value_col] if value_col is not None and value_col < len(row) else ""

                market_value = _parse_decimal(value_str)
                if market_value is None or market_value <= 0:
                    continue

                holdings.append(
                    Holding(
                        account_id=ctx.account_id,
                        statement_id=ctx.statement_id,
                        symbol=symbol if symbol else None,
                        description=desc or (symbol or "Unknown"),
                        quantity=_parse_decimal(qty_str),
                        price=_parse_decimal(price_str),
                        market_value=market_value,
                        confidence=0.75,
                        source=SourceLocation(
                            page=table.page_number,
                            section="Holdings",
                        ),
                    )
                )
            except Exception as exc:
                logger.debug("holding.row.skip", error=str(exc))

        return holdings

    def _classify_transaction_type(self, description: str) -> TransactionType:
        """Classify a transaction type from its description text."""
        desc_lower = description.lower()
        if any(w in desc_lower for w in ["advisory fee", "management fee", "portfolio fee"]):
            return TransactionType.ADVISORY_FEE
        if any(w in desc_lower for w in ["fee", "charge"]):
            return TransactionType.FEE
        if any(w in desc_lower for w in ["dividend", "div"]):
            return TransactionType.DIVIDEND
        if any(w in desc_lower for w in ["interest", "int"]):
            return TransactionType.INTEREST
        if any(w in desc_lower for w in ["deposit", "contribution", "transfer in"]):
            return TransactionType.DEPOSIT
        if any(w in desc_lower for w in ["withdrawal", "transfer out", "disbursement"]):
            return TransactionType.WITHDRAWAL
        if any(w in desc_lower for w in ["bought", "buy", "purchase"]):
            return TransactionType.TRADE_BUY
        if any(w in desc_lower for w in ["sold", "sell", "sale"]):
            return TransactionType.TRADE_SELL
        if "tax" in desc_lower:
            return TransactionType.TAX_WITHHOLDING
        return TransactionType.OTHER

    def _looks_like_fee_table(self, table: ParsedTable) -> bool:
        """Heuristic: does this table look like it contains fee line items?"""
        combined = " ".join(
            cell for row in table.rows for cell in row if cell
        ).lower()
        fee_words = ["fee", "charge", "advisory", "management", "commission"]
        return sum(1 for w in fee_words if w in combined) >= 2

    @staticmethod
    def _find_col(headers: list[str], candidates: list[str]) -> int | None:
        """Find the index of the first matching column header."""
        for candidate in candidates:
            for i, header in enumerate(headers):
                if candidate in header:
                    return i
        return None
