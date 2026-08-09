"""
decision_engine.py — Deterministic verdict for affordability analysis.

Verdict codes (simplified from the old PurchaseVerdictCode / HomeVerdictCode split):
  COMFORTABLE       — within capacity, reserve preserved
  REASONABLE        — payable, reserve slightly dipped but manageable
  STRETCH           — payable but reserve significantly depleted
  NOT_AFFORDABLE    — cannot cover from liquid cash
  NEEDS_MORE_INFO   — insufficient data to make a determination

Each verdict includes:
  - confidence (0–1)
  - primary_reason  — the single most important fact
  - secondary_reasons — supporting context
  - hard_constraints  — facts that cannot be talked around
  - soft_constraints  — risks worth mentioning
  - allowed_conclusions / forbidden_conclusions — injected into LLM prompt

No LLM involvement here. The LLM receives this result and may only narrate it.
"""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from .math_engine import MathResult

_MAX_DTI_PCT = Decimal("28")   # 28% housing-to-income guideline


class VerdictCode(str, Enum):
    COMFORTABLE = "comfortable"
    REASONABLE = "reasonable"
    STRETCH = "stretch"
    NOT_AFFORDABLE = "not_affordable"
    NEEDS_MORE_INFO = "needs_more_info"


class VerdictSeverity(str, Enum):
    OK = "ok"
    WATCH = "watch"
    CAUTION = "caution"
    STOP = "stop"


class DecisionResult(BaseModel):
    verdict_code: VerdictCode
    verdict_label: str
    severity: VerdictSeverity
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    primary_reason: str
    secondary_reasons: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_constraints: list[str] = Field(default_factory=list)

    allowed_conclusions: list[str] = Field(default_factory=list)
    forbidden_conclusions: list[str] = Field(default_factory=list)
    recommended_followups: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


# ── Purchase decision ─────────────────────────────────────────────────────────

def _decide_purchase(math: MathResult) -> DecisionResult:
    liquid = math.liquid_cash
    reserve = math.emergency_reserve_target
    capacity = math.comfortable_spend_capacity
    price = math.purchase_amount
    item = math.purchase_item or "purchase"

    # No balance data
    if liquid == 0:
        return DecisionResult(
            verdict_code=VerdictCode.NEEDS_MORE_INFO,
            verdict_label="Needs more info",
            severity=VerdictSeverity.STOP,
            confidence=0.0,
            primary_reason="No account balance data found in Coral.",
            hard_constraints=["Cannot assess affordability without balance data."],
            allowed_conclusions=["No account balance data is available to make this assessment."],
            forbidden_conclusions=[
                "Do not imply the purchase is affordable.",
                "Do not imply the purchase is unaffordable.",
            ],
            recommended_followups=[
                "Upload a bank or savings statement to Coral.",
                "What documents have been uploaded?",
            ],
        )

    # No price
    if price is None:
        return DecisionResult(
            verdict_code=VerdictCode.NEEDS_MORE_INFO,
            verdict_label="Needs more info",
            severity=VerdictSeverity.WATCH,
            confidence=0.5,
            primary_reason="No purchase price was specified or estimated.",
            hard_constraints=["Cannot give a precise verdict without a price."],
            allowed_conclusions=[
                f"Available for discretionary spending (after reserve): ${capacity:,.0f}.",
                "Provide the item price for a precise answer.",
            ],
            forbidden_conclusions=[
                "Do not say affordable or unaffordable without a price.",
            ],
            recommended_followups=[
                f"Can we afford a specific {item}?",
                "What is my available cash balance?",
                "How much do I spend per month?",
            ],
        )

    cash_after = math.cash_after_purchase or (liquid - price)
    reserve_gap = math.reserve_gap_after or Decimal("0")

    # Cannot cover from liquid at all
    if price > liquid:
        shortfall = price - liquid
        return DecisionResult(
            verdict_code=VerdictCode.NOT_AFFORDABLE,
            verdict_label="Not affordable",
            severity=VerdictSeverity.STOP,
            confidence=1.0,
            primary_reason=(
                f"The {item} costs ${price:,.0f}, which exceeds liquid cash of ${liquid:,.0f}."
            ),
            secondary_reasons=[
                f"Liquid cash is ${shortfall:,.0f} short of the purchase price.",
            ],
            hard_constraints=[
                f"Cannot cover ${price:,.0f} from liquid cash of ${liquid:,.0f}.",
                "Retirement and investment accounts are not counted as liquid.",
            ],
            allowed_conclusions=[
                f"The {item} costs ${price:,.0f}, which exceeds available liquid cash.",
                f"The shortfall is ${shortfall:,.0f}.",
            ],
            forbidden_conclusions=[
                "Do not say affordable.",
                "Do not recommend using retirement accounts.",
                "Do not recommend financing or credit card debt.",
                "Do not mention down payment or closing costs — this is not a home purchase.",
            ],
            recommended_followups=[
                "What is my total net worth including investment accounts?",
                "How much could I save in 6 months at my current rate?",
                "What are my current account balances?",
            ],
        )

    # Comfortable — fits within capacity (reserve fully preserved)
    if price <= capacity:
        remaining = capacity - price
        return DecisionResult(
            verdict_code=VerdictCode.COMFORTABLE,
            verdict_label="Comfortable",
            severity=VerdictSeverity.OK,
            confidence=0.95,
            primary_reason=(
                f"The ${price:,.0f} {item} fits within the ${capacity:,.0f} available "
                f"after preserving the ${reserve:,.0f} emergency reserve."
            ),
            secondary_reasons=[
                f"${remaining:,.0f} remains after the purchase.",
            ],
            hard_constraints=[],
            soft_constraints=[],
            allowed_conclusions=[
                f"The {item} looks affordable.",
                f"The emergency reserve of ${reserve:,.0f} is fully preserved.",
                f"${remaining:,.0f} remains after the purchase.",
            ],
            forbidden_conclusions=[
                "Do not say this is a risky or stretch purchase.",
                "Do not mention down payment or closing costs — this is not a home purchase.",
            ],
            recommended_followups=[
                f"Would buying a {item} hurt my house savings?",
                "What is my total net worth?",
                "How much do I spend per month on average?",
            ],
        )

    # Reasonable — payable but dips slightly into reserve
    reserve_dip_pct = reserve_gap / reserve * 100 if reserve > 0 else Decimal("0")
    if reserve_dip_pct <= Decimal("30"):
        return DecisionResult(
            verdict_code=VerdictCode.REASONABLE,
            verdict_label="Reasonable with caution",
            severity=VerdictSeverity.WATCH,
            confidence=0.85,
            primary_reason=(
                f"The ${price:,.0f} {item} is payable from liquid cash (${liquid:,.0f}) "
                f"but leaves ${cash_after:,.0f} — ${reserve_gap:,.0f} below the "
                f"${reserve:,.0f} emergency reserve."
            ),
            secondary_reasons=[
                f"Reserve shortfall after purchase: ${reserve_gap:,.0f} ({reserve_dip_pct:.0f}% of target).",
            ],
            hard_constraints=[],
            soft_constraints=[
                f"Reserve would be ${reserve_gap:,.0f} below the recommended ${reserve:,.0f} target.",
            ],
            allowed_conclusions=[
                f"You can pay for the {item}.",
                f"It modestly dips into the emergency reserve (${reserve_gap:,.0f} short).",
                "Consider rebuilding the reserve after this purchase.",
            ],
            forbidden_conclusions=[
                "Do not say this is fully comfortable — the reserve is slightly short.",
                "Do not say this is unaffordable — you can technically pay for it.",
                "Do not mention down payment or closing costs — this is not a home purchase.",
            ],
            recommended_followups=[
                "How much could I save in 3 months to make this comfortable?",
                "What is my monthly savings rate?",
                f"Would buying a {item} hurt my house savings?",
            ],
        )

    # Stretch — reserve significantly depleted
    return DecisionResult(
        verdict_code=VerdictCode.STRETCH,
        verdict_label="Stretch",
        severity=VerdictSeverity.CAUTION,
        confidence=0.9,
        primary_reason=(
            f"The ${price:,.0f} {item} is technically payable but would leave only "
            f"${cash_after:,.0f} — ${reserve_gap:,.0f} below the "
            f"${reserve:,.0f} recommended emergency reserve."
        ),
        secondary_reasons=[
            "This significantly reduces the financial buffer for emergencies.",
        ],
        hard_constraints=[
            f"Emergency reserve would fall ${reserve_gap:,.0f} short after this purchase.",
        ],
        soft_constraints=[],
        allowed_conclusions=[
            f"You can technically pay for the {item}.",
            "This is a stretch because the emergency reserve would be significantly depleted.",
        ],
        forbidden_conclusions=[
            "Do not say comfortable.",
            "Do not recommend credit card debt or loans.",
            "Do not mention down payment or closing costs — this is not a home purchase.",
        ],
        recommended_followups=[
            "What are my current account balances?",
            "How much do I spend per month?",
            "How much could I save in 6 months?",
        ],
    )


# ── Home decision ──────────────────────────────────────────────────────────────

def _decide_home(math: MathResult) -> DecisionResult:
    liquid = math.liquid_cash

    if liquid == 0:
        return DecisionResult(
            verdict_code=VerdictCode.NEEDS_MORE_INFO,
            verdict_label="Needs more info",
            severity=VerdictSeverity.STOP,
            confidence=0.0,
            primary_reason="No balance data found.",
            hard_constraints=["Cannot assess home affordability without balance data."],
            allowed_conclusions=["No balance data available."],
            forbidden_conclusions=["Do not imply affordability either way."],
            recommended_followups=["Upload a bank statement to Coral."],
        )

    if math.purchase_amount is None:
        max_price = math.max_affordable_home_price or Decimal("0")
        return DecisionResult(
            verdict_code=VerdictCode.NEEDS_MORE_INFO,
            verdict_label="Needs more info",
            severity=VerdictSeverity.WATCH,
            confidence=0.6,
            primary_reason=(
                f"No home price specified. Based on available cash, upfront costs could be "
                f"covered up to approximately ${max_price:,.0f}."
            ),
            hard_constraints=[],
            soft_constraints=[],
            allowed_conclusions=[
                f"Based on available cash after reserve, a home up to ~${max_price:,.0f} may be feasible for upfront costs.",
                "Share the target home price for a detailed analysis.",
            ],
            forbidden_conclusions=[
                "Do not confirm affordability without a specific price.",
                "Do not mention retirement accounts as a funding source.",
            ],
            recommended_followups=[
                "Can we afford an $800,000 house?",
                "What are my current account balances?",
            ],
        )

    reserve = math.emergency_reserve_target
    cash_at_close = math.cash_needed_at_close or Decimal("0")
    cash_gap = math.cash_gap_at_close or Decimal("0")         # positive = short
    comfortable_gap = math.comfortable_cash_gap or Decimal("0")
    down = math.down_payment or Decimal("0")
    closing = math.closing_costs or Decimal("0")
    total_housing = math.total_monthly_housing
    dti = math.dti_pct
    price = math.purchase_amount

    followups = [
        "What are my current account balances?",
        "What is my total net worth including retirement accounts?",
        f"What would a ${price:,.0f} house cost per month?",
    ]

    # Hard stop: cannot cover down payment + closing costs
    if cash_gap > 0:
        return DecisionResult(
            verdict_code=VerdictCode.NOT_AFFORDABLE,
            verdict_label="Not affordable — upfront cash shortfall",
            severity=VerdictSeverity.STOP,
            confidence=1.0,
            primary_reason=(
                f"Down payment (${down:,.0f}) + closing costs (${closing:,.0f}) = "
                f"${cash_at_close:,.0f} needed, but liquid cash is ${liquid:,.0f}. "
                f"Shortfall: ${cash_gap:,.0f}."
            ),
            secondary_reasons=[
                "The primary constraint is cash to close, not monthly income.",
            ],
            hard_constraints=[
                f"Cannot cover the ${cash_at_close:,.0f} needed at close from ${liquid:,.0f} liquid.",
                "Retirement accounts cannot be used to bridge this gap.",
            ],
            allowed_conclusions=[
                "Upfront cash appears short for this home price.",
                f"Down payment + closing costs total ${cash_at_close:,.0f}.",
                f"Liquid cash of ${liquid:,.0f} is ${cash_gap:,.0f} short.",
            ],
            forbidden_conclusions=[
                "Do not say you can afford the home.",
                "Do not say monthly payment is the only issue.",
                "Do not suggest using retirement accounts.",
                "Do not say 'comfortable' or 'possible'.",
            ],
            recommended_followups=followups,
        )

    # Technically feasible but reserves tight
    if comfortable_gap > 0:
        remaining = liquid - cash_at_close
        return DecisionResult(
            verdict_code=VerdictCode.STRETCH,
            verdict_label="Stretch — reserves tight after close",
            severity=VerdictSeverity.CAUTION,
            confidence=0.9,
            primary_reason=(
                f"Upfront costs (${cash_at_close:,.0f}) are technically covered, but only "
                f"${remaining:,.0f} would remain after close — ${comfortable_gap:,.0f} below "
                f"the ${reserve:,.0f} recommended reserve."
            ),
            secondary_reasons=[
                "Closing day would leave the emergency fund significantly below target.",
            ],
            hard_constraints=[
                f"${comfortable_gap:,.0f} reserve gap after closing needs a plan to rebuild.",
            ],
            soft_constraints=[],
            allowed_conclusions=[
                "Upfront cash is technically sufficient.",
                f"After close, only ${remaining:,.0f} remains — ${comfortable_gap:,.0f} below the reserve target.",
                "This is financially risky without a plan to rebuild savings quickly.",
            ],
            forbidden_conclusions=[
                "Do not say this is comfortable or recommended.",
                "Do not ignore the reserve depletion.",
                "Do not suggest retirement accounts.",
            ],
            recommended_followups=followups,
        )

    # Monthly payment risk
    if total_housing and dti and dti > _MAX_DTI_PCT:
        return DecisionResult(
            verdict_code=VerdictCode.REASONABLE,
            verdict_label="Reasonable — but monthly payment is high",
            severity=VerdictSeverity.WATCH,
            confidence=0.85,
            primary_reason=(
                f"Upfront costs are covered, but estimated monthly housing cost "
                f"(${total_housing:,.0f}) is {dti}% of income — above the {int(_MAX_DTI_PCT)}% guideline."
            ),
            secondary_reasons=[
                "Cash to close is manageable; the ongoing monthly burden is the concern.",
            ],
            hard_constraints=[],
            soft_constraints=[
                f"Monthly housing cost of ${total_housing:,.0f} ({dti}% of income) is above the 28% guideline.",
            ],
            allowed_conclusions=[
                "Upfront costs are covered.",
                f"Monthly housing cost (${total_housing:,.0f}) is high relative to estimated income.",
                f"DTI of {dti}% exceeds the 28% guideline.",
            ],
            forbidden_conclusions=[
                "Do not say the home is comfortably affordable.",
                "Do not ignore the DTI risk.",
            ],
            recommended_followups=followups,
        )

    # All checks pass
    remaining = liquid - cash_at_close
    return DecisionResult(
        verdict_code=VerdictCode.COMFORTABLE,
        verdict_label="Comfortable",
        severity=VerdictSeverity.OK,
        confidence=0.9,
        primary_reason=(
            f"Upfront costs (${cash_at_close:,.0f}) are covered by liquid cash (${liquid:,.0f}), "
            f"leaving ${remaining:,.0f} after close."
        ),
        secondary_reasons=[
            "Reserve target is maintained after the purchase.",
        ],
        hard_constraints=[],
        soft_constraints=[],
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


# ── Dispatcher ────────────────────────────────────────────────────────────────

def decide(math: MathResult) -> DecisionResult:
    """Dispatch to the right decision policy based on scenario type."""
    if math.scenario_type == "home_purchase":
        return _decide_home(math)
    return _decide_purchase(math)
