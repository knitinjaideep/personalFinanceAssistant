"""
Deterministic data-availability answers.

Handles questions like:
- "What data is available?"
- "What institutions do I have data for?"
- "Which statements were uploaded?"
- "Show me what's been parsed."

These queries hit metadata tables directly — no vector search, no LLM.
"""

from __future__ import annotations

import re
from typing import Optional

import structlog

from app.api.schemas.answer_schemas import ProseAnswer

logger = structlog.get_logger(__name__)

# Patterns that indicate a data-availability / metadata question
_AVAILABILITY_PATTERNS = re.compile(
    r"(what (data|info|information) (is|do I have|are) available"
    r"|what (do I have|is available|have I uploaded)"
    r"|show me what('s| is| has been) (available|uploaded|parsed|ingested)"
    r"|which (statements?|documents?|institutions?|accounts?|files?) "
    r"(have been|were|are|do I have|exist)"
    r"|what (institutions?|banks?|brokerages?|accounts?) do I have"
    r"|list my (accounts?|institutions?|statements?|documents?)"
    r"|show my (accounts?|institutions?|statements?|documents?)"
    r"|what('s| is| has been) (been )?(uploaded|parsed|ingested|processed)"
    r"|data (summary|overview|status)"
    r"|what can I ask about"
    r"|what do you know about my finances"
    r")",
    re.IGNORECASE,
)


def is_data_availability_question(question: str) -> bool:
    """Return True if the question is asking about what data exists."""
    return bool(_AVAILABILITY_PATTERNS.search(question))


async def build_data_availability_answer(
    question: str,
    bucket_ids: Optional[list[str]] = None,
) -> ProseAnswer:
    """
    Query metadata tables and build a deterministic summary of available data.

    Never calls the LLM. Returns a StructuredAnswer with a prose summary.
    """
    from app.database.engine import get_session
    from sqlalchemy import text

    summary_parts: list[str] = []
    details: list[str] = []

    async with get_session() as session:
        # 1. Documents
        row = (await session.execute(text(
            "SELECT COUNT(*) FROM statement_documents"
        ))).first()
        doc_count = row[0] if row else 0

        # Parsed vs pending
        # Get counts by status
        status_rows = (await session.execute(text(
            "SELECT document_status, COUNT(*) FROM statement_documents GROUP BY document_status"
        ))).fetchall()
        status_counts = {r[0]: r[1] for r in status_rows}
        completed_count = status_counts.get("processed", 0) + status_counts.get("completed", 0)
        failed_count = status_counts.get("failed", 0)
        deleted_count = status_counts.get("deleted", 0)
        pending_count = doc_count - completed_count - failed_count - deleted_count
        # Use active document count (exclude deleted)
        active_doc_count = doc_count - deleted_count

        # 2. Institutions
        rows = (await session.execute(text(
            "SELECT name, institution_type FROM institutions ORDER BY name"
        ))).fetchall()
        institution_names = [r[0] for r in rows]

        # 3. Accounts
        rows = (await session.execute(text(
            "SELECT a.account_number_masked, a.account_type, i.name "
            "FROM accounts a JOIN institutions i ON a.institution_id = i.id "
            "ORDER BY i.name, a.account_type"
        ))).fetchall()
        account_lines = [
            f"  - {r[2]}: {r[1]} account ({r[0]})" for r in rows
        ]

        # 4. Statements
        row = (await session.execute(text(
            "SELECT COUNT(*) FROM statements"
        ))).first()
        statement_count = row[0] if row else 0

        # Statement date range
        row = (await session.execute(text(
            "SELECT MIN(period_start), MAX(period_end) FROM statements"
        ))).first()
        date_range = None
        if row and row[0] and row[1]:
            date_range = f"{row[0]} to {row[1]}"

        # 5. Record counts
        row_txn = (await session.execute(text("SELECT COUNT(*) FROM transactions"))).first()
        row_fee = (await session.execute(text("SELECT COUNT(*) FROM fees"))).first()
        row_hold = (await session.execute(text("SELECT COUNT(*) FROM holdings"))).first()
        row_bal = (await session.execute(text("SELECT COUNT(*) FROM balance_snapshots"))).first()
        txn_count = row_txn[0] if row_txn else 0
        fee_count = row_fee[0] if row_fee else 0
        hold_count = row_hold[0] if row_hold else 0
        bal_count = row_bal[0] if row_bal else 0

    # Build summary
    if active_doc_count == 0:
        summary = (
            "No documents have been uploaded yet. "
            "Upload a financial statement PDF from the Home tab to get started."
        )
        return ProseAnswer(
            text=summary,
            title="No data available",
            confidence=1.0,
            suggested_followups=["Upload a statement to get started."],
        )

    summary_parts.append(f"You have **{active_doc_count} document(s)** uploaded")
    if completed_count:
        summary_parts.append(f"{completed_count} successfully parsed")
    if failed_count:
        summary_parts.append(f"{failed_count} failed")
    if pending_count > 0:
        summary_parts.append(f"{pending_count} pending")

    summary = ", ".join(summary_parts) + "."

    # Institutions
    if institution_names:
        details.append(f"**Institutions:** {', '.join(institution_names)}")

    # Accounts
    if account_lines:
        details.append("**Accounts:**\n" + "\n".join(account_lines))

    # Statements
    if statement_count:
        stmt_line = f"**Parsed statements:** {statement_count}"
        if date_range:
            stmt_line += f" (covering {date_range})"
        details.append(stmt_line)

    # Records
    record_parts = []
    if txn_count:
        record_parts.append(f"{txn_count} transactions")
    if fee_count:
        record_parts.append(f"{fee_count} fees")
    if hold_count:
        record_parts.append(f"{hold_count} holdings")
    if bal_count:
        record_parts.append(f"{bal_count} balance snapshots")
    if record_parts:
        details.append(f"**Extracted records:** {', '.join(record_parts)}")

    full_summary = summary + "\n\n" + "\n\n".join(details)

    return ProseAnswer(
        text=full_summary,
        title="Data Summary",
        confidence=1.0,
        suggested_followups=[
            "How much did I pay in fees?",
            "Show my recent transactions.",
            "What are my account balances?",
        ],
    )
