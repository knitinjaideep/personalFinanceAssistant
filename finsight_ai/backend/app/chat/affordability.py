"""
Affordability analysis — three-layer architecture.

Layer 1: ScenarioMathResult  — deterministic Python math (Decimal arithmetic)
Layer 2: DecisionResult      — deterministic Python policy verdict
Layer 3: ReadableAnswer      — LLM (Gemma/qwen) narrates, does not calculate

Rules:
- LLM never calculates numbers.
- LLM never changes the verdict.
- LLM never invents amounts, assumptions, or suggestions.
- All assumptions are visible in ScenarioMathResult.assumptions.
- Retirement / 529 / child accounts are excluded from liquid cash by default.
- If LLM output is invalid or violates policy, a deterministic template renders the answer.
- DecisionResult.allowed_conclusions / forbidden_conclusions constrain the LLM.

Flow:
    analyze()
        → _fetch_balance_snapshot() + _fetch_monthly_spend()
        → _build_snapshot()
        → _calc_purchase() or _calc_home()   → ScenarioMathResult
        → _decide_purchase() or _decide_home() → DecisionResult
        → _render_readable() (LLM)             → StructuredAnswer
           or _render_template_*() (fallback)
        → _verify()                            → StructuredAnswer
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from sqlalchemy import text

from app.core.logger import get_logger
from app.db.engine import get_session
from app.domain.enums import AccountType
from app.domain.entities import StructuredAnswer

logger = get_logger(__name__)


# ── Account classification ─────────────────────────────────────────────────────

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

# ── Policy constants ───────────────────────────────────────────────────────────

_EMERGENCY_FUND_MONTHS = 6
_MONTHLY_SPEND_FALLBACK = Decimal("3000")
_DOWN_PAYMENT_PCT = Decimal("0.20")
_CLOSING_COST_PCT = Decimal("0.03")
_MORTGAGE_RATE_PCT = Decimal("0.07")     # 7% — conservative assumption
_LOAN_TERM_YEARS = 30
_PROPERTY_TAX_ANNUAL_PCT = Decimal("0.012")   # 1.2% of home value/year
_INSURANCE_MONTHLY = Decimal("150")
_MAINTENANCE_ANNUAL_PCT = Decimal("0.01")     # 1% rule
_MAX_DTI = Decimal("0.28")


# ── SQL helpers ────────────────────────────────────────────────────────────────

async def _fetch_balance_snapshot() -> list[dict[str, Any]]:
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

    seen: set[str] = set()
    latest: list[dict] = []
    for r in rows:
        key = f"{r.get('account_name')}|{r.get('institution')}"
        if key not in seen:
            seen.add(key)
            latest.append(r)
    return latest


async def _fetch_monthly_spend() -> Decimal:
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
    return _MONTHLY_SPEND_FALLBACK


async def _fetch_income_estimate() -> Decimal | None:
    """Estimate average monthly income from deposit transactions."""
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


# ── Layer 0: Raw snapshot ──────────────────────────────────────────────────────

class _Snapshot:
    def __init__(self, rows: list[dict], monthly_spend: Decimal, monthly_income: Decimal | None) -> None:
        self.monthly_spend = monthly_spend
        self.monthly_income = monthly_income

        self.liquid_cash = Decimal("0")
        self.brokerage_value = Decimal("0")
        self.retirement_value = Decimal("0")
        self.child_account_value = Decimal("0")
        self.total_all = Decimal("0")

        self.liquid_accounts: list[str] = []
        self.brokerage_accounts: list[str] = []
        self.retirement_accounts: list[str] = []
        self.excluded_accounts: list[str] = []

        self.has_data = len(rows) > 0
        self._classify(rows)

    def _classify(self, rows: list[dict]) -> None:
        for r in rows:
            acct_type = (r.get("account_type") or "").lower()
            value = Decimal(str(r.get("total_value") or 0))
            name = r.get("account_name") or r.get("institution") or "Unknown"
            label = f"{name} ({acct_type})"

            self.total_all += value

            if acct_type in _LIQUID_TYPES:
                self.liquid_cash += value
                self.liquid_accounts.append(label)
            elif acct_type in _RETIREMENT_TYPES:
                self.retirement_value += value
                self.retirement_accounts.append(label)
                self.excluded_accounts.append(label)
            elif acct_type in _INVESTMENT_TYPES:
                self.brokerage_value += value
                self.brokerage_accounts.append(label)
            elif "529" in name.lower() or "child" in name.lower() or "education" in name.lower():
                self.child_account_value += value
                self.excluded_accounts.append(label)

    @property
    def emergency_reserve_target(self) -> Decimal:
        return (self.monthly_spend * _EMERGENCY_FUND_MONTHS).quantize(Decimal("1"))

    @property
    def comfortable_spend_capacity(self) -> Decimal:
        return max(Decimal("0"), self.liquid_cash - self.emergency_reserve_target)

    @property
    def monthly_surplus(self) -> Decimal | None:
        if self.monthly_income is None:
            return None
        return self.monthly_income - self.monthly_spend


# ── Layer 1: ScenarioMathResult ────────────────────────────────────────────────

class ScenarioMathResult(BaseModel):
    """
    All numbers that matter for an affordability question.
    Computed entirely in Python with Decimal arithmetic.
    The LLM receives this object and must not recalculate anything.
    """
    scenario_type: Literal["purchase_affordability", "home_affordability", "cash_reserve_analysis"]

    # Purchase fields (purchase_affordability / goal_affordability)
    purchase_item: str = ""
    purchase_category: str = ""
    purchase_price: Decimal | None = None
    purchase_price_source: str = ""      # "explicit" | "assumed" | "unknown"

    # Liquidity picture
    gross_liquid_cash: Decimal = Decimal("0")
    emergency_reserve_target: Decimal = Decimal("0")
    comfortable_spend_capacity: Decimal = Decimal("0")   # liquid - reserve (floored at 0)

    # Post-purchase picture (purchase only)
    cash_after_purchase: Decimal | None = None
    reserve_gap_before_purchase: Decimal = Decimal("0")  # max(0, reserve - liquid)
    reserve_gap_after_purchase: Decimal | None = None
    purchase_as_pct_of_liquid: Decimal | None = None     # purchase / liquid * 100

    # Home fields (home_affordability)
    down_payment_pct: Decimal | None = None
    down_payment: Decimal | None = None
    closing_costs: Decimal | None = None
    cash_needed_at_close: Decimal | None = None
    cash_remaining_after_close: Decimal | None = None
    total_cash_needed_with_reserve: Decimal | None = None
    technical_home_cash_gap: Decimal | None = None       # cash_needed - liquid (if negative, surplus)
    comfortable_home_cash_gap: Decimal | None = None     # cash_needed_with_reserve - liquid
    loan_amount: Decimal | None = None
    mortgage_rate_pct: Decimal | None = None
    loan_term_years: int | None = None
    principal_interest_monthly: Decimal | None = None
    property_tax_monthly: Decimal | None = None
    insurance_monthly: Decimal | None = None
    maintenance_monthly: Decimal | None = None
    estimated_total_monthly_housing: Decimal | None = None
    dti_estimate: Decimal | None = None                  # housing / income (if income available)
    max_affordable_home_price: Decimal | None = None     # derived when no price given

    # Income / spend context (when available)
    monthly_income: Decimal | None = None
    monthly_spending: Decimal | None = None
    monthly_surplus: Decimal | None = None

    # Account transparency
    included_assets: list[str] = Field(default_factory=list)
    excluded_assets: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)



# ── Layer 2: DecisionResult ────────────────────────────────────────────────────

class PurchaseVerdictCode(str, Enum):
    COMFORTABLE = "comfortable"
    TECHNICALLY_AFFORDABLE_NOT_COMFORTABLE = "technically_affordable_but_not_comfortable"
    STRETCH = "stretch"
    NOT_AFFORDABLE = "not_affordable"
    INSUFFICIENT_DATA = "insufficient_data"


class HomeVerdictCode(str, Enum):
    POSSIBLE = "possible"
    TECHNICALLY_POSSIBLE_RESERVES_TIGHT = "technically_possible_but_reserves_tight"
    UPFRONT_CASH_SHORTFALL = "upfront_cash_shortfall"
    MONTHLY_PAYMENT_RISK = "monthly_payment_risk"
    NOT_RECOMMENDED = "not_recommended"
    INSUFFICIENT_DATA = "insufficient_data"


class DecisionSeverity(str, Enum):
    OK = "ok"
    WATCH = "watch"
    CAUTION = "caution"
    STOP = "stop"


class DecisionResult(BaseModel):
    """
    Python-computed verdict. The LLM must not change verdict_code or verdict_label.
    allowed_conclusions and forbidden_conclusions are injected into the LLM prompt
    so it cannot misrepresent the verdict.
    """
    verdict_code: str              # PurchaseVerdictCode or HomeVerdictCode value
    verdict_label: str             # human label matching verdict_code
    severity: DecisionSeverity
    primary_reason: str
    reason_codes: list[str] = Field(default_factory=list)
    allowed_conclusions: list[str] = Field(default_factory=list)
    forbidden_conclusions: list[str] = Field(default_factory=list)
    recommended_followups: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


# ── Layer 1: purchase math ─────────────────────────────────────────────────────

_BIRKIN_ASSUMED_PRICE = Decimal("15000")
_LUXURY_ASSUMED_PRICE = Decimal("5000")


def _calc_purchase(
    snap: _Snapshot,
    purchase_price: Decimal | None,
    purchase_item: str,
    purchase_category: str,
    question: str,
) -> ScenarioMathResult:
    assumptions: list[str] = []
    caveats: list[str] = []

    price_source = "explicit"
    price = purchase_price

    if price is None:
        # Assume a sensible default for known luxury items
        item_lower = purchase_item.lower() + " " + question.lower()
        if "birkin" in item_lower or "hermes" in item_lower:
            price = _BIRKIN_ASSUMED_PRICE
            assumptions.append(f"Assumed Birkin bag price: $15,000 (entry-level new). Prices vary widely.")
            price_source = "assumed"
        elif "luxury" in item_lower or purchase_category == "luxury_discretionary":
            price = _LUXURY_ASSUMED_PRICE
            assumptions.append("No price specified — assumed $5,000 as a placeholder. Please share the actual price.")
            price_source = "assumed"
        else:
            price_source = "unknown"

    liquid = snap.liquid_cash
    reserve = snap.emergency_reserve_target
    capacity = snap.comfortable_spend_capacity
    reserve_gap_before = max(Decimal("0"), reserve - liquid)

    assumptions.append(
        f"Emergency reserve target: {_EMERGENCY_FUND_MONTHS} months × "
        f"${snap.monthly_spend:,.0f}/month estimated spend = ${reserve:,.0f}."
    )
    assumptions.append("Retirement accounts (IRA, Roth IRA, 401k) excluded from liquid cash.")
    assumptions.append("529 and child education accounts excluded from liquid cash.")
    if snap.brokerage_value > 0:
        assumptions.append(
            f"Brokerage/advisory accounts (${snap.brokerage_value:,.0f}) not counted — "
            "liquidating investments carries tax and market-timing risk."
        )

    caveats.append("This is not financial advice. Consult a financial advisor for major decisions.")
    caveats.append(
        "This does not account for upcoming large expenses, taxes, or bills unless "
        "they appear as transactions in Coral."
    )

    math = ScenarioMathResult(
        scenario_type="purchase_affordability",
        purchase_item=purchase_item,
        purchase_category=purchase_category,
        purchase_price=price,
        purchase_price_source=price_source,
        gross_liquid_cash=liquid,
        emergency_reserve_target=reserve,
        comfortable_spend_capacity=capacity,
        reserve_gap_before_purchase=reserve_gap_before,
        monthly_income=snap.monthly_income,
        monthly_spending=snap.monthly_spend,
        monthly_surplus=snap.monthly_surplus,
        included_assets=snap.liquid_accounts or [],
        excluded_assets=snap.excluded_accounts or [],
        assumptions=assumptions,
        caveats=caveats,
    )

    if price is not None:
        cash_after = liquid - price
        reserve_gap_after = max(Decimal("0"), reserve - cash_after)
        pct_of_liquid = (price / liquid * 100).quantize(Decimal("1")) if liquid > 0 else None
        math.cash_after_purchase = cash_after
        math.reserve_gap_after_purchase = reserve_gap_after
        math.purchase_as_pct_of_liquid = pct_of_liquid

    return math


def _calc_home(
    snap: _Snapshot,
    purchase_price: Decimal | None,
) -> ScenarioMathResult:
    assumptions: list[str] = []
    caveats: list[str] = []

    liquid = snap.liquid_cash
    reserve = snap.emergency_reserve_target
    capacity = snap.comfortable_spend_capacity

    assumptions.append(f"Down payment: {int(_DOWN_PAYMENT_PCT * 100)}% of purchase price.")
    assumptions.append(f"Closing costs: {int(_CLOSING_COST_PCT * 100)}% of purchase price (actual varies by location).")
    assumptions.append(f"Mortgage rate: {float(_MORTGAGE_RATE_PCT * 100):.1f}% fixed (current estimate; rates change).")
    assumptions.append(f"Loan term: {_LOAN_TERM_YEARS} years.")
    assumptions.append(f"Emergency reserve target: {_EMERGENCY_FUND_MONTHS} months × ${snap.monthly_spend:,.0f}/month = ${reserve:,.0f}.")
    assumptions.append("Retirement accounts excluded from down payment funds.")
    caveats.append("Monthly payment estimate excludes HOA, flood insurance, PMI, and local tax variations.")
    caveats.append("This is not financial advice. Work with a mortgage lender for accurate qualification.")

    math = ScenarioMathResult(
        scenario_type="home_affordability",
        gross_liquid_cash=liquid,
        emergency_reserve_target=reserve,
        comfortable_spend_capacity=capacity,
        reserve_gap_before_purchase=max(Decimal("0"), reserve - liquid),
        down_payment_pct=_DOWN_PAYMENT_PCT,
        mortgage_rate_pct=_MORTGAGE_RATE_PCT,
        loan_term_years=_LOAN_TERM_YEARS,
        insurance_monthly=_INSURANCE_MONTHLY,
        monthly_income=snap.monthly_income,
        monthly_spending=snap.monthly_spend,
        monthly_surplus=snap.monthly_surplus,
        included_assets=snap.liquid_accounts or [],
        excluded_assets=snap.excluded_accounts or [],
        assumptions=assumptions,
        caveats=caveats,
    )

    if purchase_price is not None:
        down = (purchase_price * _DOWN_PAYMENT_PCT).quantize(Decimal("1"))
        closing = (purchase_price * _CLOSING_COST_PCT).quantize(Decimal("1"))
        cash_at_close = down + closing
        cash_remaining = liquid - cash_at_close
        total_with_reserve = cash_at_close + reserve
        technical_gap = cash_at_close - liquid           # positive = short
        comfortable_gap = total_with_reserve - liquid    # positive = short

        loan = purchase_price - down
        # Monthly P&I: M = P * r*(1+r)^n / ((1+r)^n - 1)
        r = _MORTGAGE_RATE_PCT / 12
        n = Decimal(_LOAN_TERM_YEARS * 12)
        pi_monthly = (loan * r * (1 + r) ** n / ((1 + r) ** n - 1)).quantize(Decimal("1"))

        prop_tax_monthly = (purchase_price * _PROPERTY_TAX_ANNUAL_PCT / 12).quantize(Decimal("1"))
        maintenance_monthly = (purchase_price * _MAINTENANCE_ANNUAL_PCT / 12).quantize(Decimal("1"))
        total_housing = pi_monthly + prop_tax_monthly + _INSURANCE_MONTHLY + maintenance_monthly

        dti = None
        if snap.monthly_income and snap.monthly_income > 0:
            dti = (total_housing / snap.monthly_income * 100).quantize(Decimal("1"))

        math.purchase_price = purchase_price
        math.purchase_price_source = "explicit"
        math.down_payment = down
        math.closing_costs = closing
        math.cash_needed_at_close = cash_at_close
        math.cash_remaining_after_close = cash_remaining
        math.total_cash_needed_with_reserve = total_with_reserve
        math.technical_home_cash_gap = technical_gap
        math.comfortable_home_cash_gap = comfortable_gap
        math.loan_amount = loan
        math.principal_interest_monthly = pi_monthly
        math.property_tax_monthly = prop_tax_monthly
        math.maintenance_monthly = maintenance_monthly
        math.estimated_total_monthly_housing = total_housing
        math.dti_estimate = dti
    else:
        # Compute max affordable
        max_price = capacity / (_DOWN_PAYMENT_PCT + _CLOSING_COST_PCT)
        math.max_affordable_home_price = max_price.quantize(Decimal("1"))

    return math


# ── Layer 2: Decision policy ───────────────────────────────────────────────────

def _decide_purchase(math: ScenarioMathResult) -> DecisionResult:
    liquid = math.gross_liquid_cash
    capacity = math.comfortable_spend_capacity
    price = math.purchase_price
    item = math.purchase_item or "purchase"

    if not math.gross_liquid_cash or math.gross_liquid_cash == 0:
        return DecisionResult(
            verdict_code=PurchaseVerdictCode.INSUFFICIENT_DATA.value,
            verdict_label="Insufficient data",
            severity=DecisionSeverity.STOP,
            primary_reason="No balance data found in Coral.",
            reason_codes=["no_balance_data"],
            allowed_conclusions=["No account balance data is available to make this assessment."],
            forbidden_conclusions=["Do not imply affordability either way."],
            recommended_followups=[
                "Upload a bank or savings statement to Coral.",
                "Check which documents have been uploaded.",
            ],
        )

    if price is None:
        # No price known — just report capacity
        return DecisionResult(
            verdict_code=PurchaseVerdictCode.INSUFFICIENT_DATA.value,
            verdict_label="No price provided",
            severity=DecisionSeverity.WATCH,
            primary_reason="No purchase price was specified or estimated.",
            reason_codes=["no_price"],
            allowed_conclusions=[
                f"Available for discretionary spending (after emergency reserve): ${capacity:,.0f}.",
                "Share the price of the item for a precise answer.",
            ],
            forbidden_conclusions=[
                "Do not say affordable or unaffordable without a price.",
            ],
            recommended_followups=[
                f"Can we afford a $15,000 {item}?",
                "What is my available cash balance?",
                "How much do I spend per month on average?",
            ],
        )

    # Now we have both liquid and price
    reserve = math.emergency_reserve_target
    gap_after = math.reserve_gap_after_purchase or Decimal("0")
    cash_after = math.cash_after_purchase or (liquid - price)

    if price > liquid:
        # Cannot pay from liquid cash at all
        shortfall = price - liquid
        return DecisionResult(
            verdict_code=PurchaseVerdictCode.NOT_AFFORDABLE.value,
            verdict_label="Not affordable from liquid cash",
            severity=DecisionSeverity.STOP,
            primary_reason=f"Purchase price (${price:,.0f}) exceeds total liquid cash (${liquid:,.0f}).",
            reason_codes=["price_exceeds_liquid_cash"],
            allowed_conclusions=[
                f"The {item} costs ${price:,.0f}, which exceeds liquid cash of ${liquid:,.0f}.",
                f"Liquid cash is short by ${shortfall:,.0f}.",
                "Retirement and investment accounts are not counted.",
            ],
            forbidden_conclusions=[
                "Do not say affordable.",
                "Do not recommend using retirement accounts.",
                "Do not recommend financing or credit card debt.",
                "Do not mention down payment or closing costs — this is a purchase, not a home.",
            ],
            recommended_followups=[
                "What is my total net worth including investment accounts?",
                "How much could I save in 6 months at my current rate?",
                "What are my current account balances?",
            ],
        )

    if price <= capacity:
        # Comfortable — within spend capacity after keeping reserve
        remaining = capacity - price
        return DecisionResult(
            verdict_code=PurchaseVerdictCode.COMFORTABLE.value,
            verdict_label="Comfortable",
            severity=DecisionSeverity.OK,
            primary_reason=(
                f"Purchase (${price:,.0f}) fits within comfortable spend capacity "
                f"(${capacity:,.0f}) after preserving the ${reserve:,.0f} emergency reserve."
            ),
            reason_codes=["purchase_within_comfortable_spend_capacity", "reserve_preserved"],
            allowed_conclusions=[
                f"The {item} looks affordable.",
                f"Emergency reserve of ${reserve:,.0f} is preserved.",
                f"${remaining:,.0f} remains after the purchase.",
            ],
            forbidden_conclusions=[
                "Do not say this is a risky or stretch purchase.",
                "Do not mention down payment or closing costs — this is a purchase, not a home.",
            ],
            recommended_followups=[
                f"Would buying a {item} hurt my house savings?",
                "What is my total net worth?",
                "How much do I spend per month on average?",
            ],
        )

    if price <= liquid:
        # Technically payable but dips into reserve territory
        return DecisionResult(
            verdict_code=PurchaseVerdictCode.TECHNICALLY_AFFORDABLE_NOT_COMFORTABLE.value,
            verdict_label="Technically affordable, but not comfortable",
            severity=DecisionSeverity.WATCH,
            primary_reason=(
                f"Purchase (${price:,.0f}) is payable from liquid cash (${liquid:,.0f}), "
                f"but it leaves only ${cash_after:,.0f} — ${gap_after:,.0f} below the "
                f"${reserve:,.0f} emergency reserve target."
            ),
            reason_codes=["purchase_dips_into_reserve", "reserve_gap_after_purchase"],
            allowed_conclusions=[
                f"You can technically pay for the {item}.",
                f"It is not comfortable because it reduces cash below the ${reserve:,.0f} recommended reserve.",
                f"The key risk is reserve depletion (${gap_after:,.0f} short after purchase).",
            ],
            forbidden_conclusions=[
                "Do not say this is comfortable.",
                "Do not say you cannot afford it outright.",
                "Do not recommend financing or taking a loan.",
                "Do not mention down payment or closing costs — this is a purchase, not a home.",
            ],
            recommended_followups=[
                "How much could I save in 3 months to make this comfortable?",
                "What is my monthly savings rate?",
                f"Would buying a {item} hurt my house savings?",
            ],
        )

    # Stretch: liquid very tight (shouldn't reach here, but safety)
    return DecisionResult(
        verdict_code=PurchaseVerdictCode.STRETCH.value,
        verdict_label="Stretch",
        severity=DecisionSeverity.CAUTION,
        primary_reason=f"Purchase would significantly strain liquid reserves.",
        reason_codes=["significant_reserve_depletion"],
        allowed_conclusions=[
            "This is a stretch purchase that significantly reduces financial buffer.",
        ],
        forbidden_conclusions=[
            "Do not say comfortable.",
            "Do not recommend credit card debt or loans.",
        ],
        recommended_followups=[
            "What are my current account balances?",
            "How much do I spend per month?",
        ],
    )


def _decide_home(math: ScenarioMathResult) -> DecisionResult:
    liquid = math.gross_liquid_cash

    if not liquid or liquid == 0:
        return DecisionResult(
            verdict_code=HomeVerdictCode.INSUFFICIENT_DATA.value,
            verdict_label="Insufficient data",
            severity=DecisionSeverity.STOP,
            primary_reason="No balance data found.",
            reason_codes=["no_balance_data"],
            allowed_conclusions=["No balance data available."],
            forbidden_conclusions=["Do not imply affordability."],
            recommended_followups=["Upload a bank statement to Coral."],
        )

    if math.purchase_price is None:
        max_price = math.max_affordable_home_price or Decimal("0")
        return DecisionResult(
            verdict_code=HomeVerdictCode.INSUFFICIENT_DATA.value,
            verdict_label="No price specified",
            severity=DecisionSeverity.WATCH,
            primary_reason=(
                f"No home price given — based on available cash, upfront costs "
                f"(20% down + 3% closing) could be covered up to ~${max_price:,.0f}."
            ),
            reason_codes=["no_price"],
            allowed_conclusions=[
                f"With current liquid cash, after reserve, a home up to ~${max_price:,.0f} may be feasible for upfront costs.",
                "Share the target home price for a detailed analysis.",
            ],
            forbidden_conclusions=[
                "Do not confirm affordability without a specific price.",
                "Do not mention retirement accounts as a funding source.",
            ],
            recommended_followups=[
                "Can we afford a $800,000 house?",
                "What are my current account balances?",
            ],
        )

    cash_at_close = math.cash_needed_at_close or Decimal("0")
    reserve = math.emergency_reserve_target
    technical_gap = math.technical_home_cash_gap or Decimal("0")   # positive = short
    comfortable_gap = math.comfortable_home_cash_gap or Decimal("0")
    down = math.down_payment or Decimal("0")
    closing = math.closing_costs or Decimal("0")
    total_housing = math.estimated_total_monthly_housing
    dti = math.dti_estimate

    followups = [
        "What are my current account balances?",
        "What is my total net worth including retirement accounts?",
        "How much would a $800,000 house cost per month?",
    ]

    # Check 1: upfront cash short even technically
    if technical_gap > 0:
        return DecisionResult(
            verdict_code=HomeVerdictCode.UPFRONT_CASH_SHORTFALL.value,
            verdict_label="Upfront cash shortfall",
            severity=DecisionSeverity.STOP,
            primary_reason=(
                f"Down payment (${down:,.0f}) + closing costs (${closing:,.0f}) = "
                f"${cash_at_close:,.0f} needed, but liquid cash is only ${liquid:,.0f}. "
                f"Shortfall: ${technical_gap:,.0f}."
            ),
            reason_codes=["upfront_cash_short", "liquid_below_closing_costs"],
            allowed_conclusions=[
                "Upfront cash appears short for this home price.",
                f"Down payment (${down:,.0f}) + closing costs (${closing:,.0f}) = ${cash_at_close:,.0f} needed.",
                f"Liquid cash (${liquid:,.0f}) is ${technical_gap:,.0f} short.",
            ],
            forbidden_conclusions=[
                "Do not say you can afford the home.",
                "Do not say monthly payment is the only issue.",
                "Do not suggest using retirement accounts to cover the gap.",
                "Do not say 'comfortable' or 'possible'.",
            ],
            recommended_followups=followups,
        )

    # Check 2: technically feasible but reserve is tight after close
    if comfortable_gap > 0:
        remaining = liquid - cash_at_close
        return DecisionResult(
            verdict_code=HomeVerdictCode.TECHNICALLY_POSSIBLE_RESERVES_TIGHT.value,
            verdict_label="Technically possible, but reserves would be tight",
            severity=DecisionSeverity.CAUTION,
            primary_reason=(
                f"Upfront costs (${cash_at_close:,.0f}) are technically covered by liquid cash "
                f"(${liquid:,.0f}), but only ${remaining:,.0f} would remain — "
                f"well below the ${reserve:,.0f} recommended reserve."
            ),
            reason_codes=["upfront_covered", "post_close_reserve_depleted"],
            allowed_conclusions=[
                "Upfront cash is technically sufficient.",
                f"After close, only ${remaining:,.0f} remains — ${comfortable_gap:,.0f} below the recommended reserve.",
                "This is financially risky without rebuilding savings quickly.",
            ],
            forbidden_conclusions=[
                "Do not say this is comfortable or recommended.",
                "Do not ignore the reserve depletion.",
                "Do not suggest retirement accounts.",
            ],
            recommended_followups=followups,
        )

    # Upfront is fine; check monthly affordability if we have income data
    if total_housing and dti and dti > (_MAX_DTI * 100):
        return DecisionResult(
            verdict_code=HomeVerdictCode.MONTHLY_PAYMENT_RISK.value,
            verdict_label="Monthly payment risk",
            severity=DecisionSeverity.CAUTION,
            primary_reason=(
                f"Estimated monthly housing cost (${total_housing:,.0f}) represents "
                f"{dti}% of income — above the {int(_MAX_DTI * 100)}% guideline."
            ),
            reason_codes=["upfront_ok", "dti_exceeds_guideline"],
            allowed_conclusions=[
                "Upfront costs are covered.",
                f"Monthly housing cost (${total_housing:,.0f}) is high relative to estimated income.",
                f"DTI of {dti}% exceeds the {int(_MAX_DTI * 100)}% guideline.",
            ],
            forbidden_conclusions=[
                "Do not say the home is comfortably affordable.",
                "Do not ignore the DTI risk.",
            ],
            recommended_followups=followups,
        )

    # Everything looks okay
    remaining = liquid - cash_at_close
    return DecisionResult(
        verdict_code=HomeVerdictCode.POSSIBLE.value,
        verdict_label="Possible",
        severity=DecisionSeverity.OK,
        primary_reason=(
            f"Upfront costs (${cash_at_close:,.0f}) are covered by liquid cash (${liquid:,.0f}), "
            f"leaving ${remaining:,.0f} after close."
        ),
        reason_codes=["upfront_covered", "reserve_maintained"],
        allowed_conclusions=[
            "Upfront cash appears sufficient.",
            f"${remaining:,.0f} remains after close.",
            "Monthly payment and DTI look manageable based on available data.",
        ],
        forbidden_conclusions=[
            "Do not say this is risk-free.",
            "Do not recommend skipping professional advice.",
        ],
        recommended_followups=followups,
    )


# ── Layer 3: Deterministic template renderers (fallback) ───────────────────────

def _fmt(v: Decimal | None) -> str:
    if v is None:
        return "N/A"
    return f"${v:,.0f}"


_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "this", "that", "to", "for", "of", "or",
    "and", "as", "please", "your", "you", "does", "do", "not", "it", "in",
    "on", "if", "unless", "they", "appear", "with", "be", "will",
})

# Distinctive "subject" words that, when shared between two caveats, indicate
# they are about the *same* underlying fact (vs. two short caveats that merely
# share boilerplate phrasing like "excluded from liquid cash").
_CAVEAT_SUBJECT_WORDS = frozenset({
    "placeholder", "assumed", "assumes", "price", "birkin",
    "advice", "advisor", "bills", "taxes", "expenses",
})

_CAVEAT_OVERLAP_THRESHOLD = 0.55


def _caveat_tokens(text: str) -> frozenset[str]:
    norm = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return frozenset(w for w in norm.split() if w not in _STOPWORDS and len(w) > 1)


def _dedupe_caveats(items: list[str]) -> list[str]:
    """Drop near-duplicate caveats/assumptions (e.g. LLM paraphrasing one Python already gave it).

    Two sentences are treated as duplicates only when they (a) share a
    distinctive subject word — e.g. both mention "placeholder"/"price"/"advice" —
    AND (b) have high token containment. Restricting to shared subject words
    avoids collapsing genuinely distinct caveats that merely share boilerplate
    phrasing (e.g. "...excluded from liquid cash").
    """
    kept: list[str] = []
    kept_tokens: list[frozenset[str]] = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        tokens = _caveat_tokens(item)
        is_dupe = False
        for kt in kept_tokens:
            if not tokens or not kt:
                continue
            shared_subjects = (tokens & kt) & _CAVEAT_SUBJECT_WORDS
            if not shared_subjects:
                continue
            smaller, larger = (tokens, kt) if len(tokens) <= len(kt) else (kt, tokens)
            overlap = len(smaller & larger) / len(smaller)
            if overlap > _CAVEAT_OVERLAP_THRESHOLD:
                is_dupe = True
                break
        if is_dupe:
            continue
        kept.append(item)
        kept_tokens.append(tokens)
    return kept


def _render_template_purchase(math: ScenarioMathResult, decision: DecisionResult) -> StructuredAnswer:
    item = math.purchase_item or "purchase"
    liquid = math.gross_liquid_cash
    reserve = math.emergency_reserve_target
    capacity = math.comfortable_spend_capacity
    price = math.purchase_price

    highlights: list[dict[str, str]] = [
        {"label": "Verdict", "value": decision.verdict_label},
        {"label": "Liquid cash (checking + savings)", "value": _fmt(liquid)},
        {"label": f"Emergency reserve target ({_EMERGENCY_FUND_MONTHS} months)", "value": _fmt(reserve)},
        {"label": "Available after reserve", "value": _fmt(capacity)},
    ]

    if price is not None:
        highlights.append({"label": f"Cost of {item}", "value": _fmt(price)})
        if math.cash_after_purchase is not None:
            highlights.append({"label": "Cash remaining after purchase", "value": _fmt(math.cash_after_purchase)})
        if math.reserve_gap_after_purchase and math.reserve_gap_after_purchase > 0:
            highlights.append({"label": "Reserve gap after purchase", "value": _fmt(math.reserve_gap_after_purchase)})

    summary_lines = [f"**{decision.verdict_label}.**", decision.primary_reason]
    if decision.allowed_conclusions:
        summary_lines.append(" ".join(decision.allowed_conclusions[:2]))

    summary = " ".join(summary_lines)

    sections: list[dict] = []
    if math.included_assets:
        sections.append({
            "heading": "Liquid accounts included",
            "rows": [{"account": a} for a in math.included_assets],
        })
    if math.excluded_assets:
        sections.append({
            "heading": "Excluded accounts (retirement / child)",
            "rows": [{"account": a} for a in math.excluded_assets],
        })

    all_caveats = _dedupe_caveats(list(math.assumptions) + list(math.caveats) + list(decision.caveats))

    return StructuredAnswer(
        answer_type="numeric",
        title=f"Can you afford the {item}?",
        summary=summary,
        highlights=highlights,
        sections=sections,
        caveats=all_caveats,
        suggested_followups=decision.recommended_followups,
        query_path="affordability",
        intent="affordability",
        confidence=0.9,
        answer_strategy="template_only",
        llm_called=False,
    )


def _render_template_home(math: ScenarioMathResult, decision: DecisionResult) -> StructuredAnswer:
    liquid = math.gross_liquid_cash
    reserve = math.emergency_reserve_target
    price = math.purchase_price

    highlights: list[dict[str, str]] = [
        {"label": "Verdict", "value": decision.verdict_label},
        {"label": "Liquid cash (checking + savings)", "value": _fmt(liquid)},
        {"label": f"Emergency reserve target ({_EMERGENCY_FUND_MONTHS} months)", "value": _fmt(reserve)},
    ]

    if price is not None:
        highlights += [
            {"label": "Home price", "value": _fmt(price)},
            {"label": f"20% down payment", "value": _fmt(math.down_payment)},
            {"label": "Estimated closing costs (3%)", "value": _fmt(math.closing_costs)},
            {"label": "Total cash needed at close", "value": _fmt(math.cash_needed_at_close)},
        ]
        if math.cash_remaining_after_close is not None:
            highlights.append({"label": "Cash remaining after close", "value": _fmt(math.cash_remaining_after_close)})
        if math.estimated_total_monthly_housing:
            highlights.append({"label": "Estimated monthly housing cost", "value": _fmt(math.estimated_total_monthly_housing)})
        if math.principal_interest_monthly:
            highlights.append({"label": "Principal + interest (est.)", "value": _fmt(math.principal_interest_monthly)})
        if math.dti_estimate:
            highlights.append({"label": f"Est. DTI vs. income", "value": f"{math.dti_estimate}%"})
    else:
        if math.max_affordable_home_price:
            highlights.append({"label": "Max home price (upfront costs only)", "value": _fmt(math.max_affordable_home_price)})

    summary_lines = [f"**{decision.verdict_label}.**", decision.primary_reason]
    summary = " ".join(summary_lines)

    sections: list[dict] = []
    if math.included_assets:
        sections.append({
            "heading": "Liquid accounts included",
            "rows": [{"account": a} for a in math.included_assets],
        })
    if math.excluded_assets:
        sections.append({
            "heading": "Excluded accounts (retirement / child)",
            "rows": [{"account": a} for a in math.excluded_assets],
        })

    all_caveats = _dedupe_caveats(list(math.assumptions) + list(math.caveats) + list(decision.caveats))

    return StructuredAnswer(
        answer_type="numeric",
        title="Home purchase affordability",
        summary=summary,
        highlights=highlights,
        sections=sections,
        caveats=all_caveats,
        suggested_followups=decision.recommended_followups,
        query_path="affordability",
        intent="affordability",
        confidence=0.9,
        answer_strategy="template_only",
        llm_called=False,
    )


def _render_template_reserve(math: ScenarioMathResult, snap: _Snapshot) -> StructuredAnswer:
    liquid = math.gross_liquid_cash
    reserve = math.emergency_reserve_target
    capacity = math.comfortable_spend_capacity
    months = float(liquid / max(snap.monthly_spend, Decimal("1")))

    if months >= 6:
        verdict = "Healthy — exceeds 6-month reserve guideline"
    elif months >= 3:
        verdict = "Adequate — between 3–6 months of reserves"
    else:
        verdict = "Tight — below the 3-month minimum"

    highlights = [
        {"label": "Reserve status", "value": verdict},
        {"label": "Liquid cash", "value": _fmt(liquid)},
        {"label": "Monthly spend (estimated)", "value": _fmt(snap.monthly_spend)},
        {"label": "Months of runway", "value": f"{months:.1f} months"},
        {"label": "6-month reserve target", "value": _fmt(reserve)},
        {"label": "Available beyond reserve", "value": _fmt(capacity)},
    ]

    return StructuredAnswer(
        answer_type="numeric",
        title="Cash reserve analysis",
        summary=(
            f"Your liquid cash ({_fmt(liquid)}) covers approximately {months:.1f} months "
            f"at {_fmt(snap.monthly_spend)}/month. The 6-month target is {_fmt(reserve)}."
        ),
        highlights=highlights,
        caveats=math.assumptions + math.caveats,
        suggested_followups=[
            "How much could I afford for a vacation?",
            "What are my account balances?",
        ],
        query_path="affordability",
        intent="affordability",
        confidence=0.9,
        answer_strategy="template_only",
        llm_called=False,
    )


# ── Layer 3: LLM readability layer ────────────────────────────────────────────

_LLM_AFFORDABILITY_SYSTEM = """\
You are a financial answer narrator for a personal finance app called Coral.
You receive a pre-computed CalculationResult and a pre-computed DecisionResult.

YOUR ROLE:
- Convert the facts into warm, direct, plain-English prose.
- Explain the verdict and the key numbers.
- Mention assumptions and caveats where relevant.
- Keep the tone calm, direct, and non-judgmental.
- If the input includes "protected_goals", frame your answer around whether those
  goals are at risk — but use only the numbers from CalculationResult.amounts.
- If the input includes "time_horizon", acknowledge the time constraint in your narrative.
- If the input includes "user_is_asking_for" = "impact_analysis", frame the answer around
  whether the purchase impacts the protected goal, not just whether it's affordable in isolation.
- If the input includes "user_is_asking_for" = "safety_check", use "stretch" / "comfortable" /
  "safe" framing where appropriate, but ONLY if the verdict supports it.

HARD RULES (violations cause your output to be discarded):
1. Do NOT calculate. Every number must come from CalculationResult.amounts.
2. Do NOT change the verdict_code or verdict_label.
3. Do NOT invent new dollar amounts not present in CalculationResult.
4. Do NOT add assumptions not in CalculationResult.assumptions.
5. Do NOT make any conclusion listed in forbidden_conclusions.
6. Do NOT recommend loans, credit card debt, financing, or risky financial moves.
7. Do NOT mention retirement accounts as a funding option unless the user asked.
8. Suggested followups must come ONLY from DecisionResult.recommended_followups.
9. Do NOT say "I estimate" or "I calculate" — all numbers come from Python, not you.
10. If protected_goals are listed, mention them by name in your summary.

OUTPUT FORMAT — return ONLY this JSON, no markdown fences, no prose outside it:
{
  "title": "<short title for this answer>",
  "summary": "<2-4 sentences explaining the verdict and key insight>",
  "verdict_label": "<must exactly match DecisionResult.verdict_label>",
  "key_numbers": [
    {"label": "<label>", "value": "<formatted value>"}
  ],
  "explanation": "<1-3 sentences elaborating on the primary reason and risk>",
  "caveats": ["<caveat 1>", "<caveat 2>"],
  "suggested_followups": ["<followup 1>", "<followup 2>"]
}
"""


def _build_llm_input(
    question: str,
    math: ScenarioMathResult,
    decision: DecisionResult,
    *,
    protected_goals: list[str] | None = None,
    secondary_goals: list[dict] | None = None,
    time_horizon: str | None = None,
    user_is_asking_for: str = "",
    semantic_scenario_type: str = "",
) -> str:
    """Serialize math + decision into a compact JSON prompt for the LLM."""
    amounts: dict[str, str] = {}
    if math.scenario_type == "purchase_affordability":
        if math.purchase_price is not None:
            amounts["purchase_price"] = f"${math.purchase_price:,.0f}"
        amounts["gross_liquid_cash"] = f"${math.gross_liquid_cash:,.0f}"
        amounts["emergency_reserve_target"] = f"${math.emergency_reserve_target:,.0f}"
        amounts["comfortable_spend_capacity"] = f"${math.comfortable_spend_capacity:,.0f}"
        if math.cash_after_purchase is not None:
            amounts["cash_after_purchase"] = f"${math.cash_after_purchase:,.0f}"
        if math.reserve_gap_after_purchase is not None and math.reserve_gap_after_purchase > 0:
            amounts["reserve_gap_after_purchase"] = f"${math.reserve_gap_after_purchase:,.0f}"
        if math.purchase_as_pct_of_liquid is not None:
            amounts["purchase_as_pct_of_liquid"] = f"{math.purchase_as_pct_of_liquid}%"
    else:  # home
        amounts["gross_liquid_cash"] = f"${math.gross_liquid_cash:,.0f}"
        amounts["emergency_reserve_target"] = f"${math.emergency_reserve_target:,.0f}"
        if math.purchase_price:
            amounts["home_price"] = f"${math.purchase_price:,.0f}"
        if math.down_payment:
            amounts["down_payment"] = f"${math.down_payment:,.0f}"
        if math.closing_costs:
            amounts["closing_costs"] = f"${math.closing_costs:,.0f}"
        if math.cash_needed_at_close:
            amounts["cash_needed_at_close"] = f"${math.cash_needed_at_close:,.0f}"
        if math.cash_remaining_after_close is not None:
            amounts["cash_remaining_after_close"] = f"${math.cash_remaining_after_close:,.0f}"
        if math.estimated_total_monthly_housing:
            amounts["estimated_total_monthly_housing"] = f"${math.estimated_total_monthly_housing:,.0f}"
        if math.dti_estimate:
            amounts["dti_estimate"] = f"{math.dti_estimate}%"

    payload: dict = {
        "scenario_type": math.scenario_type,
        "question": question,
        "verdict": {
            "code": decision.verdict_code,
            "label": decision.verdict_label,
            "severity": decision.severity.value,
            "primary_reason": decision.primary_reason,
        },
        "amounts": amounts,
        "included_assets": math.included_assets,
        "excluded_assets": math.excluded_assets,
        "assumptions": math.assumptions,
        "caveats": math.caveats + decision.caveats,
        "allowed_conclusions": decision.allowed_conclusions,
        "forbidden_conclusions": decision.forbidden_conclusions,
        "recommended_followups": decision.recommended_followups,
    }
    # Inject semantic framing context so the LLM narrator can address the user's intent
    if protected_goals:
        payload["protected_goals"] = protected_goals
    if secondary_goals:
        payload["secondary_goals"] = secondary_goals
    if time_horizon:
        payload["time_horizon"] = time_horizon
    if user_is_asking_for:
        payload["user_is_asking_for"] = user_is_asking_for
    if semantic_scenario_type:
        payload["semantic_scenario_type"] = semantic_scenario_type
    return json.dumps(payload, ensure_ascii=False)


async def _call_llm_for_readability(
    question: str,
    math: ScenarioMathResult,
    decision: DecisionResult,
    *,
    protected_goals: list[str] | None = None,
    secondary_goals: list[dict] | None = None,
    time_horizon: str | None = None,
    user_is_asking_for: str = "",
    semantic_scenario_type: str = "",
) -> dict | None:
    """Call the local LLM to produce a readable JSON answer. Returns None on failure."""
    try:
        from app.config import settings
        from app.services import llm as llm_service

        user_prompt = _build_llm_input(
            question,
            math,
            decision,
            protected_goals=protected_goals,
            secondary_goals=secondary_goals,
            time_horizon=time_horizon,
            user_is_asking_for=user_is_asking_for,
            semantic_scenario_type=semantic_scenario_type,
        )
        raw = await llm_service.generate(
            user_prompt,
            model=settings.ollama.model,
            system=_LLM_AFFORDABILITY_SYSTEM,
            temperature=0.1,
            format_json=True,
            num_ctx=getattr(settings.ollama, "num_ctx", 4096),
        )

        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-z]*\n?", "", text)
            text = re.sub(r"```$", "", text.strip())
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]

        return json.loads(text)
    except Exception as exc:
        logger.warning("affordability.llm_failed", extra={"error": str(exc)})
        return None


# ── AnswerVerifier ─────────────────────────────────────────────────────────────

_PURCHASE_ONLY_TERMS = re.compile(
    r"\b(down payment|closing cost|mortgage|property tax|loan amount|loan term)\b",
    re.IGNORECASE,
)

# Dollar amounts in text, e.g. "$15,000" or "$15k"
_DOLLAR_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:k\b)?", re.IGNORECASE)


def _extract_amounts_from_text(text: str) -> set[int]:
    """Extract all dollar amounts from free text, rounded to nearest dollar."""
    amounts: set[int] = set()
    for m in _DOLLAR_RE.finditer(text):
        try:
            raw = m.group(1).replace(",", "")
            if "k" in m.group(0).lower():
                amounts.add(int(float(raw) * 1000))
            else:
                amounts.add(int(float(raw)))
        except ValueError:
            pass
    return amounts


def _known_amounts(math: ScenarioMathResult) -> set[int]:
    """All dollar amounts present in the math result (±1% tolerance applied at check time)."""
    fields = [
        math.gross_liquid_cash, math.emergency_reserve_target, math.comfortable_spend_capacity,
        math.purchase_price, math.cash_after_purchase, math.reserve_gap_after_purchase,
        math.down_payment, math.closing_costs, math.cash_needed_at_close,
        math.cash_remaining_after_close, math.total_cash_needed_with_reserve,
        math.loan_amount, math.principal_interest_monthly, math.property_tax_monthly,
        math.insurance_monthly, math.maintenance_monthly, math.estimated_total_monthly_housing,
        math.max_affordable_home_price, math.monthly_income, math.monthly_spending, math.monthly_surplus,
    ]
    result: set[int] = set()
    for f in fields:
        if f is not None and f > 0:
            result.add(int(f))
    return result


def _amount_is_known(amount: int, known: set[int]) -> bool:
    """True if amount is within 2% of any known amount."""
    if amount == 0:
        return True
    for k in known:
        if k == 0:
            continue
        ratio = abs(amount - k) / k
        if ratio <= 0.02:
            return True
    return False


def _verify(
    answer: StructuredAnswer,
    math: ScenarioMathResult,
    decision: DecisionResult,
    *,
    protected_goals: list[str] | None = None,
    semantic_scenario_type: str = "",
    user_is_asking_for: str = "",
) -> StructuredAnswer:
    """
    Verify the LLM-produced StructuredAnswer against math + decision.
    Returns the answer with verifier metadata set.
    Repairs: adds warnings; switches to template_only on hard violations.

    Semantic checks (when protected_goals / semantic_scenario_type provided):
    - If protected_goals exist, answer should mention them.
    - If forbidden_assumptions exist, answer must not use them.
    - For purchase_impact_on_goal or multi_goal_affordability, answer should
      mention the protected goal or caveat if unsupported.
    - Answer must not contain numbers absent from ScenarioMathResult.
    - Answer must not change DecisionResult verdict.
    """
    warnings: list[str] = []
    hard_fail = False

    full_text = (answer.summary or "") + " " + (answer.title or "")
    for s in answer.highlights:
        full_text += " " + s.get("value", "") + " " + s.get("label", "")
    full_text = full_text.lower()

    # 1. Verdict label must be present in answer text
    if decision.verdict_label.lower() not in full_text and answer.primary_value != decision.verdict_label:
        warnings.append(f"verifier: verdict_label '{decision.verdict_label}' not reflected in answer")

    # 2. Forbidden conclusions must not appear
    for forbidden in decision.forbidden_conclusions:
        # Strip "Do not say" / "Do not" prefix from rule text for substring check
        check = re.sub(r"^do not (say |mention |recommend |imply )?", "", forbidden.lower()).strip(".'\"")
        if len(check) > 5 and check in full_text:
            warnings.append(f"verifier: forbidden conclusion detected: {check!r}")
            hard_fail = True

    # 3. Purchase answers must not use home-only terms
    if math.scenario_type == "purchase_affordability":
        if _PURCHASE_ONLY_TERMS.search(answer.summary or ""):
            warnings.append("verifier: purchase answer contains home-only terms (down payment/mortgage/etc)")
            hard_fail = True

    # 4. Home answers must mention cash_needed_at_close
    if math.scenario_type == "home_affordability" and math.purchase_price is not None:
        if math.cash_needed_at_close:
            close_str = f"${int(math.cash_needed_at_close):,}"
            if close_str not in (answer.summary or "") and close_str not in str(answer.highlights):
                warnings.append(f"verifier: home answer missing cash_needed_at_close ({close_str})")

    # 4b. Summary must carry at least one dollar figure when the decision's
    # primary_reason does (guards against the LLM paraphrasing away all numbers).
    if "$" in decision.primary_reason and "$" not in (answer.summary or ""):
        warnings.append("verifier: summary dropped all dollar amounts present in primary_reason")
        hard_fail = True

    # 5. If verdict is insufficient_data, answer must not imply approval
    if decision.verdict_code in (
        PurchaseVerdictCode.INSUFFICIENT_DATA.value,
        HomeVerdictCode.INSUFFICIENT_DATA.value,
    ):
        approval_words = ["affordable", "you can", "looks good", "comfortable", "possible"]
        for word in approval_words:
            if word in full_text:
                warnings.append(f"verifier: insufficient_data verdict but approval word found: {word!r}")
                hard_fail = True

    # 6. Dollar amounts in answer must be within 2% of known math amounts
    known = _known_amounts(math)
    text_amounts = _extract_amounts_from_text((answer.summary or "") + " " + str(answer.highlights))
    for amt in text_amounts:
        if amt >= 1000 and not _amount_is_known(amt, known):
            warnings.append(f"verifier: invented amount ${amt:,} not found in ScenarioMathResult")
            hard_fail = True

    # 7. Suggested followups must be subset of recommended_followups
    allowed_followups = {f.lower() for f in decision.recommended_followups}
    for fp in answer.suggested_followups:
        if fp.lower() not in allowed_followups:
            warnings.append(f"verifier: followup not in recommended_followups: {fp!r}")
            # soft warning only — don't hard-fail on followup drift

    # 8. Semantic scenario checks (only when semantic parser was invoked)
    if protected_goals:
        # For impact/multi-goal scenarios, the answer should mention the protected goal
        if semantic_scenario_type in ("purchase_impact_on_goal", "multi_goal_affordability"):
            mentioned = any(
                g.lower() in full_text
                for g in protected_goals
                for g in [g.lower()] + g.lower().split()  # check whole phrase and words
            )
            if not mentioned:
                warnings.append(
                    f"verifier: semantic protected_goals {protected_goals!r} not mentioned "
                    f"in answer for scenario_type={semantic_scenario_type!r} — soft warning"
                )
                # Soft warning only — protected goal mention is good practice, not a hard rule

    # 9. Answer must not say Gemma-calculated phrases
    _GEMMA_CALC_PHRASES = [
        "i estimate your cash flow",
        "i calculate",
        "i estimated",
        "i computed",
        "based on my calculation",
        "my estimate",
    ]
    for phrase in _GEMMA_CALC_PHRASES:
        if phrase in full_text:
            warnings.append(f"verifier: answer contains LLM-as-calculator phrase: {phrase!r}")
            hard_fail = True

    answer.verifier_passed = not hard_fail
    answer.verifier_warnings = warnings
    answer.verifier_repaired = hard_fail

    if warnings:
        logger.warning(
            "affordability.verifier_warnings",
            extra={"warnings": warnings, "hard_fail": hard_fail},
        )

    return answer


# ── Assembly: LLM output → StructuredAnswer ────────────────────────────────────

def _assemble_from_llm(
    llm_out: dict,
    math: ScenarioMathResult,
    decision: DecisionResult,
) -> StructuredAnswer:
    """Convert LLM JSON dict into a StructuredAnswer with math-derived highlights."""
    # Build highlights from math (authoritative numbers, not LLM text)
    highlights: list[dict[str, str]] = [
        {"label": "Verdict", "value": decision.verdict_label},
    ]
    if math.scenario_type == "purchase_affordability":
        highlights += [
            {"label": "Liquid cash", "value": _fmt(math.gross_liquid_cash)},
            {"label": "Emergency reserve target", "value": _fmt(math.emergency_reserve_target)},
            {"label": "Available after reserve", "value": _fmt(math.comfortable_spend_capacity)},
        ]
        if math.purchase_price is not None:
            highlights.append({"label": f"Cost of {math.purchase_item}", "value": _fmt(math.purchase_price)})
        if math.cash_after_purchase is not None:
            highlights.append({"label": "Cash after purchase", "value": _fmt(math.cash_after_purchase)})
    else:  # home
        highlights += [
            {"label": "Liquid cash", "value": _fmt(math.gross_liquid_cash)},
            {"label": "Emergency reserve target", "value": _fmt(math.emergency_reserve_target)},
        ]
        if math.purchase_price:
            highlights += [
                {"label": "Home price", "value": _fmt(math.purchase_price)},
                {"label": "Down payment (20%)", "value": _fmt(math.down_payment)},
                {"label": "Closing costs (3%)", "value": _fmt(math.closing_costs)},
                {"label": "Cash needed at close", "value": _fmt(math.cash_needed_at_close)},
            ]
        if math.estimated_total_monthly_housing:
            highlights.append({"label": "Est. monthly housing cost", "value": _fmt(math.estimated_total_monthly_housing)})

    sections: list[dict] = []
    if math.included_assets:
        sections.append({"heading": "Liquid accounts included", "rows": [{"account": a} for a in math.included_assets]})
    if math.excluded_assets:
        sections.append({"heading": "Excluded (retirement / child)", "rows": [{"account": a} for a in math.excluded_assets]})

    # Caveats are Python-authoritative only — the LLM may not invent or paraphrase
    # its own caveat text (hard rule: "Gemma must not invent assumptions").
    # Its "caveats" field in the JSON output is ignored by design.
    all_caveats = _dedupe_caveats(list(math.assumptions) + list(math.caveats) + list(decision.caveats))

    # Only accept followups that are in the allowed set
    allowed_fp = set(decision.recommended_followups)
    followups = [fp for fp in (llm_out.get("suggested_followups") or []) if fp in allowed_fp]
    if not followups:
        followups = decision.recommended_followups[:3]

    title = (
        llm_out.get("title")
        or (f"Can you afford the {math.purchase_item}?" if math.scenario_type == "purchase_affordability" else "Home purchase affordability")
    )
    summary = llm_out.get("summary") or decision.primary_reason
    # Guard against an LLM summary that drops all dollar figures present in the
    # authoritative primary_reason (e.g. paraphrasing away every number).
    if "$" in decision.primary_reason and "$" not in summary:
        summary = f"{summary} {decision.primary_reason}".strip()

    return StructuredAnswer(
        answer_type="numeric",
        title=title,
        summary=summary,
        highlights=highlights,
        sections=sections,
        caveats=all_caveats,
        suggested_followups=followups,
        query_path="affordability",
        intent="affordability",
        confidence=0.9,
        answer_strategy="hybrid_template_plus_llm",
        llm_called=True,
    )


# ── No-data answer ─────────────────────────────────────────────────────────────

def _no_data_answer(item: str) -> StructuredAnswer:
    return StructuredAnswer(
        answer_type="prose",
        title="No balance data available",
        summary=(
            f"I couldn't find any account balance snapshots to analyze affordability for {item}. "
            "Please upload at least one bank or investment statement to get started."
        ),
        caveats=["No balance_snapshots rows found."],
        suggested_followups=["What documents have been uploaded?", "What institutions are covered?"],
        query_path="affordability",
        intent="affordability",
        confidence=0.5,
        answer_strategy="template_only",
        llm_called=False,
        verifier_passed=True,
    )


# ── Main entry point ───────────────────────────────────────────────────────────

async def analyze(
    task_type: str,
    purchase_price: float | None,
    purchase_item: str,
    purchase_category: str,
    req_id: str = "",
    question: str = "",
    # ── Semantic scenario context (from SemanticScenarioParser, optional) ─────
    # These are framing/caveat inputs only. They never change math or verdict.
    semantic_scenario_type: str = "",
    semantic_parser_called: bool = False,
    semantic_parser_confidence: float = 0.0,
    protected_goals: list[str] | None = None,
    secondary_goals: list[dict] | None = None,
    time_horizon: str | None = None,
    constraints: list[str] | None = None,
    user_is_asking_for: str = "",
) -> StructuredAnswer:
    """
    Run the three-layer affordability pipeline.

    Layer 1: Python computes ScenarioMathResult (all numbers, Decimal)
    Layer 2: Python decides DecisionResult (verdict, reason codes, allowed/forbidden)
    Layer 3: LLM narrates (only explains; cannot calculate or change verdict)
              → AnswerVerifier checks; falls back to deterministic template on violation
    """
    _protected_goals: list[str] = protected_goals or []
    _secondary_goals: list[dict] = secondary_goals or []
    _constraints: list[str] = constraints or []

    logger.info(
        "affordability.start",
        extra={
            "task_type": task_type,
            "purchase_price": purchase_price,
            "purchase_item": purchase_item,
            "purchase_category": purchase_category,
            "request_id": req_id,
            "semantic_parser_called": semantic_parser_called,
            "semantic_scenario_type": semantic_scenario_type or "none",
            "protected_goals": _protected_goals,
            "user_is_asking_for": user_is_asking_for or "none",
        },
    )

    try:
        rows = await _fetch_balance_snapshot()
        monthly_spend = await _fetch_monthly_spend()
        monthly_income = await _fetch_income_estimate()
    except Exception as exc:
        logger.warning("affordability.db_error", extra={"error": str(exc), "request_id": req_id})
        return _no_data_answer(purchase_item)

    if not rows:
        return _no_data_answer(purchase_item)

    snap = _Snapshot(rows, monthly_spend, monthly_income)
    price_dec = Decimal(str(purchase_price)) if purchase_price is not None else None

    # ── Layer 1: math ──────────────────────────────────────────────────────────
    if task_type == "cash_reserve_analysis":
        math = ScenarioMathResult(
            scenario_type="cash_reserve_analysis",
            gross_liquid_cash=snap.liquid_cash,
            emergency_reserve_target=snap.emergency_reserve_target,
            comfortable_spend_capacity=snap.comfortable_spend_capacity,
            monthly_income=snap.monthly_income,
            monthly_spending=snap.monthly_spend,
            monthly_surplus=snap.monthly_surplus,
            included_assets=snap.liquid_accounts,
            excluded_assets=snap.excluded_accounts,
            assumptions=[
                f"Monthly spend estimated from transaction history: ${snap.monthly_spend:,.0f}/month.",
                f"Emergency reserve: {_EMERGENCY_FUND_MONTHS} months × ${snap.monthly_spend:,.0f} = ${snap.emergency_reserve_target:,.0f}.",
            ],
            caveats=["This is not financial advice."],
        )
        decision = DecisionResult(
            verdict_code="reserve_analysis",
            verdict_label="Reserve analysis",
            severity=DecisionSeverity.OK,
            primary_reason="Cash reserve status computed.",
            allowed_conclusions=["Reserve health shown."],
            forbidden_conclusions=[],
            recommended_followups=["How much could I afford for a vacation?", "What are my account balances?"],
        )
        answer = _render_template_reserve(math, snap)
        answer.request_id = req_id
        return answer

    elif task_type == "home_affordability":
        math = _calc_home(snap, price_dec)
        decision = _decide_home(math)
    else:
        # purchase_affordability or goal_affordability
        math = _calc_purchase(snap, price_dec, purchase_item, purchase_category, question)
        decision = _decide_purchase(math)

    # ── Semantic context enrichment: add framing caveats + reason codes ───────
    # This block uses Python-only logic. Gemma output (protected_goals, time_horizon,
    # etc.) is used ONLY to add caveats and reason codes — never to change math or verdict.
    if semantic_parser_called:
        if _protected_goals:
            for goal in _protected_goals:
                math.caveats.append(
                    f"Your question mentions protecting '{goal}'. This analysis checks "
                    f"whether the purchase preserves your financial position relative to that goal."
                )
            # Add reason codes so downstream answer framing is aware
            if any("house" in g.lower() or "home" in g.lower() or "down" in g.lower() for g in _protected_goals):
                if "protects_house_savings" not in decision.reason_codes:
                    decision.reason_codes.append("protects_house_savings")
            if any("emergency" in g.lower() or "reserve" in g.lower() for g in _protected_goals):
                if "emergency_fund_protection_requested" not in decision.reason_codes:
                    decision.reason_codes.append("emergency_fund_protection_requested")

        if _secondary_goals:
            if "future_home_goal_mentioned" not in decision.reason_codes:
                for g in _secondary_goals:
                    if isinstance(g, dict) and g.get("goal_type") == "home_purchase":
                        decision.reason_codes.append("future_home_goal_mentioned")
                        break
            if len(_secondary_goals) > 0 and "multi_goal_tradeoff" not in decision.reason_codes:
                decision.reason_codes.append("multi_goal_tradeoff")

        if time_horizon:
            math.caveats.append(f"Time horizon context: '{time_horizon}'.")

        if _constraints:
            for constraint in _constraints:
                if constraint not in math.caveats:
                    math.caveats.append(f"User constraint: '{constraint}'.")

        if semantic_scenario_type in ("purchase_impact_on_goal", "multi_goal_affordability"):
            # Make sure the follow-ups reflect the multi-goal context
            if _protected_goals:
                goal_str = _protected_goals[0]
                followup = f"Would buying a {purchase_item} affect my {goal_str}?"
                if followup not in decision.recommended_followups:
                    decision.recommended_followups.insert(0, followup)

    # ── Layer 3: LLM readability (with template fallback) ──────────────────────
    llm_out = await _call_llm_for_readability(
        question or purchase_item,
        math,
        decision,
        protected_goals=_protected_goals if semantic_parser_called else None,
        secondary_goals=_secondary_goals if semantic_parser_called else None,
        time_horizon=time_horizon if semantic_parser_called else None,
        user_is_asking_for=user_is_asking_for if semantic_parser_called else "",
        semantic_scenario_type=semantic_scenario_type if semantic_parser_called else "",
    )

    if llm_out is not None:
        answer = _assemble_from_llm(llm_out, math, decision)
    else:
        # LLM unavailable or errored — use deterministic template
        if task_type == "home_affordability":
            answer = _render_template_home(math, decision)
        else:
            answer = _render_template_purchase(math, decision)

    # ── Verifier ───────────────────────────────────────────────────────────────
    answer = _verify(
        answer,
        math,
        decision,
        protected_goals=_protected_goals if semantic_parser_called else None,
        semantic_scenario_type=semantic_scenario_type if semantic_parser_called else "",
        user_is_asking_for=user_is_asking_for if semantic_parser_called else "",
    )

    if answer.verifier_repaired:
        # Hard violation — discard LLM output, use template
        if task_type == "home_affordability":
            answer = _render_template_home(math, decision)
        else:
            answer = _render_template_purchase(math, decision)
        answer.verifier_repaired = True
        answer.verifier_warnings = answer.verifier_warnings  # preserve warnings

    # ── Attach semantic debug metadata ─────────────────────────────────────────
    # These fields are for debug/observability only, not shown in standard responses.
    answer.request_id = req_id
    if semantic_parser_called:
        # Store metadata in searched_filters (used by debug payload) without exposing
        # to standard API response.
        answer.searched_filters["semantic_parser_called"] = True
        answer.searched_filters["semantic_scenario_type"] = semantic_scenario_type or "unknown"
        answer.searched_filters["semantic_parser_confidence"] = round(semantic_parser_confidence, 3)
        answer.searched_filters["protected_goals"] = _protected_goals
        answer.searched_filters["user_is_asking_for"] = user_is_asking_for or "unknown"

    return answer
