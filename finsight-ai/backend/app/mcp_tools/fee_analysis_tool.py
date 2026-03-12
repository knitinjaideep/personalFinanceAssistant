"""MCP tool: analyze_fees — aggregates fee data over a date range."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.mcp_tools.registry import MCPTool, ToolInput, ToolOutput


class FeeAnalysisInput(ToolInput):
    start_date: date = Field(description="Start of the analysis period (ISO date)")
    end_date: date = Field(description="End of the analysis period (ISO date)")
    institution_type: str | None = Field(
        default=None, description="Filter by institution type (e.g., 'morgan_stanley')"
    )


class FeeAnalysisOutput(ToolOutput):
    summaries: list[dict] = Field(default_factory=list)
    total_across_all: str = "0"


class FeeAnalysisTool(MCPTool):
    @property
    def name(self) -> str:
        return "analyze_fees"

    @property
    def description(self) -> str:
        return (
            "Analyze and aggregate fee data across institutions for a given date range. "
            "Returns per-institution, per-account fee totals and categories."
        )

    def _input_class(self) -> type[ToolInput]:
        return FeeAnalysisInput

    async def execute(self, input_data: FeeAnalysisInput) -> FeeAnalysisOutput:  # type: ignore
        from app.database.engine import get_session
        from app.services.analytics_service import AnalyticsService

        async with get_session() as session:
            service = AnalyticsService(session)
            summaries = await service.get_fee_summary(
                start_date=input_data.start_date,
                end_date=input_data.end_date,
                institution_type=input_data.institution_type,
            )

        total = sum(s.total_fees for s in summaries)
        return FeeAnalysisOutput(
            summaries=[
                {
                    "institution": s.institution,
                    "account": s.account,
                    "total_fees": str(s.total_fees),
                    "fee_count": s.fee_count,
                    "categories": {k: str(v) for k, v in s.categories.items()},
                }
                for s in summaries
            ],
            total_across_all=str(total),
        )
