"""
Typed domain exceptions.

Using a typed exception hierarchy allows callers to catch specific errors
without coupling to implementation details (e.g., PDF library errors).

Pattern: raise domain-level exceptions from parsers/agents;
         let API layer translate them to HTTP responses.
"""

from __future__ import annotations

from typing import Any


class FinSightError(Exception):
    """Base exception for all FinSight domain errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


# ── Ingestion errors ──────────────────────────────────────────────────────────

class DocumentIngestionError(FinSightError):
    """Raised when a document cannot be ingested (file I/O, validation)."""


class UnsupportedFileTypeError(DocumentIngestionError):
    """Raised when an uploaded file type is not supported."""


class FileTooLargeError(DocumentIngestionError):
    """Raised when an uploaded file exceeds the size limit."""


# ── Parsing errors ────────────────────────────────────────────────────────────

class DocumentParseError(FinSightError):
    """Raised when a document cannot be parsed at all."""


class PageExtractionError(DocumentParseError):
    """Raised when a specific page cannot be read."""

    def __init__(self, message: str, page_number: int, **kwargs: Any) -> None:
        super().__init__(message, details={"page_number": page_number, **kwargs})
        self.page_number = page_number


# ── Classification errors ─────────────────────────────────────────────────────

class ClassificationError(FinSightError):
    """Raised when the institution or statement type cannot be determined."""


# ── Extraction errors ─────────────────────────────────────────────────────────

class ExtractionError(FinSightError):
    """Raised when structured data cannot be extracted from a parsed document."""

    def __init__(
        self,
        message: str,
        institution: str | None = None,
        confidence: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            details={"institution": institution, "confidence": confidence, **kwargs},
        )
        self.institution = institution
        self.confidence = confidence


class NormalizationError(FinSightError):
    """Raised when raw extracted data cannot be mapped to the canonical schema."""


# ── LLM / Ollama errors ───────────────────────────────────────────────────────

class OllamaConnectionError(FinSightError):
    """Raised when the Ollama server is unreachable."""


class OllamaModelNotFoundError(FinSightError):
    """Raised when the requested model is not available in Ollama."""


class LLMResponseParseError(FinSightError):
    """Raised when the LLM response cannot be parsed into the expected structure."""


# ── Vector store errors ───────────────────────────────────────────────────────

class VectorStoreError(FinSightError):
    """Raised when a Chroma operation fails."""


# ── Repository / persistence errors ──────────────────────────────────────────

class RepositoryError(FinSightError):
    """Raised when a database operation fails."""


class EntityNotFoundError(RepositoryError):
    """Raised when a requested entity does not exist."""

    def __init__(self, entity_type: str, entity_id: Any) -> None:
        super().__init__(
            f"{entity_type} with id={entity_id!r} not found",
            details={"entity_type": entity_type, "entity_id": str(entity_id)},
        )
