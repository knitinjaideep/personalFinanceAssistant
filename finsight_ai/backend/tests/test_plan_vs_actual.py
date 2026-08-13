"""
DB-integration tests for the Plan vs Actual engine (PR 04).

Pure domain-level invariant coverage lives in
backend/tests/financial_invariants/test_plan_vs_actual_invariants.py. This
file exercises the service layer (app.services.plan_vs_actual) against a real
temp SQLite DB: multi-account aggregation, month boundaries, plan-version
resolution by period, auto-classification of never-classified transactions,
and the thin API layer.
"""

from __future__ import annotations

from datetime import date

from app.db import repositories as repo
from app.db.engine import get_session
from app.domain.entities import AllocationInput
from app.domain.plan_vs_actual import Period
from app.domain.transaction_classification import MasterBucket
from app.services import financial_plan as plan_service
from app.services import plan_vs_actual as service


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
    session, account_id, statement_id, *, day, description, amount, transaction_type="purchase",
):
    await repo.bulk_create_transactions(session, [{
        "account_id": account_id, "statement_id": statement_id,
        "transaction_date": date(2026, 8, day), "description": description,
        "amount": amount, "transaction_type": transaction_type,
    }])


# ── Multi-account aggregation ───────────────────────────────────────────────

async def test_multi_account_aggregation_via_db(temp_db):
    async with get_session() as session:
        checking, checking_stmt = await _make_account(
            session, account_type="checking", suffix="1001",
        )
        card, card_stmt = await _make_account(
            session, institution_type="amex", account_type="credit_card", suffix="2002",
        )
        await _add_txn(
            session, checking.id, checking_stmt.id,
            day=5, description="WHOLE FOODS MARKET", amount="-60.00",
        )
        await _add_txn(
            session, card.id, card_stmt.id,
            day=6, description="TRADER JOE GROCERY", amount="-40.00",
        )

    async with get_session() as session:
        result = await service.get_plan_vs_actual(session, Period.for_month(2026, 8))
    needs = next(b for b in result.buckets if b.bucket == MasterBucket.NEEDS)
    assert needs.actual_amount == "100.00"
    assert needs.transaction_count == 2


# ── Month boundaries ─────────────────────────────────────────────────────────

async def test_month_boundary_transactions_are_correctly_scoped(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=31, description="ELECTRIC UTILITY BILL",
            amount="-30.00", transaction_type="payment",
        )
        # July 31 (outside August) — reuse the July period via a distinct statement date.
        await repo.bulk_create_transactions(session, [{
            "account_id": acct.id, "statement_id": stmt.id,
            "transaction_date": date(2026, 7, 31), "description": "PSEG ELECTRIC PAYMENT",
            "amount": "-999.00", "transaction_type": "payment",
        }])
        # September 1 (outside August)
        await repo.bulk_create_transactions(session, [{
            "account_id": acct.id, "statement_id": stmt.id,
            "transaction_date": date(2026, 9, 1), "description": "PSEG ELECTRIC PAYMENT",
            "amount": "-888.00", "transaction_type": "payment",
        }])

    async with get_session() as session:
        result = await service.get_plan_vs_actual(session, Period.for_month(2026, 8))
    needs = next(b for b in result.buckets if b.bucket == MasterBucket.NEEDS)
    # Only the Aug 31 transaction (-30.00) is in scope; July 31 / Sep 1 excluded.
    assert needs.actual_amount == "30.00"
    assert needs.transaction_count == 1


# ── Plan version resolution by period (never "just the latest") ────────────

async def test_plan_version_change_does_not_rewrite_current_period(temp_db):
    future_effective = date(date.today().year + 2, 1, 1)
    async with get_session() as session:
        await plan_service.create_plan_version(
            session, effective_from=future_effective,
            allocations=[
                AllocationInput(bucket_name="needs", percentage="45"),
                AllocationInput(bucket_name="wants", percentage="25"),
                AllocationInput(bucket_name="savings", percentage="15"),
                AllocationInput(bucket_name="investments", percentage="15"),
            ],
            notes="future replan",
        )

    current_period = Period.for_month(date.today().year, date.today().month)
    future_period = Period.for_month(future_effective.year, 6)

    async with get_session() as session:
        current_result = await service.get_plan_vs_actual(session, current_period)
        future_result = await service.get_plan_vs_actual(session, future_period)

    current_needs = next(b for b in current_result.buckets if b.bucket == MasterBucket.NEEDS)
    future_needs = next(b for b in future_result.buckets if b.bucket == MasterBucket.NEEDS)
    assert current_needs.target_percentage == "50"
    assert future_needs.target_percentage == "45"


# ── Missing classifications are auto-classified before aggregating ─────────

async def test_never_classified_transactions_are_backfilled_before_aggregating(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=10, description="STARBUCKS STORE #1", amount="-6.25",
        )

    async with get_session() as session:
        txns = await repo.list_transactions(session, account_id=acct.id)
        assert txns[0].classification_source is None  # never classified yet

    async with get_session() as session:
        result = await service.get_plan_vs_actual(session, Period.for_month(2026, 8))
    wants = next(b for b in result.buckets if b.bucket == MasterBucket.WANTS)
    assert wants.actual_amount == "6.25"

    async with get_session() as session:
        txns = await repo.list_transactions(session, account_id=acct.id)
        assert txns[0].classification_source is not None  # backfilled as a side effect


async def test_user_override_survives_plan_vs_actual_auto_classification(temp_db):
    """Auto-classification must never clobber a prior user override — it only
    ever touches classification_source IS NULL rows."""
    from app.services.transaction_classification import TransactionClassificationService

    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=10, description="STARBUCKS STORE #1", amount="-6.25",
        )

    async with get_session() as session:
        txn_id = (await repo.list_transactions(session, account_id=acct.id))[0].id

    svc = TransactionClassificationService()
    async with get_session() as session:
        await svc.apply_user_override(
            session, txn_id, master_bucket=MasterBucket.NEEDS,
            cash_flow_type="expense", category="Groceries",
        )

    async with get_session() as session:
        result = await service.get_plan_vs_actual(session, Period.for_month(2026, 8))
    needs = next(b for b in result.buckets if b.bucket == MasterBucket.NEEDS)
    wants = next(b for b in result.buckets if b.bucket == MasterBucket.WANTS)
    assert needs.actual_amount == "6.25"
    assert wants.actual_amount == "0.00"


# ── Coverage-aware hybrid end-to-end (Option C, docs/coral-redesign/BLOCKED.md) ──

async def test_blocked_md_worked_example_savings_actual_is_1500_not_0(temp_db):
    """End-to-end reproduction of the exact scenario that blocked this PR: a
    real Chase checking statement with a $10,000 payroll deposit and a
    `TRANSFER TO MARCUS SAVINGS -1500.00` line, with NO Marcus statement ever
    ingested (Marcus is a catalog-only stub, `parseable=False` — no
    account_type == "savings" row can exist). Under the old
    destination-leg-only rule this read Savings actual $0.00 / OFF_TRACK. The
    coverage-aware hybrid must report Savings actual $1,500.00 instead."""
    async with get_session() as session:
        checking, checking_stmt = await _make_account(
            session, institution_type="chase", account_type="checking", suffix="9001",
        )
        await _add_txn(
            session, checking.id, checking_stmt.id,
            day=1, description="ACME CORP PAYROLL DIRECT DEP", amount="10000.00",
            transaction_type="deposit",
        )
        await _add_txn(
            session, checking.id, checking_stmt.id,
            day=3, description="TRANSFER TO MARCUS SAVINGS", amount="-1500.00",
            transaction_type="transfer",
        )

    async with get_session() as session:
        result = await service.get_plan_vs_actual(session, Period.for_month(2026, 8))

    savings = next(b for b in result.buckets if b.bucket == MasterBucket.SAVINGS)
    assert savings.actual_amount == "1500.00"  # not "0.00"
    # 15% of $10,000 income target met exactly -> on track, not "-$1,500 / OFF_TRACK".
    assert savings.variance_percentage_points == "0.00"
    assert savings.status.value == "on_track"
    assert result.completeness.origin_only_transfer_legs_count == 0


# ── Category / merchant drill-down ──────────────────────────────────────────

async def test_bucket_and_merchant_drilldown_via_service(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=5, description="WHOLE FOODS MARKET", amount="-60.00",
        )
        await _add_txn(
            session, acct.id, stmt.id, day=6, description="WHOLE FOODS MARKET", amount="-25.00",
        )
        await _add_txn(
            session, acct.id, stmt.id, day=7, description="SHELL GAS STATION", amount="-40.00",
        )

    async with get_session() as session:
        categories = await service.get_bucket_breakdown(
            session, Period.for_month(2026, 8), MasterBucket.NEEDS,
        )
    groceries = next(c for c in categories if c.category == "Groceries")
    assert groceries.actual_amount == "85.00"

    async with get_session() as session:
        drivers = await service.get_merchant_drivers(
            session, Period.for_month(2026, 8), bucket=MasterBucket.NEEDS, top_n=5,
        )
    top = drivers[0]
    assert top.merchant.upper().startswith("WHOLE FOODS")
    assert top.amount == "85.00"


# ── API layer smoke test ────────────────────────────────────────────────────

async def test_api_get_plan_vs_actual_returns_default_plan_targets(temp_db):
    from app.api.plan_vs_actual import get_plan_vs_actual as api_get_plan_vs_actual

    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=5, description="WHOLE FOODS MARKET", amount="-60.00",
        )

    result = await api_get_plan_vs_actual(year=2026, month=8)
    assert result.period.label == "2026-08"
    needs = next(b for b in result.buckets if b.bucket == MasterBucket.NEEDS)
    assert needs.target_percentage == "50"
    assert needs.actual_amount == "60.00"
    assert result.completeness.income_observed is False
