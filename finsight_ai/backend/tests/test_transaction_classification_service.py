"""
DB-backed tests for TransactionClassificationService: precedence chain wired
to real repositories/session, persistence of derived fields, and preservation
of the raw `category` column.

Uses the shared `temp_db` fixture (isolated file-backed SQLite per test).
"""

from __future__ import annotations

from datetime import date

from app.db import repositories as repo
from app.db.engine import get_session
from app.domain.transaction_classification import (
    CashFlowType,
    ClassificationResult,
    ClassificationSource,
    MasterBucket,
    RuleScope,
)
from app.services.transaction_classification import TransactionClassificationService


async def _seed_account(
    institution: str = "chase", account_type: str = "checking",
) -> tuple[str, str]:
    async with get_session() as session:
        inst = await repo.get_or_create_institution(session, institution, institution.title())
        acct = await repo.get_or_create_account(
            session, institution_id=inst.id, institution_type=institution,
            account_number_masked="****1234", account_type=account_type,
        )
        doc_id = await _dummy_document(session)
        stmt = await repo.create_statement(
            session,
            document_id=doc_id,
            institution_id=inst.id, institution_type=institution,
            account_id=acct.id, account_type=account_type, statement_type="bank",
            period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
            extraction_status="success", overall_confidence=0.9, warnings="[]",
        )
        return acct.id, stmt.id


async def _dummy_document(session) -> str:
    doc = await repo.create_document(
        session,
        original_filename="stmt.pdf", stored_filename="stmt.pdf",
        file_path="/tmp/stmt.pdf", file_size_bytes=1, mime_type="application/pdf",
        status="parsed", institution_type="chase",
    )
    return doc.id


async def _make_txn(
    account_id: str, statement_id: str, *,
    description: str, amount: str, transaction_type: str = "purchase",
    category: str | None = None, txn_date: date = date(2026, 1, 10),
) -> str:
    async with get_session() as session:
        await repo.bulk_create_transactions(session, [{
            "account_id": account_id, "statement_id": statement_id,
            "transaction_date": txn_date, "description": description,
            "amount": amount, "transaction_type": transaction_type, "category": category,
        }])
    async with get_session() as session:
        txns = await repo.list_transactions(session, account_id=account_id)
        match = [t for t in txns if t.description == description]
        return match[0].id


# ── Basic classify() persists derived fields, preserves raw category ───────

async def test_classify_persists_fields_and_preserves_raw_category(temp_db):
    account_id, statement_id = await _seed_account()
    txn_id = await _make_txn(
        account_id, statement_id,
        description="RENT PAYMENT - ACME PROPERTY MGMT", amount="-2000.00",
        category="other",  # raw parser category, deliberately generic
    )

    service = TransactionClassificationService()
    async with get_session() as session:
        result = await service.classify(session, txn_id)

    assert result.master_bucket == MasterBucket.NEEDS
    assert result.category == "Housing"

    async with get_session() as session:
        txn = await repo.get_transaction(session, txn_id)
        assert txn.master_bucket == "needs"
        assert txn.classification_category == "Housing"
        assert txn.cash_flow_type == "expense"
        assert txn.classification_source == "heuristic"
        assert txn.needs_review is False
        # Raw imported category must never be touched by classification.
        assert txn.category == "other"


# ── User override always wins and persists ──────────────────────────────────

async def test_user_override_persists_and_wins_over_reclassification(temp_db):
    account_id, statement_id = await _seed_account()
    txn_id = await _make_txn(
        account_id, statement_id,
        description="STARBUCKS STORE #123", amount="-6.25",
    )

    service = TransactionClassificationService()
    async with get_session() as session:
        # Automated classification would call this Wants/Dining.
        auto = await service.classify(session, txn_id)
    assert auto.master_bucket == MasterBucket.WANTS

    async with get_session() as session:
        overridden = await service.apply_user_override(
            session, txn_id,
            master_bucket=MasterBucket.NEEDS, cash_flow_type=CashFlowType.EXPENSE,
            category="Groceries",
        )
    assert overridden.source == ClassificationSource.USER
    assert overridden.master_bucket == MasterBucket.NEEDS

    # Re-running classification (e.g. a batch re-run) must not silently
    # overwrite the user's explicit choice.
    async with get_session() as session:
        again = await service.classify(session, txn_id)
    assert again.source == ClassificationSource.USER
    assert again.master_bucket == MasterBucket.NEEDS
    assert again.category == "Groceries"

    async with get_session() as session:
        txn = await repo.get_transaction(session, txn_id)
        assert txn.classification_source == "user"
        assert txn.master_bucket == "needs"
        assert txn.needs_review is False


# ── Merchant rule applies going forward and beats an LLM fallback ──────────

async def test_merchant_rule_beats_llm_fallback(temp_db):
    account_id, statement_id = await _seed_account()
    txn_id = await _make_txn(
        account_id, statement_id,
        description="AMAZON.COM*A1B2C3", amount="-40.00",
    )

    async def fake_llm(_txn_input):
        return ClassificationResult(
            master_bucket=MasterBucket.WANTS, category="Shopping",
            cash_flow_type=CashFlowType.EXPENSE, source=ClassificationSource.LLM,
            confidence=0.9,
        )

    service = TransactionClassificationService(llm_classifier=fake_llm)

    # Without a merchant rule, Amazon is ambiguous and gets flagged (LLM tier
    # is only reached when the deterministic engine truly finds nothing —
    # the ambiguous-merchant gate is intentionally terminal, so the LLM is
    # never even consulted for known-ambiguous merchants).
    async with get_session() as session:
        before = await service.classify(session, txn_id, persist=False)
    assert before.needs_review is True

    async with get_session() as session:
        await service.apply_merchant_rule(
            session,
            master_bucket=MasterBucket.NEEDS, cash_flow_type=CashFlowType.EXPENSE,
            category="Groceries", scope=RuleScope.MERCHANT, merchant_key="amazon",
        )

    async with get_session() as session:
        after = await service.classify(session, txn_id)
    assert after.source == ClassificationSource.USER
    assert after.master_bucket == MasterBucket.NEEDS
    assert after.category == "Groceries"
    assert after.needs_review is False


# ── LLM fallback is used only when nothing deterministic matches ───────────

async def test_llm_fallback_used_for_truly_unresolvable_transaction(temp_db):
    account_id, statement_id = await _seed_account()
    txn_id = await _make_txn(
        account_id, statement_id,
        description="MISC POS 99182734", amount="-9.00",
    )

    async def fake_llm(_txn_input):
        return ClassificationResult(
            master_bucket=MasterBucket.WANTS, category="Shopping",
            cash_flow_type=CashFlowType.EXPENSE, source=ClassificationSource.LLM,
            confidence=0.55,
        )

    service = TransactionClassificationService(llm_classifier=fake_llm)
    async with get_session() as session:
        result = await service.classify(session, txn_id)

    assert result.source == ClassificationSource.LLM
    assert result.master_bucket == MasterBucket.WANTS
    # Low-confidence LLM guesses still surface for review.
    assert result.needs_review is True


async def test_llm_fallback_failure_degrades_to_unclassified_not_an_exception(temp_db):
    """A failing/unavailable LLM (Ollama down) must never break classification —
    it degrades to the honest tier-7 `unclassified` result. Regression test for
    the warning path itself raising TypeError on the stdlib logger."""
    account_id, statement_id = await _seed_account()
    txn_id = await _make_txn(
        account_id, statement_id,
        description="MISC POS 99182734", amount="-9.00",
    )

    async def exploding_llm(_txn_input):
        raise RuntimeError("ollama unavailable")

    service = TransactionClassificationService(llm_classifier=exploding_llm)
    async with get_session() as session:
        result = await service.classify(session, txn_id)

    assert result.source == ClassificationSource.UNKNOWN
    assert result.master_bucket == MasterBucket.UNCLASSIFIED
    assert result.needs_review is True


# ── Batch classification ────────────────────────────────────────────────────

async def test_classify_batch_classifies_all_and_summarizes(temp_db):
    account_id, statement_id = await _seed_account()
    await _make_txn(account_id, statement_id, description="RENT PAYMENT", amount="-2000.00")
    await _make_txn(account_id, statement_id, description="STARBUCKS STORE #1", amount="-6.25")
    await _make_txn(
        account_id, statement_id, description="ONLINE TRANSFER TO SAVINGS",
        amount="-500.00", transaction_type="transfer",
    )

    service = TransactionClassificationService()
    async with get_session() as session:
        summary = await service.classify_batch(session, account_id=account_id)

    assert summary.total == 3
    assert summary.classified == 3

    async with get_session() as session:
        txns = await repo.list_transactions(session, account_id=account_id)
        assert all(t.classification_source is not None for t in txns)


# ── Needs-review queue ───────────────────────────────────────────────────────

async def test_needs_review_queue_surfaces_ambiguous_transactions(temp_db):
    account_id, statement_id = await _seed_account()
    await _make_txn(account_id, statement_id, description="RENT PAYMENT", amount="-2000.00")
    await _make_txn(account_id, statement_id, description="COSTCO WHOLESALE #221", amount="-120.00")

    service = TransactionClassificationService()
    async with get_session() as session:
        await service.classify_batch(session, account_id=account_id)

    async with get_session() as session:
        review = await service.get_needs_review(session)

    descriptions = {t.description for t in review}
    assert "COSTCO WHOLESALE #221" in descriptions
    assert "RENT PAYMENT" not in descriptions
