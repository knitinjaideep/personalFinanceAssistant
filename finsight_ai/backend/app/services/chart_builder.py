"""
chart_builder.py — derive a chart_payload dict from SQL result rows.

chart_payload shape (matches frontend Chart.js / Recharts conventions):
{
    "type"    : "bar" | "pie" | "line" | "horizontal_bar",
    "title"   : str,
    "labels"  : [str, ...],              # x-axis labels / pie slice names
    "datasets": [
        {
            "label": str,
            "data" : [float, ...],
        }
    ],
    "currency": bool,                    # hint: format values as $ on frontend
}

Returns None when there's no meaningful chart to produce.
"""

from __future__ import annotations

from typing import Any

from app.domain.enums import QueryIntent


def build_chart(
    intent: QueryIntent,
    rows: list[dict[str, Any]],
    timeframe_label: str = "",
) -> dict[str, Any] | None:
    """Return a chart_payload or None."""
    if not rows:
        return None

    try:
        if intent == QueryIntent.SPENDING_BY_CATEGORY:
            return _category_bar(rows, timeframe_label)
        if intent == QueryIntent.SUBSCRIPTION_LOOKUP:
            return _subscription_bar(rows)
        if intent == QueryIntent.FEE_SUMMARY:
            return _fee_pie(rows, timeframe_label)
        if intent == QueryIntent.HOLDINGS_TOTAL:
            return _holdings_pie(rows)
        if intent == QueryIntent.HOLDINGS_LOOKUP:
            return _holdings_pie(rows)
        if intent == QueryIntent.BALANCE_LOOKUP:
            return _balance_bar(rows)
        if intent == QueryIntent.CASH_FLOW_SUMMARY:
            return _cashflow_bar(rows, timeframe_label)
    except Exception:
        return None

    return None


# ── Chart producers ───────────────────────────────────────────────────────────

def _category_bar(rows: list[dict], label: str) -> dict:
    top = rows[:10]
    return {
        "type": "horizontal_bar",
        "title": f"Spending by Category{f' — {label}' if label else ''}",
        "labels": [str(r.get("category", "other")).replace("_", " ").title() for r in top],
        "datasets": [{
            "label": "Spent",
            "data": [_f(r.get("total_spent")) for r in top],
        }],
        "currency": True,
    }


def _subscription_bar(rows: list[dict]) -> dict:
    top = rows[:12]
    return {
        "type": "horizontal_bar",
        "title": "Recurring Charges",
        "labels": [str(r.get("merchant", "unknown"))[:30] for r in top],
        "datasets": [{
            "label": "Monthly Amount",
            "data": [_f(r.get("monthly_amount")) for r in top],
        }],
        "currency": True,
    }


def _fee_pie(rows: list[dict], label: str) -> dict:
    top = rows[:8]
    return {
        "type": "pie",
        "title": f"Fee Breakdown{f' — {label}' if label else ''}",
        "labels": [str(r.get("fee_category", "other")).replace("_", " ").title() for r in top],
        "datasets": [{
            "label": "Total Fees",
            "data": [_f(r.get("total_amount")) for r in top],
        }],
        "currency": True,
    }


def _holdings_pie(rows: list[dict]) -> dict:
    # Group by asset_class if available, else show top positions
    by_class: dict[str, float] = {}
    for r in rows:
        cls = str(r.get("asset_class") or "Other").title()
        by_class[cls] = by_class.get(cls, 0.0) + _f(r.get("market_value"))

    if len(by_class) > 1:
        items = sorted(by_class.items(), key=lambda x: -x[1])[:8]
        return {
            "type": "pie",
            "title": "Portfolio by Asset Class",
            "labels": [k for k, _ in items],
            "datasets": [{"label": "Market Value", "data": [v for _, v in items]}],
            "currency": True,
        }

    # Fall back: top positions by market value
    top = rows[:10]
    return {
        "type": "horizontal_bar",
        "title": "Top Holdings by Value",
        "labels": [str(r.get("symbol") or r.get("description", "?"))[:20] for r in top],
        "datasets": [{"label": "Market Value", "data": [_f(r.get("market_value")) for r in top]}],
        "currency": True,
    }


def _balance_bar(rows: list[dict]) -> dict:
    # Latest snapshot per account
    seen: set[str] = set()
    accounts: list[dict] = []
    for r in rows:
        key = f"{r.get('account_name')}|{r.get('institution')}"
        if key not in seen:
            seen.add(key)
            accounts.append(r)

    top = accounts[:10]
    return {
        "type": "bar",
        "title": "Account Balances",
        "labels": [f"{r.get('institution', '')} — {str(r.get('account_type', '')).replace('_', ' ').title()}" for r in top],
        "datasets": [{"label": "Total Value", "data": [_f(r.get("total_value")) for r in top]}],
        "currency": True,
    }


def _cashflow_bar(rows: list[dict], label: str) -> dict:
    return {
        "type": "bar",
        "title": f"Cash Flow{f' — {label}' if label else ''}",
        "labels": [f"{r.get('institution', '')} ({str(r.get('account_type', '')).replace('_', ' ')})" for r in rows],
        "datasets": [
            {"label": "Inflow",  "data": [_f(r.get("total_inflow"))  for r in rows]},
            {"label": "Outflow", "data": [_f(r.get("total_outflow")) for r in rows]},
        ],
        "currency": True,
    }


# ── Util ──────────────────────────────────────────────────────────────────────

def _f(v: Any) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0
