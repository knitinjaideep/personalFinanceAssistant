"""
Folder scanner — scans fixed local folders and returns document counts/summaries.

This service treats the filesystem as the source of truth for document
organisation. UI shows summaries per folder, not every individual file.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from app.config import FOLDER_REGISTRY, settings


class FolderSummary(TypedDict):
    folder_key: str          # e.g. "data/investments/morgan_stanley"
    label: str               # e.g. "Morgan Stanley"
    bucket: str              # "investments" | "banking"
    institution_type: str    # e.g. "morgan_stanley"
    file_count: int
    latest_file_date: str | None   # ISO date string of newest PDF mtime
    latest_filename: str | None


class FolderScanResult(TypedDict):
    folders: list[FolderSummary]
    total_files: int
    investments_total: int
    banking_total: int
    recent_files: list[RecentFile]


class RecentFile(TypedDict):
    filename: str
    folder_label: str
    institution_type: str
    bucket: str
    modified_date: str   # ISO date string
    size_bytes: int


def scan_folders(recent_limit: int = 10) -> FolderScanResult:
    """
    Scan all registered folders and return counts + recent files.
    Does NOT hit the database — pure filesystem scan.
    """
    base_dir = settings.base_dir   # e.g. finsight_ai/
    all_files: list[tuple[Path, dict]] = []

    summaries: list[FolderSummary] = []
    for entry in FOLDER_REGISTRY:
        folder_path = base_dir / entry["path"]   # base_dir / data/investments/...
        folder_path.mkdir(parents=True, exist_ok=True)

        pdfs = sorted(
            folder_path.glob("*.pdf"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        latest_file = pdfs[0] if pdfs else None
        latest_date: str | None = None
        if latest_file:
            mtime = latest_file.stat().st_mtime
            latest_date = datetime.fromtimestamp(mtime).date().isoformat()

        summaries.append(FolderSummary(
            folder_key=entry["path"],
            label=entry["label"],
            bucket=entry["bucket"],
            institution_type=entry["institution_type"],
            file_count=len(pdfs),
            latest_file_date=latest_date,
            latest_filename=latest_file.name if latest_file else None,
        ))

        for pdf in pdfs:
            all_files.append((pdf, entry))

    # Sort all files by mtime descending for recent list
    all_files.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)

    recent: list[RecentFile] = []
    for pdf, entry in all_files[:recent_limit]:
        mtime = pdf.stat().st_mtime
        recent.append(RecentFile(
            filename=pdf.name,
            folder_label=entry["label"],
            institution_type=entry["institution_type"],
            bucket=entry["bucket"],
            modified_date=datetime.fromtimestamp(mtime).date().isoformat(),
            size_bytes=pdf.stat().st_size,
        ))

    inv_total = sum(s["file_count"] for s in summaries if s["bucket"] == "investments")
    bank_total = sum(s["file_count"] for s in summaries if s["bucket"] == "banking")

    return FolderScanResult(
        folders=summaries,
        total_files=inv_total + bank_total,
        investments_total=inv_total,
        banking_total=bank_total,
        recent_files=recent,
    )
