"""
Parser plugin interface and registry.

Each institution parser implements InstitutionParser:
  - can_handle(text, metadata) → confidence score
  - parse(file_path) → ParsedDocument (raw PDF extraction)
  - extract(document) → ParsedStatement (structured data extraction)

The registry holds all parsers and provides detection/dispatch.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from app.domain.entities import ParsedStatement

logger = structlog.get_logger(__name__)


# ── Raw parsed document structures ───────────────────────────────────────────

@dataclass
class ParsedTable:
    """A table detected on a page."""
    rows: list[list[str | None]]
    header_row: list[str] | None = None
    page_number: int = 0
    bbox: tuple[float, float, float, float] | None = None


@dataclass
class ParsedPage:
    """Content extracted from a single PDF page."""
    page_number: int
    raw_text: str
    tables: list[ParsedTable] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """Complete parsed representation of an uploaded document."""
    file_path: str
    page_count: int
    pages: list[ParsedPage]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.raw_text for p in self.pages)


# ── Parser interface ─────────────────────────────────────────────────────────

class InstitutionParser(ABC):
    """Abstract base for institution-specific parsers.

    Every institution parser must implement three methods:
    1. can_handle — fast confidence check (regex/keyword, no LLM)
    2. parse — raw PDF → ParsedDocument
    3. extract — ParsedDocument → ParsedStatement (structured canonical data)
    """

    @property
    @abstractmethod
    def institution_type(self) -> str:
        """Return the InstitutionType string value this parser handles."""
        ...

    @property
    @abstractmethod
    def institution_name(self) -> str:
        """Human-readable institution name."""
        ...

    @abstractmethod
    def can_handle(self, text: str, metadata: dict[str, Any] | None = None) -> float:
        """Score how likely this parser can handle the given document text.

        Args:
            text: First ~3000 chars of the document.
            metadata: Optional file metadata.

        Returns:
            Confidence score 0.0–1.0. >0.7 = strong match.
        """
        ...

    @abstractmethod
    async def extract(self, document: ParsedDocument) -> ParsedStatement:
        """Extract structured financial data from a parsed document.

        Args:
            document: The raw parsed PDF output.

        Returns:
            ParsedStatement with all extracted transactions, fees, holdings, etc.
        """
        ...


# ── Parser registry ──────────────────────────────────────────────────────────

class ParserRegistry:
    """Registry holding all institution parsers. Provides detection and dispatch."""

    def __init__(self) -> None:
        self._parsers: list[InstitutionParser] = []

    def register(self, parser: InstitutionParser) -> None:
        self._parsers.append(parser)
        logger.info("parser.registered", institution=parser.institution_type)

    def detect_institution(self, text: str, metadata: dict[str, Any] | None = None) -> tuple[InstitutionParser | None, float]:
        """Run all parsers' can_handle and return the best match.

        Returns:
            Tuple of (best parser or None, confidence score).
        """
        best_parser: InstitutionParser | None = None
        best_score = 0.0

        for parser in self._parsers:
            try:
                score = parser.can_handle(text, metadata)
                if score > best_score:
                    best_score = score
                    best_parser = parser
            except Exception as exc:
                logger.warning("parser.can_handle.error",
                             institution=parser.institution_type, error=str(exc))

        if best_parser and best_score > 0.3:
            logger.info("parser.detected",
                       institution=best_parser.institution_type, confidence=best_score)
            return best_parser, best_score

        return None, 0.0

    def get_parser(self, institution_type: str) -> InstitutionParser | None:
        """Get a specific parser by institution type."""
        for parser in self._parsers:
            if parser.institution_type == institution_type:
                return parser
        return None

    @property
    def parsers(self) -> list[InstitutionParser]:
        return list(self._parsers)


# ── Global registry singleton ────────────────────────────────────────────────

_registry: ParserRegistry | None = None


def get_parser_registry() -> ParserRegistry:
    """Get or create the global parser registry with all institution parsers."""
    global _registry
    if _registry is None:
        _registry = ParserRegistry()
        _register_all_parsers(_registry)
    return _registry


def _register_all_parsers(registry: ParserRegistry) -> None:
    """Import and register all institution parsers."""
    from app.parsers.morgan_stanley.parser import MorganStanleyParser
    from app.parsers.chase.parser import ChaseParser
    from app.parsers.etrade.parser import ETradeParser
    from app.parsers.amex.parser import AmexParser
    from app.parsers.discover.parser import DiscoverParser

    registry.register(MorganStanleyParser())
    registry.register(ChaseParser())
    registry.register(ETradeParser())
    registry.register(AmexParser())
    registry.register(DiscoverParser())
