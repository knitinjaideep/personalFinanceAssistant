"""
Statement data endpoints.

Routes:
  GET /api/v1/statements/              List statements
  GET /api/v1/statements/{id}          Get statement detail
  GET /api/v1/statements/{id}/fees     Get fees for a statement
  GET /api/v1/statements/{id}/holdings Get holdings for a statement
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.database.models import FeeModel, HoldingModel, StatementModel, TransactionModel
from app.database.repositories.statement_repo import StatementRepository

router = APIRouter()


@router.get("/", summary="List all statements")
async def list_statements(
    limit: int = 50,
    offset: int = 0,
    institution_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    stmt = (
        select(StatementModel)
        .order_by(StatementModel.period_end.desc())
        .limit(limit)
        .offset(offset)
    )
    if institution_id:
        stmt = stmt.where(StatementModel.institution_id == institution_id)

    result = await session.execute(stmt)
    statements = result.scalars().all()

    return JSONResponse(
        content=[
            {
                "id": s.id,
                "institution_id": s.institution_id,
                "account_id": s.account_id,
                "statement_type": s.statement_type,
                "period_start": str(s.period_start),
                "period_end": str(s.period_end),
                "extraction_status": s.extraction_status,
                "overall_confidence": s.overall_confidence,
                "created_at": s.created_at.isoformat(),
            }
            for s in statements
        ]
    )


@router.get("/{statement_id}/fees", summary="Get fees for a statement")
async def get_statement_fees(
    statement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    result = await session.execute(
        select(FeeModel).where(FeeModel.statement_id == str(statement_id))
    )
    fees = result.scalars().all()
    return JSONResponse(
        content=[
            {
                "id": f.id,
                "fee_date": str(f.fee_date),
                "description": f.description,
                "amount": f.amount,
                "fee_category": f.fee_category,
                "confidence": f.confidence,
            }
            for f in fees
        ]
    )


@router.get("/{statement_id}/holdings", summary="Get holdings for a statement")
async def get_statement_holdings(
    statement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    result = await session.execute(
        select(HoldingModel).where(HoldingModel.statement_id == str(statement_id))
    )
    holdings = result.scalars().all()
    return JSONResponse(
        content=[
            {
                "id": h.id,
                "symbol": h.symbol,
                "description": h.description,
                "quantity": h.quantity,
                "price": h.price,
                "market_value": h.market_value,
                "asset_class": h.asset_class,
                "confidence": h.confidence,
            }
            for h in holdings
        ]
    )


@router.get("/{statement_id}/transactions", summary="Get transactions for a statement")
async def get_statement_transactions(
    statement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    result = await session.execute(
        select(TransactionModel).where(TransactionModel.statement_id == str(statement_id))
    )
    txns = result.scalars().all()
    return JSONResponse(
        content=[
            {
                "id": t.id,
                "transaction_date": str(t.transaction_date),
                "description": t.description,
                "transaction_type": t.transaction_type,
                "amount": t.amount,
                "symbol": t.symbol,
                "confidence": t.confidence,
            }
            for t in txns
        ]
    )
