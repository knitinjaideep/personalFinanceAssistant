"""
Fact Builder — deterministic Python calculations from SQL result rows.

The LLM must never calculate totals, averages, deltas, or percentages.
Python does all arithmetic here, then hands a typed FactBundle to the
answer layer. The LLM only receives the finished facts and is asked to
narrate them in plain English.

Usage:
    from app.chat.fact_builder import build_facts
    bundle = build_facts(query_plan, sql_result, text_results)
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import QueryIntent


# ── Typed output models ────────────────────────────────────────────────────────

class MerchantFact(BaseModel):
    merchant: str
    amount: float
    transaction_count: int = 0


class CategoryFact(BaseModel):
    category: str
    amount: float
    transaction_count: int = 0


class PeriodComparison(BaseModel):
    period_a_label: str = ""
    period_b_label: str = ""
    period_a_value: float = 0.0
    period_b_value: float = 0.0
    delta: float = 0.0          # period_b - period_a (positive = increase)
    pct_change: float | None = None  # None when period_a is zero


class FactBundle(BaseModel):
    """All facts derived from SQL rows. Every number is calculated in Python."""

    # ── Core metrics ──────────────────────────────────────────────────────────
    total_spend: float | None = None
    total_income: float | None = None
    net_cash_flow: float | None = None
    total_fees: float | None = None
    balance: float | None = None
    holdings_value: float | None = None

    transaction_count: int = 0
    average_transaction: float | None = None

    # ── Breakdowns ────────────────────────────────────────────────────────────
    top_merchants: list[MerchantFact] = Field(default_factory=list)
    top_categories: list[CategoryFact] = Field(default_factory=list)

    # ── Period context ────────────────────────────────────────────────────────
    date_range: str = ""            # "2026-03-01 to 2026-03-31"
    date_from: date | None = None
    date_to: date | None = None

    # ── Comparison ────────────────────────────────────────────────────────────
    comparison: PeriodComparison | None = None

    # ── Source metadata ───────────────────────────────────────────────────────
    rows_used: int = 0
    filters_used: dict[str, Any] = Field(default_factory=dict)
    institution: str | None = None
    account_name: str | None = None

    # ── Chart-ready series (list of {label, value} dicts) ─────────────────────
    chart_ready_data: list[dict[str, Any]] = Field(default_factory=list)

    # ── Caveats (auto-generated, no LLM) ─────────────────────────────────────
    caveats: list[str] = Field(default_factory=list)

    # ── Missing-data notes (for the template / LLM to surface) ───────────────
    missing_data_notes: list[str] = Field(default_factory=list)

    # ── Suggested follow-ups (intent-specific, rule-based) ───────────────────
    suggested_followups: list[str] = Field(default_factory=list)


# ── Public entry point ─────────────────────────────────────────────────────────

def build_facts(
    intent: QueryIntent,
    sql_result: dict[str, Any] | None,
    text_results: list[dict] | None = None,
    *,
    ctx_filters: dict[str, Any] | None = None,
) -> FactBundle:
    """
    Derive a FactBundle from SQL query results.

    Args:
        intent:       The QueryIntent that produced sql_result.
        sql_result:   The dict returned by sql_query.execute_for_intent.
        text_results: Optional FTS/RAG chunks (used only for metadata).
        ctx_filters:  The searched_filters dict from the SQL result or QueryContext.

    Returns:
        A fully-computed FactBundle ready for the template/LLM layer.
    """
    rows: list[dict] = (sql_result or {}).get("rows", [])
    searched_filters = ctx_filters or (sql_result or {}).get("searched_filters", {})

    bundle = FactBundle(
        rows_used=len(rows),
        filters_used=searched_filters,
    )

    if not rows:
        bundle.missing_data_notes.append("No rows returned for this query.")
        bundle.caveats.extend(_generate_caveats(bundle, intent, searched_filters, rows))
        bundle.suggested_followups = _suggest_followups(intent, searched_filters)
        return bundle

    # ── Date range ────────────────────────────────────────────────────────────
    bundle.date_from, bundle.date_to = _extract_date_range(rows)
    if bundle.date_from and bundle.date_to:
        bundle.date_range = f"{bundle.date_from} to {bundle.date_to}"

    # ── Institution / account ─────────────────────────────────────────────────
    bundle.institution = _first_non_null(rows, "institution")
    bundle.account_name = _first_non_null(rows, "account_name")

    # ── Dispatch by intent ────────────────────────────────────────────────────
    _dispatch_intent(bundle, intent, rows)

    # ── Caveats ───────────────────────────────────────────────────────────────
    bundle.caveats = _generate_caveats(bundle, intent, searched_filters, rows)

    # ── Follow-ups ────────────────────────────────────────────────────────────
    bundle.suggested_followups = _suggest_followups(intent, searched_filters)

    return bundle


# ── Intent dispatch ────────────────────────────────────────────────────────────

def _dispatch_intent(bundle: FactBundle, intent: QueryIntent, rows: list[dict]) -> None:
    if intent == QueryIntent.SPENDING_BY_CATEGORY:
        _compute_spending_by_category(bundle, rows)
    elif intent == QueryIntent.TRANSACTION_LOOKUP:
        _compute_transaction_lookup(bundle, rows)
    elif intent == QueryIntent.SUBSCRIPTION_LOOKUP:
        _compute_transaction_lookup(bundle, rows)
    elif intent == QueryIntent.CASH_FLOW_SUMMARY:
        _compute_cash_flow(bundle, rows)
    elif intent == QueryIntent.FEE_SUMMARY:
        _compute_fees(bundle, rows)
    elif intent == QueryIntent.BALANCE_LOOKUP:
        _compute_balance(bundle, rows)
    elif intent == QueryIntent.HOLDINGS_TOTAL:
        _compute_holdings_total(bundle, rows)
    elif intent == QueryIntent.HOLDINGS_LOOKUP:
        _compute_holdings_lookup(bundle, rows)
    elif intent == QueryIntent.SPENDING_COMPARISON:
        _compute_spending_comparison(bundle, rows)
    else:
        # Generic: sum any amount-like column we find
        _compute_generic(bundle, rows)


# ── Spending by category ───────────────────────────────────────────────────────

def _compute_spending_by_category(bundle: FactBundle, rows: list[dict]) -> None:
    total = Decimal("0")
    count = 0
    categories: list[CategoryFact] = []

    for row in rows:
        amt = _to_decimal(row.get("total_spent") or row.get("total_amount") or row.get("amount"))
        txn_count = int(row.get("transaction_count") or 0)
        total += amt
        count += txn_count

        cat = str(row.get("category") or row.get("institution") or "Unknown")
        if float(amt) != 0:
            categories.append(CategoryFact(
                category=cat,
                amount=round(float(amt), 2),
                transaction_count=txn_count,
            ))

    bundle.total_spend = round(float(total), 2)
    bundle.transaction_count = count
    bundle.average_transaction = (
        round(float(total) / count, 2) if count > 0 else None
    )
    bundle.top_categories = sorted(categories, key=lambda c: c.amount, reverse=True)
    bundle.chart_ready_data = [
        {"label": c.category, "value": c.amount}
        for c in bundle.top_categories[:10]
    ]

    # Top merchants from same rows if present
    _extract_top_merchants(bundle, rows)


# ── Transaction lookup ─────────────────────────────────────────────────────────

def _compute_transaction_lookup(bundle: FactBundle, rows: list[dict]) -> None:
    total = Decimal("0")
    count = len(rows)

    merchant_totals: dict[str, Decimal] = {}
    merchant_counts: dict[str, int] = {}

    for row in rows:
        amt = _to_decimal(row.get("amount"))
        total += amt

        merchant = str(row.get("merchant_name") or row.get("description") or "Unknown")
        if merchant not in merchant_totals:
            merchant_totals[merchant] = Decimal("0")
            merchant_counts[merchant] = 0
        merchant_totals[merchant] += amt
        merchant_counts[merchant] += 1

    bundle.total_spend = round(float(total), 2)
    bundle.transaction_count = count
    bundle.average_transaction = (
        round(float(total) / count, 2) if count > 0 else None
    )
    bundle.top_merchants = sorted(
        [
            MerchantFact(
                merchant=m,
                amount=round(float(v), 2),
                transaction_count=merchant_counts[m],
            )
            for m, v in merchant_totals.items()
        ],
        key=lambda m: m.amount,
        reverse=True,
    )[:10]
    bundle.chart_ready_data = [
        {"label": m.merchant, "value": m.amount}
        for m in bundle.top_merchants[:10]
    ]


# ── Cash flow ──────────────────────────────────────────────────────────────────

def _compute_cash_flow(bundle: FactBundle, rows: list[dict]) -> None:
    inflow = Decimal("0")
    outflow = Decimal("0")

    for row in rows:
        inflow += _to_decimal(row.get("total_inflow"))
        outflow += _to_decimal(row.get("total_outflow"))

    # Some SQL handlers return a single-row summary; others return per-period rows.
    if float(inflow) == 0 and float(outflow) == 0 and rows:
        # Fallback: look for net_flow directly
        for row in rows:
            nf = _to_decimal(row.get("net_flow"))
            if float(nf) != 0:
                bundle.net_cash_flow = round(float(nf), 2)
                return

    bundle.total_income = round(float(inflow), 2)
    bundle.total_spend = round(float(outflow), 2)
    bundle.net_cash_flow = round(float(inflow) - float(outflow), 2)
    bundle.transaction_count = sum(
        int(row.get("transaction_count") or 0) for row in rows
    )
    bundle.chart_ready_data = [
        {"label": "Income", "value": bundle.total_income},
        {"label": "Spend", "value": bundle.total_spend},
        {"label": "Net", "value": bundle.net_cash_flow},
    ]


# ── Fees ───────────────────────────────────────────────────────────────────────

def _compute_fees(bundle: FactBundle, rows: list[dict]) -> None:
    total = Decimal("0")
    count = 0
    categories: list[CategoryFact] = []

    for row in rows:
        amt = _to_decimal(row.get("total_amount") or row.get("amount"))
        cnt = int(row.get("fee_count") or row.get("count") or 0)
        total += amt
        count += cnt

        cat = str(row.get("fee_category") or row.get("category") or "Fees")
        if float(amt) != 0:
            categories.append(CategoryFact(
                category=cat,
                amount=round(float(amt), 2),
                transaction_count=cnt,
            ))

    bundle.total_fees = round(float(total), 2)
    bundle.transaction_count = count
    bundle.top_categories = sorted(categories, key=lambda c: c.amount, reverse=True)
    bundle.chart_ready_data = [
        {"label": c.category, "value": c.amount}
        for c in bundle.top_categories[:10]
    ]


# ── Balance ────────────────────────────────────────────────────────────────────

def _compute_balance(bundle: FactBundle, rows: list[dict]) -> None:
    total = Decimal("0")
    for row in rows:
        total += _to_decimal(
            row.get("total_value") or row.get("balance") or row.get("amount")
        )
    bundle.balance = round(float(total), 2)


# ── Holdings ───────────────────────────────────────────────────────────────────

def _compute_holdings_total(bundle: FactBundle, rows: list[dict]) -> None:
    total = Decimal("0")
    for row in rows:
        total += _to_decimal(row.get("total_value") or row.get("market_value"))
    bundle.holdings_value = round(float(total), 2)


def _compute_holdings_lookup(bundle: FactBundle, rows: list[dict]) -> None:
    total = Decimal("0")
    for row in rows:
        total += _to_decimal(row.get("market_value") or row.get("total_value"))
    bundle.holdings_value = round(float(total), 2)
    bundle.transaction_count = len(rows)


# ── Spending comparison ────────────────────────────────────────────────────────

def _compute_spending_comparison(bundle: FactBundle, rows: list[dict]) -> None:
    """
    Rows are expected to contain period_label + total_spent per period.
    If the SQL handler returns exactly 2 rows, compute the delta in Python.
    """
    if not rows:
        return

    _compute_generic(bundle, rows)

    if len(rows) >= 2:
        row_a = rows[0]
        row_b = rows[1]
        val_a = float(_to_decimal(row_a.get("total_spent") or row_a.get("amount")))
        val_b = float(_to_decimal(row_b.get("total_spent") or row_b.get("amount")))
        delta = round(val_b - val_a, 2)
        pct = (
            round((delta / val_a) * 100, 1)
            if val_a != 0
            else None
        )
        bundle.comparison = PeriodComparison(
            period_a_label=str(row_a.get("period_label") or row_a.get("timeframe_label") or "Period A"),
            period_b_label=str(row_b.get("period_label") or row_b.get("timeframe_label") or "Period B"),
            period_a_value=round(val_a, 2),
            period_b_value=round(val_b, 2),
            delta=delta,
            pct_change=pct,
        )


# ── Generic fallback ───────────────────────────────────────────────────────────

def _compute_generic(bundle: FactBundle, rows: list[dict]) -> None:
    """Sum whichever amount-like column exists; count rows."""
    _AMOUNT_COLS = (
        "total_spent", "total_amount", "amount", "total_value",
        "market_value", "total_inflow", "net_flow",
    )
    total = Decimal("0")
    col_used: str | None = None

    for col in _AMOUNT_COLS:
        if any(col in row for row in rows):
            col_used = col
            break

    if col_used:
        for row in rows:
            total += _to_decimal(row.get(col_used))

    bundle.transaction_count = len(rows)
    if col_used and float(total) != 0:
        bundle.total_spend = round(float(total), 2)


# ── Helper: extract top merchants from category rows ──────────────────────────

def _extract_top_merchants(bundle: FactBundle, rows: list[dict]) -> None:
    """Pull merchant column from rows if it exists (category rows sometimes include it)."""
    if not any("merchant_name" in row or "merchant" in row for row in rows):
        return
    merchant_totals: dict[str, Decimal] = {}
    merchant_counts: dict[str, int] = {}
    for row in rows:
        m = row.get("merchant_name") or row.get("merchant")
        if not m:
            continue
        amt = _to_decimal(row.get("total_spent") or row.get("amount"))
        if m not in merchant_totals:
            merchant_totals[m] = Decimal("0")
            merchant_counts[m] = 0
        merchant_totals[m] += amt
        merchant_counts[m] += 1

    bundle.top_merchants = sorted(
        [
            MerchantFact(merchant=m, amount=round(float(v), 2), transaction_count=merchant_counts[m])
            for m, v in merchant_totals.items()
        ],
        key=lambda x: x.amount,
        reverse=True,
    )[:10]


# ── Caveats ────────────────────────────────────────────────────────────────────

def _generate_caveats(
    bundle: FactBundle,
    intent: QueryIntent,
    searched_filters: dict[str, Any],
    rows: list[dict],
) -> list[str]:
    caveats: list[str] = []

    if not rows:
        caveats.append("No matching data found for the requested filters.")
        return caveats

    # Partial date range detection: warn if rows span < the expected full month
    if bundle.date_from and bundle.date_to:
        days_in_range = (bundle.date_to - bundle.date_from).days + 1
        if days_in_range < 28 and searched_filters.get("date_from"):
            caveats.append(f"Data covers only {days_in_range} days — may be a partial period.")

    # Institution filter applied
    if searched_filters.get("institution"):
        inst = str(searched_filters["institution"]).replace("_", " ").title()
        caveats.append(f"Only {inst} transactions were searched.")

    # Account filter applied
    if searched_filters.get("account") or searched_filters.get("account_name"):
        acct = searched_filters.get("account") or searched_filters.get("account_name")
        caveats.append(f"Filtered to account: {acct}.")

    # Category filter applied
    if searched_filters.get("category"):
        caveats.append(f"Category filter: {searched_filters['category']}.")

    # Merchant filter applied
    if searched_filters.get("merchant"):
        caveats.append(f"Merchant filter: {searched_filters['merchant']}.")

    # Check for refunds included (transactions with negative amounts in the result)
    if intent in (QueryIntent.SPENDING_BY_CATEGORY, QueryIntent.TRANSACTION_LOOKUP):
        has_refunds = any(
            float(_to_decimal(row.get("amount", 0))) < 0
            for row in rows
        )
        if has_refunds:
            caveats.append("Refunds and credits are included in the totals.")

    # Unknown / uncategorized transactions
    if intent == QueryIntent.SPENDING_BY_CATEGORY:
        has_unknown = any(
            str(row.get("category", "")).lower() in ("", "unknown", "other", "uncategorized")
            for row in rows
        )
        if has_unknown:
            caveats.append("Some transactions have unknown or uncategorized merchant data.")

    # Timeframe applied
    if searched_filters.get("date_from") or searched_filters.get("period"):
        period = searched_filters.get("period") or (
            f"{searched_filters.get('date_from', '')} to {searched_filters.get('date_to', '')}"
        )
        caveats.append(f"Results filtered to: {period}.")

    return caveats


# ── Follow-up suggestions ──────────────────────────────────────────────────────

def _suggest_followups(intent: QueryIntent, searched_filters: dict[str, Any]) -> list[str]:
    base: dict[QueryIntent, list[str]] = {
        QueryIntent.SPENDING_BY_CATEGORY: [
            "Show me my top spending merchants",
            "How does this compare to last month?",
            "What subscriptions am I paying?",
            "Show me transactions over $100",
        ],
        QueryIntent.TRANSACTION_LOOKUP: [
            "What's my total spend by category?",
            "Show me transactions over $500",
            "What are my recurring charges?",
            "Show me recent deposits",
        ],
        QueryIntent.CASH_FLOW_SUMMARY: [
            "Show me spending by category",
            "What are my recurring expenses?",
            "What was my net cash flow last month?",
            "Show me my account balances",
        ],
        QueryIntent.FEE_SUMMARY: [
            "Which account has the highest fees?",
            "Show me all fee transactions",
            "What are my advisory fees this year?",
            "Show me my investment performance",
        ],
        QueryIntent.BALANCE_LOOKUP: [
            "How has my balance changed over time?",
            "What's my total invested amount?",
            "Show me my holdings breakdown",
            "What fees have I been charged?",
        ],
        QueryIntent.HOLDINGS_TOTAL: [
            "Show me my top holdings",
            "What's my asset allocation?",
            "How much have I gained or lost?",
            "What fees is Morgan Stanley charging?",
        ],
    }
    suggestions = base.get(intent, [
        "Show me my account balances",
        "What fees have I been charged?",
        "What is my total invested amount?",
        "Show me my spending by category",
    ])

    # Personalize if institution is known
    inst = searched_filters.get("institution")
    if inst:
        inst_name = str(inst).replace("_", " ").title()
        suggestions = [f"Show me all {inst_name} transactions"] + suggestions[:3]

    return suggestions[:4]


# ── Date range extraction ──────────────────────────────────────────────────────

def _extract_date_range(rows: list[dict]) -> tuple[date | None, date | None]:
    """Find the earliest and latest dates across all rows."""
    dates: list[date] = []
    for row in rows:
        for col in ("transaction_date", "earliest", "period_start", "snapshot_date"):
            val = row.get(col)
            if val:
                d = _parse_date(val)
                if d:
                    dates.append(d)
        for col in ("latest", "period_end"):
            val = row.get(col)
            if val:
                d = _parse_date(val)
                if d:
                    dates.append(d)

    if not dates:
        return None, None
    return min(dates), max(dates)


def _parse_date(val: Any) -> date | None:
    if isinstance(val, date):
        return val
    try:
        from datetime import datetime
        if isinstance(val, str):
            return datetime.strptime(val[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        pass
    return None


# ── Arithmetic helpers ─────────────────────────────────────────────────────────

def _to_decimal(val: Any) -> Decimal:
    if val is None:
        return Decimal("0")
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _first_non_null(rows: list[dict], key: str) -> str | None:
    for row in rows:
        v = row.get(key)
        if v is not None and str(v).strip():
            return str(v)
    return None
