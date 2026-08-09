"""
data_collector.py — Collects the financial snapshot needed for affordability analysis.

Responsibilities:
- Query balance_snapshots, transactions for spending/income estimates
- Classify accounts into liquid, investment, retirement, child buckets
- Mark missing data explicitly (never invent numbers)
- Return a FinancialSnapshot that is the single source of financial truth for the pipeline

Design contract:
- All fields that could not be determined are None (not zero, not guessed)
- data_quality_notes explains what's missing and why it matters
- No calculations beyond classification and aggregation
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.logger import get_logger
from app.db.engine import get_session
from app.domain.enums import AccountType

logger = get_logger(__name__)

_RETIREMENT_TYPES: frozenset[str] = frozenset({
    AccountType.IRA.value,
    AccountType.ROTH_IRA.value,
    AccountType.FOUR_01K.value,
})
_LIQUID_TYPES: frozenset[str] = frozenset({
    AccountType.CHECKING.value,
    AccountType.SAVINGS.value,
})
_INVESTMENT_TYPES: frozenset[str] = frozenset({
    AccountType.INDIVIDUAL_BROKERAGE.value,
    AccountType.ADVISORY.value,
})

_EMERGENCY_FUND_MONTHS = 6
_MONTHLY_SPEND_FALLBACK = Decimal("3000")


class AccountSnapshot(BaseModel):
    account_name: str
    account_type: str
    institution: str
    total_value: Decimal
    bucket: str   # "liquid" | "investment" | "retirement" | "child" | "other"


class FinancialSnapshot(BaseModel):
    """
    Collected financial picture for an affordability question.

    Fields that are None were genuinely unavailable in the database.
    Callers must handle None gracefully — never assume zero.
    """
    # Liquid cash (checking + savings only)
    liquid_cash: Decimal = Decimal("0")
    liquid_accounts: list[AccountSnapshot] = Field(default_factory=list)

    # Investment assets (brokerage, advisory) — available but not freely liquid
    investment_value: Decimal = Decimal("0")
    investment_accounts: list[AccountSnapshot] = Field(default_factory=list)

    # Retirement assets — excluded from affordability math by policy
    retirement_value: Decimal = Decimal("0")
    retirement_accounts: list[AccountSnapshot] = Field(default_factory=list)

    # Child / education accounts (529, etc.) — excluded
    child_account_value: Decimal = Decimal("0")
    child_accounts: list[AccountSnapshot] = Field(default_factory=list)

    # Spending / income context
    monthly_spending: Optional[Decimal] = None     # None = not enough transaction data
    monthly_income: Optional[Decimal] = None       # None = no income data found
    monthly_surplus: Optional[Decimal] = None      # derived only when both available

    # Derived convenience fields
    emergency_reserve_target: Decimal = Decimal("0")   # 6 × monthly_spending (if available)
    comfortable_spend_capacity: Decimal = Decimal("0") # liquid - reserve (floored at 0)

    # Existing housing context
    estimated_monthly_rent: Optional[Decimal] = None   # from rent transactions if detectable

    # Transparency
    has_balance_data: bool = False
    has_spending_data: bool = False
    has_income_data: bool = False
    data_quality_notes: list[str] = Field(default_factory=list)
    excluded_account_labels: list[str] = Field(default_factory=list)


async def _fetch_balance_rows() -> list[dict[str, Any]]:
    sql = """
        SELECT
            a.account_name,
            a.account_type,
            i.name          AS institution,
            bs.snapshot_date,
            bs.total_value,
            bs.cash_value,
            bs.invested_value
        FROM balance_snapshots bs
        JOIN accounts     a ON bs.account_id    = a.id
        JOIN institutions i ON a.institution_id = i.id
        ORDER BY bs.snapshot_date DESC
    """
    async with get_session() as session:
        result = await session.execute(text(sql))
        rows = [dict(r._mapping) for r in result.fetchall()]

    # Deduplicate: keep only the most recent snapshot per account
    seen: set[str] = set()
    latest: list[dict] = []
    for r in rows:
        key = f"{r.get('account_name')}|{r.get('institution')}"
        if key not in seen:
            seen.add(key)
            latest.append(r)
    return latest


async def _fetch_monthly_spend() -> Decimal | None:
    sql = """
        SELECT AVG(monthly_total) AS avg_monthly
        FROM (
            SELECT
                strftime('%Y-%m', transaction_date) AS month,
                SUM(ABS(amount)) AS monthly_total
            FROM transactions
            WHERE transaction_type NOT IN ('transfer', 'deposit', 'dividend', 'interest')
              AND amount < 0
            GROUP BY month
            HAVING monthly_total > 100
        ) monthly
    """
    async with get_session() as session:
        result = await session.execute(text(sql))
        row = result.fetchone()
    if row and row[0]:
        return Decimal(str(row[0])).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return None


async def _fetch_monthly_income() -> Decimal | None:
    sql = """
        SELECT AVG(monthly_total) AS avg_monthly
        FROM (
            SELECT
                strftime('%Y-%m', transaction_date) AS month,
                SUM(ABS(amount)) AS monthly_total
            FROM transactions
            WHERE transaction_type IN ('deposit', 'credit', 'payroll')
              AND amount > 0
            GROUP BY month
            HAVING monthly_total > 500
        ) monthly
    """
    async with get_session() as session:
        result = await session.execute(text(sql))
        row = result.fetchone()
    if row and row[0]:
        return Decimal(str(row[0])).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return None


async def _fetch_monthly_rent() -> Decimal | None:
    """Try to detect a recurring rent or mortgage payment from transactions."""
    sql = """
        SELECT AVG(ABS(amount)) AS avg_rent
        FROM transactions
        WHERE (
            LOWER(description) LIKE '%rent%'
            OR LOWER(description) LIKE '%mortgage%'
            OR LOWER(description) LIKE '%landlord%'
        )
        AND amount < 0
        AND ABS(amount) > 500
    """
    async with get_session() as session:
        result = await session.execute(text(sql))
        row = result.fetchone()
    if row and row[0]:
        val = Decimal(str(row[0])).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if val > Decimal("200"):
            return val
    return None


def _classify_row(r: dict) -> AccountSnapshot:
    acct_type = (r.get("account_type") or "").lower()
    name = r.get("account_name") or r.get("institution") or "Unknown"
    institution = r.get("institution") or "Unknown"
    value = Decimal(str(r.get("total_value") or 0))

    if acct_type in _LIQUID_TYPES:
        bucket = "liquid"
    elif acct_type in _RETIREMENT_TYPES:
        bucket = "retirement"
    elif acct_type in _INVESTMENT_TYPES:
        bucket = "investment"
    elif "529" in name.lower() or "child" in name.lower() or "education" in name.lower():
        bucket = "child"
    else:
        bucket = "other"

    return AccountSnapshot(
        account_name=name,
        account_type=acct_type,
        institution=institution,
        total_value=value,
        bucket=bucket,
    )


def _build_snapshot(
    rows: list[dict],
    monthly_spend: Decimal | None,
    monthly_income: Decimal | None,
    monthly_rent: Decimal | None,
) -> FinancialSnapshot:
    if not rows:
        return FinancialSnapshot(
            has_balance_data=False,
            data_quality_notes=["No balance snapshots found. Upload a bank or investment statement."],
        )

    liquid_cash = Decimal("0")
    investment_value = Decimal("0")
    retirement_value = Decimal("0")
    child_value = Decimal("0")

    liquid_accounts: list[AccountSnapshot] = []
    investment_accounts: list[AccountSnapshot] = []
    retirement_accounts: list[AccountSnapshot] = []
    child_accounts: list[AccountSnapshot] = []
    excluded_labels: list[str] = []

    for r in rows:
        snap = _classify_row(r)
        if snap.bucket == "liquid":
            liquid_cash += snap.total_value
            liquid_accounts.append(snap)
        elif snap.bucket == "investment":
            investment_value += snap.total_value
            investment_accounts.append(snap)
        elif snap.bucket == "retirement":
            retirement_value += snap.total_value
            retirement_accounts.append(snap)
            excluded_labels.append(f"{snap.account_name} ({snap.account_type})")
        elif snap.bucket == "child":
            child_value += snap.total_value
            child_accounts.append(snap)
            excluded_labels.append(f"{snap.account_name} ({snap.account_type})")

    # Use fallback spend if DB had nothing
    effective_spend = monthly_spend or _MONTHLY_SPEND_FALLBACK
    reserve = (effective_spend * _EMERGENCY_FUND_MONTHS).quantize(Decimal("1"))
    capacity = max(Decimal("0"), liquid_cash - reserve)

    monthly_surplus: Decimal | None = None
    if monthly_income is not None:
        monthly_surplus = monthly_income - effective_spend

    quality_notes: list[str] = []
    if monthly_spend is None:
        quality_notes.append(
            f"No spending history found — using ${_MONTHLY_SPEND_FALLBACK:,.0f}/month as a fallback. "
            "Upload transaction statements for a more accurate estimate."
        )
    if monthly_income is None:
        quality_notes.append(
            "Monthly income could not be estimated from available transactions. "
            "Debt-to-income calculations are unavailable."
        )
    if investment_value > 0:
        quality_notes.append(
            f"Investment accounts (${investment_value:,.0f}) are not counted as liquid cash — "
            "liquidating carries tax and market-timing risk."
        )

    return FinancialSnapshot(
        liquid_cash=liquid_cash,
        liquid_accounts=liquid_accounts,
        investment_value=investment_value,
        investment_accounts=investment_accounts,
        retirement_value=retirement_value,
        retirement_accounts=retirement_accounts,
        child_account_value=child_value,
        child_accounts=child_accounts,
        monthly_spending=effective_spend,
        monthly_income=monthly_income,
        monthly_surplus=monthly_surplus,
        emergency_reserve_target=reserve,
        comfortable_spend_capacity=capacity,
        estimated_monthly_rent=monthly_rent,
        has_balance_data=True,
        has_spending_data=(monthly_spend is not None),
        has_income_data=(monthly_income is not None),
        data_quality_notes=quality_notes,
        excluded_account_labels=excluded_labels,
    )


async def collect() -> FinancialSnapshot:
    """Fetch all financial data needed for affordability analysis."""
    try:
        rows, monthly_spend, monthly_income, monthly_rent = (
            await _fetch_balance_rows(),
            await _fetch_monthly_spend(),
            await _fetch_monthly_income(),
            await _fetch_monthly_rent(),
        )
    except Exception as exc:
        logger.warning("data_collector.fetch_failed", extra={"error": str(exc)})
        return FinancialSnapshot(
            has_balance_data=False,
            data_quality_notes=[f"Database error: {exc}"],
        )

    return _build_snapshot(rows, monthly_spend, monthly_income, monthly_rent)
