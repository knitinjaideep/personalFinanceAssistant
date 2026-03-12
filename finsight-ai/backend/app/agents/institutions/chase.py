"""
Chase institution agent — Phase 2 stub.

This stub allows the supervisor routing logic to reference Chase
without breaking. A full implementation follows the same pattern
as MorganStanleyAgent.
"""

from __future__ import annotations

import structlog

from app.agents.institutions.base import BaseInstitutionAgent
from app.agents.state import IngestionState
from app.domain.entities import ExtractionResult
from app.domain.enums import ExtractionStatus, InstitutionType
from app.parsers.base import ParsedDocument

logger = structlog.get_logger(__name__)


class ChaseAgent(BaseInstitutionAgent):
    """Stub agent for Chase — Phase 2 implementation."""

    @property
    def institution_type(self) -> InstitutionType:
        return InstitutionType.CHASE

    async def can_handle(self, document: ParsedDocument) -> tuple[bool, float]:
        full_text = document.full_text[:2000].lower()
        if "jpmorgan chase" in full_text or "chase bank" in full_text or "chase.com" in full_text:
            return True, 0.9
        return False, 0.0

    async def extract(
        self,
        document: ParsedDocument,
        state: IngestionState,
    ) -> ExtractionResult:
        """Phase 2: not yet implemented."""
        import uuid
        doc_id_str = state.get("document_id", str(uuid.uuid4()))
        return ExtractionResult(
            document_id=uuid.UUID(doc_id_str),
            institution_type=self.institution_type,
            status=ExtractionStatus.FAILED,
            errors=["Chase agent not yet implemented — coming in Phase 2"],
        )
