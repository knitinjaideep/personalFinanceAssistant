"""
Embedding service — chunks documents and stores embeddings in Chroma.

Called from the LangGraph embed_node after successful extraction.
Also used when re-indexing existing documents.
"""

from __future__ import annotations

import asyncio

import structlog

from app.domain.enums import InstitutionType
from app.ollama.model_router import ModelRouter, get_model_router
from app.parsers.base import ParsedDocument
from app.rag.chunker import DocumentChunker, TextChunk
from app.rag.chroma_store import ChromaStore, get_chroma_store

logger = structlog.get_logger(__name__)

# Max concurrent embedding calls to Ollama (avoid overwhelming it)
_EMBED_CONCURRENCY = 4


class EmbeddingService:
    """
    Orchestrates document chunking and embedding into Chroma.
    """

    def __init__(
        self,
        chroma: ChromaStore | None = None,
        model_router: ModelRouter | None = None,
        chunker: DocumentChunker | None = None,
    ) -> None:
        self._chroma = chroma or get_chroma_store()
        self._router = model_router or get_model_router()
        self._chunker = chunker or DocumentChunker()

    async def embed_document(
        self,
        document: ParsedDocument,
        document_id: str,
        statement_id: str | None = None,
        institution_type: InstitutionType = InstitutionType.UNKNOWN,
        statement_period: str | None = None,
    ) -> int:
        """
        Chunk, embed, and store a parsed document in Chroma.

        Args:
            document: The parsed document to embed
            document_id: The document's UUID string
            statement_id: Optional linked statement UUID
            institution_type: For metadata filtering in retrieval
            statement_period: ISO period string, e.g. "2026-01-01/2026-01-31"

        Returns:
            Number of chunks embedded.
        """
        chunks = self._chunker.chunk(document)
        if not chunks:
            logger.warning("embedding.no_chunks", document_id=document_id)
            return 0

        logger.info("embedding.start", document_id=document_id, chunks=len(chunks))

        # Embed in batches with concurrency control
        semaphore = asyncio.Semaphore(_EMBED_CONCURRENCY)
        embeddings = await self._embed_chunks_concurrent(chunks, semaphore)

        # Prepare Chroma records
        ids = [f"{document_id}_{chunk.chunk_index}" for chunk in chunks]
        texts = [chunk.text for chunk in chunks]
        metadatas = [
            {
                "document_id": document_id,
                "statement_id": statement_id or "",
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number or 0,
                "section": chunk.section or "",
                "institution_type": institution_type.value,
                "statement_period": statement_period or "",
            }
            for chunk in chunks
        ]

        await self._chroma.add_chunks(
            ids=ids,
            embeddings=embeddings,
            texts=texts,
            metadatas=metadatas,
        )

        logger.info("embedding.done", document_id=document_id, chunks_stored=len(chunks))
        return len(chunks)

    async def _embed_chunks_concurrent(
        self,
        chunks: list[TextChunk],
        semaphore: asyncio.Semaphore,
    ) -> list[list[float]]:
        """Embed all chunks with concurrency limiting."""

        async def embed_one(chunk: TextChunk) -> list[float]:
            async with semaphore:
                return await self._router.embed(chunk.text)

        tasks = [embed_one(chunk) for chunk in chunks]
        return await asyncio.gather(*tasks)
