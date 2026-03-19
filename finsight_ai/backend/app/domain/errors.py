"""
Typed domain exceptions.

Raise domain-level exceptions from services/parsers;
API layer translates them to HTTP responses.
"""

from __future__ import annotations

from typing import Any


class CoralError(Exception):
    """Base exception for all Coral domain errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


# ── Ingestion ────────────────────────────────────────────────────────────────

class DocumentIngestionError(CoralError):
    """Document cannot be ingested."""

class UnsupportedFileTypeError(DocumentIngestionError):
    """Uploaded file type is not supported."""

class FileTooLargeError(DocumentIngestionError):
    """Uploaded file exceeds size limit."""


# ── Parsing ──────────────────────────────────────────────────────────────────

class DocumentParseError(CoralError):
    """Document cannot be parsed."""

class PageExtractionError(DocumentParseError):
    def __init__(self, message: str, page_number: int, **kwargs: Any) -> None:
        super().__init__(message, details={"page_number": page_number, **kwargs})
        self.page_number = page_number


# ── Classification ───────────────────────────────────────────────────────────

class ClassificationError(CoralError):
    """Institution or statement type cannot be determined."""


# ── Extraction ───────────────────────────────────────────────────────────────

class ExtractionError(CoralError):
    def __init__(self, message: str, institution: str | None = None, **kwargs: Any) -> None:
        super().__init__(message, details={"institution": institution, **kwargs})
        self.institution = institution


class NormalizationError(CoralError):
    """Cannot map extracted data to canonical schema."""


# ── LLM / Ollama ─────────────────────────────────────────────────────────────

class OllamaConnectionError(CoralError):
    """Ollama server is unreachable."""

class OllamaModelNotFoundError(CoralError):
    """Requested model not available in Ollama."""

class LLMResponseParseError(CoralError):
    """LLM response cannot be parsed into expected structure."""


# ── Database ─────────────────────────────────────────────────────────────────

class RepositoryError(CoralError):
    """Database operation failed."""

class EntityNotFoundError(RepositoryError):
    def __init__(self, entity_type: str, entity_id: Any) -> None:
        super().__init__(
            f"{entity_type} with id={entity_id!r} not found",
            details={"entity_type": entity_type, "entity_id": str(entity_id)},
        )


# ── Query ────────────────────────────────────────────────────────────────────

class QueryRoutingError(CoralError):
    """Cannot determine query intent or path."""

class SQLQueryError(CoralError):
    """SQL query generation or execution failed."""

class SearchError(CoralError):
    """FTS or vector search failed."""
