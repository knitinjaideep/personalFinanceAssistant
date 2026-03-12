"""
Base parser ABC that all institution parsers must implement.

Design decisions:
- BaseParser defines the interface; institution parsers provide
  the implementation. The supervisor agent calls parse() without
  knowing which institution it's dealing with.
- ParsedPage carries raw text + detected tables so downstream
  extractors can choose how to process each page.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedTable:
    """A table detected on a page."""

    rows: list[list[str | None]]          # Row-major, cells may be None
    header_row: list[str] | None = None
    page_number: int = 0
    bbox: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1


@dataclass
class ParsedPage:
    """All content extracted from a single PDF page."""

    page_number: int                        # 1-indexed
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
        """Concatenated text across all pages."""
        return "\n\n".join(p.raw_text for p in self.pages)


class BaseParser(ABC):
    """
    Abstract base class for document parsers.

    Each parser implementation is responsible for converting a raw
    document file into a ParsedDocument structure.
    """

    @abstractmethod
    async def parse(self, file_path: Path) -> ParsedDocument:
        """
        Parse a document file into structured pages.

        Args:
            file_path: Absolute path to the document on disk.

        Returns:
            ParsedDocument with text and table data per page.

        Raises:
            DocumentParseError: If the document cannot be parsed.
        """
        ...

    @property
    @abstractmethod
    def supported_mime_types(self) -> list[str]:
        """MIME types this parser can handle."""
        ...
