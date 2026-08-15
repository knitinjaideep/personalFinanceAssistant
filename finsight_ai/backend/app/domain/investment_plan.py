"""Deterministic investment contribution planning (PR 11).

Contribution allocation answers "Where is new income being invested?" and is
separate from portfolio allocation ("What assets do I own?"). This module
therefore reads classified cash-flow transactions, not holdings or balances.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain.entities import PlanVersionSnapshot
from app.domain.plan_vs_actual import (
    DEFAULT_STATUS_THRESHOLDS,
    ClassifiedTxn,
    CompletenessMetadata,
    DriftStatus,
    Period,
    StatusThresholds,
    aggregate_category_actuals,
    build_completeness_metadata,
    compute_plannable_income,
    compute_status,
)
from app.domain.transaction_classification import MasterBucket

_CENTS = Decimal("0.01")
_PCT = Decimal("0.01")
_HUNDRED = Decimal("100")
DEFAULT_INVESTMENT_TARGETS: tuple[tuple[str, Decimal], ...] = (
    ("401(k)", Decimal("6")),
    ("Roth IRA", Decimal("4")),
    ("ESPP", Decimal("3")),
    ("Taxable Brokerage", Decimal("2")),
)
DEFAULT_INVESTMENT_VEHICLES = tuple(name for name, _ in DEFAULT_INVESTMENT_TARGETS)

CompletenessStatus = Literal["complete", "incomplete"]


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _round_pct(value: Decimal) -> Decimal:
    return value.quantize(_PCT, rounding=ROUND_HALF_UP)


class ContributionDataCompleteness(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: CompletenessStatus
    is_complete: bool
    income_observed: bool
    plan_available: bool
    payroll_data_complete: bool
    notes: list[str]


class InvestmentContributionVehicle(BaseModel):
    model_config = ConfigDict(frozen=True)

    vehicle: str
    target_pct: str | None
    actual_pct: str | None
    target_amount: str | None
    actual_amount: str
    variance_amount: str | None
    variance_pct_points: str | None
    status: DriftStatus
    data_completeness: ContributionDataCompleteness
    recommended_next_month_delta: str | None
    transaction_count: int


class InvestmentContributionPlanResult(BaseModel):
    period: Period
    plannable_income: str
    vehicles: list[InvestmentContributionVehicle]
    total_target_pct: str | None
    total_actual_amount: str
    total_actual_pct: str | None
    completeness: CompletenessMetadata


def _investment_targets(plan: PlanVersionSnapshot | None) -> list[tuple[str, Decimal | None]]:
    if plan is None:
        return list(DEFAULT_INVESTMENT_TARGETS)
    for allocation in plan.allocations:
        if allocation.bucket_name.strip().lower() != MasterBucket.INVESTMENTS.value:
            continue
        if not allocation.suballocations:
            return list(DEFAULT_INVESTMENT_TARGETS)
        configured_targets = [
            (sub.name, Decimal(sub.percentage))
            for sub in sorted(allocation.suballocations, key=lambda s: s.sort_order)
        ]
        configured_names = {name.strip().lower() for name, _ in configured_targets}
        configured_targets.extend(
            (name, pct)
            for name, pct in DEFAULT_INVESTMENT_TARGETS
            if name.strip().lower() not in configured_names
        )
        return configured_targets
    return list(DEFAULT_INVESTMENT_TARGETS)


def _row_completeness(
    base: CompletenessMetadata, *, target_pct: Decimal | None,
) -> ContributionDataCompleteness:
    notes = list(base.notes)
    if target_pct is None:
        notes.append("No investment contribution target is defined for this vehicle.")
    complete = base.is_complete and target_pct is not None
    return ContributionDataCompleteness(
        status="complete" if complete else "incomplete",
        is_complete=complete,
        income_observed=base.income_observed,
        plan_available=base.plan_available,
        payroll_data_complete=not base.payroll_deduction_signal_detected,
        notes=notes,
    )


def _vehicle_row(
    *,
    vehicle: str,
    target_pct: Decimal | None,
    actual_amount: Decimal,
    transaction_count: int,
    plannable_income: Decimal,
    completeness: CompletenessMetadata,
    thresholds: StatusThresholds,
) -> InvestmentContributionVehicle:
    target_amount = (
        _round_money(plannable_income * target_pct / _HUNDRED)
        if target_pct is not None and plannable_income > 0
        else None
    )
    actual_pct = (
        _round_pct(actual_amount / plannable_income * _HUNDRED)
        if plannable_income > 0
        else None
    )
    variance_amount = (
        _round_money(actual_amount - target_amount) if target_amount is not None else None
    )
    variance_pct = (
        _round_pct(actual_pct - target_pct)
        if actual_pct is not None and target_pct is not None
        else None
    )
    status = compute_status(MasterBucket.INVESTMENTS, variance_pct, thresholds)
    recommended = None
    if variance_amount is not None:
        recommended = str(
            _round_money(abs(variance_amount) if variance_amount < 0 else Decimal("0"))
        )
    return InvestmentContributionVehicle(
        vehicle=vehicle,
        target_pct=str(target_pct) if target_pct is not None else None,
        actual_pct=str(actual_pct) if actual_pct is not None else None,
        target_amount=str(target_amount) if target_amount is not None else None,
        actual_amount=str(_round_money(actual_amount)),
        variance_amount=str(variance_amount) if variance_amount is not None else None,
        variance_pct_points=str(variance_pct) if variance_pct is not None else None,
        status=status,
        data_completeness=_row_completeness(completeness, target_pct=target_pct),
        recommended_next_month_delta=recommended,
        transaction_count=transaction_count,
    )


def compute_investment_contribution_plan(
    period: Period,
    transactions: list[ClassifiedTxn],
    plan: PlanVersionSnapshot | None,
    *,
    thresholds: StatusThresholds = DEFAULT_STATUS_THRESHOLDS,
    plan_version_changed_mid_period: bool = False,
) -> InvestmentContributionPlanResult:
    """Calculate Plan vs Actual investment contributions by vehicle.

    Uses `aggregate_category_actuals`, the same contribution-leg gate used by
    Plan vs Actual. Rollovers and investment activity are excluded, and
    checking->brokerage transfers are counted once.
    """
    plannable_income = compute_plannable_income(transactions)
    actuals = aggregate_category_actuals(transactions, MasterBucket.INVESTMENTS)
    completeness = build_completeness_metadata(
        transactions,
        plannable_income=plannable_income,
        plan_available=plan is not None,
        plan_version_changed_mid_period=plan_version_changed_mid_period,
    )

    targets = _investment_targets(plan)
    seen = {name for name, _ in targets}
    for actual_name in sorted(actuals):
        if actual_name not in seen:
            targets.append((actual_name, None))

    vehicles = [
        _vehicle_row(
            vehicle=name,
            target_pct=target_pct,
            actual_amount=actuals.get(name, (Decimal("0"), 0))[0],
            transaction_count=actuals.get(name, (Decimal("0"), 0))[1],
            plannable_income=plannable_income,
            completeness=completeness,
            thresholds=thresholds,
        )
        for name, target_pct in targets
    ]

    total_actual = _round_money(
        sum((Decimal(row.actual_amount) for row in vehicles), Decimal("0"))
    )
    total_actual_pct = (
        _round_pct(total_actual / plannable_income * _HUNDRED)
        if plannable_income > 0 else None
    )
    target_values = [target for _, target in targets if target is not None]
    total_target_pct = sum(target_values, Decimal("0")) if target_values else None
    return InvestmentContributionPlanResult(
        period=period,
        plannable_income=str(plannable_income),
        vehicles=vehicles,
        total_target_pct=str(total_target_pct) if total_target_pct is not None else None,
        total_actual_amount=str(total_actual),
        total_actual_pct=str(total_actual_pct) if total_actual_pct is not None else None,
        completeness=completeness,
    )
