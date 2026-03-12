"""
Document chunking strategies for financial statements.

Financial statements need specialized chunking because:
- They have identifiable sections (holdings table, transaction history, etc.)
- Mixing sections in a single chunk degrades retrieval quality
- Tables should be represented as formatted text, not split mid-row

Strategy: Section-aware chunking
1. Split document into logical sections using section header patterns
2. Within each section, apply token-limited sliding window chunking
3. Preserve page/section metadata in each chunk for provenance
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.parsers.base import ParsedDocument, ParsedPage, ParsedTable

# Target chunk size in characters (~400–600 tokens for nomic-embed-text)
DEFAULT_CHUNK_SIZE = 1500
DEFAULT_CHUNK_OVERLAP = 200

# Section header patterns — used to split document into logical segments
SECTION_SPLIT_PATTERNS = [
    r"account\s+summary",
    r"portfolio\s+(overview|detail|summary)",
    r"(transaction|activity)\s+(history|detail)",
    r"holdings?|positions?|securities",
    r"fee\s+(detail|schedule|summary)",
    r"cash\s+(flow|activity)",
    r"investment\s+detail",
    r"performance\s+summary",
]
SECTION_SPLIT_RE = re.compile(
    r"(" + "|".join(SECTION_SPLIT_PATTERNS) + r")",
    re.IGNORECASE,
)


@dataclass
class TextChunk:
    """A single text chunk ready for embedding."""

    text: str
    chunk_index: int
    page_number: int | None = None
    section: str | None = None
    metadata: dict = field(default_factory=dict)


def _format_table_as_text(table: ParsedTable) -> str:
    """Convert a ParsedTable to a pipe-delimited text representation."""
    lines: list[str] = []
    if table.header_row:
        lines.append(" | ".join(table.header_row))
        lines.append("-" * min(60, sum(len(h) + 3 for h in table.header_row)))
    for row in table.rows:
        if row and any(cell for cell in row):
            lines.append(" | ".join(str(cell) for cell in row))
    return "\n".join(lines)


def _split_by_size(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks by character count."""
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            # Try to break at a sentence or newline boundary
            break_pos = text.rfind("\n", start, end)
            if break_pos == -1:
                break_pos = text.rfind(". ", start, end)
            if break_pos != -1 and break_pos > start:
                end = break_pos + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


class DocumentChunker:
    """
    Converts a ParsedDocument into a list of TextChunks for embedding.

    Uses section-aware strategy: identifies logical sections and keeps
    them together where possible before size-splitting.
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def chunk(self, document: ParsedDocument) -> list[TextChunk]:
        """Chunk a parsed document into embedding-ready text chunks."""
        all_chunks: list[TextChunk] = []
        chunk_index = 0

        for page in document.pages:
            page_chunks = self._chunk_page(page)
            for text in page_chunks:
                if text.strip():
                    all_chunks.append(
                        TextChunk(
                            text=text,
                            chunk_index=chunk_index,
                            page_number=page.page_number,
                            section=self._detect_section(text),
                        )
                    )
                    chunk_index += 1

            # Also chunk tables as formatted text
            for table in page.tables:
                table_text = _format_table_as_text(table)
                if table_text.strip():
                    section = self._detect_section(page.raw_text[:500])
                    all_chunks.append(
                        TextChunk(
                            text=f"[TABLE]\n{table_text}",
                            chunk_index=chunk_index,
                            page_number=page.page_number,
                            section=section,
                            metadata={"type": "table"},
                        )
                    )
                    chunk_index += 1

        return all_chunks

    def _chunk_page(self, page: ParsedPage) -> list[str]:
        """Split a single page's text into size-limited chunks."""
        text = page.raw_text.strip()
        if not text:
            return []

        # Split on section headers first
        segments = SECTION_SPLIT_RE.split(text)
        result: list[str] = []
        current_section = ""

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            if SECTION_SPLIT_RE.match(segment):
                # This is a section header — start a new segment
                if current_section:
                    result.extend(_split_by_size(current_section, self._chunk_size, self._chunk_overlap))
                current_section = segment + "\n"
            else:
                current_section += segment

        if current_section:
            result.extend(_split_by_size(current_section, self._chunk_size, self._chunk_overlap))

        return result

    def _detect_section(self, text: str) -> str | None:
        """Detect what logical section a chunk belongs to."""
        match = SECTION_SPLIT_RE.search(text[:300])
        if match:
            return match.group(0).strip().lower()
        return None
