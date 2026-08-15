"""
DB-integration tests for the Classification Review API (PR 09,
docs/coral-redesign/pr-09-classification-review.md).

The classification ENGINE and SERVICE are covered directly in
test_transaction_classification_service.py — this file exercises the new
thin API layer (app.api.classification) plus the new service orchestration
it depends on (`reclassify_transaction`, the prioritized `get_needs_review`),
and confirms a correction persisted here is visible on the very next
Plan vs Actual fetch (no separate invalidation step required).

Route functions are called directly (same convention as
test_plan_vs_actual.py's `test_api_get_plan_vs_actual_...` tests) rather than
via an HTTP TestClient — none of them depend on FastAPI request context.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.classification import (
    ReclassifyRequest,
    confirm_transaction,
    get_needs_review,
    reclassify_transaction,
)
from app.db import repositories as repo
from app.db.engine import get_session
from app.domain.classification_review import ReclassifyChoice, ReclassifyScope
from app.domain.plan_vs_actual import Period
from app.domain.transaction_classification import MasterBucket
from app.services import plan_vs_actual as pva_service


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
    session, account_id, statement_id, *, day, description, amount,
    month=8, year=2026, merchant_name=None,
):
    await repo.bulk_create_transactions(session, [{
        "account_id": account_id, "statement_id": statement_id,
        "transaction_date": date(year, month, day), "description": description,
        "amount": amount, "transaction_type": "purchase", "merchant_name": merchant_name,
    }])


async def _txn_id_for(session, account_id, description) -> str:
    txns = await repo.list_transactions(session, account_id=account_id)
    return next(t.id for t in txns if t.description == description)


# ── scope=transaction: only the one transaction is touched ─────────────────

async def test_reclassify_scope_transaction_only_touches_that_row(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        # Two Amazon transactions — known-ambiguous merchant, both would
        # land in needs_review once classified.
        await _add_txn(
            session, acct.id, stmt.id, day=5,
            description="AMAZON.COM*A1", amount="-40.00", merchant_name="Amazon",
        )
        await _add_txn(
            session, acct.id, stmt.id, day=6,
            description="AMAZON.COM*B2", amount="-25.00", merchant_name="Amazon",
        )

    async with get_session() as session:
        txn1_id = await _txn_id_for(session, acct.id, "AMAZON.COM*A1")
        txn2_id = await _txn_id_for(session, acct.id, "AMAZON.COM*B2")

    resp = await reclassify_transaction(
        txn1_id,
        ReclassifyRequest(
            master_bucket=ReclassifyChoice.WANTS, category="Shopping",
            scope=ReclassifyScope.TRANSACTION,
        ),
    )
    assert resp.transaction.master_bucket == MasterBucket.WANTS
    assert resp.transaction.needs_review is False
    assert resp.other_transactions_reclassified == 0

    async with get_session() as session:
        txn2 = await repo.get_transaction(session, txn2_id)
        # The second Amazon transaction must be completely untouched — never
        # even auto-classified as a side effect of this call.
        assert txn2.classification_source is None
        assert txn2.master_bucket is None


# ── scope=merchant_future: forward-looking only, no OTHER existing row touched ──

async def test_reclassify_scope_merchant_future_does_not_touch_other_existing_rows(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=5,
            description="AMAZON.COM*A1", amount="-40.00", merchant_name="Amazon",
        )
        await _add_txn(
            session, acct.id, stmt.id, day=6,
            description="AMAZON.COM*B2", amount="-25.00", merchant_name="Amazon",
        )

    async with get_session() as session:
        txn1_id = await _txn_id_for(session, acct.id, "AMAZON.COM*A1")
        txn2_id = await _txn_id_for(session, acct.id, "AMAZON.COM*B2")

    resp = await reclassify_transaction(
        txn1_id,
        ReclassifyRequest(
            master_bucket=ReclassifyChoice.WANTS, category="Shopping",
            scope=ReclassifyScope.MERCHANT_FUTURE,
        ),
    )
    # The reviewed transaction itself resolves (it is the subject of the action).
    assert resp.transaction.master_bucket == MasterBucket.WANTS
    assert resp.transaction.needs_review is False
    # But no OTHER existing transaction was reclassified by this call.
    assert resp.other_transactions_reclassified == 0

    async with get_session() as session:
        txn2 = await repo.get_transaction(session, txn2_id)
        assert txn2.classification_source is None
        assert txn2.master_bucket is None

    # A NEW future Amazon transaction, however, picks up the merchant rule.
    async with get_session() as session:
        await _add_txn(
            session, acct.id, stmt.id, day=20,
            description="AMAZON.COM*C3", amount="-15.00", merchant_name="Amazon",
        )
    async with get_session() as session:
        txn3_id = await _txn_id_for(session, acct.id, "AMAZON.COM*C3")

    from app.services.transaction_classification import TransactionClassificationService
    svc = TransactionClassificationService()
    async with get_session() as session:
        result = await svc.classify(session, txn3_id)
    assert result.master_bucket == MasterBucket.WANTS
    assert result.category == "Shopping"
    assert result.needs_review is False


# ── scope=merchant_this_month: bounded to same merchant + same calendar month ──

async def test_reclassify_scope_merchant_this_month_is_bounded(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        # Same merchant, same month -> should be reclassified.
        await _add_txn(
            session, acct.id, stmt.id, day=5,
            description="AMAZON.COM*A1", amount="-40.00", merchant_name="Amazon",
        )
        await _add_txn(
            session, acct.id, stmt.id, day=20,
            description="AMAZON.COM*B2", amount="-25.00", merchant_name="Amazon",
        )
        # Same merchant, DIFFERENT month -> must NOT be touched.
        await _add_txn(
            session, acct.id, stmt.id, day=5, month=7,
            description="AMAZON.COM*C3", amount="-10.00", merchant_name="Amazon",
        )
        # Different merchant, same month -> must NOT be touched.
        await _add_txn(
            session, acct.id, stmt.id, day=5,
            description="TARGET STORE #4", amount="-30.00", merchant_name="Target",
        )

    async with get_session() as session:
        txn1_id = await _txn_id_for(session, acct.id, "AMAZON.COM*A1")
        txn2_id = await _txn_id_for(session, acct.id, "AMAZON.COM*B2")
        other_month_id = await _txn_id_for(session, acct.id, "AMAZON.COM*C3")
        other_merchant_id = await _txn_id_for(session, acct.id, "TARGET STORE #4")

    resp = await reclassify_transaction(
        txn1_id,
        ReclassifyRequest(
            master_bucket=ReclassifyChoice.WANTS, category="Shopping",
            scope=ReclassifyScope.MERCHANT_THIS_MONTH,
        ),
    )
    assert resp.transaction.master_bucket == MasterBucket.WANTS
    # Exactly the one OTHER same-merchant, same-month transaction was reclassified.
    assert resp.other_transactions_reclassified == 1

    async with get_session() as session:
        txn2 = await repo.get_transaction(session, txn2_id)
        assert txn2.master_bucket == "wants"
        assert txn2.classification_category == "Shopping"
        assert txn2.classification_source == "user"
        assert txn2.needs_review is False

        other_month = await repo.get_transaction(session, other_month_id)
        assert other_month.classification_source != "user"

        other_merchant = await repo.get_transaction(session, other_merchant_id)
        assert other_merchant.classification_source != "user"


async def test_reclassify_this_month_does_not_revoke_an_earlier_user_override(temp_db):
    """A bulk 'all matching this month' action aimed at ONE transaction must
    not silently re-decide a bystander row the user already corrected by
    hand — the same tier-1 protection apply_merchant_rule documents."""
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=5,
            description="AMAZON.COM*A1", amount="-40.00", merchant_name="Amazon",
        )
        await _add_txn(
            session, acct.id, stmt.id, day=12,
            description="AMAZON.COM*B2", amount="-25.00", merchant_name="Amazon",
        )

    async with get_session() as session:
        txn1_id = await _txn_id_for(session, acct.id, "AMAZON.COM*A1")
        bystander_id = await _txn_id_for(session, acct.id, "AMAZON.COM*B2")

    # The user explicitly resolves the bystander as Needs/Groceries first.
    await reclassify_transaction(
        bystander_id,
        ReclassifyRequest(
            master_bucket=ReclassifyChoice.NEEDS, category="Groceries",
            scope=ReclassifyScope.TRANSACTION,
        ),
    )

    # ...then bulk-corrects a DIFFERENT Amazon row to Wants/Shopping.
    resp = await reclassify_transaction(
        txn1_id,
        ReclassifyRequest(
            master_bucket=ReclassifyChoice.WANTS, category="Shopping",
            scope=ReclassifyScope.MERCHANT_THIS_MONTH,
        ),
    )
    assert resp.other_transactions_reclassified == 0

    async with get_session() as session:
        bystander = await repo.get_transaction(session, bystander_id)
        assert bystander.master_bucket == "needs"
        assert bystander.classification_category == "Groceries"


# ── confirm: locks in the current classification and clears needs_review ───

async def test_confirm_locks_in_current_classification_and_clears_needs_review(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=5,
            description="COSTCO WHOLESALE #221", amount="-120.00",
        )

    async with get_session() as session:
        txn_id = await _txn_id_for(session, acct.id, "COSTCO WHOLESALE #221")

    review_before = await get_needs_review(limit=20)
    assert any(r.transaction_id == txn_id for r in review_before)

    result = await confirm_transaction(txn_id)
    assert result.needs_review is False
    assert result.source.value == "user"

    review_after = await get_needs_review(limit=20)
    assert all(r.transaction_id != txn_id for r in review_after)


async def test_confirm_unclassified_transaction_is_rejected(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await repo.bulk_create_transactions(session, [{
            "account_id": acct.id, "statement_id": stmt.id,
            "transaction_date": date(2026, 8, 5), "description": "NEVER CLASSIFIED",
            "amount": "-9.00", "transaction_type": "purchase",
        }])

    async with get_session() as session:
        txn_id = await _txn_id_for(session, acct.id, "NEVER CLASSIFIED")

    with pytest.raises(HTTPException) as exc_info:
        await confirm_transaction(txn_id)
    assert exc_info.value.status_code == 422


# ── error paths ──────────────────────────────────────────────────────────────

async def test_confirm_invalid_transaction_id_is_404(temp_db):
    with pytest.raises(HTTPException) as exc_info:
        await confirm_transaction("does-not-exist")
    assert exc_info.value.status_code == 404


async def test_reclassify_invalid_transaction_id_is_404(temp_db):
    with pytest.raises(HTTPException) as exc_info:
        await reclassify_transaction(
            "does-not-exist",
            ReclassifyRequest(
                master_bucket=ReclassifyChoice.WANTS, scope=ReclassifyScope.TRANSACTION,
            ),
        )
    assert exc_info.value.status_code == 404


async def test_reclassify_invalid_bucket_value_is_rejected_at_request_construction(temp_db):
    with pytest.raises(ValidationError):
        ReclassifyRequest(master_bucket="not_a_real_bucket", scope=ReclassifyScope.TRANSACTION)


async def test_reclassify_invalid_category_for_bucket_is_422(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=5, description="RENT PAYMENT", amount="-2000.00",
        )

    async with get_session() as session:
        txn_id = await _txn_id_for(session, acct.id, "RENT PAYMENT")

    with pytest.raises(HTTPException) as exc_info:
        await reclassify_transaction(
            txn_id,
            ReclassifyRequest(
                master_bucket=ReclassifyChoice.NEEDS, category="Dining",
                scope=ReclassifyScope.TRANSACTION,
            ),
        )
    assert exc_info.value.status_code == 422


# ── needs-review prioritization ─────────────────────────────────────────────

async def test_needs_review_prioritizes_low_confidence_and_high_impact(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        # Ambiguous merchant (confidence 0.35) and unclassified (confidence 0.0).
        await _add_txn(
            session, acct.id, stmt.id, day=5, description="COSTCO WHOLESALE #1", amount="-20.00",
        )
        await _add_txn(
            session, acct.id, stmt.id, day=6, description="MISC POS 88213", amount="-500.00",
        )
        # A second ambiguous-merchant row, much larger — must outrank the
        # small one at the SAME confidence (highest $ impact first).
        await _add_txn(
            session, acct.id, stmt.id, day=7, description="COSTCO WHOLESALE #2", amount="-900.00",
        )

    review = await get_needs_review(limit=20)
    descriptions = [r.description for r in review]
    assert len(descriptions) == 3
    # Least-confident first (unclassified 0.0 before ambiguous 0.35), then
    # largest absolute dollar impact first within the same confidence.
    assert descriptions == [
        "MISC POS 88213",          # confidence 0.0
        "COSTCO WHOLESALE #2",     # confidence 0.35, -$900
        "COSTCO WHOLESALE #1",     # confidence 0.35, -$20
    ]
    assert review[0].confidence < review[1].confidence
    assert review[1].confidence == review[2].confidence


async def test_needs_review_ambiguous_merchant_reason_matches_the_engine(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=5, description="TARGET STORE #9", amount="-60.00",
        )
        await _add_txn(
            session, acct.id, stmt.id, day=6, description="MISC POS 44119", amount="-12.00",
        )

    review = await get_needs_review(limit=20)
    by_description = {r.description: r for r in review}
    assert by_description["TARGET STORE #9"].review_reason.value == "ambiguous_merchant"
    assert by_description["MISC POS 44119"].review_reason.value == "unclassified"


# ── period scoping (PR 05 unified period contract) ─────────────────────────

async def test_needs_review_is_scoped_to_the_requested_period(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=5, description="COSTCO IN PERIOD", amount="-20.00",
        )
        await _add_txn(
            session, acct.id, stmt.id, day=5, month=6,
            description="COSTCO OUT OF PERIOD", amount="-20.00",
        )

    scoped = await get_needs_review(
        limit=20, start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
    )
    assert [r.description for r in scoped] == ["COSTCO IN PERIOD"]

    # ...and the out-of-period row was not even auto-classified as a side
    # effect: a period-scoped GET must never write across all history.
    async with get_session() as session:
        out_of_period = await _txn_id_for(session, acct.id, "COSTCO OUT OF PERIOD")
        txn = await repo.get_transaction(session, out_of_period)
        assert txn.classification_source is None

    # Without a period, the queue is all-history (the default contract).
    unscoped = await get_needs_review(limit=20)
    assert {r.description for r in unscoped} == {"COSTCO IN PERIOD", "COSTCO OUT OF PERIOD"}


async def test_needs_review_requires_both_period_bounds_together(temp_db):
    with pytest.raises(HTTPException) as exc_info:
        await get_needs_review(limit=20, start_date=date(2026, 8, 1))
    assert exc_info.value.status_code == 422

    with pytest.raises(HTTPException) as exc_info:
        await get_needs_review(
            limit=20, start_date=date(2026, 8, 31), end_date=date(2026, 8, 1),
        )
    assert exc_info.value.status_code == 422


async def test_reclassify_category_on_a_bucket_without_categories_is_422(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=5, description="MISC POS 77120", amount="-31.00",
        )

    async with get_session() as session:
        txn_id = await _txn_id_for(session, acct.id, "MISC POS 77120")

    with pytest.raises(HTTPException) as exc_info:
        await reclassify_transaction(
            txn_id,
            ReclassifyRequest(
                master_bucket=ReclassifyChoice.TRANSFER, category="Dining",
                scope=ReclassifyScope.TRANSACTION,
            ),
        )
    assert exc_info.value.status_code == 422


# ── Plan vs Actual reflects a correction on the very next fetch ────────────

async def test_plan_vs_actual_reflects_reclassification_on_next_fetch(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, day=10, description="STARBUCKS STORE #1", amount="-6.25",
        )

    async with get_session() as session:
        txn_id = await _txn_id_for(session, acct.id, "STARBUCKS STORE #1")

    async with get_session() as session:
        before = await pva_service.get_plan_vs_actual(session, Period.for_month(2026, 8))
    wants_before = next(b for b in before.buckets if b.bucket == MasterBucket.WANTS)
    needs_before = next(b for b in before.buckets if b.bucket == MasterBucket.NEEDS)
    assert wants_before.actual_amount == "6.25"
    assert needs_before.actual_amount == "0.00"

    await reclassify_transaction(
        txn_id,
        ReclassifyRequest(
            master_bucket=ReclassifyChoice.NEEDS, category="Groceries",
            scope=ReclassifyScope.TRANSACTION,
        ),
    )

    async with get_session() as session:
        after = await pva_service.get_plan_vs_actual(session, Period.for_month(2026, 8))
    wants_after = next(b for b in after.buckets if b.bucket == MasterBucket.WANTS)
    needs_after = next(b for b in after.buckets if b.bucket == MasterBucket.NEEDS)
    assert wants_after.actual_amount == "0.00"
    assert needs_after.actual_amount == "6.25"
