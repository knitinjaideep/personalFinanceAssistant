"""
Chroma vector store wrapper.

Provides a clean async-compatible interface over chromadb's synchronous API.
All Chroma operations are run in a thread pool via asyncio.to_thread() to
avoid blocking the event loop.

Collection schema (per document chunk):
- id: "{document_id}_{chunk_index}"
- embedding: float list from nomic-embed-text
- document: chunk text
- metadata:
    document_id: str
    statement_id: str | None
    chunk_index: int
    page_number: int | None
    section: str | None
    institution_type: str
    statement_period: str | None   # e.g., "2026-01-01/2026-01-31"
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.config import settings
from app.domain.errors import VectorStoreError

logger = structlog.get_logger(__name__)


class ChromaStore:
    """
    Async wrapper over a persistent Chroma collection.

    Thread safety: chromadb's SQLite backend is not thread-safe.
    We serialize access via asyncio.to_thread() which runs each call
    in the thread pool executor (one at a time per event loop).
    """

    def __init__(self) -> None:
        self._client = None
        self._collection = None

    async def initialize(self) -> None:
        """Connect to or create the Chroma persistent store."""
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        persist_dir = str(settings.get_chroma_dir())
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        # get_or_create_collection is idempotent
        self._collection = self._client.get_or_create_collection(
            name=settings.chroma.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "chroma.initialized",
            collection=settings.chroma.collection_name,
            persist_dir=persist_dir,
        )

    def _ensure_ready(self) -> None:
        if self._collection is None:
            raise VectorStoreError(
                "ChromaStore not initialized. Call await chroma.initialize() first."
            )

    async def add_chunks(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Add embedded chunks to the collection."""
        self._ensure_ready()

        def _add() -> None:
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )

        try:
            await asyncio.to_thread(_add)
            logger.debug("chroma.add_chunks", count=len(ids))
        except Exception as exc:
            raise VectorStoreError(f"Failed to add chunks to Chroma: {exc}") from exc

    async def query(
        self,
        embedding: list[float],
        n_results: int | None = None,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search over the collection.

        Args:
            embedding: Query embedding vector
            n_results: Number of results to return
            where: Optional Chroma metadata filter (e.g., {"institution_type": "morgan_stanley"})

        Returns:
            List of result dicts with keys: id, text, metadata, distance
        """
        self._ensure_ready()
        k = n_results or settings.chroma.retrieval_top_k

        def _query() -> Any:
            kwargs: dict[str, Any] = {
                "query_embeddings": [embedding],
                "n_results": k,
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where
            return self._collection.query(**kwargs)

        try:
            raw = await asyncio.to_thread(_query)
        except Exception as exc:
            raise VectorStoreError(f"Chroma query failed: {exc}") from exc

        results: list[dict[str, Any]] = []
        if raw and raw.get("ids"):
            ids = raw["ids"][0]
            docs = raw["documents"][0]
            metas = raw["metadatas"][0]
            dists = raw["distances"][0]
            for i, chunk_id in enumerate(ids):
                results.append(
                    {
                        "id": chunk_id,
                        "text": docs[i],
                        "metadata": metas[i],
                        "distance": dists[i],
                    }
                )
        return results

    async def delete_by_document(self, document_id: str) -> None:
        """Remove all chunks associated with a document (for re-processing)."""
        self._ensure_ready()

        def _delete() -> None:
            self._collection.delete(where={"document_id": document_id})

        await asyncio.to_thread(_delete)
        logger.info("chroma.delete_by_document", document_id=document_id)

    async def count(self) -> int:
        """Return total number of chunks in the collection."""
        self._ensure_ready()
        result = await asyncio.to_thread(self._collection.count)
        return result


# Module-level singleton (set during FastAPI lifespan startup)
_chroma_instance: ChromaStore | None = None


def get_chroma_store() -> ChromaStore:
    """Return the initialized ChromaStore singleton."""
    global _chroma_instance
    if _chroma_instance is None:
        _chroma_instance = ChromaStore()
    return _chroma_instance
