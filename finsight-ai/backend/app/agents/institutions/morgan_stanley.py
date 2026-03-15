"""
Morgan Stanley institution agent.

Wires together:
- MorganStanleyClassifier (statement type detection)
- MorganStanleyExtractor (structured data extraction)
- ExtractionResult assembly with confidence reporting
"""

from __future__ import annotations

import time
import uuid

import structlog

from app.agents.institutions.base import BaseInstitutionAgent, InstitutionCapabilities
from app.agents.state import IngestionState
from app.domain.entities import ExtractionResult
from app.domain.enums import ExtractionStatus, InstitutionType, StatementType
from app.parsers.base import ParsedDocument
from app.parsers.morgan_stanley.classifier import MorganStanleyClassifier
from app.parsers.morgan_stanley.extractor import MorganStanleyExtractor

logger = structlog.get_logger(__name__)


class MorganStanleyAgent(BaseInstitutionAgent):
    """
    Agent responsible for all Morgan Stanley statement processing.

    Orchestrates classification → extraction → confidence reporting.
    """

    def __init__(self) -> None:
        self._classifier = MorganStanleyClassifier()
        self._extractor = MorganStanleyExtractor()

    @property
    def institution_type(self) -> InstitutionType:
        return InstitutionType.MORGAN_STANLEY

    @property
    def capabilities(self) -> InstitutionCapabilities:
        return InstitutionCapabilities(
            institution_type=InstitutionType.MORGAN_STANLEY.value,
            display_name="Morgan Stanley",
            supported_statement_types=["brokerage", "advisory", "retirement"],
            can_extract_transactions=True,
            can_extract_fees=True,
            can_extract_holdings=True,
            can_extract_balances=True,
            classification_method="regex+llm",
            extraction_method="regex+llm",
            notes="Full implementation. Handles brokerage, advisory, and retirement accounts.",
        )

    async def can_handle(self, document: ParsedDocument) -> tuple[bool, float]:
        """Check if this document is from Morgan Stanley."""
        return await self._classifier.is_morgan_stanley(document)

    async def extract(
        self,
        document: ParsedDocument,
        state: IngestionState,
    ) -> ExtractionResult:
        """Full extraction pipeline for a Morgan Stanley document."""
        start_time = time.monotonic()
        doc_id_str = state.get("document_id", str(uuid.uuid4()))

        try:
            doc_uuid = uuid.UUID(doc_id_str) if isinstance(doc_id_str, str) else doc_id_str
        except ValueError:
            doc_uuid = uuid.uuid4()

        # Step 1: Classify statement type
        statement_type, type_confidence = await self._classifier.classify_statement_type(document)
        logger.info(
            "morgan_stanley.classify",
            type=statement_type.value,
            confidence=type_confidence,
        )

        if type_confidence < 0.3:
            logger.warning(
                "morgan_stanley.low_classification_confidence",
                confidence=type_confidence,
            )

        # Step 2: Extract structured data
        statement = await self._extractor.extract(document, statement_type)

        # Step 3: Set correct document_id from state
        statement.document_id = doc_uuid

        # Step 4: Compute overall confidence from field confidences
        # (the extractor populates field_confidences internally)
        overall_confidence = statement.overall_confidence

        processing_time = time.monotonic() - start_time

        return ExtractionResult(
            document_id=doc_uuid,
            institution_type=self.institution_type,
            statement=statement,
            status=statement.extraction_status,
            overall_confidence=overall_confidence,
            field_confidences=[],  # Populated by extractor ctx — passed via statement
            missing_fields=statement.extraction_notes,
            warnings=statement.extraction_notes,
            errors=[],
            processing_time_seconds=round(processing_time, 2),
        )
