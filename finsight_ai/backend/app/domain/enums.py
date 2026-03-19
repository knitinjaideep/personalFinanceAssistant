"""
Domain enumerations — single source of truth for all taxonomy.
"""

from __future__ import annotations

from enum import Enum


class InstitutionType(str, Enum):
    MORGAN_STANLEY = "morgan_stanley"
    CHASE = "chase"
    ETRADE = "etrade"
    AMEX = "amex"
    DISCOVER = "discover"
    UNKNOWN = "unknown"


class AccountType(str, Enum):
    # Investments
    IRA = "ira"
    ROTH_IRA = "roth_ira"
    ADVISORY = "advisory"
    INDIVIDUAL_BROKERAGE = "individual_brokerage"
    FOUR_01K = "401k"
    # Banking
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    UNKNOWN = "unknown"


class StatementType(str, Enum):
    BROKERAGE = "brokerage"
    BANK = "bank"
    CREDIT_CARD = "credit_card"
    RETIREMENT = "retirement"
    ADVISORY = "advisory"
    UNKNOWN = "unknown"


class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    FEE = "fee"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    TRADE_BUY = "trade_buy"
    TRADE_SELL = "trade_sell"
    TAX_WITHHOLDING = "tax_withholding"
    ADVISORY_FEE = "advisory_fee"
    PAYMENT = "payment"
    PURCHASE = "purchase"
    REFUND = "refund"
    OTHER = "other"


class TransactionCategory(str, Enum):
    GROCERIES = "groceries"
    RESTAURANTS = "restaurants"
    SUBSCRIPTIONS = "subscriptions"
    TRAVEL = "travel"
    SHOPPING = "shopping"
    GAS = "gas"
    UTILITIES = "utilities"
    HEALTHCARE = "healthcare"
    ENTERTAINMENT = "entertainment"
    EDUCATION = "education"
    INSURANCE = "insurance"
    TRANSFERS = "transfers"
    FEES = "fees"
    ATM_CASH = "atm_cash"
    OTHER = "other"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PARSED = "parsed"
    FAILED = "failed"


class ExtractionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class QueryIntent(str, Enum):
    """Explicit query intents for the query router."""
    FEE_SUMMARY = "fee_summary"
    TRANSACTION_LOOKUP = "transaction_lookup"
    BALANCE_LOOKUP = "balance_lookup"
    HOLDINGS_LOOKUP = "holdings_lookup"
    CASH_FLOW_SUMMARY = "cash_flow_summary"
    DOCUMENT_AVAILABILITY = "document_availability"
    INSTITUTION_COVERAGE = "institution_coverage"
    STATEMENT_COVERAGE = "statement_coverage"
    TEXT_EXPLANATION = "text_explanation"
    HYBRID_FINANCIAL_QUESTION = "hybrid_financial_question"


class QueryPath(str, Enum):
    """Which retrieval path to use."""
    SQL = "sql"
    FTS = "fts"
    VECTOR = "vector"
    HYBRID = "hybrid"


# ── Taxonomy mappings ──────────────────────────────────────────────────────

INSTITUTION_ACCOUNT_TYPES: dict[InstitutionType, list[AccountType]] = {
    InstitutionType.MORGAN_STANLEY: [
        AccountType.IRA, AccountType.ROTH_IRA,
        AccountType.ADVISORY, AccountType.INDIVIDUAL_BROKERAGE,
    ],
    InstitutionType.ETRADE: [AccountType.INDIVIDUAL_BROKERAGE],
    InstitutionType.CHASE: [AccountType.CHECKING, AccountType.CREDIT_CARD],
    InstitutionType.AMEX: [AccountType.CREDIT_CARD],
    InstitutionType.DISCOVER: [AccountType.CREDIT_CARD],
}

INVESTMENTS_ACCOUNT_TYPES: frozenset[AccountType] = frozenset({
    AccountType.IRA, AccountType.ROTH_IRA, AccountType.ADVISORY,
    AccountType.INDIVIDUAL_BROKERAGE, AccountType.FOUR_01K,
})

BANKING_ACCOUNT_TYPES: frozenset[AccountType] = frozenset({
    AccountType.CHECKING, AccountType.SAVINGS, AccountType.CREDIT_CARD,
})

# Intent → primary query path mapping
INTENT_QUERY_PATH: dict[QueryIntent, QueryPath] = {
    QueryIntent.FEE_SUMMARY: QueryPath.SQL,
    QueryIntent.TRANSACTION_LOOKUP: QueryPath.SQL,
    QueryIntent.BALANCE_LOOKUP: QueryPath.SQL,
    QueryIntent.HOLDINGS_LOOKUP: QueryPath.SQL,
    QueryIntent.CASH_FLOW_SUMMARY: QueryPath.SQL,
    QueryIntent.DOCUMENT_AVAILABILITY: QueryPath.SQL,
    QueryIntent.INSTITUTION_COVERAGE: QueryPath.SQL,
    QueryIntent.STATEMENT_COVERAGE: QueryPath.SQL,
    QueryIntent.TEXT_EXPLANATION: QueryPath.FTS,
    QueryIntent.HYBRID_FINANCIAL_QUESTION: QueryPath.HYBRID,
}
