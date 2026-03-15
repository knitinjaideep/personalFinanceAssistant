"""
Base institution agent abstract class.

Each institution agent (Morgan Stanley, Chase, E*TRADE) extends this ABC.
The supervisor routes to agents via institution_type; agents are responsible
for classification, extraction, and normalization within their domain.

Adding a new institution:
1. Create a new module in app/agents/institutions/
2. Subclass BaseInstitutionAgent
3. Register in INSTITUTION_AGENT_REGISTRY in supervisor.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import structlog
from pydantic import BaseModel

from app.agents.state import IngestionState
from app.domain.entities import ExtractionResult
from app.domain.enums import ExtractionStatus, InstitutionType, StatementType
from app.parsers.base import ParsedDocument

logger = structlog.get_logger(__name__)


class InstitutionCapabilities(BaseModel):
    """
    Describes what an institution agent can extract.

    Used for:
    - Displaying accurate trace event info during ingestion
    - Routing to correct tool with capability awareness
    - Future: UI institution-capability matrix display
    """

    institution_type: str
    display_name: str
    supported_statement_types: list[str]  # e.g. ["brokerage", "advisory"]
    can_extract_transactions: bool = False
    can_extract_fees: bool = False
    can_extract_holdings: bool = False
    can_extract_balances: bool = False
    classification_method: str = "regex"      # "regex" | "regex+llm" | "llm"
    extraction_method: str = "regex+llm"      # "regex" | "regex+llm" | "llm"
    notes: str = ""


class BaseInstitutionAgent(ABC):
    """
    Abstract base for all institution-specific agents.

    An institution agent is responsible for:
    - Confirming the document belongs to its institution
    - Classifying the statement type
    - Extracting structured financial data
    - Returning an ExtractionResult with confidence scores
    """

    @property
    @abstractmethod
    def institution_type(self) -> InstitutionType:
        """The institution this agent handles."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> InstitutionCapabilities:
        """Describe what this agent can extract."""
        ...

    @abstractmethod
    async def can_handle(self, document: ParsedDocument) -> tuple[bool, float]:
        """
        Determine whether this agent can process the document.

        Returns:
            (can_handle, confidence): confidence in range [0.0, 1.0]
        """
        ...

    @abstractmethod
    async def extract(
        self,
        document: ParsedDocument,
        state: IngestionState,
    ) -> ExtractionResult:
        """
        Perform full extraction from a parsed document.

        Args:
            document: The parsed document
            state: Current pipeline state (read-only in most cases)

        Returns:
            ExtractionResult containing the extracted Statement and metadata.
        """
        ...

    async def run(self, state: IngestionState) -> IngestionState:
        """
        Execute the agent as a LangGraph node.

        Called by the supervisor's routing logic. Updates state
        with the extraction result (or error).
        """
        parsed_document = state.get("parsed_document")
        if parsed_document is None:
            state.setdefault("errors", []).append(
                f"{self.institution_type.value}: No parsed document in state"
            )
            return state

        try:
            logger.info(
                "agent.run.start",
                institution=self.institution_type.value,
                document_id=state.get("document_id"),
            )
            result = await self.extract(parsed_document, state)
            state["extraction_result"] = result
            state["document_status"] = (
                "processed" if result.status == ExtractionStatus.SUCCESS else "failed"
            )
            logger.info(
                "agent.run.done",
                institution=self.institution_type.value,
                status=result.status.value,
                confidence=result.overall_confidence,
            )
        except Exception as exc:
            error_msg = f"{self.institution_type.value} agent failed: {exc}"
            logger.exception("agent.run.error", institution=self.institution_type.value, error=str(exc))
            state.setdefault("errors", []).append(error_msg)
            state["extraction_result"] = ExtractionResult(
                document_id=state.get("document_id", ""),  # type: ignore
                institution_type=self.institution_type,
                status=ExtractionStatus.FAILED,
                errors=[error_msg],
            )
            state["document_status"] = "failed"

        return state
