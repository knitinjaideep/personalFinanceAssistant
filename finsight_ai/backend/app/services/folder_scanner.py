"""
Folder scanner — scans Coral statement folders and returns document counts/summaries.

Uses the statement catalog as the folder registry instead of the old FOLDER_REGISTRY.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TypedDict

from app.config import settings
from app.config.statement_catalog import ACCOUNT_CATALOG, get_statements_root


class FolderSummary(TypedDict):
    folder_key: str
    label: str
    bucket: str
    institution_type: str
    file_count: int
    latest_file_date: str | None
    latest_filename: str | None


class RecentFile(TypedDict):
    filename: str
    folder_label: str
    institution_type: str
    bucket: str
    modified_date: str
    size_bytes: int


class FolderScanResult(TypedDict):
    folders: list[FolderSummary]
    total_files: int
    investments_total: int
    banking_total: int
    recent_files: list[RecentFile]


def scan_folders(recent_limit: int = 10) -> FolderScanResult:
    """
    Scan all catalog-registered folders and return counts + recent files.
    Does NOT hit the database — pure filesystem scan.
    """
    statements_root = get_statements_root()
    all_files: list[tuple[Path, dict]] = []
    summaries: list[FolderSummary] = []

    for entry in ACCOUNT_CATALOG:
        folder_path = statements_root / entry.rel_path
        folder_path.mkdir(parents=True, exist_ok=True)

        pdfs = sorted(
            folder_path.glob("**/*.pdf"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        latest_file = pdfs[0] if pdfs else None
        latest_date: str | None = None
        if latest_file:
            mtime = latest_file.stat().st_mtime
            latest_date = datetime.fromtimestamp(mtime).date().isoformat()

        summaries.append(FolderSummary(
            folder_key=entry.rel_path,
            label=f"{entry.institution_label} — {entry.account_label}",
            bucket=entry.bucket,
            institution_type=entry.parser_type,
            file_count=len(pdfs),
            latest_file_date=latest_date,
            latest_filename=latest_file.name if latest_file else None,
        ))

        for pdf in pdfs:
            all_files.append((pdf, {
                "label": f"{entry.institution_label} — {entry.account_label}",
                "institution_type": entry.parser_type,
                "bucket": entry.bucket,
            }))

    all_files.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)

    recent: list[RecentFile] = []
    for pdf, meta in all_files[:recent_limit]:
        mtime = pdf.stat().st_mtime
        recent.append(RecentFile(
            filename=pdf.name,
            folder_label=meta["label"],
            institution_type=meta["institution_type"],
            bucket=meta["bucket"],
            modified_date=datetime.fromtimestamp(mtime).date().isoformat(),
            size_bytes=pdf.stat().st_size,
        ))

    inv_total  = sum(s["file_count"] for s in summaries if s["bucket"] == "investments")
    bank_total = sum(s["file_count"] for s in summaries if s["bucket"] == "banking")

    return FolderScanResult(
        folders=summaries,
        total_files=inv_total + bank_total,
        investments_total=inv_total,
        banking_total=bank_total,
        recent_files=recent,
    )
