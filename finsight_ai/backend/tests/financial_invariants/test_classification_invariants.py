"""
Financial invariant tests for the transaction classification layer.

Maps directly onto backend/tests/financial_invariants/README.md. This suite
covers the invariants that the classification engine (PR 03 —
app.domain.transaction_classification / app.services.transaction_classification)
is responsible for enforcing. Plan-total and historical-plan-version
invariants (README items 8/9) are covered by test_financial_plan.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.db import repositories as repo
from app.db.engine import get_session
from app.domain.transaction_classification import (
    CashFlowType,
    MasterBucket,
    TransactionClassificationInput,
    classify_transaction,
)
from app.services.transaction_classification import TransactionClassificationService


def _input(
    description: str, amount: str, transaction_type: str = "purchase", **kw,
) -> TransactionClassificationInput:
    return TransactionClassificationInput(
        transaction_id="t", description=description, amount=Decimal(amount),
        transaction_type=transaction_type, **kw,
    )


# ── Invariant 1: checking -> savings neutrality ─────────────────────────────

def test_invariant_checking_to_savings_is_not_spending():
    result = classify_transaction(
        _input("ONLINE TRANSFER TO MARCUS HYSA", "-500.00", transaction_type="transfer")
    )
    assert result.master_bucket not in (MasterBucket.NEEDS, MasterBucket.WANTS)
    assert result.cash_flow_type in (CashFlowType.SAVINGS_CONTRIBUTION, CashFlowType.TRANSFER)


# ── Invariant 2: checking -> brokerage neutrality ───────────────────────────

def test_invariant_checking_to_brokerage_is_not_spending():
    result = classify_transaction(
        _input("TRANSFER TO ETRADE BROKERAGE", "-800.00", transaction_type="transfer")
    )
    assert result.master_bucket not in (MasterBucket.NEEDS, MasterBucket.WANTS)
    assert result.cash_flow_type == CashFlowType.INVESTMENT_CONTRIBUTION


# ── Invariant: card purchase + card payment counts spend once ──────────────

def test_invariant_card_purchase_and_payment_counted_once():
    purchase = classify_transaction(_input("STARBUCKS STORE #1", "-6.25"))
    payment = classify_transaction(
        _input("PAYMENT THANK YOU - WEB", "500.00", transaction_type="payment")
    )
    assert purchase.cash_flow_type == CashFlowType.EXPENSE
    # The payment must NOT also register as spend — otherwise the purchase
    # would be counted twice (once as the purchase, once as the payment).
    assert payment.cash_flow_type != CashFlowType.EXPENSE
    assert payment.cash_flow_type == CashFlowType.TRANSFER


def test_invariant_checking_side_card_payment_is_never_needs_spending():
    """The checking-side leg of a card payment must stay neutral — the card
    purchases are already expensed individually (accounting-invariants #2)."""
    for description, txn_type in [
        ("CREDIT CARD PAYMENT CHASE 4455", "withdrawal"),
        ("ONLINE PAYMENT TO CHASE CARD 4455", "payment"),
        ("CHASE CREDIT CRD EPAY 4455", "payment"),
    ]:
        result = classify_transaction(_input(description, "-500.00", transaction_type=txn_type))
        assert result.cash_flow_type == CashFlowType.TRANSFER, description
        assert result.master_bucket == MasterBucket.UNCLASSIFIED, description


def test_invariant_bill_payments_are_not_neutralized_as_card_payments():
    """The inverse of the invariant above: real bills whose description merely
    contains the word "payment"/"autopay" must still count as Needs spending,
    otherwise Needs actuals are silently understated."""
    for description, category in [
        ("RENT PAYMENT - ACME PROPERTY MGMT", "Housing"),
        ("PSEG ELECTRIC PAYMENT", "Utilities"),
        ("VERIZON WIRELESS AUTOPAY", "Connectivity"),
    ]:
        result = classify_transaction(
            _input(description, "-300.00", transaction_type="payment")
        )
        assert result.master_bucket == MasterBucket.NEEDS, description
        assert result.category == category, description
        assert result.cash_flow_type == CashFlowType.EXPENSE, description


# ── Invariant: withdrawals are not contributions ────────────────────────────

def test_invariant_savings_withdrawal_is_not_a_contribution():
    result = classify_transaction(
        _input("TRANSFER FROM MARCUS SAVINGS", "1000.00",
               transaction_type="transfer", account_type="checking")
    )
    assert result.cash_flow_type != CashFlowType.SAVINGS_CONTRIBUTION
    assert result.cash_flow_type == CashFlowType.TRANSFER


def test_invariant_brokerage_withdrawal_is_not_a_contribution():
    result = classify_transaction(
        _input("TRANSFER FROM ETRADE BROKERAGE", "2500.00",
               transaction_type="transfer", account_type="checking")
    )
    assert result.cash_flow_type != CashFlowType.INVESTMENT_CONTRIBUTION
    assert result.cash_flow_type == CashFlowType.TRANSFER


# ── Invariant: refund reduces/offsets spending ──────────────────────────────

def test_invariant_refund_reduces_spending():
    charge = classify_transaction(_input("STARBUCKS STORE #1", "-6.25"))
    refund = classify_transaction(
        _input("REFUND - STARBUCKS STORE #1", "6.25", transaction_type="refund")
    )
    assert charge.cash_flow_type == CashFlowType.EXPENSE
    assert refund.cash_flow_type == CashFlowType.REFUND
    assert refund.cash_flow_type != CashFlowType.EXPENSE
    # The refund must keep the bucket/category it reverses so it can net
    # against the original spend rather than vanishing into unclassified.
    assert refund.master_bucket == charge.master_bucket
    assert refund.category == charge.category


def test_invariant_unexplained_deposit_is_not_treated_as_a_refund():
    """A deposit Coral cannot explain must not be labelled `refund` — PR 04
    nets refunds against spending, so a mislabelled paycheck/check deposit
    would silently erase real expenses."""
    for description in ["DEPOSIT MOBILE CHECK", "ACH CREDIT ACME CORP"]:
        result = classify_transaction(_input(description, "3000.00", transaction_type="deposit"))
        assert result.cash_flow_type != CashFlowType.REFUND, description
        assert result.master_bucket == MasterBucket.UNCLASSIFIED, description


# ── Invariant: investment rollover is not a new monthly contribution ───────

def test_invariant_rollover_is_not_new_contribution():
    result = classify_transaction(
        _input("401K ROLLOVER TO IRA", "-15000.00", transaction_type="transfer")
    )
    assert result.cash_flow_type == CashFlowType.INVESTMENT_ACTIVITY
    assert result.cash_flow_type != CashFlowType.INVESTMENT_CONTRIBUTION


# ── Invariant: internal transfer between checking accounts is neutral ─────

def test_invariant_internal_checking_to_checking_transfer_is_neutral():
    result = classify_transaction(
        _input("ONLINE TRANSFER TO CHK ...6789", "-250.00", transaction_type="transfer")
    )
    assert result.master_bucket == MasterBucket.UNCLASSIFIED
    assert result.cash_flow_type == CashFlowType.TRANSFER


# ── Invariant: user override beats automated classification ────────────────

async def test_invariant_user_override_beats_automated_classification(temp_db):
    async with get_session() as session:
        inst = await repo.get_or_create_institution(session, "chase", "Chase")
        acct = await repo.get_or_create_account(
            session, institution_id=inst.id, institution_type="chase",
            account_number_masked="****1234", account_type="checking",
        )
        doc = await repo.create_document(
            session, original_filename="s.pdf", stored_filename="s.pdf",
            file_path="/tmp/s.pdf", file_size_bytes=1, mime_type="application/pdf",
            status="parsed", institution_type="chase",
        )
        stmt = await repo.create_statement(
            session, document_id=doc.id, institution_id=inst.id, institution_type="chase",
            account_id=acct.id, account_type="checking", statement_type="bank",
            period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
            extraction_status="success", overall_confidence=0.9, warnings="[]",
        )
        await repo.bulk_create_transactions(session, [{
            "account_id": acct.id, "statement_id": stmt.id,
            "transaction_date": date(2026, 1, 10), "description": "STARBUCKS STORE #1",
            "amount": "-6.25", "transaction_type": "purchase",
        }])

    async with get_session() as session:
        txns = await repo.list_transactions(session, account_id=acct.id)
        txn_id = txns[0].id

    service = TransactionClassificationService()
    async with get_session() as session:
        automated = await service.classify(session, txn_id)
    assert automated.master_bucket == MasterBucket.WANTS  # auto-classified as Dining

    async with get_session() as session:
        overridden = await service.apply_user_override(
            session, txn_id,
            master_bucket=MasterBucket.NEEDS, cash_flow_type=CashFlowType.EXPENSE,
            category="Groceries",
        )
    assert overridden.master_bucket == MasterBucket.NEEDS

    # A subsequent batch reclassification must not revert the user's choice.
    async with get_session() as session:
        await service.classify_batch(session, account_id=acct.id, only_unclassified=False)
    async with get_session() as session:
        txn = await repo.get_transaction(session, txn_id)
        assert txn.master_bucket == "needs"
        assert txn.classification_source == "user"


# ── Invariant: incomplete data honesty — no fabricated bucket/category ─────

def test_invariant_unresolvable_transaction_is_not_fabricated():
    result = classify_transaction(_input("MISC POS 99182734", "-9.00"))
    assert result.master_bucket == MasterBucket.UNCLASSIFIED
    assert result.category is None
    assert result.needs_review is True


def test_invariant_ambiguous_merchant_is_not_fabricated():
    result = classify_transaction(_input("AMAZON.COM*A1B2C3", "-40.00"))
    assert result.master_bucket == MasterBucket.UNCLASSIFIED
    assert result.category is None
    assert result.needs_review is True
