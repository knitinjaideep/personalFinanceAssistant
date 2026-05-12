"""
Catalog API — serves the statement catalog to the frontend for upload dropdowns.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config.statement_catalog import (
    ACCOUNT_CATALOG,
    CATALOG_BY_INSTITUTION,
    INSTITUTION_SLUGS,
    MONTH_LABELS,
    SUPPORTED_YEARS,
    AccountCatalogEntry,
    get_statements_root,
    normalize_filename,
)

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


def _entry_to_dict(e: AccountCatalogEntry) -> dict:
    return {
        "institution_slug": e.institution_slug,
        "institution_label": e.institution_label,
        "account_slug": e.account_slug,
        "account_label": e.account_label,
        "bucket": e.bucket,
        "parser_type": e.parser_type,
        "parseable": e.parseable,
        "rel_path": e.rel_path,
        "supported_years": sorted(e.supported_years, reverse=True),
    }


@router.get("/institutions")
async def list_institutions():
    """Return all institutions with their accounts."""
    result = []
    for slug in INSTITUTION_SLUGS:
        accounts = CATALOG_BY_INSTITUTION[slug]
        result.append({
            "institution_slug": slug,
            "institution_label": accounts[0].institution_label,
            "accounts": [
                {
                    "account_slug": a.account_slug,
                    "account_label": a.account_label,
                    "bucket": a.bucket,
                    "parseable": a.parseable,
                    "supported_years": sorted(a.supported_years, reverse=True),
                }
                for a in accounts
            ],
        })
    return result


@router.get("/months")
async def list_months():
    """Return month number → label mapping."""
    return [{"month": k, "label": v} for k, v in sorted(MONTH_LABELS.items())]


@router.get("/destination-preview")
async def destination_preview(
    institution_slug: str,
    account_slug: str,
    year: int,
    month: int,
):
    """Return the canonical destination path preview for an upload."""
    from app.config.statement_catalog import CATALOG_BY_SLUGS
    entry = CATALOG_BY_SLUGS.get((institution_slug, account_slug))
    if entry is None:
        return {"error": f"Unknown account: {institution_slug}/{account_slug}"}

    root = get_statements_root()
    filename = normalize_filename(account_slug, year, month)
    rel = f"{entry.rel_path}/{year}/{filename}"
    abs_path = str(root / entry.rel_path / str(year) / filename)

    return {
        "rel_path": rel,
        "abs_path": abs_path,
        "filename": filename,
        "institution_label": entry.institution_label,
        "account_label": entry.account_label,
        "bucket": entry.bucket,
    }
