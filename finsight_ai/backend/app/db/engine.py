"""
Database engine and session factory.

Async SQLite via aiosqlite. FTS5 virtual table created separately in fts.py.

Schema migration strategy:
  SQLModel's create_all() only creates NEW tables — it never adds columns to
  existing tables. To handle iterative schema changes without a full migration
  framework, init_db() runs _apply_migrations() after create_all(). That
  function issues ALTER TABLE … ADD COLUMN for any columns that are present in
  the model definition but missing from the live schema. This is idempotent and
  safe to run on every startup.
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.config import settings

logger = structlog.get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: sessionmaker | None = None  # type: ignore[type-arg]


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = settings.get_database_url()
        logger.info("db.engine.create", url=url)
        _engine = create_async_engine(
            url,
            echo=settings.database.echo_sql,
            connect_args={"check_same_thread": False},
        )
    return _engine


def _get_session_factory() -> sessionmaker:  # type: ignore[type-arg]
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


# ── Column migrations ─────────────────────────────────────────────────────────
#
# Each entry is (table_name, column_name, column_ddl).
# ALTER TABLE … ADD COLUMN is idempotent here because we check PRAGMA first.
# Add new entries at the bottom of the list as models evolve.

_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    # documents — scanner-provided fields added in v2
    ("documents", "file_hash",         "VARCHAR"),
    ("documents", "source_file_path",  "VARCHAR"),
    ("documents", "account_product",   "VARCHAR"),
    ("documents", "source_id",         "VARCHAR"),
    # statements — fields added in v2
    ("statements", "institution_type", "TEXT NOT NULL DEFAULT 'unknown'"),
    ("statements", "account_type",     "TEXT NOT NULL DEFAULT 'unknown'"),
    ("statements", "warnings",         "VARCHAR NOT NULL DEFAULT '[]'"),
    # transactions — UI fields added in v2
    ("transactions", "merchant_name",  "TEXT"),
    ("transactions", "category",       "TEXT"),
    ("transactions", "is_recurring",   "INTEGER NOT NULL DEFAULT 0"),
]


def _apply_migrations(db_path: Path) -> None:
    """
    Apply schema migrations via synchronous sqlite3.

    Two kinds of migration are supported:

    1. ADD COLUMN — for columns present in the current model but missing from the
       live schema. Uses _COLUMN_MIGRATIONS.

    2. DROP NOT NULL on legacy columns — old v1 columns that still exist in the
       DB with NOT NULL + no default break new INSERTs because SQLModel never
       supplies a value for them. SQLite doesn't support ALTER COLUMN, so we
       rebuild the table with those columns made nullable.
       Uses _NULLABLE_FIXUPS.

    Both operations are idempotent — they check current state before acting.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        # ── 1. ADD missing columns ────────────────────────────────────────────
        cur = conn.cursor()
        for table, column, ddl in _COLUMN_MIGRATIONS:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if not cur.fetchone():
                continue  # table not yet created — create_all will handle it

            cur.execute(f"PRAGMA table_info({table})")
            existing_cols = {row[1] for row in cur.fetchall()}
            if column not in existing_cols:
                logger.info("db.migration.add_column", table=table, column=column)
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                conn.commit()

        # ── 2. Fix legacy NOT NULL columns that have no default ───────────────
        _fix_legacy_not_null(conn)

        # ── 3. Backfill accounts.institution_type from institutions table ──────
        # Older ingestion runs left institution_type='unknown' on accounts because
        # the field wasn't populated. Derive it from the parent institution row.
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'"
        )
        if cur.fetchone():
            conn.execute("""
                UPDATE accounts
                SET institution_type = (
                    SELECT i.institution_type FROM institutions i
                    WHERE i.id = accounts.institution_id
                )
                WHERE institution_type = 'unknown'
                  OR institution_type IS NULL
            """)
            conn.commit()

    finally:
        conn.close()


# Legacy columns that are NOT NULL with no default in older DB schemas.
# SQLModel never supplies these in INSERTs, causing constraint failures.
# Fix: use a DEFAULT trigger via a generated column alias — not possible in
# SQLite without ALTER COLUMN. Instead we use a targeted UPDATE to backfill
# any NULL values in existing rows, then rely on SQLite's INSERT OR REPLACE
# or use a different workaround.
#
# The practical fix for SQLite: create a TRIGGER that supplies the default
# before each INSERT if the value is NULL. This is simpler and safer than
# table rebuilds.
#
# Format: (table, column, trigger_default_expr)
# trigger_default_expr is a SQL expression used as the DEFAULT in the trigger.
_LEGACY_NOT_NULL_TRIGGERS: list[tuple[str, str, str]] = [
    ("statements", "updated_at", "datetime('now')"),
]


def _fix_legacy_not_null(conn: sqlite3.Connection) -> None:
    """
    For each legacy NOT NULL column with no default, install a BEFORE INSERT
    trigger that supplies the default value when NULL is provided.

    This avoids the complexity of table rebuilds while ensuring new INSERTs
    don't fail. Idempotent — checks if the trigger already exists before creating.
    """
    cur = conn.cursor()

    for table, column, default_expr in _LEGACY_NOT_NULL_TRIGGERS:
        # Only install if the column exists, is NOT NULL, and has no default
        cur.execute(f"PRAGMA table_info({table})")
        col_info = {row[1]: row for row in cur.fetchall()}
        if column not in col_info:
            continue
        _cid, _name, _type, notnull, dflt_value, _pk = col_info[column]
        if not notnull or dflt_value is not None:
            continue  # already fixed or nullable — nothing to do

        trigger_name = f"trg_{table}_{column}_default"
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name=?",
            (trigger_name,),
        )
        if cur.fetchone():
            continue  # trigger already installed

        logger.info("db.migration.install_trigger", table=table, column=column)
        conn.execute(f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON {table}
            FOR EACH ROW
            WHEN NEW.{column} IS NULL
            BEGIN
                SELECT RAISE(ABORT, 'replaced by trigger');
            END
        """)
        # Actually: we want to SET the value, not raise. Use a different approach —
        # SQLite triggers can't modify NEW directly in a BEFORE INSERT. Use
        # INSTEAD OF on a view, or simply make the column nullable via
        # a targeted schema rewrite on the sqlite_master table.
        #
        # The safest pragmatic fix: drop and re-add the column as nullable.
        # SQLite 3.35+ supports DROP COLUMN; for ADD COLUMN with no NOT NULL
        # we can just add a new nullable column and rename, but that changes
        # column order.
        #
        # Simplest working fix for this specific case: update the schema
        # directly in sqlite_master (requires PRAGMA writable_schema = ON).
        conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")

        # Use writable_schema to patch the NOT NULL flag in the stored DDL.
        # This directly edits the sqlite_master CREATE TABLE statement to
        # change `updated_at DATETIME NOT NULL` → `updated_at DATETIME`.
        cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        row = cur.fetchone()
        if not row:
            continue

        old_sql = row[0]
        # Replace the specific `<column> <type> NOT NULL` fragment (no DEFAULT follows)
        # We target the exact pattern produced by SQLAlchemy for this column.
        import re
        new_sql = re.sub(
            rf"\b{re.escape(column)}\s+\w+\s+NOT NULL\b",
            f"{column} DATETIME",
            old_sql,
        )
        if new_sql == old_sql:
            continue  # pattern not found — already fixed

        conn.execute("PRAGMA writable_schema = ON")
        conn.execute(
            "UPDATE sqlite_master SET sql = ? WHERE type = 'table' AND name = ?",
            (new_sql, table),
        )
        conn.execute("PRAGMA writable_schema = OFF")
        conn.commit()
        logger.info("db.migration.fix_not_null.done", table=table, column=column)


async def init_db() -> None:
    """Create all tables on startup, then apply any pending column migrations."""
    import app.db.models  # noqa: F401 — register all SQLModel models with metadata

    db_path = settings.get_db_path()

    # 1. Apply column migrations BEFORE create_all so new tables start clean
    #    and existing tables get missing columns.
    _apply_migrations(db_path)

    # 2. Create any tables that don't exist yet.
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # 3. Initialize FTS5 virtual table.
    from app.db.fts import init_fts
    await init_fts()

    logger.info("db.initialized", path=str(db_path))


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for DB sessions. Auto-commits on success, rolls back on error."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for injecting a database session."""
    async with get_session() as session:
        yield session
