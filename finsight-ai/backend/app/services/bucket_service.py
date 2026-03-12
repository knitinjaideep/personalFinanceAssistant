"""
Bucket service — business logic for bucket management.

Responsibilities:
- Create, list, and delete buckets
- Assign and unassign documents to/from buckets
- List documents within a bucket
- Emit processing events for bucket operations
"""

from __future__ import annotations

import uuid

import structlog

from app.database.engine import get_session
from app.database.repositories.bucket_repo import BucketDocumentRepository, BucketRepository
from app.database.repositories.statement_repo import StatementDocumentRepository
from app.domain.entities import Bucket, BucketCreateRequest
from app.domain.enums import BucketStatus

logger = structlog.get_logger(__name__)


class BucketService:
    """Application service for bucket management."""

    async def list_buckets(self) -> list[dict]:
        """Return all active buckets with document counts."""
        async with get_session() as session:
            repo = BucketRepository(session)
            models = await repo.list_active()
            return [_bucket_model_to_dict(m) for m in models]

    async def get_bucket(self, bucket_id: uuid.UUID) -> dict | None:
        """Return a single bucket by ID, or None if not found."""
        async with get_session() as session:
            repo = BucketRepository(session)
            model = await repo.get_by_id(bucket_id)
            if not model:
                return None
            return _bucket_model_to_dict(model)

    async def create_bucket(self, request: BucketCreateRequest) -> dict:
        """
        Create a new bucket.

        Raises ValueError if a bucket with the same name already exists.
        """
        async with get_session() as session:
            repo = BucketRepository(session)

            # Check for duplicate name
            existing = await repo.get_by_name(request.name)
            if existing:
                raise ValueError(f"A bucket named '{request.name}' already exists.")

            model = await repo.create(request)
            logger.info("bucket.created", bucket_id=model.id, name=model.name)
            return _bucket_model_to_dict(model)

    async def delete_bucket(self, bucket_id: uuid.UUID) -> bool:
        """
        Soft-delete a bucket.

        Does NOT delete the documents themselves — only the bucket record.
        Documents remain in the system and can be re-assigned.
        """
        async with get_session() as session:
            repo = BucketRepository(session)
            deleted = await repo.delete(bucket_id)
            if deleted:
                logger.info("bucket.deleted", bucket_id=str(bucket_id))
            return deleted

    async def assign_document(
        self, bucket_id: uuid.UUID, document_id: uuid.UUID
    ) -> dict:
        """
        Assign a document to a bucket.

        Raises ValueError if the bucket or document does not exist.
        Returns the updated bucket dict.
        """
        async with get_session() as session:
            bucket_repo = BucketRepository(session)
            doc_repo = StatementDocumentRepository(session)
            link_repo = BucketDocumentRepository(session)

            # Validate bucket exists and is active
            bucket = await bucket_repo.get_by_id(bucket_id)
            if not bucket or bucket.status == BucketStatus.DELETED.value:
                raise ValueError(f"Bucket {bucket_id} not found.")

            # Validate document exists
            try:
                doc = await doc_repo.get_by_id(document_id)
            except Exception:
                raise ValueError(f"Document {document_id} not found.")

            # Create link (idempotent)
            await link_repo.assign(bucket_id, document_id)

            # Refresh denormalised count
            await bucket_repo.refresh_document_count(bucket_id)

            logger.info(
                "bucket.document_assigned",
                bucket_id=str(bucket_id),
                document_id=str(document_id),
            )

            updated = await bucket_repo.get_by_id(bucket_id)
            return _bucket_model_to_dict(updated)  # type: ignore[arg-type]

    async def unassign_document(
        self, bucket_id: uuid.UUID, document_id: uuid.UUID
    ) -> bool:
        """Remove a document from a bucket."""
        async with get_session() as session:
            link_repo = BucketDocumentRepository(session)
            bucket_repo = BucketRepository(session)

            removed = await link_repo.unassign(bucket_id, document_id)
            if removed:
                await bucket_repo.refresh_document_count(bucket_id)
                logger.info(
                    "bucket.document_unassigned",
                    bucket_id=str(bucket_id),
                    document_id=str(document_id),
                )
            return removed

    async def list_documents_in_bucket(self, bucket_id: uuid.UUID) -> list[dict]:
        """Return all non-deleted documents in a bucket."""
        async with get_session() as session:
            link_repo = BucketDocumentRepository(session)
            docs = await link_repo.list_documents_for_bucket(bucket_id)
            return [
                {
                    "id": d.id,
                    "original_filename": d.original_filename,
                    "institution_type": d.institution_type,
                    "document_status": d.document_status,
                    "page_count": d.page_count,
                    "upload_timestamp": d.upload_timestamp.isoformat(),
                    "processed_timestamp": (
                        d.processed_timestamp.isoformat()
                        if d.processed_timestamp
                        else None
                    ),
                    "error_message": d.error_message,
                }
                for d in docs
            ]

    async def get_buckets_grouped_with_docs(self) -> list[dict]:
        """
        Return all active buckets, each with their documents nested.

        Used by the upload screen to render documents grouped by bucket.
        """
        async with get_session() as session:
            bucket_repo = BucketRepository(session)
            link_repo = BucketDocumentRepository(session)

            buckets = await bucket_repo.list_active()
            result = []
            for bucket in buckets:
                docs = await link_repo.list_documents_for_bucket(uuid.UUID(bucket.id))
                result.append({
                    **_bucket_model_to_dict(bucket),
                    "documents": [
                        {
                            "id": d.id,
                            "original_filename": d.original_filename,
                            "institution_type": d.institution_type,
                            "document_status": d.document_status,
                            "page_count": d.page_count,
                            "upload_timestamp": d.upload_timestamp.isoformat(),
                            "processed_timestamp": (
                                d.processed_timestamp.isoformat()
                                if d.processed_timestamp
                                else None
                            ),
                            "error_message": d.error_message,
                        }
                        for d in docs
                    ],
                })
            return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bucket_model_to_dict(model) -> dict:
    return {
        "id": model.id,
        "name": model.name,
        "description": model.description,
        "institution_type": model.institution_type,
        "status": model.status,
        "color": model.color,
        "icon": model.icon,
        "document_count": model.document_count,
        "created_at": model.created_at.isoformat(),
        "updated_at": model.updated_at.isoformat(),
    }
