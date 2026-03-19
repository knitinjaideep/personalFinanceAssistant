"""
Phase 3 — Migration 001: Add bucket_type, institution_type, account_type
                          (denormalized), category, merchant_name, is_recurring
                          columns to support bucket-aware analytics.

Run this script once against the existing SQLite database:
    python migrations/phase3_001_add_bucket_and_category_columns.py

SQLite does not support ALTER TABLE ... ADD COLUMN with NOT NULL unless a
DEFAULT is provided.  All new columns are NULLABLE or have a DEFAULT so this
migration is non-destructive and safe to run on a populated database.

Existing rows will have NULL for nullable columns and the DEFAULT value for
columns with defaults.  The application handles NULL gracefully in all
analytics queries.
"""

import sqlite3
import sys
from pathlib import Path

# Resolve DB path relative to this script's location.
_DB_PATH = Path(__file__).parent.parent.parent / "data" / "db" / "finsight.db"


def _add_column_if_missing(
    cursor: sqlite3.Cursor,
    table: str,
    column: str,
    column_def: str,
) -> None:
    """Add a column only if it does not already exist (idempotent)."""
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
        print(f"  + {table}.{column}")
    else:
        print(f"  = {table}.{column} (already exists, skipped)")


def run_migration(db_path: Path) -> None:
    print(f"Connecting to: {db_path}")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        print("\n[institutions]")
        _add_column_if_missing(
            cursor, "institutions", "bucket_type", "TEXT DEFAULT NULL"
        )

        print("\n[accounts]")
        _add_column_if_missing(
            cursor, "accounts", "institution_type", "TEXT NOT NULL DEFAULT 'unknown'"
        )
        _add_column_if_missing(
            cursor, "accounts", "bucket_type", "TEXT DEFAULT NULL"
        )

        print("\n[statements]")
        _add_column_if_missing(
            cursor, "statements", "institution_type", "TEXT NOT NULL DEFAULT 'unknown'"
        )
        _add_column_if_missing(
            cursor, "statements", "account_type", "TEXT NOT NULL DEFAULT 'unknown'"
        )
        _add_column_if_missing(
            cursor, "statements", "bucket_type", "TEXT DEFAULT NULL"
        )

        print("\n[transactions]")
        _add_column_if_missing(
            cursor, "transactions", "merchant_name", "TEXT DEFAULT NULL"
        )
        _add_column_if_missing(
            cursor, "transactions", "category", "TEXT DEFAULT NULL"
        )
        _add_column_if_missing(
            cursor, "transactions", "is_recurring", "INTEGER NOT NULL DEFAULT 0"
        )

        print("\n[buckets]")
        # Rename institution_type to bucket_type (safe: just add new column;
        # old institution_type column remains for existing data compatibility).
        _add_column_if_missing(
            cursor, "buckets", "bucket_type", "TEXT DEFAULT NULL"
        )

        print("\n[derived_monthly_metrics]")
        _add_column_if_missing(
            cursor, "derived_monthly_metrics", "institution_type",
            "TEXT NOT NULL DEFAULT 'unknown'"
        )
        _add_column_if_missing(
            cursor, "derived_monthly_metrics", "bucket_type", "TEXT DEFAULT NULL"
        )
        _add_column_if_missing(
            cursor, "derived_monthly_metrics", "total_spend", "TEXT DEFAULT NULL"
        )
        _add_column_if_missing(
            cursor, "derived_monthly_metrics", "spend_groceries", "TEXT DEFAULT NULL"
        )
        _add_column_if_missing(
            cursor, "derived_monthly_metrics", "spend_restaurants", "TEXT DEFAULT NULL"
        )
        _add_column_if_missing(
            cursor, "derived_monthly_metrics", "spend_subscriptions", "TEXT DEFAULT NULL"
        )
        _add_column_if_missing(
            cursor, "derived_monthly_metrics", "spend_travel", "TEXT DEFAULT NULL"
        )
        _add_column_if_missing(
            cursor, "derived_monthly_metrics", "spend_shopping", "TEXT DEFAULT NULL"
        )
        _add_column_if_missing(
            cursor, "derived_monthly_metrics", "spend_gas", "TEXT DEFAULT NULL"
        )
        _add_column_if_missing(
            cursor, "derived_monthly_metrics", "spend_utilities", "TEXT DEFAULT NULL"
        )
        _add_column_if_missing(
            cursor, "derived_monthly_metrics", "spend_healthcare", "TEXT DEFAULT NULL"
        )
        _add_column_if_missing(
            cursor, "derived_monthly_metrics", "spend_other", "TEXT DEFAULT NULL"
        )

        # ── Back-fill bucket_type from institution_type where possible ─────────
        print("\n[back-fill bucket_type from institution_type]")
        bucket_map = {
            "morgan_stanley": "investments",
            "etrade": "investments",
            "chase": "banking",
            "amex": "banking",
            "discover": "banking",
        }
        for inst, bucket in bucket_map.items():
            for table in ("institutions", "accounts", "statements"):
                cursor.execute(
                    f"UPDATE {table} SET bucket_type = ? "
                    f"WHERE institution_type = ? AND bucket_type IS NULL",
                    (bucket, inst),
                )
            print(f"  Back-filled {inst} → {bucket}")

        conn.commit()
        print("\nMigration completed successfully.")

    except Exception as exc:
        conn.rollback()
        print(f"\nMigration FAILED: {exc}", file=sys.stderr)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    if not _DB_PATH.exists():
        print(f"Database not found at {_DB_PATH}. Start the server once to create it.", file=sys.stderr)
        sys.exit(1)
    run_migration(_DB_PATH)
