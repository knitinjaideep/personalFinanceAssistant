"""
Financial invariant tests for PR 10 Banking Insights.

These are pure domain tests: they build synthetic classified transactions,
run the real Plan vs Actual engine / merchant-driver aggregation, then verify
Banking Insights ranks and caps deterministic facts without LLM involvement.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.banking_insights import build_banking_insights
from app.domain.classification_review import ReviewReason, TransactionReviewItem
from app.domain.entities import AllocationSnapshot, PlanVersionSnapshot, SuballocationSnapshot
from app.domain.plan_vs_actual import (
    ClassifiedTxn,
    Period,
    compute_merchant_drivers,
    compute_plan_vs_actual,
)
from app.domain.transaction_classification import (
    CashFlowType,
    ClassificationSource,
    MasterBucket,
)

PERIOD = Period.for_month(2026, 8)


def _default_plan() -> PlanVersionSnapshot:
    def sub(id_: str, name: str, percentage: str, sort_order: int) -> SuballocationSnapshot:
        return SuballocationSnapshot(
            id=id_, name=name, percentage=percentage, sort_order=sort_order,
        )

    return PlanVersionSnapshot(
        id="v1", plan_id="p1", version_number=1, effective_from=date(2026, 1, 1),
        allocations=[
            AllocationSnapshot(id="a1", bucket_name="needs", percentage="50", sort_order=0),
            AllocationSnapshot(id="a2", bucket_name="wants", percentage="20", sort_order=1),
            AllocationSnapshot(
                id="a3", bucket_name="savings", percentage="15", sort_order=2,
                suballocations=[
                    sub("s1", "Emergency Fund", "5", 0),
                    sub("s2", "House / Goals", "5", 1),
                    sub("s3", "Child Savings", "5", 2),
                ],
            ),
            AllocationSnapshot(
                id="a4", bucket_name="investments", percentage="15", sort_order=3,
                suballocations=[
                    sub("s4", "401(k)", "6", 0),
                    sub("s5", "Roth IRA", "4", 1),
                    sub("s6", "ESPP", "3", 2),
                    sub("s7", "Taxable Brokerage", "2", 3),
                ],
            ),
        ],
    )


def _txn(
    txn_id: str,
    amount: str,
    bucket: MasterBucket,
    flow: CashFlowType,
    *,
    category: str | None = None,
    merchant: str | None = None,
    account_type: str = "credit_card",
) -> ClassifiedTxn:
    return ClassifiedTxn(
        transaction_id=txn_id,
        account_id=f"acct-{account_type}",
        account_type=account_type,
        transaction_date=date(2026, 8, 15),
        amount=Decimal(amount),
        master_bucket=bucket,
        category=category,
        cash_flow_type=flow,
        merchant_name=merchant,
        description=merchant or txn_id,
    )


def _review_item(txn_id: str, amount: str) -> TransactionReviewItem:
    return TransactionReviewItem(
        transaction_id=txn_id,
        transaction_date=date(2026, 8, 15),
        description="UNKNOWN POS",
        merchant=None,
        amount=amount,
        master_bucket=MasterBucket.UNCLASSIFIED,
        category=None,
        cash_flow_type=CashFlowType.EXPENSE,
        confidence=0.0,
        needs_review=True,
        classification_source=ClassificationSource.UNKNOWN,
        review_reason=ReviewReason.UNCLASSIFIED,
    )


def _build(transactions: list[ClassifiedTxn]):
    result = compute_plan_vs_actual(PERIOD, transactions, _default_plan())
    merchants = (
        compute_merchant_drivers(transactions, bucket=MasterBucket.NEEDS, top_n=5)
        + compute_merchant_drivers(transactions, bucket=MasterBucket.WANTS, top_n=5)
    )
    return result, merchants


def test_banking_insights_are_ranked_and_capped_to_three():
    txns = [
        _txn(
            "income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME,
            account_type="checking",
        ),
        _txn(
            "rent", "-5400.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Housing", merchant="Landlord",
        ),
        _txn(
            "dining", "-2600.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Dining", merchant="Restaurant",
        ),
        _txn(
            "shop", "-900.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Shopping", merchant="Amazon",
        ),
    ]
    result, merchants = _build(txns)

    insights = build_banking_insights(
        result,
        merchants,
        [_review_item("unknown-1", "-200.00"), _review_item("unknown-2", "-100.00")],
    ).insights

    assert len(insights) == 3
    assert all(i.impact_amount is not None for i in insights)
    assert len({i.type for i in insights}) == len(insights)
    assert any(i.type in {"merchant_concentration", "merchant_overspend"} for i in insights)


def test_classification_uncertainty_uses_review_queue_amounts():
    txns = [
        _txn(
            "income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME,
            account_type="checking",
        ),
        _txn(
            "groceries", "-5000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Groceries", merchant="Market",
        ),
        _txn(
            "dining", "-2000.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Dining", merchant="Cafe",
        ),
    ]
    result, merchants = _build(txns)

    insights = build_banking_insights(
        result,
        merchants,
        [_review_item("unknown-1", "-40.00"), _review_item("unknown-2", "60.00")],
    ).insights

    uncertainty = next(i for i in insights if i.type == "classification_uncertainty")
    assert uncertainty.impact_amount == "100.00"
    assert "2 transactions need review" in uncertainty.summary
    assert uncertainty.tone == "warning"


def test_no_income_or_material_activity_does_not_fabricate_insights():
    txns = [
        _txn(
            "coffee", "-8.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Dining", merchant="Cafe",
        ),
    ]
    result, merchants = _build(txns)

    insights = build_banking_insights(result, merchants, []).insights

    assert insights == []


def test_positive_improvement_only_uses_known_consumption_surplus():
    txns = [
        _txn(
            "income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME,
            account_type="checking",
        ),
        _txn(
            "needs", "-4000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Housing", merchant="Landlord",
        ),
        _txn(
            "wants", "-1000.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Dining", merchant="Cafe",
        ),
        _txn(
            "savings",
            "1500.00",
            MasterBucket.SAVINGS,
            CashFlowType.SAVINGS_CONTRIBUTION,
            category="Emergency Fund",
            merchant="Bank",
            account_type="savings",
        ),
    ]
    result, merchants = _build(txns)

    insights = build_banking_insights(result, merchants, []).insights

    assert insights[0].type == "positive_improvement"
    assert insights[0].tone == "good"
    assert insights[0].impact_amount == "2000.00"
