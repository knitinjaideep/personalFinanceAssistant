"""
Amex statement extractor.

Extracts from American Express credit card statements:
- Account number (masked)
- Statement period / payment due date
- New balance, previous balance, credit limit
- Transactions (purchases, credits, payments, fees)
- Fees
- Cash flow summary

Amex statement layout:
- Summary box at top: previous balance, payments, new charges, new balance
- Transaction list: date | description | amount (negative = charge, positive = payment)
- Reward points (ignored for financial purposes)
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

_ACCOUNT_RE = re.compile(
    r"(?:account\s+(?:number|ending|#)\s*[:\-]?\s*)?([xX*\d]{4,}[-\s]?[xX*\d]+)",
    re.IGNORECASE,
)
_PERIOD_RE = re.compile(
    r"(?:closing\s+date|statement\s+date|billing\s+period)\s*[:\-]?\s*"
    r"(\d{1,2}/\d{1,2}/\d{2,4}|\w+\s+\d{1,2},?\s*\d{4})",
    re.IGNORECASE,
)
_NEW_BALANCE_RE = re.compile(
    r"new\s+balance\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)
_PREV_BALANCE_RE = re.compile(
    r"previous\s+balance\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)
_CREDIT_LIMIT_RE = re.compile(
    r"credit\s+limit\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d{2})?)",
    re.IGNORECASE,
)
_MIN_PAYMENT_RE = re.compile(
    r"minimum\s+payment\s+due\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)
_CARD_NAME_RE = re.compile(
    r"((?:American\s+Express\s+)?(?:Platinum|Gold|Green|Blue\s+Cash|Delta|Hilton|Marriott)[^\n]*Card[^\n]*)",
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


AMEX_INSTITUTION = FinancialInstitution(
    name="American Express",
    institution_type=InstitutionType.AMEX,
    website="https://www.americanexpress.com",
)


class AmexExtractor:
    """Extracts structured financial data from Amex credit card statements."""

    def __init__(self, normalizer: MerchantNormalizer | None = None) -> None:
        self._normalizer = normalizer or MerchantNormalizer()

    async def extract(
        self,
        document: ParsedDocument,
        account_type: AccountType = AccountType.CREDIT_CARD,
        statement_type: StatementType = StatementType.CREDIT_CARD,
    ) -> Statement:
        account = self._extract_account(document)
        ctx = _Ctx(
            document=document,
            institution_id=AMEX_INSTITUTION.id,
            account_id=account.id,
            statement_id=uuid.uuid4(),
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
            ctx.warnings.append("Limited fields extracted from Amex document")

        stmt = Statement(
            id=ctx.statement_id,
            document_id=uuid.uuid4(),
            institution_id=AMEX_INSTITUTION.id,
            institution_type=InstitutionType.AMEX,
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
            "amex_extractor.done",
            transactions=len(transactions),
            confidence=overall,
        )
        return stmt

    def _extract_account(self, document: ParsedDocument) -> Account:
        sample = "\n".join(p.raw_text for p in document.pages[:2])
        account_number = "****0000"
        m = _ACCOUNT_RE.search(sample)
        if m:
            raw = re.sub(r"[^\d]", "", m.group(1))
            account_number = f"****{raw[-4:]}" if len(raw) >= 4 else "****" + raw
        name_m = _CARD_NAME_RE.search(sample)
        account_name = name_m.group(1).strip() if name_m else "American Express Card"
        return Account(
            institution_id=AMEX_INSTITUTION.id,
            institution_type=InstitutionType.AMEX,
            account_number_masked=account_number,
            account_name=account_name,
            account_type=AccountType.CREDIT_CARD,
        )

    def _extract_period(
        self, document: ParsedDocument, ctx: _Ctx
    ) -> StatementPeriod:
        sample = "\n".join(p.raw_text for p in document.pages[:3])
        # Amex statements show closing/statement date — use as end date
        m = _PERIOD_RE.search(sample)
        if m:
            end = _parse_date(m.group(1))
            if end:
                # Estimate start as ~30 days prior
                from datetime import timedelta
                start = end - timedelta(days=30)
                ctx.add_fc("period", True, 0.75, "inferred")
                return StatementPeriod(start_date=start, end_date=end)

        today = date.today()
        ctx.add_fc("period", False, 0.10)
        ctx.warnings.append("Statement date not found; using current month")
        return StatementPeriod(start_date=today.replace(day=1), end_date=today)

    def _extract_balances(
        self,
        document: ParsedDocument,
        ctx: _Ctx,
        period: StatementPeriod,
    ) -> list[BalanceSnapshot]:
        full = "\n".join(p.raw_text for p in document.pages[:4])
        for pattern, label in [
            (_NEW_BALANCE_RE, "New Balance"),
            (_PREV_BALANCE_RE, "Previous Balance"),
        ]:
            m = pattern.search(full)
            if m:
                amt = _parse_decimal(m.group(1))
                if amt is not None:
                    ctx.add_fc("balance", True, 0.85)
                    return [BalanceSnapshot(
                        account_id=ctx.account_id,
                        statement_id=ctx.statement_id,
                        snapshot_date=period.end_date,
                        total_value=amt,
                        confidence=0.85,
                        source=SourceLocation(section=label, raw_text=m.group(0)),
                    )]
        ctx.add_fc("balance", False, 0.0)
        ctx.warnings.append("No balance found in Amex statement")
        return []

    def _extract_transactions(
        self, document: ParsedDocument, ctx: _Ctx
    ) -> list[Transaction]:
        txns: list[Transaction] = []
        for page in document.pages:
            for table in page.tables:
                txns.extend(self._parse_transaction_table(table, ctx))
        if not txns:
            for page in document.pages:
                txns.extend(self._parse_transaction_lines(page.raw_text, ctx, page.page_number))

        ctx.add_fc("transactions", bool(txns), 0.80 if txns else 0.0, "table+text")
        return txns

    def _parse_transaction_table(
        self, table: ParsedTable, ctx: _Ctx
    ) -> list[Transaction]:
        txns: list[Transaction] = []
        headers = [str(h or "").lower().strip() for h in (table.header_row or [])]
        date_col = _col(headers, ["date", "trans date"])
        desc_col = _col(headers, ["description", "merchant", "transaction"])
        amount_col = _col(headers, ["amount", "charge", "credit"])

        if date_col is None:
            return []

        for row in table.rows:
            if not row or all((c or "").strip() == "" for c in row):
                continue
            try:
                tx_date = _parse_date(_cell(row, date_col))
                desc = _cell(row, desc_col)
                amount_str = _cell(row, amount_col)
                amount = _parse_decimal(amount_str)

                if not tx_date or not desc or amount is None:
                    continue

                # Amex: positive = charge, negative = payment/credit
                # Normalize: charges should be negative (debit)
                normalized = -abs(amount) if amount > 0 else amount
                clean_name, category, _ = self._normalizer.normalize(desc)
                tx_type = _classify_amex_txn_type(desc, amount)
                txns.append(Transaction(
                    account_id=ctx.account_id,
                    statement_id=ctx.statement_id,
                    transaction_date=tx_date,
                    description=desc,
                    merchant_name=clean_name,
                    transaction_type=tx_type,
                    category=category,
                    amount=normalized,
                    is_recurring=self._normalizer.is_recurring(desc),
                    confidence=0.82,
                    source=SourceLocation(page=table.page_number, section="Transactions"),
                ))
            except Exception as exc:
                logger.debug("amex.txn.row.skip", error=str(exc))
        return txns

    def _parse_transaction_lines(
        self, text: str, ctx: _Ctx, page_num: int
    ) -> list[Transaction]:
        txns: list[Transaction] = []
        line_re = re.compile(
            r"^(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+(.+?)\s+\$?([\d,]+\.\d{2})\s*$",
            re.MULTILINE,
        )
        for m in line_re.finditer(text):
            tx_date = _parse_date(m.group(1))
            desc = m.group(2).strip()
            amount = _parse_decimal(m.group(3))
            if not tx_date or not desc or amount is None:
                continue
            clean_name, category, _ = self._normalizer.normalize(desc)
            txns.append(Transaction(
                account_id=ctx.account_id,
                statement_id=ctx.statement_id,
                transaction_date=tx_date,
                description=desc,
                merchant_name=clean_name,
                transaction_type=_classify_amex_txn_type(desc, amount),
                category=category,
                amount=-abs(amount),  # Amex charges are positive, normalize to negative
                is_recurring=self._normalizer.is_recurring(desc),
                confidence=0.68,
                source=SourceLocation(page=page_num, section="Transactions"),
            ))
        return txns

    def _extract_fees_from_transactions(
        self, transactions: list[Transaction], ctx: _Ctx
    ) -> list[Fee]:
        fees: list[Fee] = []
        for tx in transactions:
            if tx.transaction_type == TransactionType.FEE:
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
        payments = sum(t.amount for t in transactions if t.amount > 0)
        charges = abs(sum(t.amount for t in transactions if t.amount < 0))
        fee_total = sum(f.amount for f in fees)
        return CashFlow(
            total_deposits=payments,
            total_withdrawals=charges,
            total_fees=fee_total,
            net_cash_flow=payments - charges - fee_total,
        )


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


def _classify_amex_txn_type(desc: str, amount: Decimal) -> TransactionType:
    lower = desc.lower()
    if any(w in lower for w in ["payment", "autopay", "thank you"]):
        return TransactionType.PAYMENT
    if any(w in lower for w in ["annual fee", "late fee", "fee", "finance charge"]):
        return TransactionType.FEE
    if any(w in lower for w in ["interest"]):
        return TransactionType.INTEREST
    if "refund" in lower or "credit" in lower or "return" in lower:
        return TransactionType.REFUND
    return TransactionType.PURCHASE
