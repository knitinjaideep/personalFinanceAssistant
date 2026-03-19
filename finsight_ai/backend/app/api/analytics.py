"""
Analytics API endpoints — summary stats and metrics.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from app.db.engine import get_session
from app.db import repositories as repo
from app.domain.entities import AnalyticsSummary
from app.services.folder_scanner import scan_folders

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def get_summary():
    """Get high-level analytics summary."""
    async with get_session() as session:
        data = await repo.get_analytics_summary(session)
        return AnalyticsSummary(**data)


@router.get("/fees")
async def get_fees(institution: str | None = None):
    """Get fee summary grouped by category."""
    async with get_session() as session:
        return await repo.get_fee_summary(session, institution_type=institution)


@router.get("/holdings")
async def get_holdings(account_id: str | None = None):
    """Get current holdings."""
    async with get_session() as session:
        return await repo.get_holdings_summary(session, account_id=account_id)


@router.get("/balances")
async def get_balances(account_id: str | None = None):
    """Get balance history."""
    async with get_session() as session:
        return await repo.get_balance_history(session, account_id=account_id)


@router.get("/folders")
async def get_folder_summary(recent_limit: int = 10):
    """
    Scan fixed local folders and return per-folder document counts + recent files.
    This is the primary document-display API — shows summaries, not individual file lists.
    """
    return scan_folders(recent_limit=recent_limit)


@router.get("/transactions")
async def get_transactions(
    institution: str | None = None,
    category: str | None = None,
    limit: int = 50,
):
    """Get recent transactions with optional filters."""
    async with get_session() as session:
        txns = await repo.query_transactions(
            session, institution_type=institution, category=category, limit=limit
        )
        return [
            {
                "id": t.id,
                "date": str(t.transaction_date),
                "description": t.description,
                "merchant": t.merchant_name,
                "amount": t.amount,
                "type": t.transaction_type,
                "category": t.category,
            }
            for t in txns
        ]
