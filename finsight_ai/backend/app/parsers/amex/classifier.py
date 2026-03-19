"""
Amex (American Express) statement classifier.
"""

from __future__ import annotations

import re

from app.domain.enums import AccountType, StatementType
from app.parsers.base import ParsedDocument

_AMEX_PATTERNS = re.compile(
    r"american\s+express|americanexpress\.com|amex\.com|"
    r"amex\s+(?:gold|platinum|green|blue|delta|hilton|marriott)|"
    r"american\s+express\s+(?:credit\s+card|card\s+services)",
    re.IGNORECASE,
)


class AmexClassifier:
    """Classifies Amex documents."""

    async def is_amex(self, document: ParsedDocument) -> tuple[bool, float]:
        sample = "\n".join(p.raw_text for p in document.pages[:3] if p.raw_text)
        matches = _AMEX_PATTERNS.findall(sample)
        if len(matches) >= 2:
            return True, 0.95
        if len(matches) == 1:
            return True, 0.82
        return False, 0.05

    def classify_account_type(
        self, document: ParsedDocument
    ) -> tuple[AccountType, StatementType, float]:
        """Amex only issues credit cards in this implementation."""
        return AccountType.CREDIT_CARD, StatementType.CREDIT_CARD, 0.95
