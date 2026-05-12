"""
Statement source configuration — derives from the statement catalog.

This module generates StatementSource entries (used by the local scanner)
from the canonical AccountCatalogEntry definitions in config/statement_catalog.py.

Add new institutions/accounts to statement_catalog.py; do not edit here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.config.statement_catalog import (
    ACCOUNT_CATALOG,
    get_statements_root,
)


@dataclass(frozen=True)
class StatementSource:
    """Describes one logical statement source (folder on disk → institution/product).

    Attributes:
        source_id:        Unique slug — stable key across restarts.
        institution_type: Matches InstitutionType enum (used for parser routing).
        account_family:   Institution brand slug.
        account_product:  Human-readable product label shown in UI.
        bucket:           "investments" or "banking".
        root_path:        Absolute path to the folder root for this source.
        glob_pattern:     Pattern passed to Path.glob() — recurses into YYYY/ by default.
        filename_hints:   Optional fragments used for display labeling (not routing).
        institution_slug: catalog institution slug.
        account_slug:     catalog account slug.
    """
    source_id: str
    institution_type: str
    account_family: str
    account_product: str
    bucket: str
    root_path: Path
    glob_pattern: str = "**/*.pdf"
    filename_hints: list[str] = field(default_factory=list)
    institution_slug: str = ""
    account_slug: str = ""


def _build_sources() -> list[StatementSource]:
    root = get_statements_root()
    sources = []
    for entry in ACCOUNT_CATALOG:
        source_id = f"{entry.institution_slug}__{entry.account_slug}"
        sources.append(StatementSource(
            source_id=source_id,
            institution_type=entry.parser_type,
            account_family=entry.institution_slug,
            account_product=f"{entry.institution_label} — {entry.account_label}",
            bucket=entry.bucket,
            root_path=root / entry.rel_path,
            institution_slug=entry.institution_slug,
            account_slug=entry.account_slug,
        ))
    return sources


STATEMENT_SOURCES: list[StatementSource] = _build_sources()

SOURCES_BY_ID: dict[str, StatementSource] = {s.source_id: s for s in STATEMENT_SOURCES}

SOURCES_BY_SLUGS: dict[tuple[str, str], StatementSource] = {
    (s.institution_slug, s.account_slug): s for s in STATEMENT_SOURCES
}

PARSEABLE_INSTITUTION_TYPES: frozenset[str] = frozenset({
    "morgan_stanley", "chase", "etrade", "amex", "discover"
})
