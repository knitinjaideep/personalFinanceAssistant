"""
Cache service — three-tier local caching for performance.

Why each cache exists:

1. EMBEDDING CACHE: nomic-embed-text is fast but embedding the same chunk text
   repeatedly (on re-ingestion, re-queries) wastes CPU. A content-hash keyed
   SQLite cache eliminates redundant embedding calls for identical text.

2. LLM TASK CACHE: Classification and extraction prompts for well-known patterns
   are deterministic (same PDF section → same extraction prompt → same result).
   Caching by (model, task, prompt_hash) avoids repeated Ollama calls for
   unchanged document sections during re-ingestion.

3. RETRIEVAL CACHE: The same question asked twice over the same document set
   should return the same chunks without hitting Chroma again. A short-TTL
   in-memory cache handles hot repeated queries.

Design principles:
- All cache keys are stable content hashes (SHA-256, first 16 chars).
- Embedding + LLM caches persist to SQLite (survive restarts).
- Retrieval cache is in-memory with TTL (fresh per session, no disk I/O).
- Cache misses are silent — the caller falls through to the real computation.
- Cache invalidation: embedding + retrieval caches are invalidated when a
  document's embeddings are deleted (DeletionService calls invalidate_document).
- LLM task cache has a configurable max_age_days (default 30).
- All caching is opt-in via the ``cache`` section of settings (default enabled).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

logger = structlog.get_logger(__name__)

# ── SQLite schema ──────────────────────────────────────────────────────────────
# Both persistent caches share a single SQLite file to reduce the number of
# open file handles. The schema is idempotent (CREATE TABLE IF NOT EXISTS).

_SCHEMA = """
CREATE TABLE IF NOT EXISTS embedding_cache (
    key        TEXT    PRIMARY KEY,
    vector_json TEXT   NOT NULL,
    text_hash   TEXT   NOT NULL,
    model       TEXT   NOT NULL,
    created_at  REAL   NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_task_cache (
    key         TEXT   PRIMARY KEY,
    response    TEXT   NOT NULL,
    model       TEXT   NOT NULL,
    task        TEXT   NOT NULL,
    prompt_hash TEXT   NOT NULL,
    created_at  REAL   NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_task_created ON llm_task_cache (created_at);
CREATE INDEX IF NOT EXISTS idx_embed_text_hash  ON embedding_cache (text_hash);
"""


# ── Hashing helpers ────────────────────────────────────────────────────────────

def _hash(text: str) -> str:
    """Return the first 16 hex chars of the SHA-256 hash of ``text``."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _cache_key(parts: list[str]) -> str:
    """Combine multiple string parts into a single stable cache key."""
    return _hash("|".join(parts))


# ── Embedding cache ────────────────────────────────────────────────────────────

class EmbeddingCache:
    """
    SQLite-backed cache for embedding vectors.

    Key = hash(model + text).  Value = embedding vector stored as a JSON
    array. The ``text_hash`` column allows bulk invalidation when a set of
    chunks is deleted (e.g. when a document is removed from the system).

    Thread safety: aiosqlite serialises writes, so concurrent async tasks are
    safe without additional locking.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open the SQLite connection and create tables if they do not exist."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        logger.info("embedding_cache.initialized", path=self._db_path)

    async def get(self, model: str, text: str) -> list[float] | None:
        """
        Return the cached embedding vector for (model, text), or ``None`` on miss.
        """
        if self._conn is None:
            return None
        key = _cache_key([model, text])
        async with self._conn.execute(
            "SELECT vector_json FROM embedding_cache WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            logger.debug("embedding_cache.hit", key=key)
            return json.loads(row[0])
        return None

    async def put(self, model: str, text: str, vector: list[float]) -> None:
        """Store an embedding vector in the cache."""
        if self._conn is None:
            return
        key = _cache_key([model, text])
        text_hash = _hash(text)
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO embedding_cache
                (key, vector_json, text_hash, model, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key, json.dumps(vector), text_hash, model, time.time()),
        )
        await self._conn.commit()

    async def invalidate_by_text_hash(self, text_hash: str) -> int:
        """
        Delete all cached entries whose source text matches ``text_hash``.

        Returns the number of rows deleted.
        """
        if self._conn is None:
            return 0
        cursor = await self._conn.execute(
            "DELETE FROM embedding_cache WHERE text_hash = ?", (text_hash,)
        )
        await self._conn.commit()
        deleted: int = cursor.rowcount
        if deleted:
            logger.info("embedding_cache.invalidated", text_hash=text_hash, rows=deleted)
        return deleted

    async def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None


# ── LLM task cache ─────────────────────────────────────────────────────────────

class LLMTaskCache:
    """
    SQLite-backed cache for deterministic LLM task results.

    Appropriate for: institution classification prompts, extraction prompts on
    repeated content, SQL generation for identical questions.

    NOT appropriate for: chat responses (those depend on retrieval context that
    can change as new documents are ingested).

    Key = hash(model + task + prompt).  Entries expire after ``max_age_days``.
    """

    def __init__(self, db_path: str, max_age_days: int = 30) -> None:
        self._db_path = db_path
        self._max_age_seconds = max_age_days * 86_400
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open the SQLite connection and create tables if they do not exist."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        logger.info("llm_task_cache.initialized", path=self._db_path)

    async def get(self, model: str, task: str, prompt: str) -> str | None:
        """
        Return the cached LLM response for (model, task, prompt), or ``None``
        on a cache miss or expired entry.
        """
        if self._conn is None:
            return None
        key = _cache_key([model, task, prompt])
        min_time = time.time() - self._max_age_seconds
        async with self._conn.execute(
            """
            SELECT response FROM llm_task_cache
            WHERE key = ? AND created_at > ?
            """,
            (key, min_time),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            logger.debug("llm_task_cache.hit", task=task)
            return row[0]
        return None

    async def put(self, model: str, task: str, prompt: str, response: str) -> None:
        """Store an LLM task response in the cache."""
        if self._conn is None:
            return
        key = _cache_key([model, task, prompt])
        prompt_hash = _hash(prompt)
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO llm_task_cache
                (key, response, model, task, prompt_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (key, response, model, task, prompt_hash, time.time()),
        )
        await self._conn.commit()

    async def evict_expired(self) -> int:
        """
        Delete all entries that exceed the configured max age.

        Returns the number of rows deleted.  Safe to call periodically as a
        background maintenance task.
        """
        if self._conn is None:
            return 0
        min_time = time.time() - self._max_age_seconds
        cursor = await self._conn.execute(
            "DELETE FROM llm_task_cache WHERE created_at < ?", (min_time,)
        )
        await self._conn.commit()
        deleted: int = cursor.rowcount
        if deleted:
            logger.info("llm_task_cache.evicted_expired", rows=deleted)
        return deleted

    async def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None


# ── Retrieval cache ────────────────────────────────────────────────────────────

class RetrievalCache:
    """
    In-memory TTL cache for retrieval results.

    Appropriate for: repeated queries over the same document set within a
    session — e.g. a user asking two similar fee questions back-to-back.

    TTL default: 300 seconds (5 minutes) — short enough to remain fresh as
    new documents are ingested.

    Key = hash(normalised_question + sorted(bucket_ids)).
    Capacity: configurable ``max_size`` entries; evicts the soonest-to-expire
    entry when the cache is full.
    """

    def __init__(self, ttl_seconds: int = 300, max_size: int = 200) -> None:
        self._ttl = ttl_seconds
        self._max_size = max_size
        # Store: key → (expiry_timestamp, value)
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    def _key(self, question: str, bucket_ids: list[str] | None) -> str:
        bucket_str = ",".join(sorted(bucket_ids or []))
        return _cache_key([question.strip().lower(), bucket_str])

    async def get(self, question: str, bucket_ids: list[str] | None) -> Any | None:
        """
        Return the cached retrieval result for (question, bucket_ids), or
        ``None`` on a cache miss or expired entry.
        """
        key = self._key(question, bucket_ids)
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expiry, value = entry
            if time.time() > expiry:
                del self._store[key]
                return None
            logger.debug("retrieval_cache.hit", question_prefix=question[:40])
            return value

    async def put(
        self, question: str, bucket_ids: list[str] | None, value: Any
    ) -> None:
        """Store a retrieval result in the cache, evicting if over capacity."""
        key = self._key(question, bucket_ids)
        async with self._lock:
            if len(self._store) >= self._max_size:
                # Evict the entry with the soonest expiry (already-expired or
                # nearest-to-expiring).
                oldest_key = min(self._store, key=lambda k: self._store[k][0])
                del self._store[oldest_key]
            self._store[key] = (time.time() + self._ttl, value)

    async def invalidate_all(self) -> None:
        """Clear all cached retrieval results (e.g. after a new ingestion)."""
        async with self._lock:
            count = len(self._store)
            self._store.clear()
        if count:
            logger.info("retrieval_cache.invalidated_all", entries=count)


# ── Module-level singletons ────────────────────────────────────────────────────
# Caches are initialised once during app startup and reused across requests.

_embedding_cache: EmbeddingCache | None = None
_llm_task_cache: LLMTaskCache | None = None
_retrieval_cache: RetrievalCache | None = None


async def initialize_caches(
    cache_db_path: str = "data/db/finsight_cache.db",
    llm_cache_max_age_days: int = 30,
    retrieval_ttl_seconds: int = 300,
    retrieval_max_size: int = 200,
) -> None:
    """
    Initialise all three caches.

    Should be called once during FastAPI app startup (inside the ``lifespan``
    context manager).  Safe to call multiple times — subsequent calls are
    no-ops unless the singletons have been cleared by ``close_caches``.

    Args:
        cache_db_path:          Path to the shared SQLite file for persistent
                                caches.  Parent directories are created if
                                absent.
        llm_cache_max_age_days: How many days to retain LLM task cache entries
                                before eviction.
        retrieval_ttl_seconds:  TTL for in-memory retrieval cache entries.
        retrieval_max_size:     Maximum number of entries in the retrieval
                                cache before the oldest is evicted.
    """
    global _embedding_cache, _llm_task_cache, _retrieval_cache

    _embedding_cache = EmbeddingCache(cache_db_path)
    await _embedding_cache.initialize()

    _llm_task_cache = LLMTaskCache(cache_db_path, max_age_days=llm_cache_max_age_days)
    await _llm_task_cache.initialize()

    _retrieval_cache = RetrievalCache(
        ttl_seconds=retrieval_ttl_seconds,
        max_size=retrieval_max_size,
    )

    logger.info(
        "caches.initialized",
        db=cache_db_path,
        llm_max_age_days=llm_cache_max_age_days,
        retrieval_ttl=retrieval_ttl_seconds,
    )


async def close_caches() -> None:
    """
    Close all persistent cache connections.

    Called during app shutdown to flush any pending writes and release file
    handles.
    """
    global _embedding_cache, _llm_task_cache, _retrieval_cache

    if _embedding_cache:
        await _embedding_cache.close()
        _embedding_cache = None

    if _llm_task_cache:
        await _llm_task_cache.close()
        _llm_task_cache = None

    _retrieval_cache = None
    logger.info("caches.closed")


# ── Accessor helpers ───────────────────────────────────────────────────────────
# Other modules import these rather than the singletons directly so they stay
# decoupled from the initialisation order.

def get_embedding_cache() -> EmbeddingCache | None:
    """Return the global EmbeddingCache instance (None if not initialised)."""
    return _embedding_cache


def get_llm_task_cache() -> LLMTaskCache | None:
    """Return the global LLMTaskCache instance (None if not initialised)."""
    return _llm_task_cache


def get_retrieval_cache() -> RetrievalCache | None:
    """Return the global RetrievalCache instance (None if not initialised)."""
    return _retrieval_cache
