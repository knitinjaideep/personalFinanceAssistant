"""
math_engine.py — Deterministic financial calculations for affordability analysis.

Responsibilities:
- All arithmetic performed with Python Decimal (no floats in financial output)
- Scenario-specific calculation paths (home, car/purchase, travel, general)
- DTI, reserve impact, affordability ratio, post-purchase liquidity
- Transparent assumptions list for every computed value
- No LLM calls; no policy verdicts — pure math

MathResult is the single authoritative number object. All downstream layers
(decision_engine, advisory_context, narrative_builder, verifier) must use
only MathResult fields — never recalculate.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .data_collector import FinancialSnapshot, _MONTHLY_SPEND_FALLBACK
from .scenario_parser import AffordabilityScenario

# ── Policy constants ───────────────────────────────────────────────────────────

_DOWN_PAYMENT_PCT = Decimal("0.20")
_CLOSING_COST_PCT = Decimal("0.03")
_MORTGAGE_RATE = Decimal("0.07")       # 7% fixed — conservative
_LOAN_TERM_YEARS = 30
_PROPERTY_TAX_ANNUAL_PCT = Decimal("0.012")
_INSURANCE_MONTHLY = Decimal("150")
_MAINTENANCE_ANNUAL_PCT = Decimal("0.01")
_MAX_DTI = Decimal("0.28")
_EMERGENCY_FUND_MONTHS = 6


def _q(v: Decimal) -> Decimal:
    """Round to nearest dollar."""
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _qpct(v: Decimal) -> Decimal:
    """Round percentage to one decimal place."""
    return v.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


class MathResult(BaseModel):
    """
    All computed financial numbers for an affordability scenario.
    Every field that could not be computed is None (never 0 as a proxy for unknown).
    The LLM receives a serialised subset of this; it must not recalculate anything.
    """
    scenario_type: str = ""
    purchase_item: str = ""
    purchase_category: str = ""

    # Amounts
    purchase_amount: Optional[Decimal] = None
    purchase_amount_source: str = "unknown"   # explicit | assumed | unknown

    # Liquidity picture
    liquid_cash: Decimal = Decimal("0")
    emergency_reserve_target: Decimal = Decimal("0")
    comfortable_spend_capacity: Decimal = Decimal("0")   # liquid − reserve (≥0)

    # Post-purchase picture
    cash_after_purchase: Optional[Decimal] = None
    reserve_gap_after: Optional[Decimal] = None          # how far below reserve after purchase (>0 = short)
    purchase_as_pct_of_liquid: Optional[Decimal] = None  # purchase / liquid * 100
    affordability_ratio: Optional[Decimal] = None        # purchase / comfortable_capacity (>1 = overage)

    # Home-specific
    down_payment: Optional[Decimal] = None
    closing_costs: Optional[Decimal] = None
    cash_needed_at_close: Optional[Decimal] = None
    cash_remaining_after_close: Optional[Decimal] = None
    cash_gap_at_close: Optional[Decimal] = None          # positive = short (hard no), negative = surplus
    comfortable_cash_gap: Optional[Decimal] = None       # cash_at_close + reserve − liquid
    loan_amount: Optional[Decimal] = None
    principal_interest_monthly: Optional[Decimal] = None
    property_tax_monthly: Optional[Decimal] = None
    insurance_monthly: Optional[Decimal] = None
    maintenance_monthly: Optional[Decimal] = None
    total_monthly_housing: Optional[Decimal] = None
    dti_pct: Optional[Decimal] = None                    # housing / income * 100
    max_affordable_home_price: Optional[Decimal] = None  # when no price given

    # What-if / time-horizon
    months_to_save_for_purchase: Optional[Decimal] = None   # if surplus > 0 and price > capacity
    savings_per_month_needed: Optional[Decimal] = None

    # Income / spend context
    monthly_income: Optional[Decimal] = None
    monthly_spending: Optional[Decimal] = None
    monthly_surplus: Optional[Decimal] = None

    # Account transparency
    liquid_account_labels: list[str] = Field(default_factory=list)
    excluded_account_labels: list[str] = Field(default_factory=list)
    investment_value: Decimal = Decimal("0")
    retirement_value: Decimal = Decimal("0")

    # Transparency
    assumptions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)

    def all_known_amounts(self) -> set[int]:
        """Return all dollar amounts present in this result (for verifier use)."""
        fields = [
            self.purchase_amount, self.liquid_cash, self.emergency_reserve_target,
            self.comfortable_spend_capacity, self.cash_after_purchase, self.reserve_gap_after,
            self.down_payment, self.closing_costs, self.cash_needed_at_close,
            self.cash_remaining_after_close, self.cash_gap_at_close, self.comfortable_cash_gap,
            self.loan_amount, self.principal_interest_monthly,
            self.property_tax_monthly, self.insurance_monthly, self.maintenance_monthly,
            self.total_monthly_housing, self.max_affordable_home_price,
            self.monthly_income, self.monthly_spending, self.monthly_surplus,
            self.investment_value, self.retirement_value,
        ]
        result: set[int] = set()
        for f in fields:
            if f is not None and f > 0:
                result.add(int(f))
        # Include derived shortfall (purchase_amount - liquid_cash) so the LLM can
        # express the gap without triggering the invented-amount guard.
        if self.purchase_amount and self.liquid_cash and self.purchase_amount > self.liquid_cash:
            result.add(int(self.purchase_amount - self.liquid_cash))
        # Include post-close remainder (liquid_cash - cash_needed_at_close) for home answers.
        if self.liquid_cash and self.cash_needed_at_close and self.liquid_cash > self.cash_needed_at_close:
            result.add(int(self.liquid_cash - self.cash_needed_at_close))
        return result


# ── Shared assumptions builder ────────────────────────────────────────────────

def _base_assumptions(snap: FinancialSnapshot) -> list[str]:
    spend = snap.monthly_spending or _MONTHLY_SPEND_FALLBACK
    reserve = snap.emergency_reserve_target
    a = [
        f"Emergency reserve target: {_EMERGENCY_FUND_MONTHS} months × "
        f"${spend:,.0f}/month spending = ${reserve:,.0f}.",
        "Retirement accounts (IRA, Roth IRA, 401k) excluded from liquid cash.",
        "529 and child education accounts excluded from liquid cash.",
    ]
    if snap.investment_value > 0:
        a.append(
            f"Brokerage/advisory accounts (${snap.investment_value:,.0f}) not counted as liquid — "
            "liquidating investments carries tax and market-timing risk."
        )
    return a


def _base_caveats() -> list[str]:
    return [
        "This is not financial advice. Consult a financial advisor for major decisions.",
        "This does not account for upcoming large expenses, taxes, or bills unless they appear "
        "as transactions in Coral.",
    ]


# ── Purchase math ──────────────────────────────────────────────────────────────

def compute_purchase(scenario: AffordabilityScenario, snap: FinancialSnapshot) -> MathResult:
    """Compute all numbers for a non-home purchase (car, luxury, travel, general)."""
    assumptions = list(scenario.assumptions_used) + _base_assumptions(snap)
    caveats = _base_caveats()

    liquid = snap.liquid_cash
    reserve = snap.emergency_reserve_target
    capacity = snap.comfortable_spend_capacity
    price = scenario.purchase_amount

    result = MathResult(
        scenario_type=scenario.scenario_type,
        purchase_item=scenario.purchase_item,
        purchase_category=scenario.purchase_category,
        purchase_amount=price,
        purchase_amount_source=scenario.purchase_amount_source,
        liquid_cash=liquid,
        emergency_reserve_target=reserve,
        comfortable_spend_capacity=capacity,
        monthly_income=snap.monthly_income,
        monthly_spending=snap.monthly_spending,
        monthly_surplus=snap.monthly_surplus,
        liquid_account_labels=[a.account_name for a in snap.liquid_accounts],
        excluded_account_labels=snap.excluded_account_labels,
        investment_value=snap.investment_value,
        retirement_value=snap.retirement_value,
        assumptions=assumptions,
        caveats=caveats,
    )

    if price is not None and liquid > 0:
        cash_after = liquid - price
        reserve_gap = max(Decimal("0"), reserve - cash_after)
        pct_of_liquid = _qpct(price / liquid * 100)
        aff_ratio = _qpct(price / capacity) if capacity > 0 else None

        result.cash_after_purchase = cash_after
        result.reserve_gap_after = reserve_gap
        result.purchase_as_pct_of_liquid = pct_of_liquid
        result.affordability_ratio = aff_ratio

        # What-if: months to save if currently can't afford comfortably
        if price > capacity and snap.monthly_surplus and snap.monthly_surplus > 0:
            shortfall = price - capacity
            months = _q(shortfall / snap.monthly_surplus)
            result.months_to_save_for_purchase = months
            result.savings_per_month_needed = _q(shortfall / 12)  # to save in 1 year

    return result


# ── Home math ──────────────────────────────────────────────────────────────────

def compute_home(scenario: AffordabilityScenario, snap: FinancialSnapshot) -> MathResult:
    """Compute all numbers for a home purchase."""
    down_pct = scenario.down_payment_pct or _DOWN_PAYMENT_PCT
    assumptions = [
        f"Down payment: {int(down_pct * 100)}% of purchase price.",
        f"Closing costs: {int(_CLOSING_COST_PCT * 100)}% of purchase price (varies by location).",
        f"Mortgage rate: {float(_MORTGAGE_RATE * 100):.1f}% fixed (current estimate; rates change).",
        f"Loan term: {_LOAN_TERM_YEARS} years.",
        f"Emergency reserve target: {_EMERGENCY_FUND_MONTHS} months × "
        f"${snap.monthly_spending:,.0f}/month = ${snap.emergency_reserve_target:,.0f}.",
        "Retirement accounts excluded from down payment funds.",
    ]
    caveats = [
        "Monthly payment estimate excludes HOA, flood insurance, PMI, and local tax variations.",
        "This is not financial advice. Work with a mortgage lender for accurate qualification.",
    ]
    if scenario.location:
        caveats.append(f"Property tax rate used: 1.2% annual (local rates in {scenario.location} may differ).")

    liquid = snap.liquid_cash
    reserve = snap.emergency_reserve_target
    capacity = snap.comfortable_spend_capacity
    price = scenario.purchase_amount

    result = MathResult(
        scenario_type="home_purchase",
        purchase_item=scenario.purchase_item or "home",
        purchase_category="real_estate",
        purchase_amount=price,
        purchase_amount_source=scenario.purchase_amount_source,
        liquid_cash=liquid,
        emergency_reserve_target=reserve,
        comfortable_spend_capacity=capacity,
        monthly_income=snap.monthly_income,
        monthly_spending=snap.monthly_spending,
        monthly_surplus=snap.monthly_surplus,
        liquid_account_labels=[a.account_name for a in snap.liquid_accounts],
        excluded_account_labels=snap.excluded_account_labels,
        investment_value=snap.investment_value,
        retirement_value=snap.retirement_value,
        assumptions=assumptions,
        caveats=caveats,
    )

    if price is not None:
        down = _q(price * down_pct)
        closing = _q(price * _CLOSING_COST_PCT)
        cash_at_close = down + closing
        cash_remaining = liquid - cash_at_close
        cash_gap = cash_at_close - liquid               # positive = short (hard no)
        comfortable_gap = (cash_at_close + reserve) - liquid   # positive = short (tight)

        loan = price - down
        # Monthly P&I: M = P × r(1+r)^n / ((1+r)^n − 1)
        r = _MORTGAGE_RATE / 12
        n = Decimal(_LOAN_TERM_YEARS * 12)
        pi = _q(loan * r * (1 + r) ** n / ((1 + r) ** n - 1))
        prop_tax = _q(price * _PROPERTY_TAX_ANNUAL_PCT / 12)
        maintenance = _q(price * _MAINTENANCE_ANNUAL_PCT / 12)
        total_housing = pi + prop_tax + _INSURANCE_MONTHLY + maintenance

        dti: Decimal | None = None
        if snap.monthly_income and snap.monthly_income > 0:
            dti = _qpct(total_housing / snap.monthly_income * 100)

        result.down_payment = down
        result.closing_costs = closing
        result.cash_needed_at_close = cash_at_close
        result.cash_remaining_after_close = cash_remaining
        result.cash_gap_at_close = cash_gap
        result.comfortable_cash_gap = comfortable_gap
        result.loan_amount = loan
        result.principal_interest_monthly = pi
        result.property_tax_monthly = prop_tax
        result.insurance_monthly = _INSURANCE_MONTHLY
        result.maintenance_monthly = maintenance
        result.total_monthly_housing = total_housing
        result.dti_pct = dti
    else:
        # No price — compute max affordable from available cash
        if capacity > 0:
            max_price = _q(capacity / (down_pct + _CLOSING_COST_PCT))
            result.max_affordable_home_price = max_price

    return result


# ── Dispatcher ────────────────────────────────────────────────────────────────

def compute(scenario: AffordabilityScenario, snap: FinancialSnapshot) -> MathResult:
    """Dispatch to the right calculation based on scenario type."""
    if scenario.scenario_type == "home_purchase":
        return compute_home(scenario, snap)
    return compute_purchase(scenario, snap)
