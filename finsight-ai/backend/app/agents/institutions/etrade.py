"""
E*TRADE institution agent — Phase 2 stub.
"""

from __future__ import annotations

from app.agents.institutions.base import BaseInstitutionAgent
from app.agents.state import IngestionState
from app.domain.entities import ExtractionResult
from app.domain.enums import ExtractionStatus, InstitutionType
from app.parsers.base import ParsedDocument


class ETradeAgent(BaseInstitutionAgent):
    """Stub agent for E*TRADE — Phase 2 implementation."""

    @property
    def institution_type(self) -> InstitutionType:
        return InstitutionType.ETRADE

    async def can_handle(self, document: ParsedDocument) -> tuple[bool, float]:
        full_text = document.full_text[:2000].lower()
        if "e*trade" in full_text or "etrade" in full_text or "etrade.com" in full_text:
            return True, 0.9
        return False, 0.0

    async def extract(
        self,
        document: ParsedDocument,
        state: IngestionState,
    ) -> ExtractionResult:
        import uuid
        doc_id_str = state.get("document_id", str(uuid.uuid4()))
        return ExtractionResult(
            document_id=uuid.UUID(doc_id_str),
            institution_type=self.institution_type,
            status=ExtractionStatus.FAILED,
            errors=["E*TRADE agent not yet implemented — coming in Phase 2"],
        )
