"""
MCP Tool Registry.

Defines the Model Context Protocol tool interface and registry.
MCP tools serve as the interaction boundary between the LangGraph agents
and external capabilities (file I/O, parsing, DB queries, RAG).

Design:
- Each MCP tool is a callable with a typed input schema (Pydantic)
- Tools are registered by name so the supervisor can look them up dynamically
- New tools can be added without changing agent code (open/closed principle)

In this MVP, MCP tools are called directly by agents/services (not via a
networked MCP server). The interface is structured to make upgrading to
a full MCP server straightforward in the future.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog

from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class ToolInput(BaseModel):
    """Base class for all MCP tool input schemas."""

    class Config:
        extra = "forbid"  # Strict: no unknown fields


class ToolOutput(BaseModel):
    """Base class for all MCP tool output schemas."""

    success: bool = True
    error: str | None = None


class MCPTool(ABC):
    """Abstract base for all MCP tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for the LLM to understand tool purpose."""
        ...

    @abstractmethod
    async def execute(self, input_data: ToolInput) -> ToolOutput:
        """Execute the tool with validated input."""
        ...

    def to_schema(self) -> dict[str, Any]:
        """Return a JSON schema description for LangGraph tool binding."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self._input_class().model_json_schema(),
        }

    def _input_class(self) -> type[ToolInput]:
        """Override to return the specific input class for schema generation."""
        return ToolInput


class ToolRegistry:
    """Registry mapping tool names to MCPTool instances."""

    def __init__(self) -> None:
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        if tool.name in self._tools:
            logger.warning("tool_registry.duplicate", name=tool.name)
        self._tools[tool.name] = tool
        logger.debug("tool_registry.registered", name=tool.name)

    def get(self, name: str) -> MCPTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, tool_name: str, input_data: dict[str, Any]) -> ToolOutput:
        tool = self.get(tool_name)
        if not tool:
            return ToolOutput(success=False, error=f"Unknown tool: {tool_name}")
        try:
            typed_input = tool._input_class()(**input_data)
            return await tool.execute(typed_input)
        except Exception as exc:
            logger.exception("tool_registry.execute_error", tool=tool_name, error=str(exc))
            return ToolOutput(success=False, error=str(exc))


# Module-level registry singleton
_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Return (or build) the global tool registry with all tools registered."""
    global _registry
    if _registry is None:
        _registry = _build_registry()
    return _registry


def _build_registry() -> ToolRegistry:
    """Instantiate and register all MCP tools."""
    from app.mcp_tools.ingest_tool import IngestDocumentTool
    from app.mcp_tools.fee_analysis_tool import FeeAnalysisTool
    from app.mcp_tools.rag_query_tool import RAGQueryTool
    from app.mcp_tools.report_tool import ReportTool

    registry = ToolRegistry()
    registry.register(IngestDocumentTool())
    registry.register(FeeAnalysisTool())
    registry.register(RAGQueryTool())
    registry.register(ReportTool())
    return registry
