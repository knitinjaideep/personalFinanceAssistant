"""
SQL query service — generates and executes safe SQL for structured financial questions.

Uses intent-specific query templates. Never executes arbitrary user-provided SQL.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db import repositories as repo
from app.domain.enums import QueryIntent

logger = structlog.get_logger(__name__)


async def execute_for_intent(intent: QueryIntent, question: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a SQL query appropriate for the given intent.

    Returns:
        Dict with 'rows' (list of dicts), 'columns' (list of str), 'summary' (str).
    """
    params = params or {}
    handler = _INTENT_HANDLERS.get(intent)
    if handler is None:
        return {"rows": [], "columns": [], "summary": "No SQL handler for this intent."}

    try:
        return await handler(question, params)
    except Exception as exc:
        logger.error("sql_query.failed", intent=intent.value, error=str(exc))
        return {"rows": [], "columns": [], "summary": f"Query failed: {exc}"}


async def _fee_summary(question: str, params: dict) -> dict:
    async with get_session() as session:
        result = await session.execute(text("""
            SELECT
                f.fee_category,
                i.name as institution,
                COUNT(*) as fee_count,
                ROUND(SUM(CAST(f.amount AS REAL)), 2) as total_amount,
                ROUND(AVG(CAST(f.amount AS REAL)), 2) as avg_amount,
                MIN(f.fee_date) as earliest,
                MAX(f.fee_date) as latest
            FROM fees f
            JOIN accounts a ON f.account_id = a.id
            JOIN institutions i ON a.institution_id = i.id
            GROUP BY f.fee_category, i.name
            ORDER BY total_amount DESC
        """))
        rows = [dict(r._mapping) for r in result.fetchall()]
        total = sum(float(r.get("total_amount", 0) or 0) for r in rows)
        return {
            "rows": rows,
            "columns": ["fee_category", "institution", "fee_count", "total_amount", "avg_amount", "earliest", "latest"],
            "summary": f"Found {len(rows)} fee categories totaling ${total:,.2f}.",
        }


async def _transaction_lookup(question: str, params: dict) -> dict:
    async with get_session() as session:
        # Basic transaction listing — could be refined with NLP-extracted filters
        result = await session.execute(text("""
            SELECT
                t.transaction_date,
                t.description,
                t.merchant_name,
                t.amount,
                t.transaction_type,
                t.category,
                i.name as institution
            FROM transactions t
            JOIN accounts a ON t.account_id = a.id
            JOIN institutions i ON a.institution_id = i.id
            ORDER BY t.transaction_date DESC
            LIMIT 50
        """))
        rows = [dict(r._mapping) for r in result.fetchall()]
        return {
            "rows": rows,
            "columns": ["transaction_date", "description", "merchant_name", "amount", "transaction_type", "category", "institution"],
            "summary": f"Found {len(rows)} recent transactions.",
        }


async def _balance_lookup(question: str, params: dict) -> dict:
    async with get_session() as session:
        result = await session.execute(text("""
            SELECT
                a.account_name,
                a.account_type,
                i.name as institution,
                bs.snapshot_date,
                bs.total_value,
                bs.cash_value,
                bs.invested_value
            FROM balance_snapshots bs
            JOIN accounts a ON bs.account_id = a.id
            JOIN institutions i ON a.institution_id = i.id
            ORDER BY bs.snapshot_date DESC
            LIMIT 20
        """))
        rows = [dict(r._mapping) for r in result.fetchall()]
        if rows:
            latest_total = sum(float(r.get("total_value", 0) or 0) for r in rows[:5])
            summary = f"Found {len(rows)} balance snapshots. Most recent total: ${latest_total:,.2f}."
        else:
            summary = "No balance data found."
        return {
            "rows": rows,
            "columns": ["account_name", "account_type", "institution", "snapshot_date", "total_value", "cash_value", "invested_value"],
            "summary": summary,
        }


async def _holdings_lookup(question: str, params: dict) -> dict:
    async with get_session() as session:
        result = await session.execute(text("""
            SELECT
                h.symbol,
                h.description,
                h.quantity,
                h.price,
                h.market_value,
                h.asset_class,
                h.percent_of_portfolio,
                i.name as institution
            FROM holdings h
            JOIN accounts a ON h.account_id = a.id
            JOIN institutions i ON a.institution_id = i.id
            JOIN statements s ON h.statement_id = s.id
            ORDER BY s.period_end DESC, CAST(h.market_value AS REAL) DESC
            LIMIT 50
        """))
        rows = [dict(r._mapping) for r in result.fetchall()]
        total_value = sum(float(r.get("market_value", 0) or 0) for r in rows)
        return {
            "rows": rows,
            "columns": ["symbol", "description", "quantity", "price", "market_value", "asset_class", "percent_of_portfolio", "institution"],
            "summary": f"Found {len(rows)} holdings worth ${total_value:,.2f} total.",
        }


async def _cash_flow_summary(question: str, params: dict) -> dict:
    async with get_session() as session:
        result = await session.execute(text("""
            SELECT
                i.name as institution,
                a.account_type,
                SUM(CASE WHEN CAST(t.amount AS REAL) > 0 THEN CAST(t.amount AS REAL) ELSE 0 END) as total_inflow,
                SUM(CASE WHEN CAST(t.amount AS REAL) < 0 THEN ABS(CAST(t.amount AS REAL)) ELSE 0 END) as total_outflow,
                SUM(CAST(t.amount AS REAL)) as net_flow,
                COUNT(*) as txn_count
            FROM transactions t
            JOIN accounts a ON t.account_id = a.id
            JOIN institutions i ON a.institution_id = i.id
            GROUP BY i.name, a.account_type
        """))
        rows = [dict(r._mapping) for r in result.fetchall()]
        net = sum(float(r.get("net_flow", 0) or 0) for r in rows)
        return {
            "rows": rows,
            "columns": ["institution", "account_type", "total_inflow", "total_outflow", "net_flow", "txn_count"],
            "summary": f"Net cash flow across all accounts: ${net:,.2f}.",
        }


async def _document_availability(question: str, params: dict) -> dict:
    async with get_session() as session:
        result = await session.execute(text("""
            SELECT
                d.original_filename,
                d.institution_type,
                d.status,
                d.page_count,
                d.upload_time,
                COUNT(s.id) as statement_count
            FROM documents d
            LEFT JOIN statements s ON s.document_id = d.id
            GROUP BY d.id
            ORDER BY d.upload_time DESC
        """))
        rows = [dict(r._mapping) for r in result.fetchall()]
        return {
            "rows": rows,
            "columns": ["original_filename", "institution_type", "status", "page_count", "upload_time", "statement_count"],
            "summary": f"Found {len(rows)} uploaded documents.",
        }


async def _institution_coverage(question: str, params: dict) -> dict:
    async with get_session() as session:
        result = await session.execute(text("""
            SELECT
                i.name,
                i.institution_type,
                COUNT(DISTINCT a.id) as account_count,
                COUNT(DISTINCT s.id) as statement_count,
                COUNT(DISTINCT t.id) as transaction_count,
                MIN(s.period_start) as earliest,
                MAX(s.period_end) as latest
            FROM institutions i
            LEFT JOIN accounts a ON a.institution_id = i.id
            LEFT JOIN statements s ON s.institution_id = i.id
            LEFT JOIN transactions t ON t.account_id = a.id
            GROUP BY i.id
        """))
        rows = [dict(r._mapping) for r in result.fetchall()]
        return {
            "rows": rows,
            "columns": ["name", "institution_type", "account_count", "statement_count", "transaction_count", "earliest", "latest"],
            "summary": f"Data from {len(rows)} institutions.",
        }


async def _statement_coverage(question: str, params: dict) -> dict:
    async with get_session() as session:
        result = await session.execute(text("""
            SELECT
                i.name as institution,
                a.account_type,
                s.statement_type,
                s.period_start,
                s.period_end,
                s.extraction_status,
                s.overall_confidence
            FROM statements s
            JOIN institutions i ON s.institution_id = i.id
            JOIN accounts a ON s.account_id = a.id
            ORDER BY s.period_start
        """))
        rows = [dict(r._mapping) for r in result.fetchall()]
        return {
            "rows": rows,
            "columns": ["institution", "account_type", "statement_type", "period_start", "period_end", "extraction_status", "overall_confidence"],
            "summary": f"Found {len(rows)} parsed statements.",
        }


_INTENT_HANDLERS = {
    QueryIntent.FEE_SUMMARY: _fee_summary,
    QueryIntent.TRANSACTION_LOOKUP: _transaction_lookup,
    QueryIntent.BALANCE_LOOKUP: _balance_lookup,
    QueryIntent.HOLDINGS_LOOKUP: _holdings_lookup,
    QueryIntent.CASH_FLOW_SUMMARY: _cash_flow_summary,
    QueryIntent.DOCUMENT_AVAILABILITY: _document_availability,
    QueryIntent.INSTITUTION_COVERAGE: _institution_coverage,
    QueryIntent.STATEMENT_COVERAGE: _statement_coverage,
}
