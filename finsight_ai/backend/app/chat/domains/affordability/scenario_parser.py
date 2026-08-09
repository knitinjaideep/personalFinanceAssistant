"""
scenario_parser.py — Parses a user question into a typed AffordabilityScenario.

Responsibilities:
- Classify scenario type (home, car, luxury, travel, private_school, general, unknown)
- Extract purchase amount, down payment, time horizon, recurring / one-time costs
- Identify assumptions used and inputs that are missing
- No financial calculations; no LLM calls — pure text heuristics

The parser is deterministic and falls back gracefully: unknown fields are left None
and listed in missing_inputs so downstream layers know what was unavailable.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

ScenarioType = Literal[
    "home_purchase",
    "car_purchase",
    "luxury_purchase",
    "travel",
    "private_school_or_child_expense",
    "general_purchase",
    "unknown",
]


class AffordabilityScenario(BaseModel):
    """Parsed representation of what the user is asking about."""

    scenario_type: ScenarioType = "unknown"

    # Core amounts
    purchase_amount: Optional[Decimal] = None
    purchase_amount_source: Literal["explicit", "assumed", "unknown"] = "unknown"
    purchase_item: str = ""
    purchase_category: str = ""

    # Home-specific
    down_payment: Optional[Decimal] = None
    down_payment_pct: Optional[Decimal] = None   # e.g. 0.20

    # Time horizon
    time_horizon: Optional[str] = None           # human label, e.g. "next year"
    time_horizon_months: Optional[int] = None    # numeric estimate if parseable

    # Recurring / one-time split
    recurring_monthly_cost: Optional[Decimal] = None
    one_time_cost: Optional[Decimal] = None

    # Location context
    location: Optional[str] = None

    # Transparency
    assumptions_used: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)

    # Semantic framing carried from query_planner (populated by caller, not parser)
    protected_goals: list[str] = Field(default_factory=list)
    secondary_goals: list[dict] = Field(default_factory=list)
    user_is_asking_for: str = ""
    constraints: list[str] = Field(default_factory=list)


# ── Regex helpers ──────────────────────────────────────────────────────────────

_MILLION_RE = re.compile(r"\b([\d.]+)\s*million\b", re.IGNORECASE)
_BILLION_RE = re.compile(r"\b([\d.]+)\s*billion\b", re.IGNORECASE)
_K_RE = re.compile(r"\b([\d.]+)\s*k\b", re.IGNORECASE)
_DOLLAR_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)

_PCT_DOWN_RE = re.compile(r"(\d+)\s*%\s*down", re.IGNORECASE)
_TIME_MONTH_RE = re.compile(r"\bin\s+(\d+)\s+months?\b", re.IGNORECASE)
_TIME_YEAR_RE = re.compile(r"\bin\s+(\d+)\s+years?\b", re.IGNORECASE)
_NEXT_YEAR_RE = re.compile(r"\bnext\s+year\b", re.IGNORECASE)
_NEXT_MONTH_RE = re.compile(r"\bnext\s+month\b", re.IGNORECASE)

_HOME_TERMS = frozenset({
    "house", "home", "condo", "apartment", "townhouse", "townhome",
    "property", "real estate", "mortgage", "down payment",
})
_CAR_TERMS = frozenset({
    "car", "vehicle", "truck", "suv", "van", "tesla", "bmw", "mercedes",
    "toyota", "honda", "auto", "automobile",
})
_TRAVEL_TERMS = frozenset({
    "vacation", "trip", "travel", "holiday", "cruise", "flight",
    "tour", "safari", "honeymoon",
})
_LUXURY_TERMS = frozenset({
    "bag", "handbag", "purse", "birkin", "hermes", "watch", "rolex",
    "jewelry", "jewellery", "ring", "necklace", "bracelet", "luxury",
    "designer", "cartier", "gucci", "chanel", "louis vuitton",
})
_SCHOOL_TERMS = frozenset({
    "private school", "private college", "tuition", "school", "college",
    "university", "education", "529", "child", "kids", "children",
    "prep school", "boarding school",
})

_ASSUMED_PRICES: dict[str, tuple[Decimal, str]] = {
    "birkin": (Decimal("15000"), "Assumed entry-level Birkin price: $15,000 (prices vary widely)."),
    "hermes": (Decimal("15000"), "Assumed entry-level Hermès price: $15,000 (prices vary widely)."),
    "rolex": (Decimal("10000"), "Assumed Rolex price: $10,000 (prices vary by model)."),
}


def _extract_amount(text: str) -> tuple[Decimal | None, Literal["explicit", "assumed", "unknown"]]:
    """Extract the first meaningful dollar amount from text."""
    m = _MILLION_RE.search(text)
    if m:
        return Decimal(str(float(m.group(1)) * 1_000_000)), "explicit"
    m = _BILLION_RE.search(text)
    if m:
        return Decimal(str(float(m.group(1)) * 1_000_000_000)), "explicit"
    m = _K_RE.search(text)
    if m:
        return Decimal(str(float(m.group(1)) * 1_000)), "explicit"
    for m in _DOLLAR_RE.finditer(text):
        val = Decimal(m.group(1).replace(",", ""))
        if val >= 100:
            return val, "explicit"
    return None, "unknown"


def _extract_down_payment(text: str) -> tuple[Decimal | None, Decimal | None]:
    """Return (down_payment_amount, down_payment_pct) — both optional."""
    m = _PCT_DOWN_RE.search(text)
    if m:
        pct = Decimal(m.group(1)) / 100
        return None, pct
    return None, None


def _extract_time_horizon(text: str) -> tuple[str | None, int | None]:
    """Return (human_label, months_estimate)."""
    m = _TIME_MONTH_RE.search(text)
    if m:
        months = int(m.group(1))
        return f"in {months} months", months
    m = _TIME_YEAR_RE.search(text)
    if m:
        years = int(m.group(1))
        return f"in {years} years", years * 12
    if _NEXT_YEAR_RE.search(text):
        return "next year", 12
    if _NEXT_MONTH_RE.search(text):
        return "next month", 1
    # Named temporal phrases
    for phrase in ("before fellowship ends", "end of the year", "by end of", "before the"):
        if phrase in text:
            return phrase, None
    return None, None


def _classify_scenario(q: str) -> tuple[ScenarioType, str, str]:
    """Return (scenario_type, purchase_item, purchase_category)."""
    if any(t in q for t in _HOME_TERMS):
        return "home_purchase", "home", "real_estate"
    if any(t in q for t in _CAR_TERMS):
        return "car_purchase", "car", "vehicle"
    if any(t in q for t in _TRAVEL_TERMS):
        return "travel", "vacation", "travel"
    if any(t in q for t in _LUXURY_TERMS):
        item = "luxury item"
        for term in ("birkin", "hermes", "rolex", "gucci", "chanel", "cartier"):
            if term in q:
                item = term.title()
                break
        return "luxury_purchase", item, "luxury_discretionary"
    for phrase in _SCHOOL_TERMS:
        if phrase in q:
            return "private_school_or_child_expense", "education/school", "education"
    return "general_purchase", "purchase", "general"


def parse(
    question: str,
    *,
    purchase_price_override: float | None = None,
    purchase_item_override: str = "",
    purchase_category_override: str = "",
    task_type_override: str = "",
    protected_goals: list[str] | None = None,
    secondary_goals: list[dict] | None = None,
    user_is_asking_for: str = "",
    time_horizon_override: str | None = None,
    constraints: list[str] | None = None,
) -> AffordabilityScenario:
    """
    Parse a user question into an AffordabilityScenario.

    Overrides allow the query_planner's deterministic + semantic extraction to
    pass in already-resolved values (purchase_price, item, category, task_type)
    so this parser doesn't duplicate that work.
    """
    q = question.lower()
    assumptions: list[str] = []
    missing: list[str] = []

    # ── Scenario type ──────────────────────────────────────────────────────────
    if task_type_override == "home_affordability":
        scenario_type: ScenarioType = "home_purchase"
        purchase_item = purchase_item_override or "home"
        purchase_category = purchase_category_override or "real_estate"
    else:
        auto_type, auto_item, auto_cat = _classify_scenario(q)
        scenario_type = auto_type
        purchase_item = purchase_item_override or auto_item
        purchase_category = purchase_category_override or auto_cat

    # ── Purchase amount ────────────────────────────────────────────────────────
    amount: Decimal | None = None
    amount_source: Literal["explicit", "assumed", "unknown"] = "unknown"

    if purchase_price_override is not None:
        amount = Decimal(str(purchase_price_override))
        amount_source = "explicit"
    else:
        amount, amount_source = _extract_amount(q)

        # Known luxury items with assumed prices
        if amount is None:
            for keyword, (assumed_price, note) in _ASSUMED_PRICES.items():
                if keyword in q:
                    amount = assumed_price
                    amount_source = "assumed"
                    assumptions.append(note)
                    break

        if amount is None:
            missing.append("purchase_amount")

    # ── Down payment ───────────────────────────────────────────────────────────
    down_payment_amount, down_payment_pct = _extract_down_payment(q)

    # ── Time horizon ───────────────────────────────────────────────────────────
    time_horizon: str | None = time_horizon_override
    time_horizon_months: int | None = None
    if time_horizon is None:
        time_horizon, time_horizon_months = _extract_time_horizon(q)
    elif time_horizon:
        # Try to parse months from the override string too
        _, time_horizon_months = _extract_time_horizon(time_horizon.lower())

    # ── Location ───────────────────────────────────────────────────────────────
    location: str | None = None
    # Simple city/state extraction heuristic
    _LOCATION_RE = re.compile(
        r"\bin\s+(new york|los angeles|san francisco|seattle|boston|chicago|miami|austin|denver|portland)",
        re.IGNORECASE,
    )
    m = _LOCATION_RE.search(question)
    if m:
        location = m.group(1).title()

    return AffordabilityScenario(
        scenario_type=scenario_type,
        purchase_amount=amount,
        purchase_amount_source=amount_source,
        purchase_item=purchase_item,
        purchase_category=purchase_category,
        down_payment=down_payment_amount,
        down_payment_pct=down_payment_pct,
        time_horizon=time_horizon,
        time_horizon_months=time_horizon_months,
        location=location,
        assumptions_used=assumptions,
        missing_inputs=missing,
        protected_goals=protected_goals or [],
        secondary_goals=secondary_goals or [],
        user_is_asking_for=user_is_asking_for,
        constraints=constraints or [],
    )
