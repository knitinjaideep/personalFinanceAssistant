"""
Lightweight "what data do I actually have?" lookups.

Used by the chat router's helpful-fallback step so that instead of saying
"no data" we can tell the user which categories / institutions / months we
*do* have, optionally scoped to a category or institution they asked about.

Read-only, parameterized SQL. Best-effort: any failure returns empty lists.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.core.logger import get_logger
from app.db.engine import get_session

logger = get_logger(__name__)


async def _scalars(sql: str, params: dict[str, Any] | None = None) -> list[Any]:
    try:
        async with get_session() as session:
            result = await session.execute(text(sql), params or {})
            return [r[0] for r in result.fetchall() if r[0] is not None]
    except Exception as exc:  # noqa: BLE001
        logger.warning("availability.query_failed", extra={"error": str(exc)})
        return []


async def available_categories(institution: str | None = None) -> list[str]:
    where = ""
    params: dict[str, Any] = {}
    if institution:
        where = "WHERE LOWER(i.institution_type) = :inst"
        params["inst"] = institution.lower()
    sql = f"""
        SELECT DISTINCT t.category
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        JOIN institutions i ON a.institution_id = i.id
        {where}
        ORDER BY t.category
        LIMIT 25
    """
    return await _scalars(sql, params)


async def available_institutions() -> list[str]:
    return await _scalars(
        "SELECT DISTINCT name FROM institutions ORDER BY name LIMIT 25"
    )


async def available_accounts() -> list[str]:
    return await _scalars(
        "SELECT DISTINCT account_name FROM accounts WHERE account_name IS NOT NULL "
        "ORDER BY account_name LIMIT 25"
    )


async def transaction_date_bounds(institution: str | None = None) -> tuple[str | None, str | None]:
    """Return (earliest, latest) transaction date strings, optionally per institution."""
    where = ""
    params: dict[str, Any] = {}
    if institution:
        where = "WHERE LOWER(i.institution_type) = :inst"
        params["inst"] = institution.lower()
    sql = f"""
        SELECT MIN(t.transaction_date), MAX(t.transaction_date)
        FROM transactions t
        JOIN accounts a ON t.account_id = a.id
        JOIN institutions i ON a.institution_id = i.id
        {where}
    """
    try:
        async with get_session() as session:
            result = await session.execute(text(sql), params)
            row = result.fetchone()
            if row:
                return (str(row[0]) if row[0] else None, str(row[1]) if row[1] else None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("availability.bounds_failed", extra={"error": str(exc)})
    return None, None
