"""
Bucket repository — all SQL access for buckets and their document links.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BucketDocumentModel, BucketModel, StatementDocumentModel
from app.domain.entities import Bucket, BucketCreateRequest
from app.domain.enums import BucketStatus


class BucketRepository:
    """CRUD operations for BucketModel."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Read ──────────────────────────────────────────────────────────────────

    async def list_active(self) -> Sequence[BucketModel]:
        """Return all non-deleted buckets, ordered by name."""
        result = await self._session.execute(
            select(BucketModel)
            .where(BucketModel.status != BucketStatus.DELETED.value)
            .order_by(BucketModel.name)
        )
        return result.scalars().all()

    async def get_by_id(self, bucket_id: uuid.UUID) -> BucketModel | None:
        result = await self._session.execute(
            select(BucketModel).where(BucketModel.id == str(bucket_id))
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> BucketModel | None:
        result = await self._session.execute(
            select(BucketModel).where(
                BucketModel.name == name,
                BucketModel.status != BucketStatus.DELETED.value,
            )
        )
        return result.scalar_one_or_none()

    # ── Write ─────────────────────────────────────────────────────────────────

    async def create(self, request: BucketCreateRequest) -> BucketModel:
        """Create a new bucket from a create request."""
        model = BucketModel(
            name=request.name,
            description=request.description,
            institution_type=request.institution_type.value if request.institution_type else None,
            color=request.color,
            icon=request.icon,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return model

    async def delete(self, bucket_id: uuid.UUID) -> bool:
        """Soft-delete a bucket by ID. Returns True if it existed."""
        from datetime import datetime

        result = await self._session.execute(
            update(BucketModel)
            .where(BucketModel.id == str(bucket_id))
            .values(status=BucketStatus.DELETED.value, updated_at=datetime.utcnow())
        )
        await self._session.commit()
        return result.rowcount > 0

    async def refresh_document_count(self, bucket_id: uuid.UUID) -> None:
        """Recalculate and persist the document count for a bucket."""
        count_result = await self._session.execute(
            select(func.count(BucketDocumentModel.id)).where(
                BucketDocumentModel.bucket_id == str(bucket_id)
            )
        )
        count = count_result.scalar_one()
        await self._session.execute(
            update(BucketModel)
            .where(BucketModel.id == str(bucket_id))
            .values(document_count=count)
        )
        await self._session.commit()


class BucketDocumentRepository:
    """Manages the many-to-many join between buckets and documents."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def assign(self, bucket_id: uuid.UUID, document_id: uuid.UUID) -> BucketDocumentModel:
        """Assign a document to a bucket (idempotent)."""
        # Check if link already exists
        existing = await self._session.execute(
            select(BucketDocumentModel).where(
                BucketDocumentModel.bucket_id == str(bucket_id),
                BucketDocumentModel.document_id == str(document_id),
            )
        )
        link = existing.scalar_one_or_none()
        if link:
            return link

        link = BucketDocumentModel(
            bucket_id=str(bucket_id),
            document_id=str(document_id),
        )
        self._session.add(link)
        await self._session.commit()
        await self._session.refresh(link)
        return link

    async def unassign(self, bucket_id: uuid.UUID, document_id: uuid.UUID) -> bool:
        """Remove a document from a bucket."""
        from sqlalchemy import delete as sql_delete

        result = await self._session.execute(
            sql_delete(BucketDocumentModel).where(
                BucketDocumentModel.bucket_id == str(bucket_id),
                BucketDocumentModel.document_id == str(document_id),
            )
        )
        await self._session.commit()
        return result.rowcount > 0

    async def remove_all_for_document(self, document_id: uuid.UUID) -> int:
        """Remove all bucket links for a document (used during deletion)."""
        from sqlalchemy import delete as sql_delete

        result = await self._session.execute(
            sql_delete(BucketDocumentModel).where(
                BucketDocumentModel.document_id == str(document_id)
            )
        )
        await self._session.commit()
        return result.rowcount

    async def get_bucket_ids_for_document(self, document_id: uuid.UUID) -> list[str]:
        result = await self._session.execute(
            select(BucketDocumentModel.bucket_id).where(
                BucketDocumentModel.document_id == str(document_id)
            )
        )
        return list(result.scalars().all())

    async def list_documents_for_bucket(
        self, bucket_id: uuid.UUID
    ) -> Sequence[StatementDocumentModel]:
        """Return all documents linked to a bucket."""
        result = await self._session.execute(
            select(StatementDocumentModel)
            .join(
                BucketDocumentModel,
                BucketDocumentModel.document_id == StatementDocumentModel.id,
            )
            .where(
                BucketDocumentModel.bucket_id == str(bucket_id),
                StatementDocumentModel.document_status != "deleted",
            )
            .order_by(StatementDocumentModel.upload_timestamp.desc())
        )
        return result.scalars().all()
