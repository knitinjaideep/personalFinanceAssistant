"""
Repository for IngestionJobModel.

All SQL for ingestion job state is centralised here.  Services depend on
this repository rather than issuing raw queries.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional, Sequence

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.staged_models import IngestionJobModel
from app.domain.enums import IngestionJobStatus, IngestionStage

logger = structlog.get_logger(__name__)


class IngestionJobRepository:
    """Data-access layer for ingestion jobs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────────────────────

    async def create(
        self,
        document_id: str,
        bucket_id: Optional[str] = None,
    ) -> IngestionJobModel:
        """Insert a new PENDING job and return it."""
        job = IngestionJobModel(
            document_id=document_id,
            bucket_id=bucket_id,
            status=IngestionJobStatus.PENDING.value,
            current_stage=IngestionStage.RECEIVED.value,
        )
        self._session.add(job)
        await self._session.flush()
        logger.info(
            "ingestion_job.created",
            job_id=job.id,
            document_id=document_id,
        )
        return job

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get(self, job_id: str) -> Optional[IngestionJobModel]:
        """Return a job by primary key, or None."""
        result = await self._session.execute(
            select(IngestionJobModel).where(IngestionJobModel.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_by_document(self, document_id: str) -> List[IngestionJobModel]:
        """Return all jobs for a document, newest first."""
        result = await self._session.execute(
            select(IngestionJobModel)
            .where(IngestionJobModel.document_id == document_id)
            .order_by(IngestionJobModel.created_at.desc())  # type: ignore[union-attr]
        )
        return list(result.scalars().all())

    async def get_latest_for_document(
        self, document_id: str
    ) -> Optional[IngestionJobModel]:
        """Return the most recent job for a document."""
        jobs = await self.get_by_document(document_id)
        return jobs[0] if jobs else None

    async def list_resumable(self) -> List[IngestionJobModel]:
        """
        Return all jobs in PENDING or PAUSED state.

        Called on startup so the runner can resume interrupted work.
        """
        result = await self._session.execute(
            select(IngestionJobModel)
            .where(
                IngestionJobModel.status.in_(  # type: ignore[union-attr]
                    [IngestionJobStatus.PENDING.value, IngestionJobStatus.PAUSED.value]
                )
            )
            .order_by(IngestionJobModel.created_at.asc())  # type: ignore[union-attr]
        )
        return list(result.scalars().all())

    async def list_awaiting_review(self) -> List[IngestionJobModel]:
        """Return jobs blocked at the review gate."""
        result = await self._session.execute(
            select(IngestionJobModel)
            .where(
                IngestionJobModel.status
                == IngestionJobStatus.AWAITING_REVIEW.value
            )
            .order_by(IngestionJobModel.created_at.desc())  # type: ignore[union-attr]
        )
        return list(result.scalars().all())

    # ── Update ────────────────────────────────────────────────────────────────

    async def mark_running(self, job_id: str) -> None:
        """Transition job to RUNNING and record start time."""
        await self._session.execute(
            update(IngestionJobModel)
            .where(IngestionJobModel.id == job_id)
            .values(
                status=IngestionJobStatus.RUNNING.value,
                started_at=datetime.utcnow(),
                last_heartbeat=datetime.utcnow(),
                attempt_count=IngestionJobModel.attempt_count + 1,
            )
        )
        logger.info("ingestion_job.running", job_id=job_id)

    async def advance_stage(self, job_id: str, stage: IngestionStage) -> None:
        """Record that the pipeline has entered a new stage."""
        await self._session.execute(
            update(IngestionJobModel)
            .where(IngestionJobModel.id == job_id)
            .values(
                current_stage=stage.value,
                last_heartbeat=datetime.utcnow(),
            )
        )

    async def record_stage_timing(
        self, job_id: str, stage: IngestionStage, duration_ms: int
    ) -> None:
        """Append a stage timing to the JSON timings blob."""
        job = await self.get(job_id)
        if job is None:
            return
        timings: dict[str, int] = json.loads(job.stage_timings_json or "{}")
        timings[stage.value] = duration_ms
        await self._session.execute(
            update(IngestionJobModel)
            .where(IngestionJobModel.id == job_id)
            .values(stage_timings_json=json.dumps(timings))
        )

    async def append_warning(self, job_id: str, warning: str) -> None:
        """Add a warning string to the job's warnings list."""
        job = await self.get(job_id)
        if job is None:
            return
        warnings: list[str] = json.loads(job.warnings_json or "[]")
        warnings.append(warning)
        await self._session.execute(
            update(IngestionJobModel)
            .where(IngestionJobModel.id == job_id)
            .values(warnings_json=json.dumps(warnings))
        )

    async def mark_awaiting_review(self, job_id: str) -> None:
        """Transition job to AWAITING_REVIEW (extraction done, review gate open)."""
        await self._session.execute(
            update(IngestionJobModel)
            .where(IngestionJobModel.id == job_id)
            .values(
                status=IngestionJobStatus.AWAITING_REVIEW.value,
                last_heartbeat=datetime.utcnow(),
            )
        )
        logger.info("ingestion_job.awaiting_review", job_id=job_id)

    async def mark_completed(self, job_id: str) -> None:
        """Transition job to COMPLETED."""
        await self._session.execute(
            update(IngestionJobModel)
            .where(IngestionJobModel.id == job_id)
            .values(
                status=IngestionJobStatus.COMPLETED.value,
                completed_at=datetime.utcnow(),
            )
        )
        logger.info("ingestion_job.completed", job_id=job_id)

    async def mark_paused(self, job_id: str, reason: str) -> None:
        """Transition job to PAUSED (eligible for resume)."""
        await self._session.execute(
            update(IngestionJobModel)
            .where(IngestionJobModel.id == job_id)
            .values(
                status=IngestionJobStatus.PAUSED.value,
                error_detail=reason,
                last_heartbeat=datetime.utcnow(),
            )
        )
        logger.warning("ingestion_job.paused", job_id=job_id, reason=reason)

    async def mark_failed(self, job_id: str, error: str) -> None:
        """Transition job to FAILED with error details."""
        await self._session.execute(
            update(IngestionJobModel)
            .where(IngestionJobModel.id == job_id)
            .values(
                status=IngestionJobStatus.FAILED.value,
                error_detail=error,
                last_heartbeat=datetime.utcnow(),
            )
        )
        logger.error("ingestion_job.failed", job_id=job_id, error=error)

    async def heartbeat(self, job_id: str) -> None:
        """Update last_heartbeat to signal the runner is still alive."""
        await self._session.execute(
            update(IngestionJobModel)
            .where(IngestionJobModel.id == job_id)
            .values(last_heartbeat=datetime.utcnow())
        )
