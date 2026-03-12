"""
Chat service — RAG-powered financial question answering.

Flow:
1. Receive a user question
2. Use HybridRetriever to fetch relevant document chunks + SQL data
3. Build a RAG prompt with context + conversation history
4. Generate a response via Ollama chat model
5. Return the answer with source attribution
"""

from __future__ import annotations

import time

import structlog

from app.domain.entities import ChatRequest, ChatResponse, EmbeddingRecord
from app.domain.enums import InstitutionType
from app.ollama.model_router import ModelRouter, TaskType, get_model_router
from app.rag.prompt_builder import SYSTEM_PROMPT, build_chat_prompt
from app.rag.retriever import HybridRetriever, RetrievalResult

logger = structlog.get_logger(__name__)


class ChatService:
    """
    Implements the RAG chat pipeline for financial question answering.
    """

    def __init__(self, model_router: ModelRouter | None = None) -> None:
        self._router = model_router or get_model_router()
        self._retriever = HybridRetriever()

    async def answer(self, request: ChatRequest) -> ChatResponse:
        """
        Answer a financial question using RAG.

        Args:
            request: ChatRequest with question and conversation history

        Returns:
            ChatResponse with the generated answer and source chunks.
        """
        start_time = time.monotonic()
        logger.info("chat.start", question_len=len(request.question))

        # Retrieve relevant context
        retrieval: RetrievalResult = await self._retriever.retrieve(
            question=request.question,
        )

        # Build prompt
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.conversation_history
        ]
        prompt = build_chat_prompt(
            question=request.question,
            context=retrieval.context_text,
            conversation_history=history,
        )

        # Generate answer
        if not retrieval.context_text.strip():
            # No relevant context found
            answer = (
                "I don't have relevant financial data to answer that question. "
                "Please upload financial statements first, or try rephrasing your question."
            )
        else:
            try:
                answer = await self._router.generate(
                    task=TaskType.CHAT,
                    prompt=prompt,
                    system=SYSTEM_PROMPT,
                )
            except Exception as exc:
                logger.error("chat.generation_error", error=str(exc))
                answer = f"I encountered an error generating a response: {exc}"

        processing_time = time.monotonic() - start_time
        logger.info("chat.done", processing_time=round(processing_time, 2))

        # Build source records from vector chunks
        sources = self._build_sources(retrieval.vector_chunks)

        return ChatResponse(
            answer=answer,
            sources=sources,
            sql_query_used=retrieval.sql_query,
            processing_time_seconds=round(processing_time, 2),
        )

    def _build_sources(self, chunks: list[dict]) -> list[EmbeddingRecord]:
        """Convert raw Chroma results into EmbeddingRecord domain entities."""
        import uuid as _uuid
        sources: list[EmbeddingRecord] = []
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            try:
                doc_id = _uuid.UUID(meta.get("document_id", str(_uuid.uuid4())))
                stmt_id_str = meta.get("statement_id", "")
                stmt_id = _uuid.UUID(stmt_id_str) if stmt_id_str else None

                inst_str = meta.get("institution_type", "unknown")
                try:
                    inst_type = InstitutionType(inst_str)
                except ValueError:
                    inst_type = InstitutionType.UNKNOWN

                sources.append(
                    EmbeddingRecord(
                        id=chunk["id"],
                        document_id=doc_id,
                        statement_id=stmt_id,
                        chunk_index=meta.get("chunk_index", 0),
                        chunk_text=chunk.get("text", ""),
                        page_number=meta.get("page_number"),
                        section=meta.get("section") or None,
                        institution_type=inst_type,
                        statement_period=meta.get("statement_period") or None,
                    )
                )
            except Exception:
                continue
        return sources
