"""MCP tool: generate_report — produce a structured financial summary."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from app.mcp_tools.registry import MCPTool, ToolInput, ToolOutput


class ReportInput(ToolInput):
    period_start: date = Field(description="Start date of the report period")
    period_end: date = Field(description="End date of the report period")
    institution_type: str | None = Field(default=None)


class ReportOutput(ToolOutput):
    report_text: str = ""
    fee_total: str = "0"
    institution_count: int = 0


class ReportTool(MCPTool):
    @property
    def name(self) -> str:
        return "generate_report"

    @property
    def description(self) -> str:
        return (
            "Generate a structured financial summary report for a given period, "
            "including total fees, deposits, withdrawals, and account balances."
        )

    def _input_class(self) -> type[ToolInput]:
        return ReportInput

    async def execute(self, input_data: ReportInput) -> ReportOutput:  # type: ignore
        from app.database.engine import get_session
        from app.services.analytics_service import AnalyticsService
        from app.services.chat_service import ChatService
        from app.domain.entities import ChatRequest

        async with get_session() as session:
            analytics = AnalyticsService(session)
            fee_summaries = await analytics.get_fee_summary(
                start_date=input_data.period_start,
                end_date=input_data.period_end,
                institution_type=input_data.institution_type,
            )

        total_fees = sum(s.total_fees for s in fee_summaries)
        institution_count = len({s.institution for s in fee_summaries})

        # Use RAG to generate narrative summary
        period_str = f"{input_data.period_start} to {input_data.period_end}"
        chat = ChatService()
        chat_response = await chat.answer(
            ChatRequest(
                question=(
                    f"Summarize deposits, withdrawals, fees, and balances "
                    f"for the period {period_str}."
                )
            )
        )

        return ReportOutput(
            report_text=chat_response.answer,
            fee_total=str(total_fees),
            institution_count=institution_count,
        )
