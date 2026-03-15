"""
Discover institution agent — full implementation.

Handles Discover credit card statements (it, More, Miles, Cashback, etc.).

Wires together:
- DiscoverClassifier (institution detection + account type)
- DiscoverExtractor (structured data extraction: transactions, balances, fees)
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
from app.parsers.discover.classifier import DiscoverClassifier
from app.parsers.discover.extractor import DiscoverExtractor

logger = structlog.get_logger(__name__)


class DiscoverAgent(BaseInstitutionAgent):
    """
    Agent responsible for all Discover statement processing.

    Supports credit card statements with full transaction extraction
    and merchant categorization.
    """

    def __init__(self) -> None:
        self._classifier = DiscoverClassifier()
        self._extractor = DiscoverExtractor()

    @property
    def institution_type(self) -> InstitutionType:
        return InstitutionType.DISCOVER

    @property
    def bucket_type(self) -> BucketType:
        return BucketType.BANKING

    @property
    def capabilities(self) -> InstitutionCapabilities:
        return InstitutionCapabilities(
            institution_type=InstitutionType.DISCOVER.value,
            display_name="Discover",
            supported_statement_types=["credit_card"],
            can_extract_transactions=True,
            can_extract_fees=True,
            can_extract_holdings=False,
            can_extract_balances=True,
            classification_method="regex",
            extraction_method="regex+table",
            notes=(
                "Full implementation. Handles all Discover credit card variants. "
                "Transactions are categorized using deterministic merchant rules."
            ),
        )

    async def can_handle(self, document: ParsedDocument) -> tuple[bool, float]:
        """Check if this document is from Discover."""
        return await self._classifier.is_discover(document)

    async def extract(
        self,
        document: ParsedDocument,
        state: IngestionState,
    ) -> ExtractionResult:
        """Full extraction pipeline for a Discover document."""
        start_time = time.monotonic()
        doc_id_str = state.get("document_id", str(uuid.uuid4()))
        try:
            doc_uuid = uuid.UUID(doc_id_str) if isinstance(doc_id_str, str) else doc_id_str
        except ValueError:
            doc_uuid = uuid.uuid4()

        account_type, statement_type, _ = self._classifier.classify_account_type(document)

        statement = await self._extractor.extract(document, account_type, statement_type)
        statement.document_id = doc_uuid

        processing_time = time.monotonic() - start_time

        return ExtractionResult(
            document_id=doc_uuid,
            institution_type=self.institution_type,
            statement=statement,
            status=statement.extraction_status,
            overall_confidence=statement.overall_confidence,
            field_confidences=[],
            missing_fields=statement.extraction_notes,
            warnings=statement.extraction_notes,
            errors=[],
            processing_time_seconds=round(processing_time, 2),
        )
