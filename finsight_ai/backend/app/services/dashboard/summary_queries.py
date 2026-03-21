"""
Generic dashboard summary queries — counts and coverage across all institutions.

These are the numbers shown in the top-level KPI row on the Home page.
"""

from __future__ import annotations

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.models import (
    AccountModel,
    DocumentModel,
    FeeModel,
    HoldingModel,
    InstitutionModel,
    StatementModel,
    TransactionModel,
)


async def summary_counts(session: AsyncSession) -> dict:
    """
    Fast top-level counts: documents, statements, transactions, fees, holdings, accounts.
    """
    results = await session.execute(
        text("""
            SELECT
                (SELECT COUNT(*) FROM documents WHERE status = 'parsed')   AS documents,
                (SELECT COUNT(*) FROM statements)                           AS statements,
                (SELECT COUNT(*) FROM transactions)                         AS transactions,
                (SELECT COUNT(*) FROM fees)                                 AS fees,
                (SELECT COUNT(*) FROM holdings)                             AS holdings,
                (SELECT COUNT(*) FROM accounts)                             AS accounts,
                (SELECT COUNT(DISTINCT institution_type) FROM institutions) AS institutions,
                (SELECT MIN(period_start) FROM statements)                  AS earliest,
                (SELECT MAX(period_end)   FROM statements)                  AS latest
        """),
    )
    row = results.fetchone()
    return {
        "total_documents": row[0] or 0,
        "total_statements": row[1] or 0,
        "total_transactions": row[2] or 0,
        "total_fees": row[3] or 0,
        "total_holdings": row[4] or 0,
        "total_accounts": row[5] or 0,
        "total_institutions": row[6] or 0,
        "earliest_statement": str(row[7]) if row[7] else None,
        "latest_statement": str(row[8]) if row[8] else None,
    }


async def document_count_by_institution(session: AsyncSession) -> list[dict]:
    """
    Document count per institution — used for folder/institution cards.
    """
    rows = await session.execute(
        text("""
            SELECT
                COALESCE(i.name, d.institution_type) AS institution,
                d.institution_type,
                COUNT(*)                              AS doc_count,
                SUM(CASE WHEN d.status='parsed' THEN 1 ELSE 0 END)  AS parsed,
                SUM(CASE WHEN d.status='failed' THEN 1 ELSE 0 END)  AS failed,
                MAX(s.period_end)                     AS latest_statement
            FROM documents d
            LEFT JOIN institutions i ON i.institution_type = d.institution_type
            LEFT JOIN statements s   ON s.document_id = d.id
            GROUP BY d.institution_type
            ORDER BY doc_count DESC
        """),
    )
    return [
        {
            "institution": r[0] or r[1],
            "institution_type": r[1],
            "doc_count": r[2],
            "parsed": r[3] or 0,
            "failed": r[4] or 0,
            "latest_statement": str(r[5]) if r[5] else None,
        }
        for r in rows.fetchall()
    ]


async def document_count_by_product(session: AsyncSession) -> list[dict]:
    """
    Document count per account_product label (Chase Checking, Freedom, etc.)
    Useful for the per-source cards in the Home page.
    """
    rows = await session.execute(
        text("""
            SELECT
                COALESCE(d.account_product, d.institution_type) AS product,
                d.institution_type,
                COALESCE(d.source_id, d.institution_type)       AS source_id,
                COUNT(*)                                         AS doc_count,
                SUM(CASE WHEN d.status='parsed' THEN 1 ELSE 0 END) AS parsed,
                MAX(s.period_end)                                AS latest_statement
            FROM documents d
            LEFT JOIN statements s ON s.document_id = d.id
            GROUP BY COALESCE(d.source_id, d.institution_type)
            ORDER BY doc_count DESC
        """),
    )
    return [
        {
            "product": r[0],
            "institution_type": r[1],
            "source_id": r[2],
            "doc_count": r[3],
            "parsed": r[4] or 0,
            "latest_statement": str(r[5]) if r[5] else None,
        }
        for r in rows.fetchall()
    ]


async def latest_statement_dates(session: AsyncSession) -> list[dict]:
    """
    Most recent statement period_end per institution — used in coverage cards.
    """
    rows = await session.execute(
        text("""
            SELECT
                d.institution_type,
                MAX(s.period_end) AS latest
            FROM statements s
            JOIN documents d ON d.id = s.document_id
            GROUP BY d.institution_type
            ORDER BY latest DESC
        """),
    )
    return [
        {"institution_type": r[0], "latest_statement": str(r[1]) if r[1] else None}
        for r in rows.fetchall()
    ]
