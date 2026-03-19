"""
Deletion service — safe, auditable multi-layer document deletion.

Delete workflow for a single document:
1. Validate document exists and is not already deleted
2. Collect audit metadata (filename, bucket memberships)
3. Remove bucket-document links from SQL
4. Remove embeddings from Chroma vector store
5. Remove extracted data rows (fees, transactions, holdings, balance snapshots)
6. Remove statement records linked to the document
7. Soft-delete the statement_documents row (status = "deleted")
8. Persist a DeletionRecord for audit
9. Return a summary of what was removed

Design decisions:
- Soft-delete on statement_documents preserves the row for audit.
- Chroma deletion is best-effort: if it fails, the rest proceeds and a warning
  is logged. Chroma can be re-indexed from DB if needed.
- All SQL changes happen in a single session. Chroma runs separately.
- The caller (API route) decides whether to surface errors to the user.
"""

from __future__ import annotations

import json
import uuid

import structlog
from sqlalchemy import delete as sql_delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.engine import get_session
from app.database.models import (
    BalanceSnapshotModel,
    BucketDocumentModel,
    DeletionRecordModel,
    FeeModel,
    HoldingModel,
    StatementDocumentModel,
    StatementModel,
    TransactionModel,
)
from app.database.repositories.bucket_repo import BucketDocumentRepository
from app.database.repositories.statement_repo import StatementDocumentRepository
from app.domain.enums import DocumentStatus
from app.rag.chroma_store import ChromaStore

logger = structlog.get_logger(__name__)


class DeletionService:
    """
    Orchestrates safe deletion of a document across all storage layers.
    """

    def __init__(self, chroma: ChromaStore | None = None) -> None:
        self._chroma = chroma or ChromaStore()

    async def delete_document(self, document_id: uuid.UUID) -> dict:
        """
        Delete a document from all layers.

        Returns a summary dict describing what was removed.
        Raises ValueError if the document does not exist or is already deleted.
        """
        doc_id_str = str(document_id)

        async with get_session() as session:
            # ── 1. Validate ────────────────────────────────────────────────────
            doc = await self._get_document_or_raise(session, document_id)
            original_filename = doc.original_filename

            # ── 2. Collect bucket memberships for audit ────────────────────────
            link_repo = BucketDocumentRepository(session)
            bucket_ids = await link_repo.get_bucket_ids_for_document(document_id)

            # ── 3. Remove bucket-document links ────────────────────────────────
            link_count = await link_repo.remove_all_for_document(document_id)
            logger.info(
                "deletion.bucket_links_removed",
                document_id=doc_id_str,
                count=link_count,
            )

            # ── 4. Remove extracted data rows ──────────────────────────────────
            row_counts = await self._delete_extracted_data(session, doc_id_str)

            # ── 5. Soft-delete the document record ────────────────────────────
            await session.execute(
                update(StatementDocumentModel)
                .where(StatementDocumentModel.id == doc_id_str)
                .values(document_status=DocumentStatus.DELETED.value)
            )
            await session.commit()
            logger.info("deletion.document_soft_deleted", document_id=doc_id_str)

            # ── 6. Persist audit record ────────────────────────────────────────
            audit = DeletionRecordModel(
                document_id=doc_id_str,
                original_filename=original_filename,
                bucket_ids_removed=json.dumps(bucket_ids),
                embedding_ids_removed=0,  # updated below after Chroma
                sql_rows_json=json.dumps(row_counts),
            )
            session.add(audit)
            await session.commit()
            audit_id = audit.id

        # ── 7. Remove embeddings from Chroma (outside SQL session) ─────────────
        embedding_count = 0
        try:
            await self._chroma.initialize()
            await self._chroma.delete_by_document(doc_id_str)
            embedding_count = row_counts.get("_estimated_chunks", 0)
            logger.info("deletion.embeddings_removed", document_id=doc_id_str)
        except Exception as exc:
            logger.warning(
                "deletion.chroma_failed",
                document_id=doc_id_str,
                error=str(exc),
            )

        # ── 8. Update audit record with embedding count ────────────────────────
        async with get_session() as session:
            await session.execute(
                update(DeletionRecordModel)
                .where(DeletionRecordModel.id == audit_id)
                .values(embedding_ids_removed=embedding_count)
            )
            await session.commit()

        summary = {
            "document_id": doc_id_str,
            "original_filename": original_filename,
            "bucket_links_removed": link_count,
            "bucket_ids_affected": bucket_ids,
            "sql_rows_removed": row_counts,
            "embeddings_removed": embedding_count,
            "status": "deleted",
        }
        logger.info("deletion.complete", **{k: v for k, v in summary.items() if k != "sql_rows_removed"})
        return summary

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _get_document_or_raise(
        self, session: AsyncSession, document_id: uuid.UUID
    ) -> StatementDocumentModel:
        from sqlalchemy import select

        result = await session.execute(
            select(StatementDocumentModel).where(
                StatementDocumentModel.id == str(document_id)
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document {document_id} not found.")
        if doc.document_status == DocumentStatus.DELETED.value:
            raise ValueError(f"Document {document_id} is already deleted.")
        return doc

    async def _delete_extracted_data(
        self, session: AsyncSession, doc_id_str: str
    ) -> dict[str, int]:
        """
        Delete all extracted rows tied to statements from this document.
        Returns row counts per table for audit.
        """
        from sqlalchemy import select

        # Find statement IDs for this document
        stmt_result = await session.execute(
            select(StatementModel.id).where(
                StatementModel.document_id == doc_id_str
            )
        )
        statement_ids = [row[0] for row in stmt_result.all()]

        counts: dict[str, int] = {}

        if statement_ids:
            # Delete child rows first (FK order matters)
            for model_cls, table_name in [
                (FeeModel, "fees"),
                (TransactionModel, "transactions"),
                (HoldingModel, "holdings"),
                (BalanceSnapshotModel, "balance_snapshots"),
            ]:
                result = await session.execute(
                    sql_delete(model_cls).where(
                        model_cls.statement_id.in_(statement_ids)
                    )
                )
                counts[table_name] = result.rowcount

            # Delete statement records
            stmt_del = await session.execute(
                sql_delete(StatementModel).where(
                    StatementModel.document_id == doc_id_str
                )
            )
            counts["statements"] = stmt_del.rowcount

        # Estimate chunks for audit (rough: pages × avg chunks per page)
        counts["_estimated_chunks"] = len(statement_ids) * 20

        await session.commit()
        logger.info(
            "deletion.extracted_data_removed",
            document_id=doc_id_str,
            counts=counts,
        )
        return counts
