"""
PDF parser using pdfplumber.

pdfplumber is chosen over PyPDF2/pypdf for financial statements because:
- It preserves layout/column alignment better
- It has superior table extraction with configurable strategies
- It handles the complex multi-column layouts common in brokerage statements

Design: parse() is a CPU-bound operation run in a thread pool via
asyncio.to_thread() so it doesn't block the async event loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pdfplumber
import structlog

from app.domain.errors import DocumentParseError, PageExtractionError
from app.parsers.base import BaseParser, ParsedDocument, ParsedPage, ParsedTable

logger = structlog.get_logger(__name__)

# pdfplumber table extraction settings tuned for financial statement layouts
_TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
    "min_words_vertical": 3,
    "min_words_horizontal": 1,
    "text_tolerance": 3,
}

# Fallback settings when line-based strategy finds no tables
_TABLE_SETTINGS_FALLBACK = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 5,
    "join_tolerance": 5,
}


class PDFParser(BaseParser):
    """
    Parse PDF financial statements into structured page data.

    Supports both native PDFs (text-based) and image-based PDFs.
    For image PDFs, falls back to text-only extraction (OCR can be
    added in Phase 3 via tesseract).
    """

    @property
    def supported_mime_types(self) -> list[str]:
        return ["application/pdf"]

    async def parse(self, file_path: Path) -> ParsedDocument:
        """
        Parse a PDF file asynchronously.

        Delegates CPU-bound work to a thread pool to keep the event loop free.
        """
        if not file_path.exists():
            raise DocumentParseError(f"File not found: {file_path}")
        if file_path.stat().st_size == 0:
            raise DocumentParseError(f"File is empty: {file_path}")

        logger.info("pdf.parse.start", path=str(file_path))

        try:
            parsed = await asyncio.to_thread(self._parse_sync, file_path)
            logger.info(
                "pdf.parse.done",
                path=str(file_path),
                pages=parsed.page_count,
            )
            return parsed
        except DocumentParseError:
            raise
        except Exception as exc:
            raise DocumentParseError(
                f"Failed to parse PDF '{file_path.name}': {exc}"
            ) from exc

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        """Synchronous PDF parsing — runs in thread pool."""
        pages: list[ParsedPage] = []
        metadata: dict[str, Any] = {}

        with pdfplumber.open(str(file_path)) as pdf:
            # Extract document-level metadata
            if pdf.metadata:
                metadata.update(
                    {
                        k: str(v)
                        for k, v in pdf.metadata.items()
                        if v is not None and k in ("Title", "Author", "CreationDate", "Producer")
                    }
                )

            for page_num, page in enumerate(pdf.pages, start=1):
                try:
                    parsed_page = self._parse_page(page, page_num)
                    pages.append(parsed_page)
                except Exception as exc:
                    logger.warning(
                        "pdf.page.parse_error",
                        page=page_num,
                        error=str(exc),
                    )
                    # Don't fail the whole document for one bad page
                    pages.append(
                        ParsedPage(
                            page_number=page_num,
                            raw_text="",
                            metadata={"parse_error": str(exc)},
                        )
                    )

        return ParsedDocument(
            file_path=str(file_path),
            page_count=len(pages),
            pages=pages,
            metadata=metadata,
        )

    def _parse_page(self, page: Any, page_number: int) -> ParsedPage:
        """Extract text and tables from a single pdfplumber page object."""
        # Extract text with layout preservation
        raw_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""

        # Try line-based table extraction first, then fall back to text-based
        tables: list[ParsedTable] = []
        try:
            pdfplumber_tables = page.extract_tables(_TABLE_SETTINGS)
            if not pdfplumber_tables:
                pdfplumber_tables = page.extract_tables(_TABLE_SETTINGS_FALLBACK)
        except Exception:
            pdfplumber_tables = []

        for raw_table in (pdfplumber_tables or []):
            if not raw_table:
                continue

            # Convert None cells to empty strings, strip whitespace
            cleaned_rows = [
                [str(cell).strip() if cell is not None else "" for cell in row]
                for row in raw_table
            ]

            # Use first row as header if it looks like a header
            header: list[str] | None = None
            data_rows = cleaned_rows
            if cleaned_rows and self._looks_like_header(cleaned_rows[0]):
                header = cleaned_rows[0]
                data_rows = cleaned_rows[1:]

            tables.append(
                ParsedTable(
                    rows=data_rows,
                    header_row=header,
                    page_number=page_number,
                )
            )

        return ParsedPage(
            page_number=page_number,
            raw_text=raw_text,
            tables=tables,
            metadata={"table_count": len(tables)},
        )

    def _looks_like_header(self, row: list[str]) -> bool:
        """
        Heuristic: a header row usually has short non-numeric cells
        and doesn't contain dollar amounts.
        """
        if not row:
            return False
        non_empty = [cell for cell in row if cell]
        if not non_empty:
            return False
        # If more than half the cells look like column headers (text, not numbers)
        header_like = sum(
            1
            for cell in non_empty
            if not cell.replace(",", "").replace(".", "").replace("-", "").replace("$", "").strip().lstrip("-").isdigit()
        )
        return header_like / len(non_empty) > 0.6
