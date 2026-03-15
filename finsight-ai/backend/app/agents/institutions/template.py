"""
Institution Agent Template — copy this file to add a new institution.

Step-by-step checklist:
  1. Copy this file to `backend/app/agents/institutions/<institution_name>.py`
  2. Create `backend/app/parsers/<institution_name>/` with:
     - `__init__.py`
     - `classifier.py` — institution detection logic
     - `extractor.py` — field extraction logic
  3. Add the institution to `InstitutionType` enum in `backend/app/domain/enums.py`
  4. Register the agent in `INSTITUTION_AGENT_REGISTRY` in `backend/app/agents/supervisor.py`
  5. Run tests in `tests/test_institution_routing.py` to verify routing works

That's it. No other changes required.
"""

from __future__ import annotations

import uuid

import structlog

from app.agents.institutions.base import BaseInstitutionAgent, InstitutionCapabilities
from app.agents.state import IngestionState
from app.domain.entities import ExtractionResult
from app.domain.enums import ExtractionStatus, InstitutionType, StatementType
from app.parsers.base import ParsedDocument

logger = structlog.get_logger(__name__)


# ── Step 1: Replace "TemplateBank" with your institution name ─────────────────

class TemplateBankAgent(BaseInstitutionAgent):
    """
    Agent for TemplateBank statement extraction.

    Replace all occurrences of "TemplateBank" with your institution name.
    """

    def __init__(self) -> None:
        # Step 2: Import and instantiate your classifier
        # from app.parsers.template_bank.classifier import TemplateBankClassifier
        # self._classifier = TemplateBankClassifier()
        pass

    @property
    def institution_type(self) -> InstitutionType:
        # Step 3: Return your institution's enum value
        # return InstitutionType.TEMPLATE_BANK
        return InstitutionType.UNKNOWN  # placeholder

    @property
    def capabilities(self) -> InstitutionCapabilities:
        # Step 4: Declare what your agent can extract (be honest — stubs use False)
        return InstitutionCapabilities(
            institution_type="template_bank",    # match your InstitutionType value
            display_name="Template Bank",
            supported_statement_types=["bank"],  # list statement types you handle
            can_extract_transactions=False,       # set True once implemented
            can_extract_fees=False,
            can_extract_holdings=False,
            can_extract_balances=False,
            classification_method="regex",        # update as you implement
            extraction_method="regex+llm",
            notes="Stub — replace this note with implementation status.",
        )

    async def can_handle(self, document: ParsedDocument) -> tuple[bool, float]:
        """
        Return (True, confidence) if this document belongs to TemplateBank.

        Implement with:
        1. Regex scan of first 3 pages for institution name (fast path)
        2. LLM fallback if regex confidence < 0.5 (slow path)

        Example:
            first_pages = " ".join(p.raw_text or "" for p in document.pages[:3]).lower()
            if "template bank" in first_pages:
                return True, 0.90
            return False, 0.0
        """
        # TODO: implement institution detection
        return False, 0.0

    async def extract(
        self,
        document: ParsedDocument,
        state: IngestionState,
    ) -> ExtractionResult:
        """
        Extract structured financial data from a TemplateBank statement.

        Implementation guide:
        1. Call self._classifier.classify_statement_type(document) → StatementType
        2. Call TemplateBankExtractor(document, statement_type).extract()
        3. Return ExtractionResult with the Statement and confidence scores

        See morgan_stanley.py for a full implementation example.
        """
        # TODO: implement extraction
        return ExtractionResult(
            document_id=uuid.UUID(state["document_id"]),
            institution_type=self.institution_type,
            status=ExtractionStatus.FAILED,
            errors=["TemplateBankAgent.extract() is not implemented yet."],
        )
