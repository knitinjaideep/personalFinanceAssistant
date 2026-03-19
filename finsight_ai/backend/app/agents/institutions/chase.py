"""
Chase institution agent — full implementation.

Handles:
- Chase checking accounts
- Chase credit cards (Sapphire, Freedom, United, Southwest, Ink, etc.)

Wires together:
- ChaseClassifier (institution detection + account type)
- ChaseExtractor (structured data extraction)
- ExtractionResult assembly with confidence reporting
"""

from __future__ import annotations

import time
import uuid

import structlog

from app.agents.institutions.base import BaseInstitutionAgent, InstitutionCapabilities
from app.agents.state import IngestionState
from app.domain.entities import ExtractionResult
from app.domain.enums import BucketType, ExtractionStatus, InstitutionType
from app.parsers.base import ParsedDocument
from app.parsers.chase.classifier import ChaseClassifier
from app.parsers.chase.extractor import ChaseExtractor

logger = structlog.get_logger(__name__)


class ChaseAgent(BaseInstitutionAgent):
    """
    Agent responsible for all Chase statement processing.

    Supports checking accounts and credit cards.
    """

    def __init__(self) -> None:
        self._classifier = ChaseClassifier()
        self._extractor = ChaseExtractor()

    @property
    def institution_type(self) -> InstitutionType:
        return InstitutionType.CHASE

    @property
    def bucket_type(self) -> BucketType:
        return BucketType.BANKING

    @property
    def capabilities(self) -> InstitutionCapabilities:
        return InstitutionCapabilities(
            institution_type=InstitutionType.CHASE.value,
            display_name="Chase",
            supported_statement_types=["bank", "credit_card"],
            can_extract_transactions=True,
            can_extract_fees=True,
            can_extract_holdings=False,
            can_extract_balances=True,
            classification_method="regex",
            extraction_method="regex+table",
            notes=(
                "Full implementation. Handles checking accounts and credit cards. "
                "Transactions are categorized using deterministic merchant rules."
            ),
        )

    async def can_handle(self, document: ParsedDocument) -> tuple[bool, float]:
        """Check if this document is from Chase."""
        return await self._classifier.is_chase(document)

    async def extract(
        self,
        document: ParsedDocument,
        state: IngestionState,
    ) -> ExtractionResult:
        """Full extraction pipeline for a Chase document."""
        start_time = time.monotonic()
        doc_id_str = state.get("document_id", str(uuid.uuid4()))
        try:
            doc_uuid = uuid.UUID(doc_id_str) if isinstance(doc_id_str, str) else doc_id_str
        except ValueError:
            doc_uuid = uuid.uuid4()

        # Step 1: Classify account type (checking vs credit card)
        account_type, statement_type, type_confidence = self._classifier.classify_account_type(
            document
        )
        logger.info(
            "chase_agent.classify",
            account_type=account_type.value,
            statement_type=statement_type.value,
            confidence=type_confidence,
        )

        # Step 2: Extract structured data
        statement = await self._extractor.extract(document, account_type, statement_type)
        statement.document_id = doc_uuid

        overall_confidence = statement.overall_confidence
        processing_time = time.monotonic() - start_time

        return ExtractionResult(
            document_id=doc_uuid,
            institution_type=self.institution_type,
            statement=statement,
            status=statement.extraction_status,
            overall_confidence=overall_confidence,
            field_confidences=[],
            missing_fields=statement.extraction_notes,
            warnings=statement.extraction_notes,
            errors=[],
            processing_time_seconds=round(processing_time, 2),
        )
