"""
Pydantic response schemas for the analytics API (Phase 3).

All monetary values are serialised as strings to preserve Decimal precision.
``partial`` is True whenever warnings are present, signalling the UI to show
a "partial data" badge rather than treating missing data as an error.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

class AnalyticsEnvelope(BaseModel, Generic[T]):
    """Standard envelope for all analytics responses."""

    data: T
    warnings: List[str] = Field(default_factory=list)
    partial: bool = False

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Investments schemas
# ---------------------------------------------------------------------------

class AccountSummarySchema(BaseModel):
    account_id: str
    account_name: str
    account_type: str
    institution: str
    current_value: str          # Decimal string
    as_of_date: Optional[date]
    portfolio_pct: str          # e.g. "34.21"


class HoldingRowSchema(BaseModel):
    symbol: Optional[str]
    description: str
    quantity: Optional[str]
    price: Optional[str]
    market_value: str
    cost_basis: Optional[str]
    unrealized_gain_loss: Optional[str]
    unrealized_pct: Optional[str]
    asset_class: Optional[str]
    account_id: str
    account_name: str
    institution: str


class MonthlyFeeSchema(BaseModel):
    year: int
    month: int
    total_fees: str
    fee_count: int
    by_category: Dict[str, str]  # category → Decimal string


class BalancePointSchema(BaseModel):
    snapshot_date: date
    total_value: str
    account_id: str
    account_name: str
    institution: str


class PeriodChangeSchema(BaseModel):
    account_id: str
    account_name: str
    institution: str
    previous_value: Optional[str]
    current_value: str
    change_amount: Optional[str]
    change_pct: Optional[str]
    period_start: Optional[date]
    period_end: Optional[date]


class InvestmentsOverviewSchema(BaseModel):
    total_portfolio_value: str
    accounts: List[AccountSummarySchema]
    holdings_breakdown: List[HoldingRowSchema]
    fee_trend: List[MonthlyFeeSchema]
    balance_trend: List[BalancePointSchema]
    period_changes: List[PeriodChangeSchema]


# ---------------------------------------------------------------------------
# Banking schemas
# ---------------------------------------------------------------------------

class MerchantSpendSchema(BaseModel):
    merchant_name: str
    total_amount: str
    transaction_count: int
    category: Optional[str]


class SubscriptionSchema(BaseModel):
    merchant_name: str
    typical_amount: str
    frequency_days: int
    last_charged: date
    category: Optional[str]
    transaction_ids: List[str]


class CardBalanceSchema(BaseModel):
    account_id: str
    account_name: str
    institution: str
    current_balance: str
    as_of_date: Optional[date]


class CheckingInOutSchema(BaseModel):
    total_inflows: str
    total_outflows: str
    net: str


class TransactionSchema(BaseModel):
    """Minimal transaction shape for top/unusual transaction lists."""

    id: str
    account_id: str
    transaction_date: date
    description: str
    merchant_name: str
    amount: str
    spend_amount: Optional[str]
    type: Optional[str]
    category: Optional[str]


class BankingOverviewSchema(BaseModel):
    total_spend_this_month: str
    spend_by_category: Dict[str, str]           # category → Decimal string
    spend_by_merchant: List[MerchantSpendSchema]
    subscriptions: List[SubscriptionSchema]
    credit_card_balances: List[CardBalanceSchema]
    checking_summary: CheckingInOutSchema
    top_transactions: List[TransactionSchema]
    unusual_transactions: List[TransactionSchema]


# ---------------------------------------------------------------------------
# Spend breakdown schema
# ---------------------------------------------------------------------------

class SpendBreakdownSchema(BaseModel):
    by_category: Dict[str, str]
    by_merchant: List[MerchantSpendSchema]
