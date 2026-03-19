"""
Repository for ReviewItemModel.

The review service (Phase 2.2) will call this repository to:
- bulk-create review items after extraction
- fetch the pending queue for the UI
- record resolution actions

Priority convention: 0 = highest urgency, 100 = lowest.
The service layer assigns priority based on confidence bands and
reconciliation severity.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.staged_models import ReviewItemModel
from app.domain.enums import ReviewItemStatus, ReviewItemType

logger = structlog.get_logger(__name__)


class ReviewItemRepository:
    """Data-access layer for review queue items."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────────────────────

    async def create(
        self,
        ingestion_job_id: str,
        record_type: ReviewItemType,
        record_id: str,
        reason: str,
        confidence: float,
        priority: int = 50,
    ) -> ReviewItemModel:
        """Insert a single review item."""
        item = ReviewItemModel(
            ingestion_job_id=ingestion_job_id,
            record_type=record_type.value,
            record_id=record_id,
            status=ReviewItemStatus.PENDING.value,
            reason=reason,
            priority=priority,
            confidence=confidence,
        )
        self._session.add(item)
        await self._session.flush()
        logger.info(
            "review_item.created",
            item_id=item.id,
            record_type=record_type.value,
            record_id=record_id,
            reason=reason,
        )
        return item

    async def bulk_create(
        self, items: List[ReviewItemModel]
    ) -> List[ReviewItemModel]:
        """Insert multiple review items in one flush."""
        for item in items:
            self._session.add(item)
        await self._session.flush()
        logger.info("review_items.bulk_created", count=len(items))
        return items

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get(self, item_id: str) -> Optional[ReviewItemModel]:
        result = await self._session.execute(
            select(ReviewItemModel).where(ReviewItemModel.id == item_id)
        )
        return result.scalar_one_or_none()

    async def list_pending(
        self,
        job_id: Optional[str] = None,
        record_type: Optional[ReviewItemType] = None,
        limit: int = 100,
    ) -> List[ReviewItemModel]:
        """
        Return pending review items ordered by priority (ascending) then confidence.

        Optionally filtered by ingestion job or record type.
        """
        q = (
            select(ReviewItemModel)
            .where(ReviewItemModel.status == ReviewItemStatus.PENDING.value)
            .order_by(
                ReviewItemModel.priority.asc(),    # type: ignore[union-attr]
                ReviewItemModel.confidence.asc(),  # type: ignore[union-attr]
            )
            .limit(limit)
        )
        if job_id:
            q = q.where(ReviewItemModel.ingestion_job_id == job_id)
        if record_type:
            q = q.where(ReviewItemModel.record_type == record_type.value)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def count_pending(self, job_id: Optional[str] = None) -> int:
        """Return the number of pending items, optionally scoped to a job."""
        from sqlalchemy import func
        q = select(func.count(ReviewItemModel.id)).where(
            ReviewItemModel.status == ReviewItemStatus.PENDING.value
        )
        if job_id:
            q = q.where(ReviewItemModel.ingestion_job_id == job_id)
        result = await self._session.execute(q)
        return result.scalar_one() or 0

    async def list_for_record(self, record_id: str) -> List[ReviewItemModel]:
        """Return all review items for a specific staged record."""
        result = await self._session.execute(
            select(ReviewItemModel)
            .where(ReviewItemModel.record_id == record_id)
            .order_by(ReviewItemModel.created_at.desc())  # type: ignore[union-attr]
        )
        return list(result.scalars().all())

    async def list_for_job(self, job_id: str) -> List[ReviewItemModel]:
        result = await self._session.execute(
            select(ReviewItemModel)
            .where(ReviewItemModel.ingestion_job_id == job_id)
            .order_by(
                ReviewItemModel.priority.asc(),   # type: ignore[union-attr]
                ReviewItemModel.created_at.asc(), # type: ignore[union-attr]
            )
        )
        return list(result.scalars().all())

    # ── Resolve ───────────────────────────────────────────────────────────────

    async def resolve(
        self,
        item_id: str,
        action: str,
        notes: Optional[str] = None,
    ) -> None:
        """
        Mark a review item as RESOLVED with the action taken.

        ``action`` should be one of: "approved", "corrected", "rejected".
        """
        await self._session.execute(
            update(ReviewItemModel)
            .where(ReviewItemModel.id == item_id)
            .values(
                status=ReviewItemStatus.RESOLVED.value,
                resolution_action=action,
                resolution_notes=notes,
                resolved_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        logger.info("review_item.resolved", item_id=item_id, action=action)

    async def skip(self, item_id: str) -> None:
        """Mark a review item as SKIPPED (deferred without decision)."""
        await self._session.execute(
            update(ReviewItemModel)
            .where(ReviewItemModel.id == item_id)
            .values(
                status=ReviewItemStatus.SKIPPED.value,
                updated_at=datetime.utcnow(),
            )
        )
        logger.info("review_item.skipped", item_id=item_id)

    async def requeue(self, item_id: str, reason: str) -> None:
        """
        Reset a SKIPPED or RESOLVED item back to PENDING.

        Used when a correction to one record invalidates the review
        decision of a related record.
        """
        await self._session.execute(
            update(ReviewItemModel)
            .where(ReviewItemModel.id == item_id)
            .values(
                status=ReviewItemStatus.PENDING.value,
                reason=reason,
                resolved_at=None,
                resolution_action=None,
                resolution_notes=None,
                updated_at=datetime.utcnow(),
            )
        )
        logger.info("review_item.requeued", item_id=item_id, reason=reason)
