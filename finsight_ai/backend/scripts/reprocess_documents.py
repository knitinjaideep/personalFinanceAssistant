#!/usr/bin/env python
"""
Reprocess / backfill documents from the command line.

Repairs a local database whose downstream tables (transactions, chunks,
embeddings, fees, balances) were never fully populated — without re-uploading or
deleting any PDF.

Usage (run from the backend/ directory):

    python scripts/reprocess_documents.py --missing-data
    python scripts/reprocess_documents.py --failed
    python scripts/reprocess_documents.py --all
    python scripts/reprocess_documents.py --document-id <id>
    python scripts/reprocess_documents.py --health        # report only, no changes

Add --dry-run with any selector to list what WOULD be reprocessed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Make `app` importable when run as `python scripts/reprocess_documents.py`.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core.logger import configure_logging  # noqa: E402
from app.db.engine import init_db  # noqa: E402


def _print_health(report: dict) -> None:
    s = report["summary"]
    print("\n=== Ingestion Health ===")
    for k, v in s.items():
        print(f"  {k:24s} {v}")
    docs = report["documents"]
    if docs:
        print(f"\n  {len(docs)} document(s) with issues:")
        for d in docs:
            print(f"    - {d['filename']:36s} {d['status']:10s} {','.join(d['issues'])}")
    print()


async def _resolve_ids(args) -> list[str]:
    from app.services.reprocess_service import (
        all_document_ids,
        failed_document_ids,
        missing_data_document_ids,
    )

    if args.document_id:
        return [args.document_id]
    if args.all:
        return await all_document_ids()
    if args.failed:
        return await failed_document_ids()
    if args.missing_data:
        return await missing_data_document_ids()
    return []


async def _main_async(args) -> int:
    await init_db()

    from app.services.reprocess_service import ingestion_health, reprocess_document

    if args.health:
        _print_health(await ingestion_health())
        return 0

    doc_ids = await _resolve_ids(args)
    if not doc_ids:
        print("No documents matched the selector. Nothing to do.")
        print("(Use one of --all / --failed / --missing-data / --document-id <id>, or --health.)")
        return 0

    print(f"Selected {len(doc_ids)} document(s) for reprocessing.")
    if args.dry_run:
        for did in doc_ids:
            print(f"  would reprocess: {did}")
        return 0

    ok = failed = 0
    totals = {"transactions": 0, "fees": 0, "balances": 0, "chunks": 0, "embeddings": 0}
    for i, doc_id in enumerate(doc_ids, 1):
        result = await reprocess_document(doc_id)
        status = "OK " if result.ok else "FAIL"
        print(
            f"[{i}/{len(doc_ids)}] {status} {result.filename:36s} "
            f"txn={result.transactions} fee={result.fees} bal={result.balances} "
            f"chunks={result.chunks} emb={result.embeddings}"
            + (f"  ERROR: {result.error}" if result.error else "")
        )
        if result.ok:
            ok += 1
            for k in totals:
                totals[k] += getattr(result, k)
        else:
            failed += 1

    print("\n=== Summary ===")
    print(f"  succeeded: {ok}")
    print(f"  failed:    {failed}")
    print(f"  totals:    {totals}")

    print("\n=== Ingestion Health (after) ===")
    _print_health(await ingestion_health())
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocess/backfill Coral documents.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="Reprocess every document.")
    group.add_argument("--failed", action="store_true", help="Reprocess failed documents.")
    group.add_argument("--missing-data", action="store_true",
                       help="Reprocess parsed-but-incomplete documents.")
    group.add_argument("--document-id", type=str, help="Reprocess a single document by id.")
    parser.add_argument("--health", action="store_true",
                        help="Print the ingestion-health report and exit (no changes).")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be reprocessed without changing anything.")
    args = parser.parse_args()

    configure_logging()
    exit_code = asyncio.run(_main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
