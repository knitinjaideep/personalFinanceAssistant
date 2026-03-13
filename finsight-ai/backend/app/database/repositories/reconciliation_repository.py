"""
Repository for ReconciliationResultModel.

One row per reconciliation run per staged statement.
Multiple runs are possible (e.g. user corrects a field and re-reconciles).
"""

from __future__ import annotations

import json
from typing import List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.staged_models import ReconciliationResultModel

logger = structlog.get_logger(__name__)


class ReconciliationRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, result: ReconciliationResultModel) -> ReconciliationResultModel:
        self._session.add(result)
        await self._session.flush()
        logger.info(
            "reconciliation.persisted",
            result_id=result.id,
            staged_statement_id=result.staged_statement_id,
            status=result.status,
            score=result.integrity_score,
        )
        return result

    async def get(self, result_id: str) -> Optional[ReconciliationResultModel]:
        r = await self._session.execute(
            select(ReconciliationResultModel).where(
                ReconciliationResultModel.id == result_id
            )
        )
        return r.scalar_one_or_none()

    async def get_latest_for_statement(
        self, staged_statement_id: str
    ) -> Optional[ReconciliationResultModel]:
        """Return the most recent reconciliation run for a staged statement."""
        r = await self._session.execute(
            select(ReconciliationResultModel)
            .where(
                ReconciliationResultModel.staged_statement_id == staged_statement_id
            )
            .order_by(ReconciliationResultModel.run_number.desc())  # type: ignore[union-attr]
            .limit(1)
        )
        return r.scalar_one_or_none()

    async def list_for_job(self, job_id: str) -> List[ReconciliationResultModel]:
        """Return all reconciliation results for all statements in a job."""
        r = await self._session.execute(
            select(ReconciliationResultModel)
            .where(ReconciliationResultModel.ingestion_job_id == job_id)
            .order_by(ReconciliationResultModel.ran_at.desc())  # type: ignore[union-attr]
        )
        return list(r.scalars().all())

    async def next_run_number(self, staged_statement_id: str) -> int:
        """Return the next run_number for a staged statement (1-based)."""
        latest = await self.get_latest_for_statement(staged_statement_id)
        return (latest.run_number + 1) if latest else 1
