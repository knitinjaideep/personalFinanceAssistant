"""
Morgan Stanley statement classifier.

Determines:
1. Whether the document is indeed a Morgan Stanley statement
2. The specific statement type (brokerage, advisory, retirement, etc.)

Strategy:
- First uses fast regex/keyword matching on the parsed text
- Falls back to LLM classification if the text-based approach is uncertain
"""

from __future__ import annotations

import json
import re

import structlog

from app.domain.enums import InstitutionType, StatementType
from app.ollama.client import OllamaClient, get_ollama_client
from app.ollama.model_router import ModelRouter, get_model_router, TaskType
from app.parsers.base import ParsedDocument

logger = structlog.get_logger(__name__)


# Keywords that strongly indicate Morgan Stanley origin
_MS_INDICATORS = [
    r"morgan\s+stanley",
    r"morganstanley\.com",
    r"MS\s+Smith\s+Barney",
    r"Wealth\s+Management",  # Combined with Morgan Stanley context
]

_MS_PATTERN = re.compile("|".join(_MS_INDICATORS), re.IGNORECASE)

# Statement type keyword mapping
_TYPE_PATTERNS: dict[StatementType, list[str]] = {
    StatementType.BROKERAGE: [
        r"brokerage\s+account",
        r"individual\s+account",
        r"taxable\s+account",
        r"portfolio\s+summary",
    ],
    StatementType.ADVISORY: [
        r"advisory\s+(fee|account|service)",
        r"managed\s+account",
        r"investment\s+advisory",
        r"discretionary",
    ],
    StatementType.RETIREMENT: [
        r"traditional\s+ira",
        r"roth\s+ira",
        r"rollover\s+ira",
        r"401\s*\(?k\)?",
        r"retirement\s+account",
    ],
}


class MorganStanleyClassifier:
    """
    Classifies Morgan Stanley documents by type.

    Uses a two-step approach:
    1. Fast regex matching (no LLM cost)
    2. LLM fallback if confidence is below threshold
    """

    CONFIDENCE_THRESHOLD = 0.7

    def __init__(self, model_router: ModelRouter | None = None) -> None:
        self._router = model_router or get_model_router()

    async def is_morgan_stanley(self, document: ParsedDocument) -> tuple[bool, float]:
        """
        Check if the document is from Morgan Stanley.

        Returns:
            Tuple of (is_morgan_stanley, confidence)
        """
        # Sample first 3 pages for header/footer matching
        sample_text = "\n".join(
            p.raw_text for p in document.pages[:3] if p.raw_text
        )

        matches = _MS_PATTERN.findall(sample_text)
        if len(matches) >= 2:
            return True, 0.95
        if len(matches) == 1:
            return True, 0.75

        return False, 0.1

    async def classify_statement_type(
        self, document: ParsedDocument
    ) -> tuple[StatementType, float]:
        """
        Determine the type of Morgan Stanley statement.

        Returns:
            Tuple of (StatementType, confidence)
        """
        full_text = document.full_text[:3000]  # First 3000 chars for classification

        # Try regex-based classification first
        best_type = StatementType.UNKNOWN
        best_score = 0

        for stmt_type, patterns in _TYPE_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, full_text, re.IGNORECASE)
                score += len(matches)
            if score > best_score:
                best_score = score
                best_type = stmt_type

        if best_score >= 2:
            return best_type, 0.85
        if best_score == 1:
            return best_type, 0.65

        # Fall back to LLM classification
        logger.info("classifier.llm_fallback", reason="low_regex_score")
        return await self._llm_classify(full_text)

    async def _llm_classify(
        self, text_sample: str
    ) -> tuple[StatementType, float]:
        """Use the LLM to classify statement type from a text sample."""
        system = (
            "You are a financial document classifier. "
            "Analyze the provided text and respond with JSON only."
        )
        prompt = f"""Classify this financial statement text.

Text sample:
{text_sample[:2000]}

Respond with this exact JSON structure:
{{
  "statement_type": "<one of: brokerage, bank, credit_card, retirement, advisory, unknown>",
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<brief explanation>"
}}"""

        try:
            response = await self._router.generate(
                task=TaskType.CLASSIFICATION,
                prompt=prompt,
                system=system,
                format="json",
            )
            data = json.loads(response.strip())
            stmt_type_str = data.get("statement_type", "unknown")
            confidence = float(data.get("confidence", 0.5))

            try:
                stmt_type = StatementType(stmt_type_str)
            except ValueError:
                stmt_type = StatementType.UNKNOWN

            logger.info(
                "classifier.llm_result",
                type=stmt_type.value,
                confidence=confidence,
                reasoning=data.get("reasoning", ""),
            )
            return stmt_type, confidence

        except Exception as exc:
            logger.warning("classifier.llm_failed", error=str(exc))
            return StatementType.UNKNOWN, 0.1
