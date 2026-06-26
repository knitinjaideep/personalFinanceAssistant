"""
One-time data fix: merge duplicate `accounts` rows created by a race condition
in get_or_create_account (concurrent ingestion tasks from bulk upload each ran
a check-then-act find-or-create without serialization, so several tasks saw
"no match" at once and inserted separate rows for the same logical account).

Groups accounts by (institution_id, account_number_masked, account_name),
keeps the oldest row per group as canonical, repoints all child rows
(statements, transactions, fees, holdings, balance_snapshots, derived_metrics)
to the canonical account, then deletes the now-empty duplicate account rows.

Usage: python scripts/merge_duplicate_accounts.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from sqlalchemy import text

from app.db.engine import get_session

CHILD_TABLES = [
    "statements",
    "transactions",
    "fees",
    "holdings",
    "balance_snapshots",
    "derived_metrics",
]


async def main(dry_run: bool) -> None:
    async with get_session() as session:
        rows = (await session.execute(
            text("SELECT id, institution_id, account_number_masked, account_name, created_at "
                 "FROM accounts ORDER BY created_at")
        )).fetchall()

        groups: dict[tuple, list] = defaultdict(list)
        for r in rows:
            key = (r.institution_id, r.account_number_masked, r.account_name)
            groups[key].append(r)

        dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
        if not dup_groups:
            print("No duplicate accounts found.")
            return

        total_merged = 0
        for key, accts in dup_groups.items():
            canonical = accts[0]
            dupes = accts[1:]
            print(f"\nGroup {key}: canonical={canonical.id} ({canonical.created_at}), "
                  f"merging {len(dupes)} duplicate(s)")

            for dup in dupes:
                for table in CHILD_TABLES:
                    result = await session.execute(
                        text(f"SELECT COUNT(*) FROM {table} WHERE account_id = :aid"),
                        {"aid": dup.id},
                    )
                    count = result.scalar_one()
                    if count:
                        print(f"  {table}: repointing {count} row(s) from {dup.id} -> {canonical.id}")
                        if not dry_run:
                            await session.execute(
                                text(f"UPDATE {table} SET account_id = :cid WHERE account_id = :aid"),
                                {"cid": canonical.id, "aid": dup.id},
                            )
                if not dry_run:
                    await session.execute(
                        text("DELETE FROM accounts WHERE id = :aid"), {"aid": dup.id}
                    )
                print(f"  deleted duplicate account {dup.id}")
                total_merged += 1

        if dry_run:
            print(f"\n[dry-run] Would merge {total_merged} duplicate account(s). No changes made.")
        else:
            await session.commit()
            print(f"\nMerged {total_merged} duplicate account(s).")


if __name__ == "__main__":
    asyncio.run(main(dry_run="--dry-run" in sys.argv))
