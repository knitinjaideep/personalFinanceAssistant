"""Service/API wiring tests for PR 10 Banking Insights."""

from __future__ import annotations

from datetime import date

from app.api.dashboard import get_banking_insights
from app.db import repositories as repo
from app.db.engine import get_session


async def _make_account(session, *, suffix: str):
    inst = await repo.get_or_create_institution(session, "chase", "Chase")
    acct = await repo.get_or_create_account(
        session,
        institution_id=inst.id,
        institution_type="chase",
        account_number_masked=f"****{suffix}",
        account_type="checking",
    )
    doc = await repo.create_document(
        session,
        original_filename=f"{suffix}.pdf",
        stored_filename=f"{suffix}.pdf",
        file_path=f"/tmp/{suffix}.pdf",
        file_size_bytes=1,
        mime_type="application/pdf",
        status="parsed",
        institution_type="chase",
    )
    stmt = await repo.create_statement(
        session,
        document_id=doc.id,
        institution_id=inst.id,
        institution_type="chase",
        account_id=acct.id,
        account_type="checking",
        statement_type="bank",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        extraction_status="success",
        overall_confidence=0.9,
        warnings="[]",
    )
    return acct, stmt


async def _add_txn(
    session,
    account_id: str,
    statement_id: str,
    *,
    txn_date: date,
    description: str,
    amount: str,
    needs_review: bool = False,
):
    await repo.bulk_create_transactions(session, [{
        "account_id": account_id,
        "statement_id": statement_id,
        "transaction_date": txn_date,
        "description": description,
        "amount": amount,
        "transaction_type": "deposit" if amount.startswith("-") is False else "purchase",
        "master_bucket": "unclassified",
        "cash_flow_type": "income" if amount.startswith("-") is False else "expense",
        "classification_source": "unknown" if needs_review else "deterministic_rule",
        "classification_confidence": 0.0 if needs_review else 1.0,
        "needs_review": needs_review,
    }])


async def test_banking_insights_scopes_classification_uncertainty_by_account_and_period(temp_db):
    async with get_session() as session:
        acct_a, stmt_a = await _make_account(session, suffix="1001")
        acct_b, stmt_b = await _make_account(session, suffix="2002")

        await _add_txn(
            session, acct_a.id, stmt_a.id,
            txn_date=date(2026, 8, 1), description="PAYCHECK A", amount="1000.00",
        )
        await _add_txn(
            session, acct_b.id, stmt_b.id,
            txn_date=date(2026, 8, 1), description="PAYCHECK B", amount="1000.00",
        )
        await _add_txn(
            session, acct_a.id, stmt_a.id,
            txn_date=date(2026, 8, 2), description="A UNKNOWN 1", amount="-40.00",
            needs_review=True,
        )
        await _add_txn(
            session, acct_a.id, stmt_a.id,
            txn_date=date(2026, 8, 3), description="A UNKNOWN 2", amount="-60.00",
            needs_review=True,
        )
        await _add_txn(
            session, acct_a.id, stmt_a.id,
            txn_date=date(2026, 7, 31), description="A OLD UNKNOWN", amount="-999.00",
            needs_review=True,
        )
        await _add_txn(
            session, acct_b.id, stmt_b.id,
            txn_date=date(2026, 8, 2), description="B UNKNOWN", amount="-70.00",
            needs_review=True,
        )

    result = await get_banking_insights(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        account_id=acct_a.id,
    )

    uncertainty = next(i for i in result.insights if i.type == "classification_uncertainty")
    assert uncertainty.impact_amount == "100.00"
    assert "2 transactions need review" in uncertainty.summary
