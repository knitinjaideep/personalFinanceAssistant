"""Service/API wiring tests for PR 11 Investment Contribution Plan."""

from __future__ import annotations

from datetime import date

from app.api.investment_plan import get_investment_contribution_plan
from app.db import repositories as repo
from app.db.engine import get_session


async def _make_account(
    session,
    *,
    institution_type: str,
    account_type: str,
    suffix: str,
):
    inst = await repo.get_or_create_institution(
        session, institution_type, institution_type.title(),
    )
    acct = await repo.get_or_create_account(
        session,
        institution_id=inst.id,
        institution_type=institution_type,
        account_number_masked=f"****{suffix}",
        account_type=account_type,
    )
    doc = await repo.create_document(
        session,
        original_filename=f"{suffix}.pdf",
        stored_filename=f"{suffix}.pdf",
        file_path=f"/tmp/{suffix}.pdf",
        file_size_bytes=1,
        mime_type="application/pdf",
        status="parsed",
        institution_type=institution_type,
    )
    stmt = await repo.create_statement(
        session,
        document_id=doc.id,
        institution_id=inst.id,
        institution_type=institution_type,
        account_id=acct.id,
        account_type=account_type,
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
    description: str,
    amount: str,
    transaction_type: str,
    master_bucket: str,
    cash_flow_type: str,
    category: str | None,
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


async def test_api_get_investment_contribution_plan_uses_default_targets(temp_db):
    async with get_session() as session:
        checking, checking_stmt = await _make_account(
            session, institution_type="chase", account_type="checking", suffix="1001",
        )
        brokerage, brokerage_stmt = await _make_account(
            session,
            institution_type="etrade",
            account_type="individual_brokerage",
            suffix="2002",
        )
        await _add_txn(
            session,
            checking.id,
            checking_stmt.id,
            description="ACME PAYROLL DIRECT DEP",
            amount="10000.00",
            transaction_type="deposit",
            master_bucket="unclassified",
            cash_flow_type="income",
            category=None,
        )
        await _add_txn(
            session,
            brokerage.id,
            brokerage_stmt.id,
            description="ETF CONTRIBUTION",
            amount="200.00",
            transaction_type="transfer",
            master_bucket="investments",
            cash_flow_type="investment_contribution",
            category="Taxable Brokerage",
        )

    result = await get_investment_contribution_plan(year=2026, month=8)

    assert result.period.label == "2026-08"
    assert result.plannable_income == "10000.00"
    assert result.total_target_pct == "15"
    assert result.total_actual_amount == "200.00"
    taxable = next(v for v in result.vehicles if v.vehicle == "Taxable Brokerage")
    assert taxable.target_pct == "2"
    assert taxable.target_amount == "200.00"
    assert taxable.actual_amount == "200.00"
