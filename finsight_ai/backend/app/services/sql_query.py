"""
SQL query service — generates and executes parameterized read-only SQL
for structured financial questions.

All handlers receive a QueryContext and build safe parameterized queries.
No raw user input is ever interpolated into SQL strings.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text

from app.core.logger import get_logger, get_request_id
from app.db.engine import get_session
from app.domain.entities import QueryContext
from app.domain.enums import QueryIntent

logger = get_logger(__name__)

# ── Return type ───────────────────────────────────────────────────────────────

# Each handler returns:
#   rows    : list[dict]   — data rows
#   columns : list[str]    — ordered column names
#   summary : str          — human-readable single sentence
#   sql_used: str          — the parameterized SQL template shown to the user

SQLResult = dict[str, Any]


# ── Public entry point ────────────────────────────────────────────────────────

async def execute_for_intent(intent: QueryIntent, question: str, ctx: QueryContext) -> SQLResult:
    """Execute the appropriate SQL handler for the given intent + context."""
    handler = _INTENT_HANDLERS.get(intent)
    if handler is None:
        return _empty("No SQL handler for this intent.")

    req_id = get_request_id()
    logger.info(
        "sql_planning_started",
        extra={"stage": "sql_planning_started", "request_id": req_id, "intent": intent.value},
    )
    t0 = time.perf_counter()
    try:
        result = await handler(question, ctx)
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        row_count = len(result.get("rows", []))

        logger.info(
            "sql_planning_completed",
            extra={
                "stage": "sql_planning_completed",
                "request_id": req_id,
                "intent": intent.value,
                "duration_ms": duration_ms,
            },
        )
        logger.info(
            "sql_execution_completed",
            extra={
                "stage": "sql_execution_completed",
                "request_id": req_id,
                "intent": intent.value,
                "result_count": row_count,
                "sql_summary": result.get("summary", ""),
                "duration_ms": duration_ms,
            },
        )
        result["_sql_duration_ms"] = duration_ms
        return result
    except Exception as exc:
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.error(
            "sql_query.failed",
            extra={
                "stage": "sql_execution_failed",
                "request_id": req_id,
                "intent": intent.value,
                "error": str(exc),
                "duration_ms": duration_ms,
            },
        )
        return _empty(f"Query failed: {exc}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _empty(msg: str = "") -> SQLResult:
    return {"rows": [], "columns": [], "summary": msg, "sql_used": ""}


def _date_clause(
    ctx: QueryContext,
    date_col: str,
    params: dict,
) -> str:
    """Return a WHERE fragment (without leading AND) for the date range, or ''."""
    parts: list[str] = []
    if ctx.date_from:
        parts.append(f"{date_col} >= :date_from")
        params["date_from"] = str(ctx.date_from)
    if ctx.date_to:
        parts.append(f"{date_col} <= :date_to")
        params["date_to"] = str(ctx.date_to)
    return " AND ".join(parts)


def _and(clause: str) -> str:
    """Prefix a non-empty clause with AND."""
    return f" AND {clause}" if clause else ""


def _account_clause(ctx: QueryContext, params: dict, alias: str = "a") -> str:
    """Return an account-name WHERE fragment (with leading AND), or ''.

    Matches accounts.account_name with LIKE so a partial name from the user
    ("prime") scopes results to that card ("Prime Visa"). Requires the query to
    join the accounts table as `alias`.
    """
    if not ctx.account_name:
        return ""
    params["account_name"] = f"%{ctx.account_name.lower()}%"
    return f" AND LOWER({alias}.account_name) LIKE :account_name"


# ── Handler: spending_by_category ────────────────────────────────────────────

async def _spending_by_category(question: str, ctx: QueryContext) -> SQLResult:
    params: dict[str, Any] = {}
    date_frag = _date_clause(ctx, "t.transaction_date", params)

    category_frag = ""
    if ctx.category:
        category_frag = " AND LOWER(t.category) = :category"
        params["category"] = ctx.category.lower()

    merchant_frag = ""
    if ctx.merchant:
        merchant_frag = " AND LOWER(COALESCE(t.merchant_name, t.description)) LIKE :merchant"
        params["merchant"] = f"%{ctx.merchant}%"

    institution_frag = ""
    if ctx.institution:
        institution_frag = " AND LOWER(i.institution_type) = :institution"
        params["institution"] = ctx.institution.lower()

    account_frag = _account_clause(ctx, params)

    sql = f"""
        SELECT
            COALESCE(t.category, 'other') AS category,
            i.name                        AS institution,
            a.account_name                AS account_name,
            COUNT(*)                      AS transaction_count,
            ROUND(SUM(ABS(CAST(t.amount AS REAL))), 2) AS total_spent,
            ROUND(AVG(ABS(CAST(t.amount AS REAL))), 2) AS avg_per_txn,
            MIN(t.transaction_date)       AS earliest,
            MAX(t.transaction_date)       AS latest
        FROM transactions t
        JOIN accounts      a ON t.account_id     = a.id
        JOIN institutions  i ON a.institution_id = i.id
        WHERE CAST(t.amount AS REAL) < 0
          AND t.transaction_type NOT IN ('transfer', 'payment', 'refund')
          {_and(date_frag)}{category_frag}{merchant_frag}{institution_frag}{account_frag}
        GROUP BY t.category, i.name, a.account_name
        ORDER BY total_spent DESC
        LIMIT 30
    """

    async with get_session() as session:
        result = await session.execute(text(sql), params)
        rows = [dict(r._mapping) for r in result.fetchall()]

    total = sum(float(r.get("total_spent") or 0) for r in rows)
    period = f" ({ctx.timeframe_label})" if ctx.timeframe_label else ""
    cat_label = f" on {ctx.category}" if ctx.category else ""
    acct_label = f" with {ctx.account_name.title()}" if ctx.account_name else ""
    return {
        "rows": rows,
        "columns": ["category", "institution", "account_name", "transaction_count", "total_spent", "avg_per_txn", "earliest", "latest"],
        "summary": f"Total spending{cat_label}{acct_label}{period}: ${total:,.2f} across {len(rows)} categories.",
        "sql_used": sql.strip(),
    }


# ── Handler: subscription_lookup ─────────────────────────────────────────────

async def _subscription_lookup(question: str, ctx: QueryContext) -> SQLResult:
    params: dict[str, Any] = {"is_recurring": 1}
    date_frag = _date_clause(ctx, "t.transaction_date", params)

    institution_frag = ""
    if ctx.institution:
        institution_frag = " AND LOWER(i.institution_type) = :institution"
        params["institution"] = ctx.institution.lower()

    sql = f"""
        SELECT
            COALESCE(t.merchant_name, t.description) AS merchant,
            COALESCE(t.category, 'subscriptions')    AS category,
            i.name                                   AS institution,
            ROUND(ABS(CAST(t.amount AS REAL)), 2)    AS monthly_amount,
            COUNT(*)                                 AS occurrences,
            MIN(t.transaction_date)                  AS first_seen,
            MAX(t.transaction_date)                  AS last_seen
        FROM transactions t
        JOIN accounts     a ON t.account_id     = a.id
        JOIN institutions i ON a.institution_id = i.id
        WHERE t.is_recurring = :is_recurring
          {_and(date_frag)}{institution_frag}
        GROUP BY LOWER(COALESCE(t.merchant_name, t.description)), i.name
        ORDER BY monthly_amount DESC
        LIMIT 50
    """

    async with get_session() as session:
        result = await session.execute(text(sql), params)
        rows = [dict(r._mapping) for r in result.fetchall()]

    total = sum(float(r.get("monthly_amount") or 0) for r in rows)
    return {
        "rows": rows,
        "columns": ["merchant", "category", "institution", "monthly_amount", "occurrences", "first_seen", "last_seen"],
        "summary": f"Found {len(rows)} recurring charges totaling ${total:,.2f}.",
        "sql_used": sql.strip(),
    }


# ── Handler: fee_summary ──────────────────────────────────────────────────────

async def _fee_summary(question: str, ctx: QueryContext) -> SQLResult:
    params: dict[str, Any] = {}
    date_frag = _date_clause(ctx, "f.fee_date", params)

    institution_frag = ""
    if ctx.institution:
        institution_frag = " AND LOWER(i.institution_type) = :institution"
        params["institution"] = ctx.institution.lower()

    sql = f"""
        SELECT
            COALESCE(f.fee_category, 'other') AS fee_category,
            i.name                            AS institution,
            COUNT(*)                          AS fee_count,
            ROUND(SUM(CAST(f.amount AS REAL)), 2)  AS total_amount,
            ROUND(AVG(CAST(f.amount AS REAL)), 2)  AS avg_amount,
            MIN(f.fee_date)                   AS earliest,
            MAX(f.fee_date)                   AS latest
        FROM fees f
        JOIN accounts     a ON f.account_id     = a.id
        JOIN institutions i ON a.institution_id = i.id
        WHERE 1=1
          {_and(date_frag)}{institution_frag}
        GROUP BY f.fee_category, i.name
        ORDER BY total_amount DESC
    """

    async with get_session() as session:
        result = await session.execute(text(sql), params)
        rows = [dict(r._mapping) for r in result.fetchall()]

    total = sum(float(r.get("total_amount") or 0) for r in rows)
    period = f" ({ctx.timeframe_label})" if ctx.timeframe_label else ""
    inst_label = f" at {ctx.institution.replace('_', ' ').title()}" if ctx.institution else ""
    return {
        "rows": rows,
        "columns": ["fee_category", "institution", "fee_count", "total_amount", "avg_amount", "earliest", "latest"],
        "summary": f"Total fees{inst_label}{period}: ${total:,.2f} across {len(rows)} categories.",
        "sql_used": sql.strip(),
    }


# ── Handler: transaction_lookup ───────────────────────────────────────────────

async def _transaction_lookup(question: str, ctx: QueryContext) -> SQLResult:
    params: dict[str, Any] = {}
    date_frag = _date_clause(ctx, "t.transaction_date", params)

    category_frag = ""
    if ctx.category:
        category_frag = " AND LOWER(t.category) = :category"
        params["category"] = ctx.category.lower()

    merchant_frag = ""
    if ctx.merchant:
        merchant_frag = " AND LOWER(COALESCE(t.merchant_name, t.description)) LIKE :merchant"
        params["merchant"] = f"%{ctx.merchant}%"

    institution_frag = ""
    if ctx.institution:
        institution_frag = " AND LOWER(i.institution_type) = :institution"
        params["institution"] = ctx.institution.lower()

    recurring_frag = " AND t.is_recurring = 1" if ctx.is_recurring_only else ""
    account_frag = _account_clause(ctx, params)

    params["limit"] = ctx.limit

    sql = f"""
        SELECT
            t.transaction_date,
            COALESCE(t.merchant_name, t.description) AS merchant,
            t.description,
            t.amount,
            t.transaction_type,
            COALESCE(t.category, 'other')            AS category,
            i.name                                   AS institution,
            a.account_name,
            a.account_type
        FROM transactions t
        JOIN accounts     a ON t.account_id     = a.id
        JOIN institutions i ON a.institution_id = i.id
        WHERE 1=1
          {_and(date_frag)}{category_frag}{merchant_frag}{institution_frag}{recurring_frag}{account_frag}
        ORDER BY t.transaction_date DESC
        LIMIT :limit
    """

    async with get_session() as session:
        result = await session.execute(text(sql), params)
        rows = [dict(r._mapping) for r in result.fetchall()]

    period = f" ({ctx.timeframe_label})" if ctx.timeframe_label else ""
    acct_label = f" on {ctx.account_name.title()}" if ctx.account_name else ""
    return {
        "rows": rows,
        "columns": ["transaction_date", "merchant", "description", "amount", "transaction_type", "category", "institution", "account_name", "account_type"],
        "summary": f"Found {len(rows)} transactions{acct_label}{period}.",
        "sql_used": sql.strip(),
    }


# ── Handler: balance_lookup ───────────────────────────────────────────────────

async def _balance_lookup(question: str, ctx: QueryContext) -> SQLResult:
    params: dict[str, Any] = {}
    date_frag = _date_clause(ctx, "bs.snapshot_date", params)

    institution_frag = ""
    if ctx.institution:
        institution_frag = " AND LOWER(i.institution_type) = :institution"
        params["institution"] = ctx.institution.lower()

    account_type_frag = ""
    if ctx.account_type:
        account_type_frag = " AND LOWER(a.account_type) = :account_type"
        params["account_type"] = ctx.account_type.lower()

    account_frag = _account_clause(ctx, params)

    sql = f"""
        SELECT
            a.account_name,
            a.account_type,
            i.name        AS institution,
            bs.snapshot_date,
            bs.total_value,
            bs.cash_value,
            bs.invested_value
        FROM balance_snapshots bs
        JOIN accounts     a ON bs.account_id    = a.id
        JOIN institutions i ON a.institution_id = i.id
        WHERE 1=1
          {_and(date_frag)}{institution_frag}{account_type_frag}{account_frag}
        ORDER BY bs.snapshot_date DESC
        LIMIT 30
    """

    async with get_session() as session:
        result = await session.execute(text(sql), params)
        rows = [dict(r._mapping) for r in result.fetchall()]

    # Deduplicate to latest snapshot per account
    seen: set[str] = set()
    latest_rows: list[dict] = []
    for r in rows:
        key = f"{r.get('account_name')}|{r.get('institution')}"
        if key not in seen:
            seen.add(key)
            latest_rows.append(r)

    latest_total = sum(float(r.get("total_value") or 0) for r in latest_rows)
    return {
        "rows": rows,
        "columns": ["account_name", "account_type", "institution", "snapshot_date", "total_value", "cash_value", "invested_value"],
        "summary": f"Latest balance across {len(latest_rows)} accounts: ${latest_total:,.2f}.",
        "sql_used": sql.strip(),
    }


# ── Handler: holdings_total ───────────────────────────────────────────────────

async def _holdings_total(question: str, ctx: QueryContext) -> SQLResult:
    """Sum of market values from the most recent statement per account."""
    params: dict[str, Any] = {}

    institution_frag = ""
    if ctx.institution:
        institution_frag = " AND LOWER(i.institution_type) = :institution"
        params["institution"] = ctx.institution.lower()

    account_type_frag = ""
    if ctx.account_type:
        account_type_frag = " AND LOWER(a.account_type) = :account_type"
        params["account_type"] = ctx.account_type.lower()

    # Get the latest statement per account first, then join holdings to those
    sql = f"""
        WITH latest_stmt AS (
            SELECT account_id, MAX(period_end) AS max_end
            FROM statements
            GROUP BY account_id
        ),
        latest_holdings AS (
            SELECT
                h.id,
                h.account_id,
                h.statement_id,
                h.symbol,
                h.description,
                h.quantity,
                h.market_value,
                h.asset_class,
                h.percent_of_portfolio,
                h.unrealized_gain_loss
            FROM holdings h
            JOIN statements s ON h.statement_id = s.id
            JOIN latest_stmt ls ON s.account_id = ls.account_id AND s.period_end = ls.max_end
        )
        SELECT
            lh.symbol,
            lh.description,
            lh.quantity,
            ROUND(CAST(lh.market_value AS REAL), 2)       AS market_value,
            lh.asset_class,
            lh.percent_of_portfolio,
            ROUND(CAST(lh.unrealized_gain_loss AS REAL), 2) AS unrealized_gain_loss,
            i.name                                         AS institution,
            a.account_type
        FROM latest_holdings lh
        JOIN accounts     a ON lh.account_id    = a.id
        JOIN institutions i ON a.institution_id = i.id
        WHERE 1=1
          {institution_frag}{account_type_frag}
        ORDER BY CAST(lh.market_value AS REAL) DESC
        LIMIT 100
    """

    async with get_session() as session:
        result = await session.execute(text(sql), params)
        rows = [dict(r._mapping) for r in result.fetchall()]

    total = sum(float(r.get("market_value") or 0) for r in rows)
    return {
        "rows": rows,
        "columns": ["symbol", "description", "quantity", "market_value", "asset_class", "percent_of_portfolio", "unrealized_gain_loss", "institution", "account_type"],
        "summary": f"Total invested: ${total:,.2f} across {len(rows)} positions.",
        "sql_used": sql.strip(),
    }


# ── Handler: holdings_lookup ──────────────────────────────────────────────────

async def _holdings_lookup(question: str, ctx: QueryContext) -> SQLResult:
    params: dict[str, Any] = {}

    institution_frag = ""
    if ctx.institution:
        institution_frag = " AND LOWER(i.institution_type) = :institution"
        params["institution"] = ctx.institution.lower()

    sql = f"""
        SELECT
            h.symbol,
            h.description,
            h.quantity,
            h.price,
            ROUND(CAST(h.market_value AS REAL), 2) AS market_value,
            h.asset_class,
            h.percent_of_portfolio,
            i.name AS institution
        FROM holdings h
        JOIN accounts     a ON h.account_id     = a.id
        JOIN institutions i ON a.institution_id = i.id
        JOIN statements   s ON h.statement_id   = s.id
        WHERE 1=1
          {institution_frag}
        ORDER BY s.period_end DESC, CAST(h.market_value AS REAL) DESC
        LIMIT 50
    """

    async with get_session() as session:
        result = await session.execute(text(sql), params)
        rows = [dict(r._mapping) for r in result.fetchall()]

    total = sum(float(r.get("market_value") or 0) for r in rows)
    return {
        "rows": rows,
        "columns": ["symbol", "description", "quantity", "price", "market_value", "asset_class", "percent_of_portfolio", "institution"],
        "summary": f"Found {len(rows)} holdings worth ${total:,.2f} total.",
        "sql_used": sql.strip(),
    }


# ── Handler: cash_flow_summary ────────────────────────────────────────────────

async def _cash_flow_summary(question: str, ctx: QueryContext) -> SQLResult:
    params: dict[str, Any] = {}
    date_frag = _date_clause(ctx, "t.transaction_date", params)

    institution_frag = ""
    if ctx.institution:
        institution_frag = " AND LOWER(i.institution_type) = :institution"
        params["institution"] = ctx.institution.lower()

    account_frag = _account_clause(ctx, params)

    sql = f"""
        SELECT
            i.name       AS institution,
            a.account_type,
            ROUND(SUM(CASE WHEN CAST(t.amount AS REAL) > 0 THEN CAST(t.amount AS REAL) ELSE 0 END), 2) AS total_inflow,
            ROUND(SUM(CASE WHEN CAST(t.amount AS REAL) < 0 THEN ABS(CAST(t.amount AS REAL)) ELSE 0 END), 2) AS total_outflow,
            ROUND(SUM(CAST(t.amount AS REAL)), 2) AS net_flow,
            COUNT(*) AS txn_count
        FROM transactions t
        JOIN accounts     a ON t.account_id     = a.id
        JOIN institutions i ON a.institution_id = i.id
        WHERE 1=1
          {_and(date_frag)}{institution_frag}{account_frag}
        GROUP BY i.name, a.account_type
        ORDER BY ABS(net_flow) DESC
    """

    async with get_session() as session:
        result = await session.execute(text(sql), params)
        rows = [dict(r._mapping) for r in result.fetchall()]

    net = sum(float(r.get("net_flow") or 0) for r in rows)
    period = f" ({ctx.timeframe_label})" if ctx.timeframe_label else ""
    return {
        "rows": rows,
        "columns": ["institution", "account_type", "total_inflow", "total_outflow", "net_flow", "txn_count"],
        "summary": f"Net cash flow{period}: ${net:,.2f}.",
        "sql_used": sql.strip(),
    }


# ── Handler: document_availability ───────────────────────────────────────────

async def _document_availability(question: str, ctx: QueryContext) -> SQLResult:
    sql = """
        SELECT
            d.original_filename,
            d.institution_type,
            d.status,
            d.page_count,
            d.upload_time,
            COUNT(s.id) AS statement_count
        FROM documents d
        LEFT JOIN statements s ON s.document_id = d.id
        GROUP BY d.id
        ORDER BY d.upload_time DESC
    """
    async with get_session() as session:
        result = await session.execute(text(sql))
        rows = [dict(r._mapping) for r in result.fetchall()]
    return {
        "rows": rows,
        "columns": ["original_filename", "institution_type", "status", "page_count", "upload_time", "statement_count"],
        "summary": f"Found {len(rows)} uploaded documents.",
        "sql_used": sql.strip(),
    }


# ── Handler: institution_coverage ────────────────────────────────────────────

async def _institution_coverage(question: str, ctx: QueryContext) -> SQLResult:
    sql = """
        SELECT
            i.name,
            i.institution_type,
            COUNT(DISTINCT a.id)  AS account_count,
            COUNT(DISTINCT s.id)  AS statement_count,
            COUNT(DISTINCT t.id)  AS transaction_count,
            MIN(s.period_start)   AS earliest,
            MAX(s.period_end)     AS latest
        FROM institutions i
        LEFT JOIN accounts      a ON a.institution_id  = i.id
        LEFT JOIN statements    s ON s.institution_id  = i.id
        LEFT JOIN transactions  t ON t.account_id      = a.id
        GROUP BY i.id
        ORDER BY statement_count DESC
    """
    async with get_session() as session:
        result = await session.execute(text(sql))
        rows = [dict(r._mapping) for r in result.fetchall()]
    return {
        "rows": rows,
        "columns": ["name", "institution_type", "account_count", "statement_count", "transaction_count", "earliest", "latest"],
        "summary": f"Data from {len(rows)} institutions.",
        "sql_used": sql.strip(),
    }


# ── Handler: statement_coverage ──────────────────────────────────────────────

async def _statement_coverage(question: str, ctx: QueryContext) -> SQLResult:
    sql = """
        SELECT
            i.name         AS institution,
            a.account_type,
            s.statement_type,
            s.period_start,
            s.period_end,
            s.extraction_status,
            s.overall_confidence
        FROM statements   s
        JOIN institutions i ON s.institution_id = i.id
        JOIN accounts     a ON s.account_id     = a.id
        ORDER BY s.period_start
    """
    async with get_session() as session:
        result = await session.execute(text(sql))
        rows = [dict(r._mapping) for r in result.fetchall()]
    return {
        "rows": rows,
        "columns": ["institution", "account_type", "statement_type", "period_start", "period_end", "extraction_status", "overall_confidence"],
        "summary": f"Found {len(rows)} parsed statements.",
        "sql_used": sql.strip(),
    }


# ── Dispatch table ────────────────────────────────────────────────────────────

_INTENT_HANDLERS = {
    QueryIntent.SPENDING_BY_CATEGORY: _spending_by_category,
    QueryIntent.SUBSCRIPTION_LOOKUP:  _subscription_lookup,
    QueryIntent.FEE_SUMMARY:          _fee_summary,
    QueryIntent.TRANSACTION_LOOKUP:   _transaction_lookup,
    QueryIntent.BALANCE_LOOKUP:       _balance_lookup,
    QueryIntent.HOLDINGS_TOTAL:       _holdings_total,
    QueryIntent.HOLDINGS_LOOKUP:      _holdings_lookup,
    QueryIntent.CASH_FLOW_SUMMARY:    _cash_flow_summary,
    QueryIntent.DOCUMENT_AVAILABILITY:  _document_availability,
    QueryIntent.INSTITUTION_COVERAGE:   _institution_coverage,
    QueryIntent.STATEMENT_COVERAGE:     _statement_coverage,
}
