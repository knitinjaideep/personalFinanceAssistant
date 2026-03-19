"""
Discover statement classifier.
"""

from __future__ import annotations

import re

from app.domain.enums import AccountType, StatementType
from app.parsers.base import ParsedDocument

_DISCOVER_PATTERNS = re.compile(
    r"discover\s+(?:card|it|more|miles|cashback)|"
    r"discovercard\.com|discover\s+financial|"
    r"discover\s+bank|discover\s+credit",
    re.IGNORECASE,
)


class DiscoverClassifier:
    """Classifies Discover documents."""

    async def is_discover(self, document: ParsedDocument) -> tuple[bool, float]:
        sample = "\n".join(p.raw_text for p in document.pages[:3] if p.raw_text)
        matches = _DISCOVER_PATTERNS.findall(sample)
        if len(matches) >= 2:
            return True, 0.95
        if len(matches) == 1:
            return True, 0.80
        return False, 0.05

    def classify_account_type(
        self, document: ParsedDocument
    ) -> tuple[AccountType, StatementType, float]:
        """Discover only issues credit cards in this implementation."""
        return AccountType.CREDIT_CARD, StatementType.CREDIT_CARD, 0.95
