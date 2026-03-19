"""
Chase statement classifier.

Determines:
1. Whether the document is from Chase / JPMorgan Chase
2. The specific account type: checking or credit card

Strategy:
- Regex/keyword matching on first 3 pages
- Checking accounts have "checking", "available balance", debit card signals
- Credit cards have "credit card", "minimum payment due", "statement balance"
"""

from __future__ import annotations

import re

import structlog

from app.domain.enums import AccountType, StatementType
from app.parsers.base import ParsedDocument

logger = structlog.get_logger(__name__)

# Strong Chase origin indicators
_CHASE_PATTERNS = re.compile(
    r"jpmorgan\s+chase|chase\s+bank|chase\.com|"
    r"chasebank\.com|j\.p\.\s*morgan|chase\s+sapphire|"
    r"chase\s+freedom|chase\s+united|chase\s+southwest|"
    r"chase\s+ink|chase\s+total\s+checking|chase\s+premier",
    re.IGNORECASE,
)

# Checking account indicators
_CHECKING_PATTERNS = re.compile(
    r"total\s+checking|checking\s+account|"
    r"available\s+balance|debit\s+card\s+purchase|"
    r"direct\s+deposit|atm\s+withdrawal|"
    r"beginning\s+balance|ending\s+balance",
    re.IGNORECASE,
)

# Credit card indicators
_CREDIT_CARD_PATTERNS = re.compile(
    r"credit\s+card\s+statement|minimum\s+payment\s+due|"
    r"statement\s+balance|previous\s+balance|"
    r"payment\s+due\s+date|credit\s+limit|"
    r"sapphire|freedom|united\s+miles|southwest\s+rapid|ink\s+business",
    re.IGNORECASE,
)


class ChaseClassifier:
    """Classifies Chase documents by account type."""

    async def is_chase(self, document: ParsedDocument) -> tuple[bool, float]:
        """Return (is_chase, confidence)."""
        sample = "\n".join(p.raw_text for p in document.pages[:3] if p.raw_text)
        matches = _CHASE_PATTERNS.findall(sample)
        if len(matches) >= 2:
            return True, 0.95
        if len(matches) == 1:
            return True, 0.80
        return False, 0.05

    def classify_account_type(
        self, document: ParsedDocument
    ) -> tuple[AccountType, StatementType, float]:
        """
        Determine whether this is a checking or credit card statement.

        Returns:
            (AccountType, StatementType, confidence)
        """
        sample = "\n".join(p.raw_text for p in document.pages[:4] if p.raw_text)

        checking_hits = len(_CHECKING_PATTERNS.findall(sample))
        credit_hits = len(_CREDIT_CARD_PATTERNS.findall(sample))

        if credit_hits > checking_hits:
            confidence = min(0.95, 0.60 + credit_hits * 0.05)
            return AccountType.CREDIT_CARD, StatementType.CREDIT_CARD, confidence

        if checking_hits > 0:
            confidence = min(0.95, 0.60 + checking_hits * 0.05)
            return AccountType.CHECKING, StatementType.BANK, confidence

        # Default to checking if we can't distinguish (Chase checking is more common)
        logger.debug("chase.classifier.default_to_checking")
        return AccountType.CHECKING, StatementType.BANK, 0.50
