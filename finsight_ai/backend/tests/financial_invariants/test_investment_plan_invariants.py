"""Financial invariants for PR 11 investment contribution planning."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.entities import AllocationSnapshot, PlanVersionSnapshot, SuballocationSnapshot
from app.domain.investment_plan import compute_investment_contribution_plan
from app.domain.plan_vs_actual import ClassifiedTxn, DriftStatus, Period
from app.domain.transaction_classification import CashFlowType, MasterBucket

PERIOD = Period.for_month(2026, 8)


def _plan() -> PlanVersionSnapshot:
    return PlanVersionSnapshot(
        id="v1",
        plan_id="p1",
        version_number=1,
        effective_from=date(2026, 1, 1),
        allocations=[
            AllocationSnapshot(id="a1", bucket_name="needs", percentage="50", sort_order=0),
            AllocationSnapshot(id="a2", bucket_name="wants", percentage="20", sort_order=1),
            AllocationSnapshot(id="a3", bucket_name="savings", percentage="15", sort_order=2),
            AllocationSnapshot(
                id="a4",
                bucket_name="investments",
                percentage="15",
                sort_order=3,
                suballocations=[
                    SuballocationSnapshot(id="s1", name="401(k)", percentage="6", sort_order=0),
                    SuballocationSnapshot(id="s2", name="Roth IRA", percentage="4", sort_order=1),
                    SuballocationSnapshot(id="s3", name="ESPP", percentage="3", sort_order=2),
                    SuballocationSnapshot(
                        id="s4", name="Taxable Brokerage", percentage="2", sort_order=3,
                    ),
                ],
            ),
        ],
    )


def _plan_without_investment_suballocations() -> PlanVersionSnapshot:
    return PlanVersionSnapshot(
        id="v1",
        plan_id="p1",
        version_number=1,
        effective_from=date(2026, 1, 1),
        allocations=[
            AllocationSnapshot(id="a1", bucket_name="needs", percentage="50", sort_order=0),
            AllocationSnapshot(id="a2", bucket_name="wants", percentage="20", sort_order=1),
            AllocationSnapshot(id="a3", bucket_name="savings", percentage="15", sort_order=2),
            AllocationSnapshot(id="a4", bucket_name="investments", percentage="15", sort_order=3),
        ],
    )


def _txn(
    txn_id: str,
    amount: str,
    bucket: MasterBucket,
    flow: CashFlowType,
    *,
    category: str | None = None,
    account_type: str | None = "checking",
    day: int = 15,
) -> ClassifiedTxn:
    return ClassifiedTxn(
        transaction_id=txn_id,
        account_id=f"acct-{account_type}",
        account_type=account_type,
        transaction_date=date(2026, 8, day),
        amount=Decimal(amount),
        master_bucket=bucket,
        category=category,
        cash_flow_type=flow,
    )


def _income(amount: str = "10000.00") -> ClassifiedTxn:
    return _txn("income", amount, MasterBucket.UNCLASSIFIED, CashFlowType.INCOME)


def _vehicle(result, name: str):
    return next(v for v in result.vehicles if v.vehicle == name)


def test_all_investment_targets_met_by_vehicle():
    result = compute_investment_contribution_plan(
        PERIOD,
        [
            _income(),
            _txn(
                "401k",
                "600.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_CONTRIBUTION,
                category="401(k)",
                account_type="401k",
            ),
            _txn(
                "roth",
                "400.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_CONTRIBUTION,
                category="Roth IRA",
                account_type="roth_ira",
            ),
            _txn(
                "espp",
                "300.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_CONTRIBUTION,
                category="ESPP",
                account_type="individual_brokerage",
            ),
            _txn(
                "taxable",
                "200.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_CONTRIBUTION,
                category="Taxable Brokerage",
                account_type="individual_brokerage",
            ),
        ],
        _plan(),
    )

    assert result.total_target_pct == "15"
    assert result.total_actual_amount == "1500.00"
    assert result.total_actual_pct == "15.00"
    for vehicle in result.vehicles:
        assert vehicle.status == DriftStatus.ON_TRACK
        assert vehicle.variance_pct_points == "0.00"
        assert vehicle.recommended_next_month_delta == "0.00"


def test_top_level_investment_plan_without_suballocations_uses_required_vehicle_targets():
    result = compute_investment_contribution_plan(
        PERIOD,
        [_income()],
        _plan_without_investment_suballocations(),
    )

    assert [(v.vehicle, v.target_pct) for v in result.vehicles] == [
        ("401(k)", "6"),
        ("Roth IRA", "4"),
        ("ESPP", "3"),
        ("Taxable Brokerage", "2"),
    ]
    assert result.total_target_pct == "15"


def test_one_investment_target_behind_recommends_next_month_delta():
    result = compute_investment_contribution_plan(
        PERIOD,
        [
            _income(),
            _txn(
                "roth",
                "0.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_CONTRIBUTION,
                category="Roth IRA",
                account_type="roth_ira",
            ),
        ],
        _plan(),
    )

    roth = _vehicle(result, "Roth IRA")
    assert roth.target_pct == "4"
    assert roth.actual_pct == "0.00"
    assert roth.target_amount == "400.00"
    assert roth.actual_amount == "0.00"
    assert roth.variance_amount == "-400.00"
    assert roth.variance_pct_points == "-4.00"
    assert roth.status == DriftStatus.WATCH
    assert roth.recommended_next_month_delta == "400.00"


def test_over_contribution_is_ahead_not_a_shortfall():
    result = compute_investment_contribution_plan(
        PERIOD,
        [
            _income(),
            _txn(
                "taxable",
                "500.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_CONTRIBUTION,
                category="Taxable Brokerage",
                account_type="individual_brokerage",
            ),
        ],
        _plan(),
    )

    taxable = _vehicle(result, "Taxable Brokerage")
    assert taxable.target_amount == "200.00"
    assert taxable.variance_amount == "300.00"
    assert taxable.variance_pct_points == "3.00"
    assert taxable.status == DriftStatus.ON_TRACK
    assert taxable.recommended_next_month_delta == "0.00"


def test_missing_payroll_data_returns_incomplete_metadata_without_fabricated_income():
    result = compute_investment_contribution_plan(
        PERIOD,
        [
            _income("8000.00"),
            _txn(
                "401k",
                "600.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_CONTRIBUTION,
                category="401(k)",
                account_type="401k",
            ),
        ],
        _plan(),
    )

    row = _vehicle(result, "401(k)")
    assert result.plannable_income == "8000.00"
    assert row.actual_amount == "600.00"
    assert row.target_amount == "480.00"
    assert result.completeness.payroll_deduction_signal_detected is True
    assert row.data_completeness.payroll_data_complete is False
    assert row.data_completeness.is_complete is False


def test_zero_income_never_fabricates_targets_or_percentages():
    result = compute_investment_contribution_plan(
        PERIOD,
        [
            _txn(
                "taxable",
                "250.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_CONTRIBUTION,
                category="Taxable Brokerage",
                account_type="individual_brokerage",
            ),
        ],
        _plan(),
    )

    taxable = _vehicle(result, "Taxable Brokerage")
    assert result.plannable_income == "0.00"
    assert taxable.actual_amount == "250.00"
    assert taxable.target_pct == "2"
    assert taxable.target_amount is None
    assert taxable.actual_pct is None
    assert taxable.variance_amount is None
    assert taxable.status == DriftStatus.UNKNOWN
    assert result.completeness.income_observed is False


def test_multi_account_contributions_roll_up_by_vehicle():
    result = compute_investment_contribution_plan(
        PERIOD,
        [
            _income(),
            _txn(
                "roth-1",
                "150.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_CONTRIBUTION,
                category="Roth IRA",
                account_type="ira",
                day=4,
            ),
            _txn(
                "roth-2",
                "250.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_CONTRIBUTION,
                category="Roth IRA",
                account_type="ira",
                day=20,
            ),
        ],
        _plan(),
    )

    roth = _vehicle(result, "Roth IRA")
    assert roth.actual_amount == "400.00"
    assert roth.transaction_count == 2
    assert roth.status == DriftStatus.ON_TRACK


def test_rollovers_are_not_counted_as_new_contributions():
    result = compute_investment_contribution_plan(
        PERIOD,
        [
            _income(),
            _txn(
                "rollover",
                "15000.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_ACTIVITY,
                category="401(k)",
                account_type="401k",
            ),
        ],
        _plan(),
    )

    row = _vehicle(result, "401(k)")
    assert row.actual_amount == "0.00"
    assert row.transaction_count == 0


def test_investment_transfer_is_counted_once_not_double_counted():
    result = compute_investment_contribution_plan(
        PERIOD,
        [
            _income(),
            _txn(
                "origin",
                "-200.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_CONTRIBUTION,
                category="Taxable Brokerage",
                account_type="checking",
            ),
            _txn(
                "dest",
                "200.00",
                MasterBucket.INVESTMENTS,
                CashFlowType.INVESTMENT_CONTRIBUTION,
                category="Taxable Brokerage",
                account_type="individual_brokerage",
            ),
        ],
        _plan(),
    )

    row = _vehicle(result, "Taxable Brokerage")
    assert row.actual_amount == "200.00"
    assert row.transaction_count == 1
    assert result.total_actual_amount == "200.00"
