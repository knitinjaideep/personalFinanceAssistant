"""MCP tool: ingest_document — triggers document ingestion from a file path."""

from __future__ import annotations

from pydantic import Field

from app.mcp_tools.registry import MCPTool, ToolInput, ToolOutput


class IngestDocumentInput(ToolInput):
    file_path: str = Field(description="Absolute path to the file to ingest")
    original_filename: str = Field(description="Original user-facing filename")
    document_id: str = Field(description="Pre-assigned document UUID string")


class IngestDocumentOutput(ToolOutput):
    document_id: str = ""
    status: str = ""


class IngestDocumentTool(MCPTool):
    @property
    def name(self) -> str:
        return "ingest_document"

    @property
    def description(self) -> str:
        return (
            "Trigger the document ingestion pipeline for an uploaded financial statement. "
            "Parses, classifies, extracts, normalizes, and stores the document."
        )

    def _input_class(self) -> type[ToolInput]:
        return IngestDocumentInput

    async def execute(self, input_data: IngestDocumentInput) -> IngestDocumentOutput:  # type: ignore
        from app.agents.supervisor import ingestion_graph
        from app.agents.state import IngestionState

        state: IngestionState = {
            "document_id": input_data.document_id,
            "file_path": input_data.file_path,
            "original_filename": input_data.original_filename,
            "errors": [],
            "warnings": [],
        }
        final_state = await ingestion_graph.ainvoke(state)
        errors = final_state.get("errors", [])
        return IngestDocumentOutput(
            document_id=input_data.document_id,
            status="failed" if errors else "success",
            success=not bool(errors),
            error="; ".join(errors) if errors else None,
        )
