"""
MerchantNormalizer — clean merchant names and assign spending categories.

Strategy:
1. Clean the raw description string (strip location suffixes, POS codes, etc.)
2. Apply deterministic category_rules (zero LLM cost, ~200 rules)
3. If rules produce no match AND llm_fallback=True, call LLM with a short prompt
4. Detect subscription signals independently

This normalizer is stateless and synchronous for the rules path.
The async path (with LLM fallback) is gated behind normalize_async().

Usage (sync, rules-only):
    normalizer = MerchantNormalizer()
    clean, category, confidence = normalizer.normalize("AMZN*MKTP US 123XYZ")

Usage (async, with LLM fallback):
    clean, category, confidence = await normalizer.normalize_async(
        "SQ *SOME LOCAL STORE",
        llm_fallback=True,
    )
"""

from __future__ import annotations

import re

import structlog

from app.domain.enums import TransactionCategory
from app.services.normalization.category_rules import (
    categorize_merchant,
    is_likely_subscription,
)

logger = structlog.get_logger(__name__)

# ── Cleaning patterns ──────────────────────────────────────────────────────────

# Strip trailing location / POS noise:
#   "STARBUCKS #12345 SEATTLE WA" → "STARBUCKS"
#   "AMZN*MKTP US 29XABC" → "AMAZON"
#   "SQ *MERCHANT NAME" → "MERCHANT NAME"
# Applied in order; first successful transform wins.
_CLEAN_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Amazon variants
    (re.compile(r"\bAMZN\b[\s*]+", re.IGNORECASE), "AMAZON "),
    # Square POS prefix
    (re.compile(r"\bSQ\s*\*\s*", re.IGNORECASE), ""),
    # TST* (Toast POS)
    (re.compile(r"\bTST\s*\*\s*", re.IGNORECASE), ""),
    # Paypal prefix
    (re.compile(r"\bPAYPAL\s*\*\s*", re.IGNORECASE), "PAYPAL "),
    # Strip alphanumeric codes at end (e.g. "STORE 12345 NY")
    (re.compile(r"\s+#\d+.*$"), ""),
    # Strip state abbreviation + context at end ("MERCHANT SEATTLE WA 98101")
    (re.compile(r"\s+[A-Z]{2}\s+\d{5}(-\d{4})?$"), ""),
    # Strip 2-letter state at end
    (re.compile(r"\s+[A-Z]{2}$"), ""),
    # Strip trailing numeric codes
    (re.compile(r"\s+\d{4,}$"), ""),
    # Strip common POS suffixes
    (re.compile(r"\s+(INC|LLC|CORP|CO|LTD|LP)\.?\s*$", re.IGNORECASE), ""),
]

# Characters to collapse (runs of spaces, asterisks, slashes as separator noise)
_COLLAPSE_RE = re.compile(r"\s{2,}")


def _clean_description(raw: str) -> str:
    """
    Clean a raw transaction description into a merchant name.

    Applies regex substitutions in order, then collapses whitespace
    and title-cases the result.
    """
    text = raw.strip()
    for pattern, replacement in _CLEAN_PATTERNS:
        text = pattern.sub(replacement, text)
    text = _COLLAPSE_RE.sub(" ", text).strip()
    # Title-case only if all-caps (common in banking exports)
    if text.isupper():
        text = text.title()
    return text or raw.strip()


class MerchantNormalizer:
    """
    Cleans and categorizes banking transaction descriptions.

    Injecting a ModelRouter is optional; only required when using
    normalize_async() with llm_fallback=True.
    """

    # Only invoke LLM if rule confidence is below this threshold
    LLM_FALLBACK_THRESHOLD: float = 0.4

    def __init__(self, model_router=None) -> None:
        self._router = model_router

    def normalize(
        self, raw_description: str
    ) -> tuple[str, TransactionCategory, float]:
        """
        Synchronous normalization using rules only.

        Returns:
            (cleaned_merchant_name, category, confidence)
            confidence = 1.0 if a rule matched, 0.0 if no match (OTHER).
        """
        clean = _clean_description(raw_description)
        category, confidence = categorize_merchant(clean)
        if confidence == 0.0:
            # Try against the raw description too (covers noisy prefixes)
            category, confidence = categorize_merchant(raw_description)
        return clean, category, confidence

    def is_recurring(self, raw_description: str) -> bool:
        """Return True if this transaction looks like a recurring subscription."""
        return is_likely_subscription(raw_description)

    async def normalize_async(
        self,
        raw_description: str,
        llm_fallback: bool = False,
    ) -> tuple[str, TransactionCategory, float]:
        """
        Async normalization with optional LLM fallback.

        Falls back to the LLM only when:
        - llm_fallback=True
        - rules produced no match (confidence == 0.0)
        - a ModelRouter was injected

        LLM fallback adds latency; use sparingly (e.g. only for unknown merchants).
        """
        clean, category, confidence = self.normalize(raw_description)

        if confidence >= self.LLM_FALLBACK_THRESHOLD or not llm_fallback:
            return clean, category, confidence

        if self._router is None:
            logger.debug(
                "merchant_normalizer.llm_skip",
                reason="no model router injected",
                description=raw_description[:60],
            )
            return clean, category, 0.0

        # LLM fallback — short classification prompt, structured output
        try:
            from app.ollama.model_router import TaskType

            categories_list = ", ".join(c.value for c in TransactionCategory)
            prompt = (
                f"Classify this bank transaction into exactly one spending category.\n\n"
                f"Transaction: {clean}\n\n"
                f"Categories: {categories_list}\n\n"
                f'Respond with JSON: {{"category": "<value>", "confidence": <0.0-1.0>}}'
            )
            response = await self._router.generate(
                task=TaskType.CLASSIFICATION,
                prompt=prompt,
                format="json",
            )
            import json

            data = json.loads(response.strip())
            cat_str = data.get("category", "other")
            llm_confidence = float(data.get("confidence", 0.5))
            try:
                category = TransactionCategory(cat_str)
            except ValueError:
                category = TransactionCategory.OTHER

            logger.debug(
                "merchant_normalizer.llm_result",
                merchant=clean[:40],
                category=category.value,
                confidence=llm_confidence,
            )
            return clean, category, llm_confidence

        except Exception as exc:
            logger.warning(
                "merchant_normalizer.llm_failed",
                error=str(exc),
                description=raw_description[:60],
            )
            return clean, TransactionCategory.OTHER, 0.0

    def normalize_batch(
        self, raw_descriptions: list[str]
    ) -> list[tuple[str, TransactionCategory, float]]:
        """Normalize a list of descriptions synchronously (rules only)."""
        return [self.normalize(d) for d in raw_descriptions]
