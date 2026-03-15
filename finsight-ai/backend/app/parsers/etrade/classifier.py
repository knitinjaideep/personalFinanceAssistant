"""
E*TRADE statement classifier.

Determines:
1. Whether the document is from E*TRADE
2. Account type: individual brokerage (always for E*TRADE in this implementation)
"""

from __future__ import annotations

import re

import structlog

from app.domain.enums import AccountType, StatementType
from app.parsers.base import ParsedDocument

logger = structlog.get_logger(__name__)

_ETRADE_PATTERNS = re.compile(
    r"e\*trade|etrade\.com|etrade\s+securities|"
    r"e\*trade\s+financial|morgan\s+stanley.*e\*trade|"
    r"e\*trade\s+from\s+morgan\s+stanley",
    re.IGNORECASE,
)

_BROKERAGE_PATTERNS = re.compile(
    r"brokerage\s+account|individual\s+account|"
    r"portfolio\s+summary|securities\s+held|"
    r"equity|option|market\s+value",
    re.IGNORECASE,
)


class ETradeClassifier:
    """Classifies E*TRADE documents."""

    async def is_etrade(self, document: ParsedDocument) -> tuple[bool, float]:
        """Return (is_etrade, confidence)."""
        sample = "\n".join(p.raw_text for p in document.pages[:3] if p.raw_text)
        matches = _ETRADE_PATTERNS.findall(sample)
        if len(matches) >= 2:
            return True, 0.95
        if len(matches) == 1:
            return True, 0.80
        return False, 0.05

    def classify_account_type(
        self, document: ParsedDocument
    ) -> tuple[AccountType, StatementType, float]:
        """E*TRADE only supports individual brokerage in this implementation."""
        return AccountType.INDIVIDUAL_BROKERAGE, StatementType.BROKERAGE, 0.90
