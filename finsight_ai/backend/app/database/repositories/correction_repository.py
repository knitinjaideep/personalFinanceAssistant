"""
CorrectionRepository — persistence layer for the field correction journal.

Responsibilities:
- Append new corrections (never update existing rows).
- Query corrections by (institution, record_type, field_name) for hint retrieval.
- Query corrections by institution for calibration aggregation.
- List all corrections for a given staged record (for the review drawer).
- List all corrections for an ingestion job (for bulk audit).

All queries return SQLModel instances; the service layer maps them to domain
or schema objects before returning them to the API.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.staged_models import FieldCorrectionModel

logger = structlog.get_logger(__name__)


class CorrectionRepository:
    """Repository for ``field_corrections`` table operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Write ──────────────────────────────────────────────────────────────────

    async def create(self, correction: FieldCorrectionModel) -> FieldCorrectionModel:
        """
        Persist a new correction record.

        This is append-only — existing rows are never modified.
        """
        self._session.add(correction)
        await self._session.flush()
        logger.debug(
            "correction.created",
            id=correction.id,
            institution=correction.institution_type,
            record_type=correction.record_type,
            field_name=correction.field_name,
        )
        return correction

    async def bulk_create(
        self, corrections: list[FieldCorrectionModel]
    ) -> list[FieldCorrectionModel]:
        """Persist multiple corrections in a single flush."""
        for c in corrections:
            self._session.add(c)
        await self._session.flush()
        return corrections

    # ── Read ───────────────────────────────────────────────────────────────────

    async def list_for_record(
        self, staged_record_id: str
    ) -> list[FieldCorrectionModel]:
        """
        Return all corrections for a specific staged record.

        Ordered by ``corrected_at`` ascending so the review drawer can show
        the correction history chronologically.
        """
        result = await self._session.execute(
            select(FieldCorrectionModel)
            .where(FieldCorrectionModel.staged_record_id == staged_record_id)
            .order_by(FieldCorrectionModel.corrected_at.asc())
        )
        return list(result.scalars().all())

    async def list_for_job(
        self, ingestion_job_id: str
    ) -> list[FieldCorrectionModel]:
        """
        Return all corrections made during a specific ingestion job.

        Useful for the job audit trail and bulk correction review.
        """
        result = await self._session.execute(
            select(FieldCorrectionModel)
            .where(FieldCorrectionModel.ingestion_job_id == ingestion_job_id)
            .order_by(FieldCorrectionModel.corrected_at.asc())
        )
        return list(result.scalars().all())

    async def list_hints(
        self,
        institution_type: str,
        record_type: str,
        field_name: str,
        limit: int = 10,
    ) -> list[FieldCorrectionModel]:
        """
        Return the most recent corrections for a (institution, record_type, field_name) key.

        These are returned to the extraction prompt as few-shot examples.
        Ordered by ``corrected_at`` descending so the freshest corrections
        are used first.

        Args:
            institution_type: e.g. 'morgan_stanley'
            record_type: e.g. 'staged_transaction'
            field_name: e.g. 'amount'
            limit: Max number of examples to return (default 10).
        """
        result = await self._session.execute(
            select(FieldCorrectionModel)
            .where(
                FieldCorrectionModel.institution_type == institution_type,
                FieldCorrectionModel.record_type == record_type,
                FieldCorrectionModel.field_name == field_name,
            )
            .order_by(FieldCorrectionModel.corrected_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_for_institution(
        self,
        institution_type: str,
        limit: int = 200,
        offset: int = 0,
    ) -> list[FieldCorrectionModel]:
        """Return corrections for an institution, paginated."""
        result = await self._session.execute(
            select(FieldCorrectionModel)
            .where(FieldCorrectionModel.institution_type == institution_type)
            .order_by(FieldCorrectionModel.corrected_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    # ── Aggregates (calibration) ───────────────────────────────────────────────

    async def count_by_field(
        self,
        institution_type: str,
        record_type: str,
    ) -> dict[str, int]:
        """
        Count corrections grouped by field_name for a given institution + record type.

        Returns a dict of ``{field_name: correction_count}``.
        Used by confidence calibration to identify systematically wrong fields.
        """
        result = await self._session.execute(
            select(
                FieldCorrectionModel.field_name,
                func.count(FieldCorrectionModel.id).label("cnt"),
            )
            .where(
                FieldCorrectionModel.institution_type == institution_type,
                FieldCorrectionModel.record_type == record_type,
            )
            .group_by(FieldCorrectionModel.field_name)
        )
        return {row.field_name: row.cnt for row in result.all()}

    async def total_count(
        self,
        institution_type: str | None = None,
    ) -> int:
        """Count total corrections, optionally filtered by institution."""
        q = select(func.count(FieldCorrectionModel.id))
        if institution_type:
            q = q.where(FieldCorrectionModel.institution_type == institution_type)
        result = await self._session.execute(q)
        return result.scalar_one()
