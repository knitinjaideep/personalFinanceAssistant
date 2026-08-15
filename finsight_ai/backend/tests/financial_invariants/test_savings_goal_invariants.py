"""
Financial invariant tests for the Savings Goal Engine (PR 13 —
app.domain.savings_goals / app.services.savings_goals).

Maps onto backend/tests/financial_invariants/README.md. A goal's
`current_amount` is a financial total shown to the user, so it must obey the
same invariants as every other Coral total:

  - it must never double count a transfer leg (invariant 1/2/6),
  - it must never be inflated by a credit-card payment (invariant 3),
  - refunds must not inflate it (invariant 4),
  - a rollover between investment accounts is not a savings contribution
    (invariant 5),
  - a user's explicit override must win over the automated classification
    (invariant 7),
  - missing data must be reported, never fabricated into a number
    (invariant 10),
  - and it must RECONCILE EXACTLY with what Plan vs Actual reports for the
    same category over the same window — the two surfaces must never
    disagree, which is only guaranteed because the goal engine reuses
    `compute_transaction_drivers` rather than running its own sum.

Pure domain-level tests (no DB) — DB-integration coverage lives in
backend/tests/test_savings_goals.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.plan_vs_actual import (
    ClassifiedTxn,
    aggregate_category_actuals,
    compute_transaction_drivers,
)
from app.domain.savings_goals import (
    GoalAccountMapping,
    GoalStatus,
    assess_goal_completeness,
    build_completion_recommendation,
    compute_goal_status,
    derive_percentage_target_amount,
    resolve_effective_target_amount,
)
from app.domain.transaction_classification import CashFlowType, MasterBucket

AS_OF = date(2026, 8, 31)
EMERGENCY_FUND = "Emergency Fund"


def _txn(
    txn_id: str, amount: str, bucket: MasterBucket, flow: CashFlowType,
    *, category: str | None = None, account_type: str | None = "checking",
    day: int = 15, month: int = 8, description: str = "SYNTHETIC",
) -> ClassifiedTxn:
    return ClassifiedTxn(
        transaction_id=txn_id, account_id=f"acct-{account_type}",
        account_type=account_type, transaction_date=date(2026, month, day),
        amount=Decimal(amount), master_bucket=bucket, category=category,
        cash_flow_type=flow, description=description,
    )


def _goal_total(transactions: list[ClassifiedTxn], category: str = EMERGENCY_FUND) -> Decimal:
    """Exactly what app.services.savings_goals._compute_progress sums."""
    drivers = compute_transaction_drivers(
        transactions, bucket=MasterBucket.SAVINGS, category=category,
    )
    return sum((Decimal(d.amount) for d in drivers), Decimal("0"))


# ── Invariant 1/6: transfer legs are never double counted ───────────────────

def test_goal_total_counts_a_checking_to_savings_transfer_once_when_both_legs_ingested():
    """Origin (checking) + destination (Marcus) legs of the SAME $500
    transfer: the goal must show $500, not $1,000."""
    transactions = [
        _txn(
            "origin", "-500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=EMERGENCY_FUND, account_type="checking",
        ),
        _txn(
            "destination", "500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=EMERGENCY_FUND, account_type="savings",
        ),
    ]
    assert _goal_total(transactions) == Decimal("500.00")


def test_goal_total_counts_the_origin_leg_when_the_savings_side_is_not_ingested():
    """Coral's real coverage today: Marcus/529 have no parser, so only the
    checking-side leg exists. It must still count (BLOCKED decision 1,
    Option C) — the goal must not read $0 while the user is saving."""
    transactions = [
        _txn(
            "origin", "-500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=EMERGENCY_FUND, account_type="checking",
        ),
    ]
    assert _goal_total(transactions) == Decimal("500.00")


def test_internal_checking_to_checking_transfer_contributes_nothing_to_a_goal():
    transactions = [
        _txn(
            "internal", "-1000.00", MasterBucket.UNCLASSIFIED, CashFlowType.TRANSFER,
            category=None, account_type="checking",
        ),
    ]
    assert _goal_total(transactions) == Decimal("0")


# ── Invariant 3: credit-card payments never inflate a savings goal ──────────

def test_credit_card_payment_does_not_inflate_a_savings_goal():
    transactions = [
        _txn(
            "contribution", "-500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=EMERGENCY_FUND, account_type="checking",
        ),
        _txn(
            # A card payment is classified UNCLASSIFIED/TRANSFER (neutral) —
            # the purchases it settles are already counted on the card side.
            "card_payment", "-2000.00", MasterBucket.UNCLASSIFIED,
            CashFlowType.TRANSFER, category=None, account_type="checking",
            description="PAYMENT THANK YOU - CHASE CARD",
        ),
    ]
    assert _goal_total(transactions) == Decimal("500.00")


# ── Invariant 4/5: refunds and rollovers ────────────────────────────────────

def test_refund_on_a_spending_category_does_not_touch_a_savings_goal():
    transactions = [
        _txn(
            "contribution", "-500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=EMERGENCY_FUND, account_type="checking",
        ),
        _txn(
            "refund", "80.00", MasterBucket.WANTS, CashFlowType.REFUND,
            category="Shopping", account_type="chase_credit",
        ),
    ]
    assert _goal_total(transactions) == Decimal("500.00")


def test_investment_rollover_is_not_a_savings_goal_contribution():
    transactions = [
        _txn(
            "rollover", "25000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INVESTMENT_ACTIVITY,
            category=None, account_type="roth_ira",
        ),
    ]
    assert _goal_total(transactions) == Decimal("0")


# ── Reconciliation: goals and Plan vs Actual must never disagree ────────────

def test_goal_total_reconciles_exactly_with_plan_vs_actual_category_actual():
    """Same category, same transactions, same window -> identical dollars.
    Guards against a parallel aggregation path being introduced later."""
    transactions = [
        _txn("income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn(
            "ef1", "-300.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=EMERGENCY_FUND, account_type="checking", day=3,
        ),
        _txn(
            "ef2", "-200.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=EMERGENCY_FUND, account_type="checking", day=17,
        ),
        _txn(
            "house", "-400.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category="House / Goals", account_type="checking", day=17,
        ),
        _txn(
            "card_payment", "-2000.00", MasterBucket.UNCLASSIFIED,
            CashFlowType.TRANSFER, account_type="checking",
            description="PAYMENT THANK YOU - CHASE CARD",
        ),
    ]
    category_actuals = aggregate_category_actuals(transactions, MasterBucket.SAVINGS)
    assert _goal_total(transactions) == category_actuals[EMERGENCY_FUND][0]
    assert _goal_total(transactions, "House / Goals") == category_actuals["House / Goals"][0]


def test_cumulative_goal_total_equals_the_sum_of_its_monthly_plan_vs_actual_totals():
    """A goal window spanning a coverage CHANGE (savings side unparsed in
    July, ingested in August) must still equal the sum of the monthly Plan vs
    Actual actuals — the service slices the window by calendar month so the
    coverage-aware transfer-leg gate resolves exactly as it does monthly.
    Evaluating the whole window at once would treat July as covered and
    silently drop its origin leg.
    """
    july = [
        _txn(
            "jul_origin", "-500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=EMERGENCY_FUND, account_type="checking", month=7, day=5,
        ),
    ]
    august = [
        _txn(
            "aug_origin", "-700.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=EMERGENCY_FUND, account_type="checking", month=8, day=5,
        ),
        _txn(
            "aug_destination", "700.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=EMERGENCY_FUND, account_type="savings", month=8, day=6,
        ),
    ]
    monthly_sum = _goal_total(july) + _goal_total(august)
    assert monthly_sum == Decimal("1200.00")

    # Whole-window-in-one-shot would be wrong — this documents WHY the
    # service slices by month.
    assert _goal_total(july + august) == Decimal("700.00")

    from app.services.savings_goals import _monthly_savings_drivers

    sliced = _monthly_savings_drivers(july + august, category=EMERGENCY_FUND)
    assert sum((Decimal(d.amount) for d in sliced), Decimal("0")) == monthly_sum


# ── Invariant 7: user override precedence ───────────────────────────────────

def test_user_override_moving_a_txn_out_of_the_goal_category_removes_it_from_the_total():
    """The goal engine reads whatever classification survived the precedence
    chain — it never re-derives a category from the description text, so an
    override that says "this is not Emergency Fund" is honoured."""
    overridden = _txn(
        "overridden", "-500.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
        category="Shopping", account_type="checking",
        description="TRANSFER TO MARCUS SAVINGS EMERGENCY FUND",
    )
    assert _goal_total([overridden]) == Decimal("0")


# ── Invariant 10: incomplete data is reported, never fabricated ─────────────

def test_no_ingested_history_is_reported_as_incomplete_not_as_zero_saved():
    result = assess_goal_completeness(
        [], effective_date=date(2026, 1, 1),
        earliest_observed_transaction_date=None,
        contribution_transaction_count=0,
        unparseable_mappings=[], unknown_mappings=[],
    )
    assert result.any_observed_transaction_history is False
    assert result.is_complete is False


def test_unparseable_mapped_account_is_reported_as_incomplete():
    mapping = GoalAccountMapping(institution_slug="marcus", account_slug="emergency_fund")
    result = assess_goal_completeness(
        [mapping], effective_date=date(2026, 1, 1),
        earliest_observed_transaction_date=date(2026, 1, 1),
        contribution_transaction_count=2,
        unparseable_mappings=[mapping], unknown_mappings=[],
    )
    assert result.is_complete is False


def test_savings_contributions_coral_cannot_attribute_are_surfaced_not_dropped():
    result = assess_goal_completeness(
        [], effective_date=date(2026, 1, 1),
        earliest_observed_transaction_date=date(2026, 1, 1),
        contribution_transaction_count=1,
        unparseable_mappings=[], unknown_mappings=[],
        unattributed_savings_contribution_count=2,
        unattributed_savings_contribution_amount=Decimal("1500"),
    )
    assert result.unattributed_savings_contribution_amount == "1500.00"
    assert result.is_complete is False
    assert any("could not be attributed" in n for n in result.notes)


def test_percentage_target_without_observed_income_is_unmeasurable_not_zero():
    assert derive_percentage_target_amount(Decimal("5"), None) is None
    assert derive_percentage_target_amount(Decimal("5"), Decimal("0")) is None
    effective, source = resolve_effective_target_amount(
        target_amount=None, target_percentage_of_income=Decimal("5"),
        plannable_income=Decimal("0"),
    )
    assert effective is None
    assert source.value == "none"


def test_explicit_dollar_target_wins_over_derived_percentage_target():
    """User-authored intent beats a Coral-derived number."""
    effective, source = resolve_effective_target_amount(
        target_amount=Decimal("15000"), target_percentage_of_income=Decimal("5"),
        plannable_income=Decimal("10000"),
    )
    assert effective == Decimal("15000")
    assert source.value == "explicit"


# ── Status: plan-anchored, never fabricated ─────────────────────────────────

def test_percentage_goal_below_plan_target_is_behind_not_on_track():
    """$100 saved against a 5%-of-$10,000 plan target is $400 short — recent
    activity must not mask a plan shortfall."""
    status = compute_goal_status(
        target_amount=None, current_amount=Decimal("100"),
        most_recent_contribution_date=date(2026, 8, 30), as_of=AS_OF,
        target_percentage_of_income=Decimal("5"), plannable_income=Decimal("10000"),
    )
    assert status == GoalStatus.BEHIND


def test_percentage_goal_at_plan_target_is_on_track():
    status = compute_goal_status(
        target_amount=None, current_amount=Decimal("500"),
        most_recent_contribution_date=date(2026, 8, 30), as_of=AS_OF,
        target_percentage_of_income=Decimal("5"), plannable_income=Decimal("10000"),
    )
    assert status == GoalStatus.ON_TRACK


def test_percentage_goal_is_never_marked_complete_even_when_far_above_target():
    """A rate commitment has no finish line — only an explicit $ target can
    complete a goal (and only completion triggers the reallocation prompt)."""
    status = compute_goal_status(
        target_amount=None, current_amount=Decimal("99999"),
        most_recent_contribution_date=date(2026, 8, 30), as_of=AS_OF,
        target_percentage_of_income=Decimal("5"), plannable_income=Decimal("10000"),
    )
    assert status == GoalStatus.ON_TRACK
    assert build_completion_recommendation(
        goal_id="g", goal_name="Emergency Fund", status=status,
        target_amount=None, current_amount=Decimal("99999"),
    ) is None


def test_completion_recommendation_always_requires_user_approval():
    """M6: completed goals must not auto-reallocate."""
    rec = build_completion_recommendation(
        goal_id="g", goal_name="Emergency Fund", status=GoalStatus.COMPLETE,
        target_amount=Decimal("1000"), current_amount=Decimal("1000"),
    )
    assert rec is not None
    assert rec.requires_user_approval is True
