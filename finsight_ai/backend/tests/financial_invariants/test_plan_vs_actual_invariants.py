"""
Financial invariant tests for the Plan vs Actual engine (PR 04 —
app.domain.plan_vs_actual / app.services.plan_vs_actual).

Maps onto backend/tests/financial_invariants/README.md. Pure domain-level
tests only (no DB) — DB-integration coverage (multi-account aggregation via
real accounts, plan-version resolution by date, auto-classification of NULL
rows) lives in backend/tests/test_plan_vs_actual.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.entities import AllocationSnapshot, PlanVersionSnapshot, SuballocationSnapshot
from app.domain.plan_vs_actual import (
    UNCATEGORIZED,
    ClassifiedTxn,
    DriftStatus,
    Period,
    compute_category_breakdown,
    compute_merchant_drivers,
    compute_plan_vs_actual,
    compute_plannable_income,
    compute_status,
    compute_transaction_drivers,
    is_canonical_contribution_leg,
    payroll_deduction_signal,
)
from app.domain.transaction_classification import CashFlowType, MasterBucket

PERIOD = Period.for_month(2026, 8)


def _default_plan(
    effective_from: date = date(2026, 1, 1), version_number: int = 1,
) -> PlanVersionSnapshot:
    """Mirrors app.services.financial_plan._DEFAULT_ALLOCATIONS (50/20/15/15)."""
    return PlanVersionSnapshot(
        id=f"v{version_number}",
        plan_id="p1",
        version_number=version_number,
        effective_from=effective_from,
        allocations=[
            AllocationSnapshot(id="a1", bucket_name="needs", percentage="50", sort_order=0),
            AllocationSnapshot(id="a2", bucket_name="wants", percentage="20", sort_order=1),
            AllocationSnapshot(
                id="a3", bucket_name="savings", percentage="15", sort_order=2,
                suballocations=[
                    SuballocationSnapshot(
                        id="s1", name="Emergency Fund", percentage="5", sort_order=0,
                    ),
                    SuballocationSnapshot(
                        id="s2", name="House / Goals", percentage="5", sort_order=1,
                    ),
                    SuballocationSnapshot(
                        id="s3", name="Child Savings", percentage="5", sort_order=2,
                    ),
                ],
            ),
            AllocationSnapshot(
                id="a4", bucket_name="investments", percentage="15", sort_order=3,
                suballocations=[
                    SuballocationSnapshot(id="s4", name="401(k)", percentage="6", sort_order=0),
                    SuballocationSnapshot(id="s5", name="Roth IRA", percentage="4", sort_order=1),
                    SuballocationSnapshot(id="s6", name="ESPP", percentage="3", sort_order=2),
                    SuballocationSnapshot(
                        id="s7", name="Taxable Brokerage", percentage="2", sort_order=3,
                    ),
                ],
            ),
        ],
    )


def _txn(
    txn_id: str, amount: str, bucket: MasterBucket, flow: CashFlowType,
    *, category: str | None = None, account_type: str | None = "checking",
    day: int = 15, needs_review: bool = False, merchant: str | None = None,
) -> ClassifiedTxn:
    return ClassifiedTxn(
        transaction_id=txn_id, account_id=f"acct-{account_type}",
        account_type=account_type, transaction_date=date(2026, 8, day),
        amount=Decimal(amount), master_bucket=bucket, category=category,
        cash_flow_type=flow, needs_review=needs_review, merchant_name=merchant,
    )


# ── Invariant: master plan allocation totals 100% ───────────────────────────

def test_default_plan_targets_sum_to_100():
    plan = _default_plan()
    top_level_total = sum(Decimal(a.percentage) for a in plan.allocations)
    assert top_level_total == Decimal("100")


# ── Perfect 50/20/15/15 month ───────────────────────────────────────────────

def test_perfect_5020_15_15_month_is_on_track_for_every_bucket():
    plan = _default_plan()
    income = Decimal("10000.00")
    transactions = [
        _txn("income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("needs", "-5000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Groceries"),
        _txn("wants", "-2000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
        _txn(
            "savings", "1500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category="Emergency Fund", account_type="savings",
        ),
        _txn(
            "invest", "1500.00", MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_CONTRIBUTION,
            category="Taxable Brokerage", account_type="individual_brokerage",
        ),
    ]
    result = compute_plan_vs_actual(PERIOD, transactions, plan)
    assert result.plannable_income == str(income)
    for bucket_row in result.buckets:
        assert bucket_row.status == DriftStatus.ON_TRACK, bucket_row
        assert bucket_row.variance_percentage_points == "0.00"


# ── Wants overspend crosses watch then off_track thresholds ────────────────

def test_wants_overspend_triggers_watch_then_off_track():
    plan = _default_plan()
    base = [_txn("income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME)]

    watch = base + [
        _txn("wants", "-2600.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
    ]
    result = compute_plan_vs_actual(PERIOD, watch, plan)
    wants = next(b for b in result.buckets if b.bucket == MasterBucket.WANTS)
    assert wants.variance_percentage_points == "6.00"
    assert wants.status == DriftStatus.WATCH

    off_track = base + [
        _txn("wants", "-3000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
    ]
    result2 = compute_plan_vs_actual(PERIOD, off_track, plan)
    wants2 = next(b for b in result2.buckets if b.bucket == MasterBucket.WANTS)
    assert wants2.variance_percentage_points == "10.00"
    assert wants2.status == DriftStatus.OFF_TRACK


# ── Savings under target ────────────────────────────────────────────────────

def test_savings_under_target_is_adverse_not_overspend():
    plan = _default_plan()
    transactions = [
        _txn("income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn(
            "savings", "500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category="Emergency Fund", account_type="savings",
        ),
    ]
    result = compute_plan_vs_actual(PERIOD, transactions, plan)
    savings = next(b for b in result.buckets if b.bucket == MasterBucket.SAVINGS)
    # target 15% of 10000 = 1500; actual 500 -> actual% 5.00, variance -10.00pp
    assert savings.actual_percentage == "5.00"
    assert savings.variance_percentage_points == "-10.00"
    assert savings.status == DriftStatus.OFF_TRACK
    # Overshooting is never penalized (accumulation-bucket polarity).
    over_transactions = transactions[:-1] + [
        _txn(
            "savings2", "3000.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category="Emergency Fund", account_type="savings",
        )
    ]
    over_result = compute_plan_vs_actual(PERIOD, over_transactions, plan)
    over_savings = next(b for b in over_result.buckets if b.bucket == MasterBucket.SAVINGS)
    assert over_savings.status == DriftStatus.ON_TRACK


# ── Investments under target ────────────────────────────────────────────────

def test_investments_under_target_is_off_track():
    plan = _default_plan()
    transactions = [
        _txn("income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn(
            "invest", "200.00", MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_CONTRIBUTION,
            category="Roth IRA", account_type="roth_ira",
        ),
    ]
    result = compute_plan_vs_actual(PERIOD, transactions, plan)
    investments = next(b for b in result.buckets if b.bucket == MasterBucket.INVESTMENTS)
    assert investments.actual_percentage == "2.00"
    assert investments.status == DriftStatus.OFF_TRACK


# ── Transfer handling: cross-statement double counting ──────────────────────

def test_checking_to_brokerage_transfer_is_counted_once_not_twice():
    """Both legs of the SAME transfer are independently classified as
    INVESTMENT_CONTRIBUTION by PR 03 (it cannot see across statements). The
    engine must count the contribution exactly once: on the destination
    (brokerage) leg, never the checking origin leg."""
    plan = _default_plan()
    origin_leg = _txn(
        "origin", "-800.00", MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_CONTRIBUTION,
        category="Taxable Brokerage", account_type="checking",
    )
    destination_leg = _txn(
        "dest", "800.00", MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_CONTRIBUTION,
        category="Taxable Brokerage", account_type="individual_brokerage",
    )
    # Both legs are present, so the investment side has coverage this period
    # -> the destination leg is canonical (Option C, coverage-aware hybrid).
    assert is_canonical_contribution_leg(
        destination_leg, savings_coverage=False, investment_coverage=True,
    ) is True
    assert is_canonical_contribution_leg(
        origin_leg, savings_coverage=False, investment_coverage=True,
    ) is False

    result = compute_plan_vs_actual(PERIOD, [origin_leg, destination_leg], plan)
    investments = next(b for b in result.buckets if b.bucket == MasterBucket.INVESTMENTS)
    assert investments.actual_amount == "800.00"  # not 1600.00
    assert investments.transaction_count == 1

    # The excluded origin leg must stay auditable, not silently vanish.
    assert result.completeness.origin_only_transfer_legs_count == 1
    assert result.completeness.origin_only_transfer_legs_amount == "800.00"


def test_checking_to_savings_transfer_is_counted_once_not_twice():
    plan = _default_plan()
    origin_leg = _txn(
        "origin", "-500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
        category="Emergency Fund", account_type="checking",
    )
    destination_leg = _txn(
        "dest", "500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
        category="Emergency Fund", account_type="savings",
    )
    result = compute_plan_vs_actual(PERIOD, [origin_leg, destination_leg], plan)
    savings = next(b for b in result.buckets if b.bucket == MasterBucket.SAVINGS)
    assert savings.actual_amount == "500.00"
    assert savings.transaction_count == 1


# ── Coverage-aware hybrid (Option C, docs/coral-redesign/BLOCKED.md) ───────
#
# Destination-leg-only produced a structural $0.00 Savings actual whenever the
# savings/investment side of the transfer has no ingested transaction
# coverage for the period (Coral's real coverage today: Marcus/529 are
# catalog-only stubs with no parser). These tests cover the resolution.

def test_savings_side_with_no_coverage_falls_back_to_origin_leg():
    """The exact BLOCKED.md worked example: a Chase checking statement shows
    `TRANSFER TO MARCUS SAVINGS -1500.00`, but no Marcus statement has been
    ingested this period (no account_type == "savings" transaction exists at
    all). Under the coverage-aware hybrid, the origin (checking) leg counts
    instead of silently reading Savings actual as $0."""
    plan = _default_plan()
    transactions = [
        _txn("income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn(
            "origin", "-1500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=None, account_type="checking",
        ),
    ]
    result = compute_plan_vs_actual(PERIOD, transactions, plan)
    savings = next(b for b in result.buckets if b.bucket == MasterBucket.SAVINGS)
    assert savings.actual_amount == "1500.00"  # not "0.00"
    assert savings.transaction_count == 1
    # No destination coverage -> the origin leg is counted, not excluded, so
    # there is nothing to report as an "origin-only" leg for this bucket.
    assert result.completeness.origin_only_transfer_legs_count == 0


def test_savings_side_with_coverage_counts_destination_leg_and_excludes_origin():
    """Once the destination (Marcus) statement IS ingested, coverage flips —
    the destination leg becomes canonical and the origin leg is correctly
    excluded as a duplicate, with no double counting and a healthy (complete)
    result."""
    plan = _default_plan()
    transactions = [
        _txn("income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn(
            "origin", "-1500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=None, account_type="checking",
        ),
        _txn(
            "dest", "1500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category="Emergency Fund", account_type="savings",
        ),
    ]
    result = compute_plan_vs_actual(PERIOD, transactions, plan)
    savings = next(b for b in result.buckets if b.bucket == MasterBucket.SAVINGS)
    assert savings.actual_amount == "1500.00"  # not "3000.00" (no double count)
    assert savings.transaction_count == 1

    assert result.completeness.origin_only_transfer_legs_count == 1
    assert result.completeness.origin_only_transfer_legs_amount == "1500.00"
    # Fix verified: exclusion backed by real destination coverage is the
    # healthy dedup case and must NOT report the result as incomplete.
    assert result.completeness.is_complete is True


def test_mixed_bucket_coverage_is_a_documented_known_limitation():
    """Known, accepted limitation of Option C (not a bug): coverage is a
    per-bucket proxy, not per-institution pairing. If E*TRADE is ingested but
    Morgan Stanley is not, the Investments bucket as a whole is "covered", so
    a Morgan-Stanley-directed checking-side origin leg is still excluded even
    though the actual Morgan Stanley statement was never ingested — that
    specific contribution silently drops out of the total. This test pins the
    documented tradeoff so a future change doesn't accidentally "fix" it
    without a conscious decision (see docs/coral-redesign/BLOCKED.md
    Option C)."""
    plan = _default_plan()
    etrade_destination_leg = _txn(
        "etrade", "300.00", MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_CONTRIBUTION,
        category="Taxable Brokerage", account_type="individual_brokerage",
    )
    morgan_stanley_origin_leg = _txn(
        "ms_origin", "-1000.00", MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_CONTRIBUTION,
        category=None, account_type="checking",
    )
    result = compute_plan_vs_actual(
        PERIOD, [etrade_destination_leg, morgan_stanley_origin_leg], plan,
    )
    investments = next(b for b in result.buckets if b.bucket == MasterBucket.INVESTMENTS)
    # The $1,000 Morgan Stanley contribution is NOT represented — only the
    # $300 E*TRADE leg counts, because investment_coverage is True (E*TRADE
    # has a transaction this period) even though Morgan Stanley itself was
    # never ingested. This is the accepted tradeoff, not the ideal outcome.
    assert investments.actual_amount == "300.00"
    assert investments.transaction_count == 1
    assert result.completeness.origin_only_transfer_legs_count == 1
    assert result.completeness.origin_only_transfer_legs_amount == "1000.00"


def test_accumulation_to_accumulation_move_counts_as_a_new_contribution():
    """KNOWN LIMITATION of the origin-leg fallback (see "Known limitations" in
    docs/PLAN_VS_ACTUAL_ENGINE.md): the fallback counts ANY leg that is not on
    the destination account type — including one living on the *other*
    accumulation account. A `TRANSFER TO MARCUS SAVINGS` line on an E*TRADE
    statement, in a period with no ingested savings-typed account, therefore
    reads as a new Savings contribution even though those dollars were
    allocated in an earlier period (compare accounting-invariants.md #5).

    The dedup itself is still sound — the movement is counted exactly once,
    never on both statements. Pinned so a future change to the fallback
    predicate is a conscious decision rather than an accident.
    """
    plan = _default_plan()
    transactions = [
        _txn("income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        # Origin leg observed on the BROKERAGE statement, headed for Marcus.
        _txn(
            "etrade_to_marcus", "-2000.00", MasterBucket.SAVINGS,
            CashFlowType.SAVINGS_CONTRIBUTION, category=None,
            account_type="individual_brokerage",
        ),
    ]
    result = compute_plan_vs_actual(PERIOD, transactions, plan)
    savings = next(b for b in result.buckets if b.bucket == MasterBucket.SAVINGS)
    investments = next(b for b in result.buckets if b.bucket == MasterBucket.INVESTMENTS)
    # Counted as a new Savings contribution (the documented limitation)...
    assert savings.actual_amount == "2000.00"
    assert savings.transaction_count == 1
    # ...and it does NOT also reduce Investments, so the two buckets are not
    # reconciled against each other — the reason this is worth revisiting.
    assert investments.actual_amount == "0.00"
    # Counted exactly once, never on both statements.
    assert result.completeness.origin_only_transfer_legs_count == 0


# ── Credit-card payment must never double count purchase spend ─────────────

def test_credit_card_payment_does_not_double_count_purchase():
    plan = _default_plan()
    purchase = _txn(
        "purchase", "-150.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Shopping",
    )
    # The checking-side card payment is neutral (UNCLASSIFIED/TRANSFER) per
    # PR 03 — it must never be aggregated into any bucket.
    payment = _txn("payment", "-150.00", MasterBucket.UNCLASSIFIED, CashFlowType.TRANSFER)

    result = compute_plan_vs_actual(PERIOD, [purchase, payment], plan)
    wants = next(b for b in result.buckets if b.bucket == MasterBucket.WANTS)
    assert wants.actual_amount == "150.00"
    assert wants.transaction_count == 1


# ── Refund reduces/offsets spending ─────────────────────────────────────────

def test_refund_reduces_spending_within_same_category():
    plan = _default_plan()
    charge = _txn(
        "charge", "-100.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Groceries",
    )
    refund = _txn("refund", "30.00", MasterBucket.NEEDS, CashFlowType.REFUND, category="Groceries")

    result = compute_plan_vs_actual(PERIOD, [charge, refund], plan)
    needs = next(b for b in result.buckets if b.bucket == MasterBucket.NEEDS)
    assert needs.actual_amount == "70.00"

    breakdown = compute_category_breakdown([charge, refund], MasterBucket.NEEDS, plan)
    groceries = next(c for c in breakdown if c.category == "Groceries")
    assert groceries.actual_amount == "70.00"


# ── Investment rollover is not a new contribution ───────────────────────────

def test_rollover_activity_is_excluded_from_investment_actuals():
    plan = _default_plan()
    rollover = _txn(
        "rollover", "-15000.00", MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_ACTIVITY,
        category="401(k)", account_type="401k",
    )
    result = compute_plan_vs_actual(PERIOD, [rollover], plan)
    investments = next(b for b in result.buckets if b.bucket == MasterBucket.INVESTMENTS)
    assert investments.actual_amount == "0.00"
    assert investments.transaction_count == 0


# ── Multi-account aggregation ───────────────────────────────────────────────

def test_multi_account_spending_aggregates_into_one_bucket_total():
    plan = _default_plan()
    transactions = [
        _txn(
            "a1", "-50.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Groceries", account_type="checking",
        ),
        _txn(
            "a2", "-25.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Utilities", account_type="checking",
        ),
        _txn(
            "a3", "-10.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Healthcare", account_type="credit_card",
        ),
    ]
    for i, t in enumerate(transactions):
        t.account_id = f"account-{i}"
    result = compute_plan_vs_actual(PERIOD, transactions, plan)
    needs = next(b for b in result.buckets if b.bucket == MasterBucket.NEEDS)
    assert needs.actual_amount == "85.00"
    assert needs.transaction_count == 3


# ── Historical plan version stability ───────────────────────────────────────

def test_plan_change_does_not_rewrite_a_prior_periods_targets():
    plan_a = _default_plan(effective_from=date(2026, 8, 1), version_number=1)
    plan_b = PlanVersionSnapshot(
        id="v2", plan_id="p1", version_number=2, effective_from=date(2027, 1, 1),
        allocations=[
            AllocationSnapshot(id="b1", bucket_name="needs", percentage="45", sort_order=0),
            AllocationSnapshot(id="b2", bucket_name="wants", percentage="25", sort_order=1),
            AllocationSnapshot(id="b3", bucket_name="savings", percentage="15", sort_order=2),
            AllocationSnapshot(id="b4", bucket_name="investments", percentage="15", sort_order=3),
        ],
    )
    transactions = [_txn("income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME)]

    december_result = compute_plan_vs_actual(Period.for_month(2026, 12), transactions, plan_a)
    needs_dec = next(b for b in december_result.buckets if b.bucket == MasterBucket.NEEDS)
    assert needs_dec.target_percentage == "50"

    january_result = compute_plan_vs_actual(Period.for_month(2027, 1), transactions, plan_b)
    needs_jan = next(b for b in january_result.buckets if b.bucket == MasterBucket.NEEDS)
    assert needs_jan.target_percentage == "45"


# ── Missing classification / incomplete data honesty ────────────────────────

def test_unclassified_transactions_are_excluded_not_fabricated():
    plan = _default_plan()
    transactions = [
        _txn("income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("mystery", "-40.00", MasterBucket.UNCLASSIFIED, CashFlowType.OTHER, needs_review=True),
    ]
    result = compute_plan_vs_actual(PERIOD, transactions, plan)
    for bucket_row in result.buckets:
        assert bucket_row.transaction_count == 0 or bucket_row.bucket in (
            MasterBucket.NEEDS, MasterBucket.WANTS, MasterBucket.SAVINGS, MasterBucket.INVESTMENTS,
        )
    assert result.completeness.unclassified_transaction_count == 1
    assert result.completeness.unclassified_amount == "40.00"
    assert result.completeness.needs_review_count == 1
    assert result.completeness.is_complete is False


def test_null_category_groups_under_explicit_uncategorized_not_dropped():
    plan = _default_plan()
    transactions = [
        _txn(
            "savings_generic", "300.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category=None, account_type="savings",
        ),
    ]
    breakdown = compute_category_breakdown(transactions, MasterBucket.SAVINGS, plan)
    assert len(breakdown) == 1
    assert breakdown[0].category == UNCATEGORIZED
    assert breakdown[0].actual_amount == "300.00"
    # No plan suballocation target is defined for the generic bucket — must
    # not fabricate one.
    assert breakdown[0].target_percentage is None
    assert breakdown[0].status == DriftStatus.UNKNOWN


# ── Incomplete payroll data ──────────────────────────────────────────────────

def test_payroll_deducted_contribution_is_counted_and_flagged_incomplete():
    """A 401(k) contribution that only ever appears on the retirement account
    (payroll-deducted, never touches checking) must still be counted exactly
    once as an Investments actual — but Plannable Income must NOT invent a
    matching gross-pay figure, and the gap must be reported."""
    plan = _default_plan()
    transactions = [
        _txn("income", "8000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn(
            "401k", "600.00", MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_CONTRIBUTION,
            category="401(k)", account_type="401k",
        ),
    ]
    assert payroll_deduction_signal(transactions) is True
    assert compute_plannable_income(transactions) == Decimal("8000.00")

    result = compute_plan_vs_actual(PERIOD, transactions, plan)
    investments = next(b for b in result.buckets if b.bucket == MasterBucket.INVESTMENTS)
    assert investments.actual_amount == "600.00"
    assert result.completeness.payroll_deduction_signal_detected is True
    assert result.completeness.is_complete is False
    assert any("Payroll-deducted" in note for note in result.completeness.notes)


def test_no_income_observed_never_fabricates_a_percentage():
    plan = _default_plan()
    transactions = [
        _txn("needs", "-500.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Groceries"),
    ]
    result = compute_plan_vs_actual(PERIOD, transactions, plan)
    needs = next(b for b in result.buckets if b.bucket == MasterBucket.NEEDS)
    assert needs.actual_amount == "500.00"  # the real $ is still shown
    assert needs.actual_percentage is None  # but % against $0 income is honestly undefined
    assert needs.status == DriftStatus.UNKNOWN
    assert result.completeness.income_observed is False


def test_no_income_observed_never_fabricates_a_zero_dollar_target():
    """50% of an unobserved income is NOT "$0 target"; rendering
    'Target $0 / Actual $500 / +$500 over plan' would be fabricated precision
    for what is almost always missing payroll coverage (invariant #10)."""
    plan = _default_plan()
    transactions = [
        _txn("needs", "-500.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Groceries"),
    ]
    result = compute_plan_vs_actual(PERIOD, transactions, plan)
    for bucket_row in result.buckets:
        assert bucket_row.target_percentage is not None  # the PLAN is still known
        assert bucket_row.target_amount is None          # the target $ is not
        assert bucket_row.variance_amount is None
        assert bucket_row.variance_percentage_points is None
        assert bucket_row.status == DriftStatus.UNKNOWN

    breakdown = compute_category_breakdown(transactions, MasterBucket.NEEDS, plan)
    assert breakdown[0].actual_amount == "500.00"
    assert breakdown[0].target_amount is None
    assert breakdown[0].variance_amount is None


def test_completeness_note_never_claims_a_destination_leg_was_searched_for():
    """The engine performs no cross-statement pairing, so it must not assert
    that a matching destination transaction 'was not found' — that claim is
    false exactly when both legs are ingested and dedup worked correctly."""
    plan = _default_plan()
    origin_leg = _txn(
        "origin", "-500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
        category="Emergency Fund", account_type="checking",
    )
    destination_leg = _txn(
        "dest", "500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
        category="Emergency Fund", account_type="savings",
    )
    result = compute_plan_vs_actual(PERIOD, [origin_leg, destination_leg], plan)
    savings = next(b for b in result.buckets if b.bucket == MasterBucket.SAVINGS)
    assert savings.actual_amount == "500.00"  # deduped correctly
    joined = " ".join(result.completeness.notes)
    assert "no matching destination-account transaction was found" not in joined


def test_category_target_matches_plan_suballocation_case_insensitively():
    """A user-authored plan storing 'emergency fund' must still resolve the
    'Emergency Fund' category's 5% target rather than silently reporting no
    target at all."""
    plan = _default_plan()
    savings_alloc = next(a for a in plan.allocations if a.bucket_name == "savings")
    savings_alloc.suballocations[0].name = "  emergency fund  "

    transactions = [
        _txn("income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn(
            "ef", "500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
            category="Emergency Fund", account_type="savings",
        ),
    ]
    breakdown = compute_category_breakdown(transactions, MasterBucket.SAVINGS, plan)
    row = next(c for c in breakdown if c.category == "Emergency Fund")
    assert row.target_percentage == "5"
    assert row.target_amount == "500.00"
    assert row.status == DriftStatus.ON_TRACK


# ── Transaction-level drivers (PR 08 — Category -> merchants -> transactions) ─

def test_transaction_drivers_sum_reconciles_to_merchant_driver_amount():
    """The `compute_transaction_drivers` leaf level must always sum to the
    `compute_merchant_drivers` amount for the same merchant/bucket/category —
    both use the identical `_counts_toward_bucket` eligibility gate, so a
    reconciliation gap here would indicate the two functions' gates drifted
    apart (accounting-invariants.md: never double count, never silently drop)."""
    transactions = [
        _txn(
            "t1", "-60.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Groceries", merchant="Whole Foods",
        ),
        _txn(
            "t2", "-25.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Groceries", merchant="Whole Foods",
        ),
        _txn(
            "t3", "-40.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Transportation", merchant="Shell",
        ),
        # Checking-side card payment — must never appear in either driver list.
        _txn("payment", "-150.00", MasterBucket.UNCLASSIFIED, CashFlowType.TRANSFER),
    ]
    merchants = compute_merchant_drivers(transactions, bucket=MasterBucket.NEEDS)
    whole_foods = next(m for m in merchants if m.merchant == "Whole Foods")

    txn_drivers = compute_transaction_drivers(
        transactions, bucket=MasterBucket.NEEDS, merchant="Whole Foods",
    )
    assert len(txn_drivers) == 2
    total = sum((Decimal(t.amount) for t in txn_drivers), Decimal("0"))
    assert str(total) == whole_foods.amount == "85.00"

    # The excluded card-payment transfer never appears in either list.
    all_txn_drivers = compute_transaction_drivers(transactions)
    assert not any(t.transaction_id == "payment" for t in all_txn_drivers)


def test_transaction_drivers_net_refunds_the_same_way_merchant_drivers_do():
    """Invariant #6 must hold identically at the leaf level: a refund appears
    as a NEGATIVE TransactionDrift.amount and the merchant's transactions still
    sum exactly to its MerchantDriver.amount. If the leaf level ever stopped
    netting refunds, a drill-down would appear to show more spending than the
    category/merchant row above it."""
    transactions = [
        _txn(
            "buy", "-200.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Shopping", merchant="Amazon",
        ),
        _txn(
            "refund", "50.00", MasterBucket.WANTS, CashFlowType.REFUND,
            category="Shopping", merchant="Amazon",
        ),
    ]
    merchants = compute_merchant_drivers(
        transactions, bucket=MasterBucket.WANTS, category="Shopping",
    )
    amazon = next(m for m in merchants if m.merchant == "Amazon")
    assert amazon.amount == "150.00"

    rows = compute_transaction_drivers(
        transactions, bucket=MasterBucket.WANTS, category="Shopping", merchant="Amazon",
    )
    by_id = {r.transaction_id: Decimal(r.amount) for r in rows}
    assert by_id == {"buy": Decimal("200.00"), "refund": Decimal("-50.00")}
    assert sum(by_id.values()) == Decimal(amazon.amount)


def test_transaction_drivers_apply_the_same_option_c_transfer_leg_gate():
    """The transaction drill-down must resolve the checking -> savings transfer
    leg with the SAME coverage-aware (Option C, docs/coral-redesign/BLOCKED.md)
    rule as bucket/category/merchant totals — never a parallel gate.

    With destination coverage, the excluded origin leg must not surface in the
    drill-down (it would look like double the real contribution when read
    alongside the counted destination leg); with no coverage, the origin leg
    IS the canonical leg and must surface.
    """
    origin_leg = _txn(
        "origin", "-1500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
        category=None, account_type="checking", merchant="TRANSFER TO MARCUS SAVINGS",
    )
    destination_leg = _txn(
        "dest", "1500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
        category="Emergency Fund", account_type="savings", merchant="DEPOSIT FROM CHASE",
    )

    # Destination coverage present -> only the destination leg drills down.
    covered = compute_transaction_drivers(
        [origin_leg, destination_leg], bucket=MasterBucket.SAVINGS,
    )
    assert [r.transaction_id for r in covered] == ["dest"]
    assert sum(Decimal(r.amount) for r in covered) == Decimal("1500.00")

    # No destination coverage -> the origin leg is canonical and drills down,
    # normalized to the positive dollar amount that actually moved (same
    # `_signed_bucket_amount` convention as every other level).
    uncovered = compute_transaction_drivers([origin_leg], bucket=MasterBucket.SAVINGS)
    assert [r.transaction_id for r in uncovered] == ["origin"]
    assert uncovered[0].amount == "1500.00"

    # And the leaf level reconciles to the merchant level in BOTH coverage
    # states — the two gates can never silently diverge.
    for txns in ([origin_leg, destination_leg], [origin_leg]):
        merchant_total = sum(
            Decimal(m.amount)
            for m in compute_merchant_drivers(txns, bucket=MasterBucket.SAVINGS)
        )
        leaf_total = sum(
            Decimal(r.amount)
            for r in compute_transaction_drivers(txns, bucket=MasterBucket.SAVINGS)
        )
        assert leaf_total == merchant_total == Decimal("1500.00")


def test_transaction_drivers_exclude_internal_transfers_between_own_accounts():
    """Invariant #1: a checking -> checking internal transfer is neutral and
    must never appear as a "driver" the user can drill into (pr-08: "Internal
    transfers must never appear in Top Drivers")."""
    transactions = [
        _txn(
            "spend", "-80.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Groceries", merchant="Whole Foods",
        ),
        _txn("xfer_out", "-500.00", MasterBucket.UNCLASSIFIED, CashFlowType.TRANSFER),
        _txn(
            "xfer_in", "500.00", MasterBucket.UNCLASSIFIED, CashFlowType.TRANSFER,
            account_type="checking",
        ),
        # Defensive: even a transfer mislabelled into a consumption bucket by a
        # future classifier change stays out — the gate keys off cash_flow_type.
        _txn("xfer_mislabelled", "-500.00", MasterBucket.NEEDS, CashFlowType.TRANSFER),
    ]
    rows = compute_transaction_drivers(transactions)
    assert [r.transaction_id for r in rows] == ["spend"]


def test_transaction_drivers_sorted_by_date_descending():
    transactions = [
        _txn(
            "early", "-10.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Groceries", day=1,
        ),
        _txn(
            "late", "-20.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Groceries", day=20,
        ),
    ]
    rows = compute_transaction_drivers(transactions, bucket=MasterBucket.NEEDS)
    assert [r.transaction_id for r in rows] == ["late", "early"]


# ── Whole-bucket merchant drivers reconcile to the bucket's actual $ ───────
# This is the invariant Banking's bucket-anchored "Top Drivers" card depends
# on (docs/coral-redesign/BLOCKED.md, Decision 2 — Option B): the card
# decomposes a Needs/Wants bucket's ACTUAL $ into "top N merchants + all other
# merchants", where the "all other" row is computed as
# `bucket.actual_amount - sum(top N merchant amounts)`. If an unbounded
# whole-bucket merchant list ever stopped summing to the bucket total, that
# residual would silently absorb the discrepancy and misstate the money.

def test_whole_bucket_merchant_drivers_sum_to_the_bucket_actual_amount():
    plan = _default_plan()
    transactions = [
        _txn("income", "10000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn(
            "w1", "-900.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Shopping", merchant="Amazon",
        ),
        # Same merchant in a DIFFERENT category within the same bucket — the
        # whole-bucket (category=None) call groups these as two separate rows,
        # and both must be part of the reconciliation.
        _txn(
            "w2", "-300.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Dining", merchant="Amazon",
        ),
        _txn(
            "w3", "-450.00", MasterBucket.WANTS, CashFlowType.EXPENSE,
            category="Shopping", merchant="Target",
        ),
        # Refund nets down its merchant (invariant #6) at both levels.
        _txn(
            "w4", "120.00", MasterBucket.WANTS, CashFlowType.REFUND,
            category="Shopping", merchant="Target",
        ),
        # Uncategorized Wants spend must still be reconciled, not dropped.
        _txn("w5", "-70.00", MasterBucket.WANTS, CashFlowType.EXPENSE, merchant="Kiosk"),
        # Excluded everywhere: card payment + internal transfer + another
        # bucket's spend must not leak into the Wants reconciliation.
        _txn("payment", "-800.00", MasterBucket.UNCLASSIFIED, CashFlowType.TRANSFER),
        _txn("xfer", "-200.00", MasterBucket.UNCLASSIFIED, CashFlowType.TRANSFER),
        _txn(
            "n1", "-5000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE,
            category="Housing", merchant="Landlord",
        ),
    ]

    result = compute_plan_vs_actual(PERIOD, transactions, plan)
    wants = next(b for b in result.buckets if b.bucket == MasterBucket.WANTS)
    assert wants.actual_amount == "1600.00"  # 900 + 300 + 450 - 120 + 70

    # Unbounded whole-bucket merchant list (no category filter) — exactly what
    # `bankingApi.merchantDrivers(bucket, null, …)` requests, minus the display
    # limit — reconciles to the bucket total to the cent.
    merchants = compute_merchant_drivers(
        transactions, bucket=MasterBucket.WANTS, category=None, top_n=1000,
    )
    assert sum(Decimal(m.amount) for m in merchants) == Decimal(wants.actual_amount)
    assert not any(m.merchant == "Landlord" for m in merchants)

    # The card's "all other merchants" residual is therefore exactly the net
    # total of the merchants that were not displayed — never a plug figure.
    top_2 = compute_merchant_drivers(
        transactions, bucket=MasterBucket.WANTS, category=None, top_n=2,
    )
    residual = Decimal(wants.actual_amount) - sum(Decimal(m.amount) for m in top_2)
    untouched = sum(Decimal(m.amount) for m in merchants[2:])
    assert residual == untouched

    # The bucket's drift is a different number from its actual $ — the merchant
    # list must never be presented as summing to the drift (Option B's copy
    # requirement). target = 20% of 10000 = 2000, so Wants is $400 UNDER plan
    # here even though $1,600 of merchant spend decomposes cleanly.
    assert wants.target_amount == "2000.00"
    assert wants.variance_amount == "-400.00"
    assert Decimal(wants.variance_amount) != sum(Decimal(m.amount) for m in merchants)


# ── compute_status is centralized, not scattered magic numbers ─────────────

def test_compute_status_polarity_differs_by_bucket_type():
    # +5pp variance: overspend is adverse for a consumption bucket...
    assert compute_status(MasterBucket.WANTS, Decimal("5")) == DriftStatus.WATCH
    # ...but the same +5pp (overshoot) is NOT adverse for an accumulation bucket.
    assert compute_status(MasterBucket.SAVINGS, Decimal("5")) == DriftStatus.ON_TRACK
    # -5pp (shortfall) is adverse for accumulation buckets.
    assert compute_status(MasterBucket.INVESTMENTS, Decimal("-5")) == DriftStatus.WATCH
