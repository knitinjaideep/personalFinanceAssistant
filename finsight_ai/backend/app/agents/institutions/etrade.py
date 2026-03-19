"""
E*TRADE institution agent — full implementation.

Handles individual brokerage accounts.

Wires together:
- ETradeClassifier (institution detection)
- ETradeExtractor (structured data extraction: holdings, trades, balances, fees)
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
from app.parsers.etrade.classifier import ETradeClassifier
from app.parsers.etrade.extractor import ETradeExtractor

logger = structlog.get_logger(__name__)


class ETradeAgent(BaseInstitutionAgent):
    """
    Agent responsible for all E*TRADE statement processing.

    Supports individual brokerage accounts with full holdings,
    transaction, and fee extraction.
    """

    def __init__(self) -> None:
        self._classifier = ETradeClassifier()
        self._extractor = ETradeExtractor()

    @property
    def institution_type(self) -> InstitutionType:
        return InstitutionType.ETRADE

    @property
    def bucket_type(self) -> BucketType:
        return BucketType.INVESTMENTS

    @property
    def capabilities(self) -> InstitutionCapabilities:
        return InstitutionCapabilities(
            institution_type=InstitutionType.ETRADE.value,
            display_name="E*TRADE",
            supported_statement_types=["brokerage"],
            can_extract_transactions=True,
            can_extract_fees=True,
            can_extract_holdings=True,
            can_extract_balances=True,
            classification_method="regex",
            extraction_method="regex+table",
            notes="Full implementation. Handles individual brokerage accounts.",
        )

    async def can_handle(self, document: ParsedDocument) -> tuple[bool, float]:
        """Check if this document is from E*TRADE."""
        return await self._classifier.is_etrade(document)

    async def extract(
        self,
        document: ParsedDocument,
        state: IngestionState,
    ) -> ExtractionResult:
        """Full extraction pipeline for an E*TRADE document."""
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
