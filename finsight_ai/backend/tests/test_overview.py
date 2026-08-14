"""
DB-integration tests for the Overview page service/API (PR 06 —
app.services.overview / app.api.overview). Mirrors the pattern in
test_plan_vs_actual.py: exercises the service layer against a real temp
SQLite DB, plus a couple of direct API-function smoke tests.

Pure domain-level coverage (ranking, materiality, caps, honesty invariants)
lives in backend/tests/financial_invariants/test_overview_insights_invariants.py.
"""

from __future__ import annotations

from datetime import date

from app.db import repositories as repo
from app.db.engine import get_session
from app.domain.plan_vs_actual import Period
from app.services import overview as service


async def _make_account(session, *, institution_type="chase", account_type="checking", suffix="1"):
    inst = await repo.get_or_create_institution(session, institution_type, institution_type.title())
    acct = await repo.get_or_create_account(
        session, institution_id=inst.id, institution_type=institution_type,
        account_number_masked=f"****{suffix}", account_type=account_type,
    )
    doc = await repo.create_document(
        session, original_filename="s.pdf", stored_filename="s.pdf",
        file_path="/tmp/s.pdf", file_size_bytes=1, mime_type="application/pdf",
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
    day, description, amount, transaction_type="purchase", month=8,
):
    await repo.bulk_create_transactions(session, [{
        "account_id": account_id, "statement_id": statement_id,
        "transaction_date": date(2026, month, day), "description": description,
        "amount": amount, "transaction_type": transaction_type,
    }])


# ── get_overview_insights: end-to-end status + insights + next month plan ──

async def test_overview_insights_reports_off_plan_wants_overspend(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id,
            day=1, description="ACME PAYROLL", amount="10000.00", transaction_type="deposit",
        )
        # Needs on target.
        await _add_txn(
            session, acct.id, stmt.id,
            day=2, description="RENT PAYMENT", amount="-5000.00",
        )
        # Wants way over target (2000) -> off track.
        await _add_txn(
            session, acct.id, stmt.id,
            day=3, description="FANCY RESTAURANT", amount="-2900.00",
        )

    async with get_session() as session:
        overview = await service.get_overview_insights(session, Period.for_month(2026, 8))

    assert overview.status.data_available is True
    assert "off plan" in overview.status.headline.lower()
    assert len(overview.insights) >= 1
    assert len(overview.insights) <= 3
    assert any(i.bucket is not None and i.bucket.value == "wants" for i in overview.insights)
    assert len(overview.next_month_plan) <= 3
    assert any(item.action_type == "reduce_category" for item in overview.next_month_plan)


async def test_overview_insights_no_income_reports_not_enough_data(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id,
            day=5, description="WHOLE FOODS MARKET", amount="-60.00",
        )

    async with get_session() as session:
        overview = await service.get_overview_insights(session, Period.for_month(2026, 8))

    assert overview.status.data_available is False
    assert overview.insights == []
    assert overview.next_month_plan == []


# ── get_monthly_flow_summary: single-month vs multi-month splitting ────────

async def test_monthly_flow_summary_single_month_returns_one_row(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id,
            day=1, description="ACME PAYROLL", amount="5000.00", transaction_type="deposit",
        )
        await _add_txn(
            session, acct.id, stmt.id,
            day=2, description="RENT PAYMENT", amount="-1000.00",
        )

    async with get_session() as session:
        rows = await service.get_monthly_flow_summary(session, Period.for_month(2026, 8))

    assert len(rows) == 1
    assert rows[0].period_label == "2026-08"
    assert rows[0].income == "5000.00"
    assert rows[0].spent == "1000.00"


async def test_monthly_flow_summary_multi_month_returns_one_row_per_calendar_month(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, month=7,
            day=1, description="JULY PAYROLL", amount="4000.00", transaction_type="deposit",
        )
        await _add_txn(
            session, acct.id, stmt.id,
            day=2, description="JULY RENT", amount="-800.00", month=7,
        )
        await _add_txn(
            session, acct.id, stmt.id,
            day=1, description="AUG PAYROLL", amount="5000.00", transaction_type="deposit", month=8,
        )
        await _add_txn(
            session, acct.id, stmt.id,
            day=2, description="AUG RENT", amount="-900.00", month=8,
        )

    async with get_session() as session:
        rows = await service.get_monthly_flow_summary(
            session, Period.for_range(date(2026, 7, 1), date(2026, 8, 31)),
        )

    assert [r.period_label for r in rows] == ["2026-07", "2026-08"]
    assert rows[0].income == "4000.00"
    assert rows[0].spent == "800.00"
    assert rows[1].income == "5000.00"
    assert rows[1].spent == "900.00"


# ── API layer smoke tests ───────────────────────────────────────────────────

async def test_api_overview_insights_endpoint(temp_db):
    from app.api.overview import get_overview_insights as api_get_overview_insights

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

    result = await api_get_overview_insights(year=2026, month=8)
    assert result.period.label == "2026-08"
    assert result.status.data_available is True


async def test_api_monthly_flow_endpoint_start_end_date(temp_db):
    from app.api.overview import get_monthly_flow as api_get_monthly_flow

    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id,
            day=1, description="ACME PAYROLL", amount="10000.00", transaction_type="deposit",
        )

    rows = await api_get_monthly_flow(start_date=date(2026, 8, 1), end_date=date(2026, 8, 31))
    assert len(rows) == 1
    assert rows[0].income == "10000.00"
