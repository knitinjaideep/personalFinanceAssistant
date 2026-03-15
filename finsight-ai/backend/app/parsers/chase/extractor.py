"""
Chase statement extractor.

Supports:
- Checking accounts: transactions (debits/credits), beginning/ending balance,
  direct deposits, ATM withdrawals, debit card purchases
- Credit cards: transactions (purchases/payments/fees), statement balance,
  minimum payment, credit limit, payment due date

Strategy:
- Regex for structured fields (dates, amounts, account numbers)
- Table parsing for transaction listings
- Section detection for checking vs credit card layouts
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
from app.services.normalization.merchant_normalizer import MerchantNormalizer

logger = structlog.get_logger(__name__)

# ── Regex patterns ─────────────────────────────────────────────────────────────

_AMOUNT_RE = re.compile(r"\(?\$?\s*([\d,]+\.\d{2})\)?")
_DATE_RE = re.compile(
    r"\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b|"
    r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s*\d{4})\b",
    re.IGNORECASE,
)
_ACCOUNT_RE = re.compile(
    r"account\s*(?:number|#|no\.?)?\s*[:\-]?\s*(?:ending\s+in\s+)?([xX*\d]{4,}[-\s]?[xX*\d]*)",
    re.IGNORECASE,
)

# Checking balance patterns
_BEGIN_BALANCE_RE = re.compile(
    r"(?:beginning|opening|previous)\s+balance\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)
_END_BALANCE_RE = re.compile(
    r"(?:ending|closing)\s+balance\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)
_AVAIL_BALANCE_RE = re.compile(
    r"available\s+balance\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)

# Credit card balance patterns
_STMT_BALANCE_RE = re.compile(
    r"(?:statement|new)\s+balance\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)
_MIN_PAYMENT_RE = re.compile(
    r"minimum\s+payment\s+due\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)
_CREDIT_LIMIT_RE = re.compile(
    r"credit\s+limit\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d{2})?)",
    re.IGNORECASE,
)
_PREV_BALANCE_RE = re.compile(
    r"previous\s+balance\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)

# Statement period
_PERIOD_RE = re.compile(
    r"(?:statement\s+period|for\s+the\s+period|billing\s+period)\s*[:\-]?\s*"
    r"(\w[\w\s,]+?)\s+(?:through|to|-)\s+(\w[\w\s,]+?)(?:\n|$)",
    re.IGNORECASE,
)

# Card name from header
_CARD_NAME_RE = re.compile(
    r"((?:Chase\s+)?(?:Sapphire|Freedom|United|Southwest|Ink|Total\s+Checking)[^\n]*)",
    re.IGNORECASE,
)


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
    text = text.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m/%d", "%B %d, %Y", "%b %d, %Y",
                "%B %d %Y", "%b %d %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.year == 1900:
                parsed = parsed.replace(year=datetime.today().year)
            return parsed.date()
        except ValueError:
            continue
    try:
        from dateutil import parser as du
        return du.parse(text, fuzzy=True).date()
    except Exception:
        return None


@dataclass
class _Ctx:
    """Extraction context for a single Chase document."""
    document: ParsedDocument
    institution_id: uuid.UUID
    account_id: uuid.UUID
    statement_id: uuid.UUID
    account_type: AccountType
    field_confidences: list[FieldConfidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_fc(self, name: str, found: bool, conf: float, method: str = "regex") -> None:
        self.field_confidences.append(
            FieldConfidence(field_name=name, was_found=found,
                            confidence=conf, extraction_method=method)
        )


CHASE_INSTITUTION = FinancialInstitution(
    name="Chase",
    institution_type=InstitutionType.CHASE,
    website="https://www.chase.com",
)


class ChaseExtractor:
    """Extracts structured financial data from Chase statements."""

    def __init__(self, normalizer: MerchantNormalizer | None = None) -> None:
        self._normalizer = normalizer or MerchantNormalizer()

    async def extract(
        self,
        document: ParsedDocument,
        account_type: AccountType,
        statement_type: StatementType,
    ) -> Statement:
        """
        Extract a complete Statement from a Chase document.

        Args:
            document: Parsed PDF
            account_type: CHECKING or CREDIT_CARD (pre-classified)
            statement_type: BANK or CREDIT_CARD
        """
        account = self._extract_account(document, account_type)
        ctx = _Ctx(
            document=document,
            institution_id=CHASE_INSTITUTION.id,
            account_id=account.id,
            statement_id=uuid.uuid4(),
            account_type=account_type,
        )

        period = self._extract_period(document, ctx)
        balance_snapshots = self._extract_balances(document, ctx, period)
        transactions = self._extract_transactions(document, ctx)
        fees = self._extract_fees_from_transactions(transactions, ctx)
        cash_flow = self._compute_cash_flow(transactions, fees)

        found_fc = [f for f in ctx.field_confidences if f.was_found]
        overall = (
            sum(f.confidence for f in found_fc) / len(ctx.field_confidences)
            if ctx.field_confidences else 0.0
        )
        status = ExtractionStatus.SUCCESS
        if overall < 0.4 or (not transactions and not balance_snapshots):
            status = ExtractionStatus.PARTIAL
            ctx.warnings.append("Limited fields extracted — check document quality")

        stmt = Statement(
            id=ctx.statement_id,
            document_id=uuid.uuid4(),  # overwritten by agent
            institution_id=CHASE_INSTITUTION.id,
            institution_type=InstitutionType.CHASE,
            account_id=account.id,
            account_type=account_type,
            statement_type=statement_type,
            period=period,
            balance_snapshots=balance_snapshots,
            transactions=transactions,
            fees=fees,
            holdings=[],
            cash_flow=cash_flow,
            extraction_status=status,
            overall_confidence=round(overall, 3),
            extraction_notes=ctx.warnings,
        )
        logger.info(
            "chase_extractor.done",
            account_type=account_type.value,
            transactions=len(transactions),
            fees=len(fees),
            confidence=overall,
        )
        return stmt

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _extract_account(
        self, document: ParsedDocument, account_type: AccountType
    ) -> Account:
        sample = "\n".join(p.raw_text for p in document.pages[:2])
        account_number = "****0000"
        m = _ACCOUNT_RE.search(sample)
        if m:
            raw = re.sub(r"[^\d]", "", m.group(1))
            account_number = f"****{raw[-4:]}" if len(raw) >= 4 else "****" + raw

        # Try to find card name
        name_m = _CARD_NAME_RE.search(sample)
        account_name = name_m.group(1).strip() if name_m else (
            "Chase Checking" if account_type == AccountType.CHECKING else "Chase Credit Card"
        )
        return Account(
            institution_id=CHASE_INSTITUTION.id,
            institution_type=InstitutionType.CHASE,
            account_number_masked=account_number,
            account_name=account_name,
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

        # Fallback: scan for any dates and use min/max
        dates: list[date] = []
        for match in _DATE_RE.finditer(sample):
            ds = next((g for g in match.groups() if g), None)
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

        if ctx.account_type == AccountType.CHECKING:
            for pattern, label in [
                (_END_BALANCE_RE, "Ending Balance"),
                (_BEGIN_BALANCE_RE, "Beginning Balance"),
                (_AVAIL_BALANCE_RE, "Available Balance"),
            ]:
                m = pattern.search(full)
                if m:
                    amt = _parse_decimal(m.group(1))
                    if amt is not None:
                        snapshots.append(BalanceSnapshot(
                            account_id=ctx.account_id,
                            statement_id=ctx.statement_id,
                            snapshot_date=period.end_date,
                            total_value=amt,
                            confidence=0.85,
                            source=SourceLocation(section=label, raw_text=m.group(0)),
                        ))
                        ctx.add_fc("balance", True, 0.85)
                        break
        else:
            # Credit card
            for pattern, label in [
                (_STMT_BALANCE_RE, "Statement Balance"),
                (_PREV_BALANCE_RE, "Previous Balance"),
            ]:
                m = pattern.search(full)
                if m:
                    amt = _parse_decimal(m.group(1))
                    if amt is not None:
                        snapshots.append(BalanceSnapshot(
                            account_id=ctx.account_id,
                            statement_id=ctx.statement_id,
                            snapshot_date=period.end_date,
                            total_value=amt,
                            confidence=0.85,
                            source=SourceLocation(section=label, raw_text=m.group(0)),
                        ))
                        ctx.add_fc("balance", True, 0.85)
                        break

        if not snapshots:
            ctx.add_fc("balance", False, 0.0)
            ctx.warnings.append("No balance found")

        return snapshots

    def _extract_transactions(
        self, document: ParsedDocument, ctx: _Ctx
    ) -> list[Transaction]:
        transactions: list[Transaction] = []

        for page in document.pages:
            for table in page.tables:
                txns = self._parse_transaction_table(table, ctx)
                transactions.extend(txns)

        # Also try text-based line parsing for pages without tables
        if not transactions:
            for page in document.pages:
                txns = self._parse_transaction_lines(page.raw_text, ctx, page.page_number)
                transactions.extend(txns)

        ctx.add_fc(
            "transactions",
            bool(transactions),
            0.80 if transactions else 0.0,
            "table+text",
        )
        return transactions

    def _parse_transaction_table(
        self, table: ParsedTable, ctx: _Ctx
    ) -> list[Transaction]:
        txns: list[Transaction] = []
        headers = [str(h or "").lower().strip() for h in (table.header_row or [])]

        date_col = _col(headers, ["date", "trans date", "post date"])
        desc_col = _col(headers, ["description", "merchant", "details", "transaction"])
        debit_col = _col(headers, ["debit", "amount", "withdrawals"])
        credit_col = _col(headers, ["credit", "deposits", "additions"])
        amount_col = _col(headers, ["amount"]) if debit_col is None else None

        if date_col is None:
            return []

        for row in table.rows:
            if not row or all((c or "").strip() == "" for c in row):
                continue
            try:
                date_str = _cell(row, date_col)
                desc = _cell(row, desc_col)
                tx_date = _parse_date(date_str)
                if not tx_date or not desc:
                    continue

                # Resolve amount
                if debit_col is not None or credit_col is not None:
                    debit = _parse_decimal(_cell(row, debit_col))
                    credit = _parse_decimal(_cell(row, credit_col))
                    if debit is not None:
                        amount = -abs(debit)
                    elif credit is not None:
                        amount = abs(credit)
                    else:
                        continue
                elif amount_col is not None:
                    amount = _parse_decimal(_cell(row, amount_col))
                    if amount is None:
                        continue
                else:
                    continue

                clean_name, category, _ = self._normalizer.normalize(desc)
                tx_type = _classify_chase_txn_type(desc, amount)
                recurring = self._normalizer.is_recurring(desc)

                txns.append(Transaction(
                    account_id=ctx.account_id,
                    statement_id=ctx.statement_id,
                    transaction_date=tx_date,
                    description=desc,
                    merchant_name=clean_name,
                    transaction_type=tx_type,
                    category=category,
                    amount=amount,
                    is_recurring=recurring,
                    confidence=0.82,
                    source=SourceLocation(
                        page=table.page_number,
                        section="Transactions",
                    ),
                ))
            except Exception as exc:
                logger.debug("chase.txn.row.skip", error=str(exc))

        return txns

    def _parse_transaction_lines(
        self, text: str, ctx: _Ctx, page_num: int
    ) -> list[Transaction]:
        """
        Fallback: parse transaction-like lines from raw text.
        Pattern: date  description  amount
        e.g. "01/15  AMAZON.COM  -$42.99"
        """
        txns: list[Transaction] = []
        # Matches: date (mm/dd or mm/dd/yy) + description + amount
        line_re = re.compile(
            r"^(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+(.+?)\s+(-?\$?[\d,]+\.\d{2})\s*$",
            re.MULTILINE,
        )
        for m in line_re.finditer(text):
            date_str, desc, amt_str = m.group(1), m.group(2).strip(), m.group(3)
            tx_date = _parse_date(date_str)
            amount = _parse_decimal(amt_str)
            if not tx_date or not desc or amount is None:
                continue
            clean_name, category, _ = self._normalizer.normalize(desc)
            txns.append(Transaction(
                account_id=ctx.account_id,
                statement_id=ctx.statement_id,
                transaction_date=tx_date,
                description=desc,
                merchant_name=clean_name,
                transaction_type=_classify_chase_txn_type(desc, amount),
                category=category,
                amount=amount,
                is_recurring=self._normalizer.is_recurring(desc),
                confidence=0.68,
                source=SourceLocation(page=page_num, section="Transactions"),
            ))
        return txns

    def _extract_fees_from_transactions(
        self, transactions: list[Transaction], ctx: _Ctx
    ) -> list[Fee]:
        """Promote fee-type transactions to the Fee entity for analytics."""
        fees: list[Fee] = []
        for tx in transactions:
            if tx.transaction_type in (TransactionType.FEE, TransactionType.ADVISORY_FEE):
                fees.append(Fee(
                    account_id=ctx.account_id,
                    statement_id=ctx.statement_id,
                    fee_date=tx.transaction_date,
                    description=tx.description,
                    amount=abs(tx.amount),
                    fee_category="credit_card_fee",
                    confidence=tx.confidence,
                    source=tx.source,
                ))
        return fees

    def _compute_cash_flow(
        self, transactions: list[Transaction], fees: list[Fee]
    ) -> CashFlow:
        deposits = sum(t.amount for t in transactions if t.amount > 0)
        withdrawals = abs(sum(t.amount for t in transactions if t.amount < 0))
        fee_total = sum(f.amount for f in fees)
        return CashFlow(
            total_deposits=deposits,
            total_withdrawals=withdrawals,
            total_fees=fee_total,
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


def _classify_chase_txn_type(desc: str, amount: Decimal) -> TransactionType:
    lower = desc.lower()
    if any(w in lower for w in ["payment", "thank you", "autopay"]):
        return TransactionType.PAYMENT
    if any(w in lower for w in ["annual fee", "late fee", "fee"]):
        return TransactionType.FEE
    if any(w in lower for w in ["interest charge", "interest"]):
        return TransactionType.INTEREST
    if any(w in lower for w in ["transfer", "balance transfer"]):
        return TransactionType.TRANSFER
    if any(w in lower for w in ["cash advance"]):
        return TransactionType.WITHDRAWAL
    if any(w in lower for w in ["refund", "credit", "return"]) and amount > 0:
        return TransactionType.REFUND
    if amount > 0:
        return TransactionType.DEPOSIT
    return TransactionType.PURCHASE
