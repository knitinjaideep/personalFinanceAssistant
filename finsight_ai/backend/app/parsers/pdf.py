"""
PDF parser using pdfplumber.

CPU-bound work runs in a thread pool via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pdfplumber
import structlog

from app.domain.errors import DocumentParseError
from app.parsers.base import ParsedDocument, ParsedPage, ParsedTable

logger = structlog.get_logger(__name__)

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

_TABLE_SETTINGS_FALLBACK = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 5,
    "join_tolerance": 5,
}


async def parse_pdf(file_path: Path) -> ParsedDocument:
    """Parse a PDF file into a ParsedDocument. Runs in thread pool."""
    if not file_path.exists():
        raise DocumentParseError(f"File not found: {file_path}")
    if file_path.stat().st_size == 0:
        raise DocumentParseError(f"File is empty: {file_path}")

    logger.info("pdf.parse.start", path=str(file_path))
    try:
        parsed = await asyncio.to_thread(_parse_sync, file_path)
        logger.info("pdf.parse.done", path=str(file_path), pages=parsed.page_count)
        return parsed
    except DocumentParseError:
        raise
    except Exception as exc:
        raise DocumentParseError(f"Failed to parse PDF '{file_path.name}': {exc}") from exc


def _parse_sync(file_path: Path) -> ParsedDocument:
    pages: list[ParsedPage] = []
    metadata: dict[str, Any] = {}

    with pdfplumber.open(str(file_path)) as pdf:
        if pdf.metadata:
            metadata.update({
                k: str(v) for k, v in pdf.metadata.items()
                if v is not None and k in ("Title", "Author", "CreationDate", "Producer")
            })

        for page_num, page in enumerate(pdf.pages, start=1):
            try:
                parsed_page = _parse_page(page, page_num)
                pages.append(parsed_page)
            except Exception as exc:
                logger.warning("pdf.page.error", page=page_num, error=str(exc))
                pages.append(ParsedPage(
                    page_number=page_num, raw_text="",
                    metadata={"parse_error": str(exc)}
                ))

    return ParsedDocument(
        file_path=str(file_path), page_count=len(pages),
        pages=pages, metadata=metadata,
    )


def _parse_page(page: Any, page_number: int) -> ParsedPage:
    raw_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""

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
        cleaned_rows = [
            [str(cell).strip() if cell is not None else "" for cell in row]
            for row in raw_table
        ]
        header: list[str] | None = None
        data_rows = cleaned_rows
        if cleaned_rows and _looks_like_header(cleaned_rows[0]):
            header = cleaned_rows[0]
            data_rows = cleaned_rows[1:]
        tables.append(ParsedTable(rows=data_rows, header_row=header, page_number=page_number))

    return ParsedPage(
        page_number=page_number, raw_text=raw_text,
        tables=tables, metadata={"table_count": len(tables)},
    )


def _looks_like_header(row: list[str]) -> bool:
    if not row:
        return False
    non_empty = [cell for cell in row if cell]
    if not non_empty:
        return False
    header_like = sum(
        1 for cell in non_empty
        if not cell.replace(",", "").replace(".", "").replace("-", "").replace("$", "").strip().lstrip("-").isdigit()
    )
    return header_like / len(non_empty) > 0.6
