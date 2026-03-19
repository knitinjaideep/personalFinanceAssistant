"""
In-flight document store — short-lived, in-memory session state for parsed documents.

During ingestion the ``parse_node`` produces a ``ParsedDocument`` object that
is later needed by the ``ExtractDocumentTool``.  Passing large Python objects
through the LangGraph state dict is possible but carries serialisation overhead
and couples the graph state schema to a concrete dataclass.

This module provides a lightweight, thread-safe dict-based store that:
  - is keyed by document_id (UUID string)
  - holds ``ParsedDocument`` objects only for the duration of one ingestion run
  - is cleaned up by ``report_node`` after the pipeline completes

The store lives entirely in the process memory and is intentionally NOT
persisted to disk — the raw PDF is still on disk if a re-parse is ever needed.

Usage pattern::

    # parse_node (supervisor.py)
    from app.mcp_tools.document_store import document_store
    document_store.put(doc_id, parsed_document)

    # ExtractDocumentTool (institution_tools.py)
    parsed = document_store.get(doc_id)

    # report_node (supervisor.py)
    document_store.remove(doc_id)
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

import structlog

from app.parsers.base import ParsedDocument

if TYPE_CHECKING:
    from app.domain.entities import ExtractionResult

logger = structlog.get_logger(__name__)


class InFlightDocumentStore:
    """
    Thread-safe in-memory store for ``ParsedDocument`` objects.

    Each entry is keyed by the document UUID string and exists only for the
    lifetime of the ingestion graph run that produced it.  Entries must be
    explicitly removed via ``remove()`` — there is no automatic TTL, but the
    store is small (one entry per concurrent ingestion) so memory pressure is
    not a concern in practice.
    """

    def __init__(self) -> None:
        self._store: dict[str, ParsedDocument] = {}
        self._result_store: dict[str, Any] = {}  # document_id → ExtractionResult
        self._lock = threading.Lock()

    def put(self, document_id: str, parsed_doc: ParsedDocument) -> None:
        """
        Store a ``ParsedDocument`` under ``document_id``.

        Overwrites any existing entry with the same id (safe for retry logic).
        """
        with self._lock:
            self._store[document_id] = parsed_doc
        logger.debug(
            "document_store.put",
            document_id=document_id,
            page_count=parsed_doc.page_count,
        )

    def get(self, document_id: str) -> ParsedDocument | None:
        """
        Retrieve the ``ParsedDocument`` for ``document_id``.

        Returns ``None`` if no entry exists (e.g. was already removed or was
        never stored because the parse step failed).
        """
        with self._lock:
            doc = self._store.get(document_id)
        if doc is None:
            logger.warning("document_store.miss", document_id=document_id)
        return doc

    def put_result(self, document_id: str, result: ExtractionResult) -> None:
        """
        Store an ``ExtractionResult`` produced by an institution agent.

        Called by ``ExtractDocumentTool`` so that ``extract_node`` in the
        supervisor can retrieve the full entity and write it into graph state.
        """
        with self._lock:
            self._result_store[document_id] = result
        logger.debug("document_store.put_result", document_id=document_id)

    def get_result(self, document_id: str) -> ExtractionResult | None:
        """
        Retrieve a previously stored ``ExtractionResult``.

        Returns ``None`` if the result was never stored or was already removed.
        """
        with self._lock:
            return self._result_store.get(document_id)  # type: ignore[return-value]

    def remove(self, document_id: str) -> None:
        """
        Remove both the ``ParsedDocument`` and any ``ExtractionResult`` entries
        for ``document_id`` from the store.

        Safe to call even if the id was never stored or was already removed.
        """
        with self._lock:
            removed_doc = self._store.pop(document_id, None)
            removed_result = self._result_store.pop(document_id, None)
        if removed_doc is not None or removed_result is not None:
            logger.debug("document_store.removed", document_id=document_id)

    def size(self) -> int:
        """Return the current number of entries in the store (for diagnostics)."""
        with self._lock:
            return len(self._store)

    def __contains__(self, document_id: str) -> bool:
        with self._lock:
            return document_id in self._store


# Module-level singleton — import this directly from consuming modules.
document_store = InFlightDocumentStore()
