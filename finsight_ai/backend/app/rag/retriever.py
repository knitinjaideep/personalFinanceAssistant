"""
Hybrid retriever — combines vector (semantic) search with SQL (structured) queries.

Architecture:
- Vector search: finds relevant document chunks from Chroma for
  open-ended natural language questions
- SQL search: runs structured queries for precise aggregations
  (total fees, specific date ranges, account comparisons)
- The retriever decides the right mix based on question analysis

The RAG chain in chat_service.py calls this retriever, then passes
results to the LLM for response generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import structlog

from app.ollama.model_router import ModelRouter, get_model_router
from app.rag.chroma_store import ChromaStore, get_chroma_store

logger = structlog.get_logger(__name__)


# Patterns that indicate a question needs SQL aggregation
_SQL_QUESTION_PATTERNS = re.compile(
    r"(how much|total|sum|average|compare|highest|lowest|most|least|"
    r"which month|which account|year|quarter|last \d+ months?|"
    r"fees?|transactions?|holdings?|balances?|accounts?|institutions?|"
    r"statements?|charges?|payments?|deposits?|withdrawals?|"
    r"show (me |my )|list |recent|what did|how many|"
    r"missing|trend|spend|cost|paid|earned|received)",
    re.IGNORECASE,
)


@dataclass
class RetrievalResult:
    """Combined result from hybrid retrieval."""

    vector_chunks: list[dict] = field(default_factory=list)
    sql_results: list[dict] = field(default_factory=list)
    sql_query: str | None = None
    context_text: str = ""    # Pre-formatted context for the LLM prompt


class HybridRetriever:
    """
    Performs hybrid (vector + SQL) retrieval for RAG-powered chat.

    Decision logic:
    - Always run vector search (handles semantic/narrative questions)
    - Run SQL when the question has aggregation keywords
    - Merge and deduplicate results before passing to LLM
    """

    def __init__(
        self,
        chroma: ChromaStore | None = None,
        model_router: ModelRouter | None = None,
    ) -> None:
        self._chroma = chroma or get_chroma_store()
        self._router = model_router or get_model_router()

    async def retrieve(
        self,
        question: str,
        institution_filter: str | None = None,
        n_vector_results: int = 6,
        bucket_ids: list[str] | None = None,
    ) -> RetrievalResult:
        """
        Retrieve relevant context for a question.

        Checks the RetrievalCache before running vector + SQL queries.  On a
        cache hit the cached RetrievalResult is returned immediately.  On a
        miss the full retrieval pipeline runs and the result is stored in the
        cache for subsequent identical queries.

        Args:
            question:           The user's natural language question.
            institution_filter: Optional institution type to filter Chroma results.
            n_vector_results:   Number of vector results to fetch.
            bucket_ids:         Optional list of bucket IDs to scope the query.
                                Used as part of the cache key so different
                                bucket scopes are cached independently.

        Returns:
            RetrievalResult with chunks, SQL results, and formatted context.
        """
        # ── Cache read ─────────────────────────────────────────────────────────
        from app.services.cache_service import get_retrieval_cache
        cache = get_retrieval_cache()
        if cache is not None:
            cached_result = await cache.get(question, bucket_ids)
            if cached_result is not None:
                return cached_result  # type: ignore[return-value]

        result = RetrievalResult()
        vector_search_ok = False

        # 1. Vector search (always)
        try:
            embedding = await self._router.embed(question)

            # Resolve bucket_ids → document_ids for Chroma filtering
            doc_ids: list[str] | None = None
            if bucket_ids:
                doc_ids = await self._resolve_document_ids(bucket_ids)
                logger.debug(
                    "retriever.bucket_filter",
                    bucket_count=len(bucket_ids),
                    doc_count=len(doc_ids) if doc_ids else 0,
                )

            # If bucket has no linked documents, fall back to unscoped search
            # instead of returning empty — documents may exist but not be linked yet.
            if bucket_ids and doc_ids is not None and len(doc_ids) == 0:
                logger.warning(
                    "retriever.bucket_empty_fallback",
                    bucket_ids=bucket_ids,
                    msg="Bucket has no linked documents; falling back to unscoped search",
                )
                doc_ids = None  # Clear filter so we search everything

            where_filter: dict | None = None
            if institution_filter and doc_ids:
                where_filter = {
                    "$and": [
                        {"institution_type": institution_filter},
                        {"document_id": {"$in": doc_ids}},
                    ]
                }
            elif doc_ids:
                where_filter = {"document_id": {"$in": doc_ids}}
            elif institution_filter:
                where_filter = {"institution_type": institution_filter}

            chunks = await self._chroma.query(
                embedding=embedding,
                n_results=n_vector_results,
                where=where_filter,
            )
            result.vector_chunks = chunks
            vector_search_ok = True
            logger.debug("retriever.vector", question_len=len(question), chunks=len(chunks))
        except Exception as exc:
            logger.warning("retriever.vector.error", error=str(exc))

        # 2. SQL search (conditional).
        # First try deterministic SQL templates for common questions (fast,
        # reliable, no LLM needed).  Fall back to LLM-generated SQL only
        # if no template matched.
        if _SQL_QUESTION_PATTERNS.search(question):
            try:
                sql_results, sql_query = await self._run_sql_retrieval(question)
                result.sql_results = sql_results
                result.sql_query = sql_query
                logger.debug("retriever.sql", rows=len(sql_results))
            except Exception as exc:
                logger.warning("retriever.sql.error", error=str(exc))

        # 3. Build context text
        result.context_text = self._format_context(result)

        # ── Cache write ────────────────────────────────────────────────────────
        if cache is not None:
            await cache.put(question, bucket_ids, result)

        return result

    async def _resolve_document_ids(self, bucket_ids: list[str]) -> list[str]:
        """
        Look up which document IDs belong to the given bucket IDs.

        Returns a flat deduplicated list of document_id strings.
        Returns an empty list on error (fails open — caller should skip filter).
        """
        from app.database.engine import get_session
        from sqlalchemy import text

        try:
            placeholders = ", ".join(f":b{i}" for i in range(len(bucket_ids)))
            params = {f"b{i}": bid for i, bid in enumerate(bucket_ids)}
            query = f"SELECT document_id FROM bucket_documents WHERE bucket_id IN ({placeholders})"
            async with get_session() as session:
                raw = await session.execute(text(query), params)
                return list({row[0] for row in raw.fetchall()})
        except Exception as exc:
            logger.warning("retriever.resolve_doc_ids.error", error=str(exc))
            return []

    async def _run_sql_retrieval(
        self, question: str
    ) -> tuple[list[dict], str]:
        """
        Execute a SQL query to answer the question.

        Strategy:
        1. Try deterministic SQL templates first (fast, reliable).
        2. Fall back to LLM-generated SQL only if no template matched.

        Returns (results, query_string).
        """
        from app.database.engine import get_session
        from app.rag.sql_templates import match_template
        from sqlalchemy import text

        # 1. Try deterministic templates
        template_match = match_template(question)
        if template_match is not None:
            sql_query, params = template_match
            logger.info("retriever.sql.template_hit", sql=sql_query[:100])
            results: list[dict] = []
            async with get_session() as session:
                try:
                    raw = await session.execute(text(sql_query), params)
                    columns = list(raw.keys())
                    for row in raw.fetchall():
                        results.append(dict(zip(columns, row)))
                except Exception as exc:
                    logger.warning(
                        "retriever.sql.template_execute_error",
                        sql=sql_query,
                        error=str(exc),
                    )
                    return [], sql_query
            if results:
                return results, sql_query
            # Template matched but returned 0 rows — fall through to LLM

        # 2. Fall back to LLM-generated SQL
        sql_query = await self._generate_sql(question)
        if not sql_query:
            return [], ""

        results = []
        async with get_session() as session:
            try:
                raw = await session.execute(text(sql_query))
                columns = list(raw.keys())
                for row in raw.fetchall():
                    results.append(dict(zip(columns, row)))
            except Exception as exc:
                logger.warning("retriever.sql.execute_error", sql=sql_query, error=str(exc))
                return [], sql_query

        return results, sql_query

    async def _generate_sql(self, question: str) -> str | None:
        """
        Use the LLM to generate a safe read-only SQL query for the question.

        Only SELECT queries are allowed; the LLM is instructed accordingly.
        """
        schema_context = """
Database schema (SQLite):
- statement_documents(id, original_filename, institution_type, document_status, page_count, upload_timestamp, processed_timestamp)
- institutions(id, name, institution_type, created_at)
- accounts(id, institution_id, account_number_masked, account_type, institution_type)
- statements(id, document_id, institution_id, account_id, statement_type, period_start, period_end, overall_confidence, institution_type)
- fees(id, account_id, statement_id, fee_date, description, amount, fee_category)
- transactions(id, account_id, statement_id, transaction_date, description, transaction_type, amount, merchant_name, category)
- balance_snapshots(id, account_id, statement_id, snapshot_date, total_value)
- holdings(id, account_id, statement_id, symbol, description, quantity, market_value)

All monetary amounts (amount, total_value, market_value) are stored as TEXT (Decimal strings).
Use CAST(amount AS REAL) for numeric operations.
Dates are stored as TEXT in YYYY-MM-DD format.
"""
        prompt = f"""{schema_context}

Generate a safe, read-only SQL SELECT query to answer this question:
"{question}"

Rules:
- Only SELECT statements
- No subqueries that could be slow on large tables
- Always include a LIMIT (max 100 rows)
- Return ONLY the SQL query, no explanation

SQL:"""

        try:
            from app.ollama.model_router import TaskType
            response = await self._router.generate(
                task=TaskType.ANALYSIS,
                prompt=prompt,
            )
            # Extract just the SQL from the response
            sql = response.strip()
            # Remove markdown code fences if present
            sql = re.sub(r"```sql\s*", "", sql)
            sql = re.sub(r"```\s*", "", sql)
            sql = sql.strip()

            # Safety check: only allow SELECT
            if not sql.upper().startswith("SELECT"):
                logger.warning("retriever.sql.rejected", reason="non-SELECT query", sql=sql[:100])
                return None

            return sql
        except Exception as exc:
            logger.warning("retriever.sql.generate_error", error=str(exc))
            return None

    def _format_context(self, result: RetrievalResult) -> str:
        """Format retrieval results into a single context string for the LLM."""
        parts: list[str] = []

        if result.vector_chunks:
            parts.append("=== Relevant Document Excerpts ===")
            for i, chunk in enumerate(result.vector_chunks[:5], 1):
                meta = chunk.get("metadata", {})
                institution = meta.get("institution_type", "")
                period = meta.get("statement_period", "")
                page = meta.get("page_number", "")
                header = f"[Excerpt {i}"
                if institution:
                    header += f" | {institution}"
                if period:
                    header += f" | {period}"
                if page:
                    header += f" | page {page}"
                header += "]"
                parts.append(f"{header}\n{chunk['text']}")

        if result.sql_results:
            parts.append("\n=== Database Query Results ===")
            if result.sql_query:
                parts.append(f"Query: {result.sql_query}")
            for row in result.sql_results[:20]:
                parts.append(str(row))

        return "\n\n".join(parts)
