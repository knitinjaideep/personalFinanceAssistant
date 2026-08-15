"""Service/API tests for PR 15 Monthly Coral Close."""

from __future__ import annotations

from datetime import date

from app.db import repositories as repo
from app.db.engine import get_session
from app.domain.plan_vs_actual import Period
from app.services import monthly_close as service


async def _make_account(session, *, institution_type="chase", account_type="checking", suffix="1"):
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
    session, account_id, statement_id, *,
    day, description, amount, transaction_type="purchase", master_bucket: str | None = None,
    cash_flow_type: str | None = None, category: str | None = None,
):
    payload = {
        "account_id": account_id,
        "statement_id": statement_id,
        "transaction_date": date(2026, 8, day),
        "description": description,
        "amount": amount,
        "transaction_type": transaction_type,
    }
    if master_bucket is not None:
        payload["master_bucket"] = master_bucket
    if cash_flow_type is not None:
        payload["cash_flow_type"] = cash_flow_type
    if category is not None:
        payload["classification_category"] = category
    await repo.bulk_create_transactions(session, [payload])


async def test_monthly_close_summarizes_income_buckets_drivers_goals_and_next_plan(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id,
            day=1, description="ACME PAYROLL", amount="10000.00", transaction_type="deposit",
        )
        await _add_txn(
            session, acct.id, stmt.id,
            day=2, description="RENT PAYMENT", amount="-5000.00",
        )
        await _add_txn(
            session, acct.id, stmt.id,
            day=3, description="FANCY RESTAURANT", amount="-2900.00",
        )

    async with get_session() as session:
        close = await service.get_monthly_close(
            session, Period.for_month(2026, 8), generated_on=date(2026, 9, 5),
        )

    assert close.period.label == "2026-08"
    assert close.is_completed_month is True
    labels = [line.label for line in close.line_items]
    assert labels == ["Income", "Needs", "Wants", "Savings", "Investments"]
    assert close.line_items[0].actual_amount == "10000.00"
    wants = next(line for line in close.line_items if line.label == "Wants")
    assert wants.status == "danger"
    assert close.needs_attention
    assert close.biggest_drivers
    assert len(close.goal_progress) <= 3
    assert len(close.next_month_plan) <= 3


async def test_monthly_close_api_accepts_start_end_date(temp_db):
    from app.api.monthly_close import get_monthly_close

    async with get_session() as session:
        acct, stmt = await _make_account(session, suffix="2")
        await _add_txn(
            session, acct.id, stmt.id,
            day=1, description="ACME PAYROLL", amount="10000.00", transaction_type="deposit",
        )

    result = await get_monthly_close(
        year=None, month=None, start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
    )
    assert result.period.start == date(2026, 8, 1)
    assert result.period.end == date(2026, 8, 31)
