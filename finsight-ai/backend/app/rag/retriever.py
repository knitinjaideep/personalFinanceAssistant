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
    r"fees? (this|last|in)|missing|trend)",
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
    ) -> RetrievalResult:
        """
        Retrieve relevant context for a question.

        Args:
            question: The user's natural language question
            institution_filter: Optional institution type to filter Chroma results
            n_vector_results: Number of vector results to fetch

        Returns:
            RetrievalResult with chunks, SQL results, and formatted context.
        """
        result = RetrievalResult()

        # 1. Vector search (always)
        try:
            embedding = await self._router.embed(question)
            where_filter = None
            if institution_filter:
                where_filter = {"institution_type": institution_filter}

            chunks = await self._chroma.query(
                embedding=embedding,
                n_results=n_vector_results,
                where=where_filter,
            )
            result.vector_chunks = chunks
            logger.debug("retriever.vector", question_len=len(question), chunks=len(chunks))
        except Exception as exc:
            logger.warning("retriever.vector.error", error=str(exc))

        # 2. SQL search (conditional)
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
        return result

    async def _run_sql_retrieval(
        self, question: str
    ) -> tuple[list[dict], str]:
        """
        Generate and execute a SQL query based on the question.

        Returns (results, query_string).
        """
        # Use the LLM to generate the SQL query
        sql_query = await self._generate_sql(question)
        if not sql_query:
            return [], ""

        # Execute the generated SQL
        from app.database.engine import get_session
        from sqlalchemy import text

        results: list[dict] = []
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
- institutions(id, name, institution_type, created_at)
- accounts(id, institution_id, account_number_masked, account_type)
- statements(id, institution_id, account_id, statement_type, period_start, period_end, overall_confidence)
- fees(id, account_id, statement_id, fee_date, description, amount, fee_category)
- transactions(id, account_id, statement_id, transaction_date, description, transaction_type, amount)
- balance_snapshots(id, account_id, statement_id, snapshot_date, total_value)
- holdings(id, account_id, statement_id, symbol, description, quantity, market_value)

All monetary amounts (amount, total_value, market_value) are stored as TEXT (Decimal strings).
Use CAST(amount AS REAL) for numeric operations.
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
