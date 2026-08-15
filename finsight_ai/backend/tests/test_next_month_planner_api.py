"""Service/API wiring tests for PR 14 Next Month Planner.

Mirrors backend/tests/test_investment_plan_api.py's pattern: call the FastAPI
route function directly against a temp DB (seeded with the default plan +
default savings goals by `init_db()` via the `temp_db` fixture), rather than
spinning up a full HTTP client.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from app.api.next_month_planner import get_next_month_plan
from app.db import repositories as repo
from app.db.engine import get_session
from app.domain.next_month_planner import MAX_RECOMMENDATIONS


async def _make_account(session, *, institution_type: str, account_type: str, suffix: str):
    inst = await repo.get_or_create_institution(session, institution_type, institution_type.title())
    acct = await repo.get_or_create_account(
        session, institution_id=inst.id, institution_type=institution_type,
        account_number_masked=f"****{suffix}", account_type=account_type,
    )
    doc = await repo.create_document(
        session, original_filename=f"{suffix}.pdf", stored_filename=f"{suffix}.pdf",
        file_path=f"/tmp/{suffix}.pdf", file_size_bytes=1, mime_type="application/pdf",
        status="parsed", institution_type=institution_type,
    )
    stmt = await repo.create_statement(
        session, document_id=doc.id, institution_id=inst.id, institution_type=institution_type,
        account_id=acct.id, account_type=account_type, statement_type="bank",
        period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
        extraction_status="success", overall_confidence=0.9, warnings="[]",
    )
    return acct, stmt


async def _add_txn(
    session, account_id: str, statement_id: str, *, description: str, amount: str,
    transaction_type: str, master_bucket: str, cash_flow_type: str, category: str | None,
):
    await repo.bulk_create_transactions(session, [{
        "account_id": account_id,
        "statement_id": statement_id,
        "transaction_date": date(2026, 8, 15),
        "description": description,
        "amount": amount,
        "transaction_type": transaction_type,
        "master_bucket": master_bucket,
        "classification_category": category,
        "cash_flow_type": cash_flow_type,
        "classification_source": "deterministic_rule",
        "classification_confidence": 1.0,
        "needs_review": False,
    }])


async def test_api_returns_ranked_recommendations_capped_at_three(temp_db):
    async with get_session() as session:
        checking, checking_stmt = await _make_account(
            session, institution_type="chase", account_type="checking", suffix="1001",
        )
        await _add_txn(
            session, checking.id, checking_stmt.id, description="ACME PAYROLL DIRECT DEP",
            amount="10000.00", transaction_type="deposit", master_bucket="unclassified",
            cash_flow_type="income", category=None,
        )
        # Needs way over target (50% * 10000 = 5000).
        await _add_txn(
            session, checking.id, checking_stmt.id, description="RENT", amount="-8000.00",
            transaction_type="withdrawal", master_bucket="needs", cash_flow_type="expense",
            category="Housing",
        )
        # Wants way over target (20% * 10000 = 2000).
        await _add_txn(
            session, checking.id, checking_stmt.id, description="DINING OUT", amount="-3000.00",
            transaction_type="withdrawal", master_bucket="wants", cash_flow_type="expense",
            category="Dining",
        )

    result = await get_next_month_plan(year=2026, month=8)

    assert result.period.label == "2026-08"
    assert len(result.recommendations) <= MAX_RECOMMENDATIONS
    assert len(result.recommendations) >= 1
    priorities = [r.priority for r in result.recommendations]
    assert priorities == sorted(priorities)
    assert priorities == list(range(1, len(result.recommendations) + 1))


async def test_api_no_income_yields_no_recommendations(temp_db):
    async with get_session() as session:
        checking, checking_stmt = await _make_account(
            session, institution_type="chase", account_type="checking", suffix="1002",
        )
        await _add_txn(
            session, checking.id, checking_stmt.id, description="GROCERY", amount="-50.00",
            transaction_type="withdrawal", master_bucket="needs", cash_flow_type="expense",
            category="Groceries",
        )

    result = await get_next_month_plan(year=2026, month=8)
    assert result.recommendations == []


# ── PR 05's both-or-neither start/end date period contract ─────────────────

async def test_api_start_date_without_end_date_is_rejected(temp_db):
    with pytest.raises(HTTPException) as exc_info:
        await get_next_month_plan(year=None, month=None, start_date=date(2026, 8, 1), end_date=None)
    assert exc_info.value.status_code == 422


async def test_api_start_and_end_date_together_scope_the_period(temp_db):
    async with get_session() as session:
        checking, checking_stmt = await _make_account(
            session, institution_type="chase", account_type="checking", suffix="1003",
        )
        await _add_txn(
            session, checking.id, checking_stmt.id, description="ACME PAYROLL DIRECT DEP",
            amount="10000.00", transaction_type="deposit", master_bucket="unclassified",
            cash_flow_type="income", category=None,
        )

    result = await get_next_month_plan(
        year=None, month=None, start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
    )
    assert result.period.start == date(2026, 8, 1)
    assert result.period.end == date(2026, 8, 31)


async def test_api_requires_a_period(temp_db):
    with pytest.raises(HTTPException) as exc_info:
        await get_next_month_plan(year=None, month=None, start_date=None, end_date=None)
    assert exc_info.value.status_code == 422
