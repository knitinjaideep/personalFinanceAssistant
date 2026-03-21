"""
Statement source configuration — maps local filesystem folders to institutions.

This is the single source of truth for where statements live on disk.
The local scanner reads from these definitions to discover, hash, and
route PDFs into the ingestion pipeline.

To add a new institution:
  1. Add a StatementSource entry below.
  2. Create a parser in app/parsers/<name>/parser.py.
  3. Register the parser in app/parsers/base.py.

To add a new product for an existing institution:
  1. Add a new StatementSource with the correct root_path and filename_hints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class StatementSource:
    """Describes one logical statement source (folder on disk → institution/product).

    Attributes:
        source_id:        Unique slug, used as a stable key across restarts.
        institution_type: Matches InstitutionType enum value (used for parser routing).
        account_family:   Institution brand (e.g. "chase", "amex").
        account_product:  Human-readable product name shown in UI.
        bucket:           "investments" or "banking".
        root_path:        Absolute path to the root folder for this source.
        glob_pattern:     Pattern passed to Path.glob() — use "**/*.pdf" to recurse
                          into YYYY subdirectories.
        filename_hints:   Optional filename fragments to help the scanner label files.
                          The parser's can_handle() is the authoritative router;
                          hints are for display only.
    """
    source_id: str
    institution_type: str
    account_family: str
    account_product: str
    bucket: str                             # "investments" | "banking"
    root_path: Path
    glob_pattern: str = "**/*.pdf"          # recurse into YYYY/ subfolders by default
    filename_hints: list[str] = field(default_factory=list)


# ── Banking sources ───────────────────────────────────────────────────────────

_CORAL_ROOT = Path("/Users/nitinkotcherlakota/Documents/Personal/Coral")

STATEMENT_SOURCES: list[StatementSource] = [
    # ── Chase ──────────────────────────────────────────────────────────────
    StatementSource(
        source_id="chase_checking",
        institution_type="chase",
        account_family="chase",
        account_product="Chase Checking",
        bucket="banking",
        root_path=_CORAL_ROOT / "Chase" / "Checking",
        filename_hints=["Chase_Checking"],
    ),
    StatementSource(
        source_id="chase_freedom",
        institution_type="chase",
        account_family="chase",
        account_product="Chase Freedom Unlimited",
        bucket="banking",
        root_path=_CORAL_ROOT / "Chase" / "Checking",   # same folder, different filename
        filename_hints=["Freedom"],
    ),
    StatementSource(
        source_id="chase_prime",
        institution_type="chase",
        account_family="chase",
        account_product="Chase Prime",
        bucket="banking",
        root_path=_CORAL_ROOT / "Chase" / "Checking",
        filename_hints=["Prime"],
    ),
    StatementSource(
        source_id="chase_sapphire",
        institution_type="chase",
        account_family="chase",
        account_product="Chase Sapphire Preferred",
        bucket="banking",
        root_path=_CORAL_ROOT / "Chase" / "Checking",
        filename_hints=["Sapphire_Preferred"],
    ),

    # ── American Express ───────────────────────────────────────────────────
    StatementSource(
        source_id="amex",
        institution_type="amex",
        account_family="amex",
        account_product="American Express",
        bucket="banking",
        root_path=_CORAL_ROOT / "Amex",
    ),

    # ── Bank of America ────────────────────────────────────────────────────
    StatementSource(
        source_id="bofa",
        institution_type="bofa",          # parser stub — scanned but not yet parsed
        account_family="bofa",
        account_product="Bank of America",
        bucket="banking",
        root_path=_CORAL_ROOT / "BOFA",
    ),

    # ── Discover ───────────────────────────────────────────────────────────
    StatementSource(
        source_id="discover",
        institution_type="discover",
        account_family="discover",
        account_product="Discover",
        bucket="banking",
        root_path=_CORAL_ROOT / "Discover",
    ),

    # ── Marcus (Goldman Sachs) ─────────────────────────────────────────────
    StatementSource(
        source_id="marcus",
        institution_type="marcus",        # parser stub — scanned but not yet parsed
        account_family="marcus",
        account_product="Marcus Goldman Sachs",
        bucket="banking",
        root_path=_CORAL_ROOT / "Marcus",
    ),

    # ── Investments ────────────────────────────────────────────────────────
    StatementSource(
        source_id="etrade",
        institution_type="etrade",
        account_family="etrade",
        account_product="E*TRADE",
        bucket="investments",
        root_path=_CORAL_ROOT / "Etrade",
    ),
    StatementSource(
        source_id="morgan_stanley_ira",
        institution_type="morgan_stanley",
        account_family="morgan_stanley",
        account_product="Morgan Stanley IRA",
        bucket="investments",
        root_path=_CORAL_ROOT / "Morgan Stanley" / "IRA",
    ),
    StatementSource(
        source_id="morgan_stanley_joint",
        institution_type="morgan_stanley",
        account_family="morgan_stanley",
        account_product="Morgan Stanley Joint Investment",
        bucket="investments",
        root_path=_CORAL_ROOT / "Morgan Stanley" / "Joint Investment",
    ),
]


# Convenience: look up a source by its source_id
SOURCES_BY_ID: dict[str, StatementSource] = {s.source_id: s for s in STATEMENT_SOURCES}

# Institution types that have fully implemented parsers
PARSEABLE_INSTITUTION_TYPES: frozenset[str] = frozenset({
    "morgan_stanley", "chase", "etrade", "amex", "discover"
})
