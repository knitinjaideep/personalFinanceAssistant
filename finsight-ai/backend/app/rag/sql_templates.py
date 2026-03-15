"""
Deterministic SQL query templates for common financial questions.

These templates bypass the LLM SQL generator for well-known question patterns,
ensuring reliable answers for fee totals, transaction lookups, balance queries,
cash flow, and holdings.

Design:
- Each template is a (pattern, query_builder) pair.
- Patterns are tried in order; the first match wins.
- Query builders return a (sql, params) tuple for safe parameterised execution.
- Templates always use CAST(amount AS REAL) for monetary aggregation.
- Templates always include a LIMIT to prevent runaway queries.
"""

from __future__ import annotations

import re
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

TemplateResult = tuple[str, dict]  # (sql_query, params)


def match_template(question: str) -> Optional[TemplateResult]:
    """
    Try to match the question against known SQL templates.

    Returns (sql, params) on match, or None if no template fits.
    """
    q = question.lower().strip()

    for pattern, builder in _TEMPLATES:
        if pattern.search(q):
            result = builder(q)
            if result is not None:
                logger.debug(
                    "sql_template.matched",
                    question_prefix=q[:60],
                    template=builder.__name__,
                )
                return result

    return None


# ---------------------------------------------------------------------------
# Template builders
# ---------------------------------------------------------------------------

def _total_fees(q: str) -> TemplateResult:
    """Total fees paid — SUM of all fee amounts."""
    return (
        "SELECT "
        "  COALESCE(ROUND(SUM(CAST(amount AS REAL)), 2), 0) AS total_fees, "
        "  COUNT(*) AS fee_count "
        "FROM fees",
        {},
    )


def _fees_by_category(q: str) -> TemplateResult:
    """Fee breakdown by category."""
    return (
        "SELECT "
        "  fee_category, "
        "  ROUND(SUM(CAST(amount AS REAL)), 2) AS total_amount, "
        "  COUNT(*) AS fee_count "
        "FROM fees "
        "GROUP BY fee_category "
        "ORDER BY total_amount DESC "
        "LIMIT 50",
        {},
    )


def _list_fees(q: str) -> TemplateResult:
    """List all fee records."""
    return (
        "SELECT "
        "  f.fee_date, f.description, f.amount, f.fee_category, "
        "  a.account_number_masked, a.institution_type "
        "FROM fees f "
        "LEFT JOIN accounts a ON f.account_id = a.id "
        "ORDER BY f.fee_date DESC "
        "LIMIT 100",
        {},
    )


def _largest_transactions(q: str) -> TemplateResult:
    """Show largest transactions by absolute amount."""
    return (
        "SELECT "
        "  t.transaction_date, t.description, t.amount, "
        "  t.transaction_type, t.merchant_name, t.category, "
        "  a.account_number_masked, a.institution_type "
        "FROM transactions t "
        "LEFT JOIN accounts a ON t.account_id = a.id "
        "ORDER BY ABS(CAST(t.amount AS REAL)) DESC "
        "LIMIT 25",
        {},
    )


def _recent_transactions(q: str) -> TemplateResult:
    """Show recent transactions."""
    return (
        "SELECT "
        "  t.transaction_date, t.description, t.amount, "
        "  t.transaction_type, t.merchant_name, t.category, "
        "  a.account_number_masked, a.institution_type "
        "FROM transactions t "
        "LEFT JOIN accounts a ON t.account_id = a.id "
        "ORDER BY t.transaction_date DESC "
        "LIMIT 25",
        {},
    )


def _total_transactions(q: str) -> TemplateResult:
    """Total transaction count and sum."""
    return (
        "SELECT "
        "  COUNT(*) AS transaction_count, "
        "  ROUND(SUM(CAST(t.amount AS REAL)), 2) AS total_amount "
        "FROM transactions t",
        {},
    )


def _transaction_by_category(q: str) -> TemplateResult:
    """Spending by category."""
    return (
        "SELECT "
        "  COALESCE(category, 'Uncategorized') AS category, "
        "  ROUND(SUM(CAST(amount AS REAL)), 2) AS total_amount, "
        "  COUNT(*) AS transaction_count "
        "FROM transactions "
        "GROUP BY category "
        "ORDER BY total_amount DESC "
        "LIMIT 50",
        {},
    )


def _cash_flow(q: str) -> TemplateResult:
    """Cash flow — inflows vs outflows from transactions."""
    return (
        "SELECT "
        "  SUM(CASE WHEN CAST(amount AS REAL) > 0 THEN CAST(amount AS REAL) ELSE 0 END) AS total_inflow, "
        "  SUM(CASE WHEN CAST(amount AS REAL) < 0 THEN CAST(amount AS REAL) ELSE 0 END) AS total_outflow, "
        "  ROUND(SUM(CAST(amount AS REAL)), 2) AS net_cash_flow, "
        "  COUNT(*) AS transaction_count "
        "FROM transactions",
        {},
    )


def _account_balances(q: str) -> TemplateResult:
    """Latest balance snapshot per account."""
    return (
        "SELECT "
        "  a.account_number_masked, a.account_type, a.institution_type, "
        "  bs.snapshot_date, bs.total_value "
        "FROM balance_snapshots bs "
        "JOIN accounts a ON bs.account_id = a.id "
        "WHERE bs.snapshot_date = ("
        "  SELECT MAX(bs2.snapshot_date) FROM balance_snapshots bs2 "
        "  WHERE bs2.account_id = bs.account_id"
        ") "
        "ORDER BY CAST(bs.total_value AS REAL) DESC "
        "LIMIT 50",
        {},
    )


def _portfolio_value(q: str) -> TemplateResult:
    """Total portfolio value from latest balance snapshots."""
    return (
        "SELECT "
        "  ROUND(SUM(CAST(bs.total_value AS REAL)), 2) AS total_portfolio_value, "
        "  COUNT(DISTINCT bs.account_id) AS account_count "
        "FROM balance_snapshots bs "
        "WHERE bs.snapshot_date = ("
        "  SELECT MAX(bs2.snapshot_date) FROM balance_snapshots bs2 "
        "  WHERE bs2.account_id = bs.account_id"
        ")",
        {},
    )


def _top_holdings(q: str) -> TemplateResult:
    """Top holdings by market value."""
    return (
        "SELECT "
        "  h.symbol, h.description, h.quantity, h.market_value, "
        "  a.account_number_masked, a.institution_type "
        "FROM holdings h "
        "LEFT JOIN accounts a ON h.account_id = a.id "
        "ORDER BY CAST(h.market_value AS REAL) DESC "
        "LIMIT 25",
        {},
    )


def _top_merchants(q: str) -> TemplateResult:
    """Top merchants by total spend."""
    return (
        "SELECT "
        "  COALESCE(merchant_name, description) AS merchant, "
        "  ROUND(SUM(ABS(CAST(amount AS REAL))), 2) AS total_spent, "
        "  COUNT(*) AS transaction_count "
        "FROM transactions "
        "WHERE CAST(amount AS REAL) < 0 "
        "GROUP BY merchant "
        "ORDER BY total_spent DESC "
        "LIMIT 25",
        {},
    )


# ---------------------------------------------------------------------------
# Pattern → builder mapping (order matters — first match wins)
# ---------------------------------------------------------------------------

_TEMPLATES: list[tuple[re.Pattern, callable]] = [
    # Fee queries
    (re.compile(r"(fee.*(category|breakdown|by type|by category))|((category|breakdown).* fee)", re.I), _fees_by_category),
    (re.compile(r"(list|show|all|detail|itemize).*(fee|charge)", re.I), _list_fees),
    (re.compile(r"(how much|total|sum|amount).*(fee|paid in fee|pay in fee)", re.I), _total_fees),
    (re.compile(r"fee", re.I), _total_fees),  # catch-all for fee questions

    # Transaction queries
    (re.compile(r"(largest|biggest|highest|top|most expensive).*(transaction|charge|purchase|payment|spend)", re.I), _largest_transactions),
    (re.compile(r"(recent|latest|last|newest).*(transaction|charge|purchase|payment)", re.I), _recent_transactions),
    (re.compile(r"(spend|spending).*(category|breakdown|by category)", re.I), _transaction_by_category),
    (re.compile(r"(category|breakdown).*(spend|transaction)", re.I), _transaction_by_category),
    (re.compile(r"(how many|total|count).*(transaction)", re.I), _total_transactions),
    (re.compile(r"(top|biggest|most).*(merchant|vendor|store|retailer)", re.I), _top_merchants),
    (re.compile(r"(show|list|all|detail).*(transaction|charge|purchase)", re.I), _recent_transactions),

    # Cash flow
    (re.compile(r"(cash\s*flow|inflow|outflow|net flow|money in|money out|income.*expense|deposit.*withdraw)", re.I), _cash_flow),

    # Balance queries
    (re.compile(r"(account|current|latest|my).*(balance|balances)", re.I), _account_balances),
    (re.compile(r"(portfolio|net worth|total value|total balance)", re.I), _portfolio_value),

    # Holdings
    (re.compile(r"(holding|investment|stock|position|asset)", re.I), _top_holdings),
]
