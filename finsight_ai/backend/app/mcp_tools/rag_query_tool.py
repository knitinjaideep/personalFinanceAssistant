"""MCP tool: rag_query — answer a financial question using RAG."""

from __future__ import annotations

from pydantic import Field

from app.mcp_tools.registry import MCPTool, ToolInput, ToolOutput


class RAGQueryInput(ToolInput):
    question: str = Field(description="The natural language financial question to answer")
    institution_filter: str | None = Field(
        default=None,
        description="Optional institution type to restrict search (e.g., 'morgan_stanley')",
    )


class RAGQueryOutput(ToolOutput):
    answer: str = ""
    source_chunk_ids: list[str] = Field(default_factory=list)
    sql_query_used: str | None = None


class RAGQueryTool(MCPTool):
    @property
    def name(self) -> str:
        return "rag_query"

    @property
    def description(self) -> str:
        return (
            "Answer a financial question by retrieving relevant document excerpts "
            "from uploaded statements using semantic search and SQL, then generating "
            "an answer with the local LLM."
        )

    def _input_class(self) -> type[ToolInput]:
        return RAGQueryInput

    async def execute(self, input_data: RAGQueryInput) -> RAGQueryOutput:  # type: ignore
        from app.domain.entities import ChatRequest
        from app.services.chat_service import ChatService

        service = ChatService()
        request = ChatRequest(question=input_data.question)
        response = await service.answer(request)

        return RAGQueryOutput(
            answer=response.answer,
            source_chunk_ids=[s.id for s in response.sources],
            sql_query_used=response.sql_query_used,
        )
