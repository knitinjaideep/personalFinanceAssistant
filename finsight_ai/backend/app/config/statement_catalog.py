"""
Statement catalog — single source of truth for all institutions, accounts, and folder structure.

Maps to the fixed Coral folder layout:
  $CORAL_STATEMENTS_ROOT/
    american_express/blue_cash/2025/
    american_express/gold/2025/
    bank_of_america/2025/
    chase/checking/2025/
    chase/freedom_unlimited/2025/
    chase/prime/2025/
    chase/sapphire_preferred/2025/
    chase/united/2025/
    discover/2025/
    etrade/2025/
    marcus/emergency_fund/2025/
    marcus/arjun_fun/2025/
    morgan_stanley/nitin_ira/2025/
    morgan_stanley/pavani_ira/2025/
    morgan_stanley/joint_investments/2025/
    morgan_stanley/house_downpayment/2026/
    morgan_stanley/arjun_investment/2026/
    529/2026/

Bucket classification:
  banking     — bank_of_america, chase/checking, marcus/*
  investments — everything else (amex, chase credit cards, discover, etrade, morgan_stanley, 529)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
MONTH_NUMBERS = {name: i + 1 for i, name in enumerate(MONTHS)}
MONTH_LABELS  = {i + 1: name.title() for i, name in enumerate(MONTHS)}

SUPPORTED_YEARS = list(range(2022, 2028))

Bucket = Literal["banking", "investments"]


@dataclass(frozen=True)
class AccountCatalogEntry:
    """One logical account within an institution."""
    institution_slug: str
    institution_label: str
    account_slug: str
    account_label: str
    bucket: Bucket
    parser_type: str             # matches InstitutionType enum, or "stub"
    parseable: bool              # True = full parser exists
    rel_path: str                # path relative to CORAL_STATEMENTS_ROOT, no trailing slash
    supported_years: list[int] = field(default_factory=lambda: SUPPORTED_YEARS)


# ── Catalog ───────────────────────────────────────────────────────────────────

ACCOUNT_CATALOG: list[AccountCatalogEntry] = [
    # ── American Express ──────────────────────────────────────────────────────
    AccountCatalogEntry(
        institution_slug="american_express",
        institution_label="American Express",
        account_slug="blue_cash",
        account_label="Blue Cash",
        bucket="investments",
        parser_type="amex",
        parseable=True,
        rel_path="american_express/blue_cash",
    ),
    AccountCatalogEntry(
        institution_slug="american_express",
        institution_label="American Express",
        account_slug="gold",
        account_label="Gold Card",
        bucket="investments",
        parser_type="amex",
        parseable=True,
        rel_path="american_express/gold",
    ),

    # ── Bank of America ───────────────────────────────────────────────────────
    AccountCatalogEntry(
        institution_slug="bank_of_america",
        institution_label="Bank of America",
        account_slug="checking",
        account_label="Checking",
        bucket="banking",
        parser_type="bofa",
        parseable=False,
        rel_path="bank_of_america",
    ),

    # ── Chase ─────────────────────────────────────────────────────────────────
    AccountCatalogEntry(
        institution_slug="chase",
        institution_label="Chase",
        account_slug="checking",
        account_label="Checking",
        bucket="banking",
        parser_type="chase",
        parseable=True,
        rel_path="chase/checking",
    ),
    AccountCatalogEntry(
        institution_slug="chase",
        institution_label="Chase",
        account_slug="freedom_unlimited",
        account_label="Freedom Unlimited",
        bucket="investments",
        parser_type="chase",
        parseable=True,
        rel_path="chase/freedom_unlimited",
    ),
    AccountCatalogEntry(
        institution_slug="chase",
        institution_label="Chase",
        account_slug="prime",
        account_label="Prime Visa",
        bucket="investments",
        parser_type="chase",
        parseable=True,
        rel_path="chase/prime",
    ),
    AccountCatalogEntry(
        institution_slug="chase",
        institution_label="Chase",
        account_slug="sapphire_preferred",
        account_label="Sapphire Preferred",
        bucket="investments",
        parser_type="chase",
        parseable=True,
        rel_path="chase/sapphire_preferred",
    ),
    AccountCatalogEntry(
        institution_slug="chase",
        institution_label="Chase",
        account_slug="united",
        account_label="United Explorer",
        bucket="investments",
        parser_type="chase",
        parseable=True,
        rel_path="chase/united",
    ),

    # ── Discover ──────────────────────────────────────────────────────────────
    AccountCatalogEntry(
        institution_slug="discover",
        institution_label="Discover",
        account_slug="it",
        account_label="Discover it",
        bucket="investments",
        parser_type="discover",
        parseable=True,
        rel_path="discover",
    ),

    # ── E*TRADE ───────────────────────────────────────────────────────────────
    AccountCatalogEntry(
        institution_slug="etrade",
        institution_label="E*TRADE",
        account_slug="brokerage",
        account_label="Brokerage",
        bucket="investments",
        parser_type="etrade",
        parseable=True,
        rel_path="etrade",
    ),

    # ── Marcus (Goldman Sachs) ────────────────────────────────────────────────
    AccountCatalogEntry(
        institution_slug="marcus",
        institution_label="Marcus by Goldman Sachs",
        account_slug="emergency_fund",
        account_label="Emergency Fund",
        bucket="banking",
        parser_type="marcus",
        parseable=False,
        rel_path="marcus/emergency_fund",
    ),
    AccountCatalogEntry(
        institution_slug="marcus",
        institution_label="Marcus by Goldman Sachs",
        account_slug="arjun_fun",
        account_label="Arjun Fun",
        bucket="banking",
        parser_type="marcus",
        parseable=False,
        rel_path="marcus/arjun_fun",
    ),

    # ── Morgan Stanley ────────────────────────────────────────────────────────
    AccountCatalogEntry(
        institution_slug="morgan_stanley",
        institution_label="Morgan Stanley",
        account_slug="nitin_ira",
        account_label="Nitin IRA",
        bucket="investments",
        parser_type="morgan_stanley",
        parseable=True,
        rel_path="morgan_stanley/nitin_ira",
    ),
    AccountCatalogEntry(
        institution_slug="morgan_stanley",
        institution_label="Morgan Stanley",
        account_slug="pavani_ira",
        account_label="Pavani IRA",
        bucket="investments",
        parser_type="morgan_stanley",
        parseable=True,
        rel_path="morgan_stanley/pavani_ira",
    ),
    AccountCatalogEntry(
        institution_slug="morgan_stanley",
        institution_label="Morgan Stanley",
        account_slug="joint_investments",
        account_label="Joint Investments",
        bucket="investments",
        parser_type="morgan_stanley",
        parseable=True,
        rel_path="morgan_stanley/joint_investments",
    ),
    AccountCatalogEntry(
        institution_slug="morgan_stanley",
        institution_label="Morgan Stanley",
        account_slug="house_downpayment",
        account_label="House Downpayment",
        bucket="investments",
        parser_type="morgan_stanley",
        parseable=True,
        rel_path="morgan_stanley/house_downpayment",
        supported_years=[2026, 2027],
    ),
    AccountCatalogEntry(
        institution_slug="morgan_stanley",
        institution_label="Morgan Stanley",
        account_slug="arjun_investment",
        account_label="Arjun Investment",
        bucket="investments",
        parser_type="morgan_stanley",
        parseable=True,
        rel_path="morgan_stanley/arjun_investment",
        supported_years=[2026, 2027],
    ),

    # ── 529 ───────────────────────────────────────────────────────────────────
    AccountCatalogEntry(
        institution_slug="529",
        institution_label="529 College Savings",
        account_slug="college_savings",
        account_label="College Savings",
        bucket="investments",
        parser_type="stub",
        parseable=False,
        rel_path="529",
        supported_years=[2026, 2027],
    ),
]

# ── Indexes ───────────────────────────────────────────────────────────────────

# (institution_slug, account_slug) → entry
CATALOG_BY_SLUGS: dict[tuple[str, str], AccountCatalogEntry] = {
    (e.institution_slug, e.account_slug): e for e in ACCOUNT_CATALOG
}

# institution_slug → list of entries
CATALOG_BY_INSTITUTION: dict[str, list[AccountCatalogEntry]] = {}
for _entry in ACCOUNT_CATALOG:
    CATALOG_BY_INSTITUTION.setdefault(_entry.institution_slug, []).append(_entry)

# parser_type → list of entries (for scanner routing)
CATALOG_BY_PARSER: dict[str, list[AccountCatalogEntry]] = {}
for _entry in ACCOUNT_CATALOG:
    CATALOG_BY_PARSER.setdefault(_entry.parser_type, []).append(_entry)

# All unique institution slugs in display order
INSTITUTION_SLUGS: list[str] = list(dict.fromkeys(e.institution_slug for e in ACCOUNT_CATALOG))


def get_statements_root() -> Path:
    """Return the absolute path to CORAL_STATEMENTS_ROOT from env or default."""
    root = os.environ.get(
        "CORAL_STATEMENTS_ROOT",
        str(Path.home() / "Documents" / "Personal" / "Coral"),
    )
    return Path(root)


def get_account_root(institution_slug: str, account_slug: str) -> Path | None:
    """Return the absolute root folder for a specific account, or None if unknown."""
    entry = CATALOG_BY_SLUGS.get((institution_slug, account_slug))
    if entry is None:
        return None
    return get_statements_root() / entry.rel_path


def get_year_folder(institution_slug: str, account_slug: str, year: int) -> Path | None:
    """Return the absolute path to a year subfolder, creating it if needed."""
    root = get_account_root(institution_slug, account_slug)
    if root is None:
        return None
    return root / str(year)


def normalize_filename(account_slug: str, year: int, month: int) -> str:
    """Return canonical filename: {account_slug}_{year}_{month:02d}_{month_name}.pdf"""
    month_name = MONTHS[month - 1]
    return f"{account_slug}_{year}_{month:02d}_{month_name}.pdf"


def validate_upload(
    institution_slug: str,
    account_slug: str,
    year: int,
    month: int,
) -> AccountCatalogEntry:
    """Validate upload params. Raises ValueError if any param is invalid."""
    entry = CATALOG_BY_SLUGS.get((institution_slug, account_slug))
    if entry is None:
        raise ValueError(
            f"Unknown institution/account: {institution_slug}/{account_slug}. "
            f"Valid pairs: {sorted(CATALOG_BY_SLUGS.keys())}"
        )
    if year not in SUPPORTED_YEARS:
        raise ValueError(f"Year {year} not in supported range {SUPPORTED_YEARS}")
    if month < 1 or month > 12:
        raise ValueError(f"Month must be 1–12, got {month}")
    return entry


def safe_dest_path(institution_slug: str, account_slug: str, year: int, month: int) -> Path:
    """
    Return the canonical destination path for an upload.
    Validates that the result is strictly inside CORAL_STATEMENTS_ROOT.
    Raises ValueError on path traversal attempt.
    """
    root = get_statements_root().resolve()
    entry = CATALOG_BY_SLUGS[(institution_slug, account_slug)]
    year_folder = (root / entry.rel_path / str(year)).resolve()

    # Path traversal guard
    try:
        year_folder.relative_to(root)
    except ValueError:
        raise ValueError(f"Path traversal detected: {year_folder} is outside {root}")

    filename = normalize_filename(account_slug, year, month)
    return year_folder / filename
