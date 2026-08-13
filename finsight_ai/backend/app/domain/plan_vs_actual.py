"""
Plan vs Actual calculation engine — pure, deterministic Decimal math.

Answers, for any requested period: PLAN vs ACTUAL = DRIFT.

This module never touches the database and never calls an LLM — it consumes
already-classified transaction rows (see `ClassifiedTxn`, duck-typed from
`TransactionModel` + the transaction's account by the service layer in
`app.services.plan_vs_actual`) and a resolved plan version (see
`app.domain.entities.PlanVersionSnapshot` from `app.services.financial_plan`),
and produces a `PlanVsActualResult`.

See docs/PLAN_VS_ACTUAL_ENGINE.md for the full model description, including
the documented cross-statement double-counting rule and Plannable Income
definition.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.domain.entities import PlanVersionSnapshot
from app.domain.transaction_classification import (
    INVESTMENT_ACCOUNT_TYPES,
    SAVINGS_ACCOUNT_TYPES,
    CashFlowType,
    MasterBucket,
)

_CENTS = Decimal("0.01")
_PCT = Decimal("0.01")
_HUNDRED = Decimal("100")

# Categories (from app.domain.transaction_classification) that the seeded
# financial plan defines explicit suballocation targets for. Needs/Wants
# categories have NO plan-defined sub-targets (only the top-level 50%/20%),
# so their category breakdown never fabricates a target — see
# CategoryDrift.target_percentage being None for those rows.
_ACCUMULATION_BUCKETS: frozenset[MasterBucket] = frozenset(
    {MasterBucket.SAVINGS, MasterBucket.INVESTMENTS}
)
_CONSUMPTION_BUCKETS: frozenset[MasterBucket] = frozenset(
    {MasterBucket.NEEDS, MasterBucket.WANTS}
)

UNCATEGORIZED = "Uncategorized"


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _round_pct(value: Decimal) -> Decimal:
    return value.quantize(_PCT, rounding=ROUND_HALF_UP)


# ── Period ───────────────────────────────────────────────────────────────────

class Period(BaseModel):
    """An inclusive [start, end] date range plus a display label."""

    start: date
    end: date
    label: str

    model_config = ConfigDict(frozen=True)

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, v: date, info: ValidationInfo) -> date:
        start = info.data.get("start")
        if start is not None and v < start:
            raise ValueError("Period.end must not be before Period.start")
        return v

    @classmethod
    def for_month(cls, year: int, month: int) -> Period:
        start = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end = date(year, month, last_day)
        return cls(start=start, end=end, label=f"{year:04d}-{month:02d}")


# ── Status ───────────────────────────────────────────────────────────────────

class DriftStatus(str, Enum):
    ON_TRACK = "on_track"
    WATCH = "watch"
    OFF_TRACK = "off_track"
    # Not enough data to assess drift honestly (e.g. Plannable Income is $0
    # this period, or the bucket/category has no plan target) — never
    # fabricated as on_track/off_track. See accounting-invariants.md #10.
    UNKNOWN = "unknown"


class StatusThresholds(BaseModel):
    """Centralized, configurable drift-status thresholds, expressed in
    percentage points of Plannable Income. Every status decision in this
    module goes through `compute_status()` with one of these — no scattered
    magic numbers.

    Defaults (documented, not hard facts): a bucket/category is `on_track`
    while its adverse drift is within 3 percentage points of target, `watch`
    between 3 and 7 points, and `off_track` beyond 7 points. "Adverse" means
    overspend for Needs/Wants (consumption) and shortfall for
    Savings/Investments (accumulation) — see `compute_status()`.
    """

    watch_pp: Decimal = Decimal("3")
    off_track_pp: Decimal = Decimal("7")

    model_config = ConfigDict(frozen=True)


DEFAULT_STATUS_THRESHOLDS = StatusThresholds()


def compute_status(
    bucket: MasterBucket,
    variance_percentage_points: Decimal | None,
    thresholds: StatusThresholds = DEFAULT_STATUS_THRESHOLDS,
) -> DriftStatus:
    """Resolve a DriftStatus from a signed variance (actual% - target%).

    Needs/Wants are consumption buckets — overspend (positive variance) is
    adverse. Savings/Investments are accumulation buckets — shortfall
    (negative variance) is adverse. Overshooting a savings/investment target,
    or underspending Needs/Wants, is never penalized.
    """
    if variance_percentage_points is None:
        return DriftStatus.UNKNOWN
    adverse = (
        variance_percentage_points
        if bucket in _CONSUMPTION_BUCKETS
        else -variance_percentage_points
    )
    if adverse <= thresholds.watch_pp:
        return DriftStatus.ON_TRACK
    if adverse <= thresholds.off_track_pp:
        return DriftStatus.WATCH
    return DriftStatus.OFF_TRACK


# ── Input: a single classified transaction ──────────────────────────────────

class ClassifiedTxn(BaseModel):
    """Everything the engine needs about one already-classified transaction.
    Duck-typed from TransactionModel + its account by the service layer, so
    this module stays DB-free and independently testable."""

    transaction_id: str
    account_id: str
    account_type: str | None = None
    transaction_date: date
    amount: Decimal = Decimal("0")
    master_bucket: MasterBucket = MasterBucket.UNCLASSIFIED
    category: str | None = None
    cash_flow_type: CashFlowType = CashFlowType.OTHER
    needs_review: bool = False
    merchant_name: str | None = None
    description: str = ""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("amount", mode="before")
    @classmethod
    def _to_decimal(cls, v: object) -> Decimal:
        if isinstance(v, Decimal):
            return v
        if v is None:
            return Decimal("0")
        return Decimal(str(v))

    @field_validator("master_bucket", mode="before")
    @classmethod
    def _bucket_or_unclassified(cls, v: object) -> MasterBucket:
        # Tolerate a NULL/never-classified transaction (accounting-invariants
        # #10 — treat honestly as unclassified rather than raising).
        if v is None or v == "":
            return MasterBucket.UNCLASSIFIED
        return MasterBucket(v) if not isinstance(v, MasterBucket) else v

    @field_validator("cash_flow_type", mode="before")
    @classmethod
    def _flow_or_other(cls, v: object) -> CashFlowType:
        if v is None or v == "":
            return CashFlowType.OTHER
        return CashFlowType(v) if not isinstance(v, CashFlowType) else v

    def driver_key(self) -> str:
        """Merchant-drivers grouping key — merchant_name if present, else a
        trimmed description. Never fabricated; falls back to a literal
        placeholder rather than silently merging distinct unnamed rows."""
        return (self.merchant_name or self.description or "Unknown").strip() or "Unknown"


# ── Cross-statement double-counting rule ────────────────────────────────────
#
# Coverage-aware hybrid (Option C, docs/coral-redesign/BLOCKED.md — resolved
# 2026-08-13). A checking -> savings or checking -> brokerage transfer is
# visible TWICE whenever both statements are ingested — once as an outflow on
# the checking/credit account (the "origin" leg), once as an inflow on the
# savings/investment account (the "destination" leg). PR 03's classifier
# cannot see across statements, so both legs are independently classified as
# SAVINGS_CONTRIBUTION / INVESTMENT_CONTRIBUTION and the engine must pick
# exactly one to avoid double counting.
#
# Destination-leg-only (the original PR 04 rule) is correct and
# non-double-counting, but produces a structural $0.00 Savings actual for any
# account coverage gap -- including Coral's real coverage today, where the
# Marcus HYSA and 529 are catalog-only stubs with no parser
# (parseable=False), so no account_type == "savings" row can ever exist.
#
# The rule implemented here: for EACH bucket (Savings, Investments)
# independently, ask "does the period have ingested transaction coverage on
# that bucket's destination account type?" -- i.e. does ANY transaction this
# period live on an account whose account_type is in SAVINGS_ACCOUNT_TYPES /
# INVESTMENT_ACCOUNT_TYPES, regardless of that transaction's own
# classification. If yes, the destination leg is canonical (exactly the
# original rule) and the origin leg is excluded as a duplicate. If NO such
# account has any transaction this period, the origin leg counts instead --
# there is no destination statement to have double-counted against, so
# dropping the origin leg would silently understate the user's real
# contribution (see the BLOCKED.md worked example: a $1,500
# "TRANSFER TO MARCUS SAVINGS" with no Marcus statement ingested).
#
# This still transparently and correctly captures payroll-deducted 401(k)/
# ESPP contributions, which have NO checking-side leg at all: they only ever
# appear on the destination (401k/brokerage) account, which by definition
# means that bucket has coverage, so the (only) leg present is counted.
#
# Known, accepted limitation ("mixed-bucket" case): coverage is a per-bucket
# proxy, not per-institution/per-transaction pairing. If E*TRADE is ingested
# but Morgan Stanley is not, investment_coverage is True (E*TRADE has
# transactions this period) -- so a Morgan Stanley-directed checking-side
# origin leg is still treated as covered and excluded, even though the
# specific Morgan Stanley statement was never ingested. This is the
# documented tradeoff of Option C, not a bug: it is exactly as correct as
# destination-leg-only once every real destination account is parseable, and
# strictly better than destination-leg-only for every currently-ingested
# single-institution-per-bucket household.

def compute_transfer_leg_coverage(transactions: list[ClassifiedTxn]) -> tuple[bool, bool]:
    """Per-period, per-bucket coverage used to resolve which leg of a
    checking -> savings / checking -> brokerage transfer counts.

    Returns `(savings_has_coverage, investment_has_coverage)`: True when ANY
    transaction this period lives on an account whose `account_type` is in
    `SAVINGS_ACCOUNT_TYPES` / `INVESTMENT_ACCOUNT_TYPES` -- independent of
    that transaction's own classification, so e.g. a $0 monthly-fee line
    inside the Marcus account is still evidence the Marcus statement was
    ingested for this period.
    """
    savings_has_coverage = False
    investment_has_coverage = False
    for txn in transactions:
        account_type = (txn.account_type or "").strip().lower()
        if not savings_has_coverage and account_type in SAVINGS_ACCOUNT_TYPES:
            savings_has_coverage = True
        if not investment_has_coverage and account_type in INVESTMENT_ACCOUNT_TYPES:
            investment_has_coverage = True
        if savings_has_coverage and investment_has_coverage:
            break
    return savings_has_coverage, investment_has_coverage


def is_canonical_contribution_leg(
    txn: ClassifiedTxn, *, savings_coverage: bool, investment_coverage: bool,
) -> bool:
    """Decide whether this transaction is the ONE leg of a savings/investment
    contribution that counts toward Plan vs Actual totals -- see the
    coverage-aware hybrid rule documented above.

    `savings_coverage` / `investment_coverage` come from
    `compute_transfer_leg_coverage()` over the FULL period transaction list
    (not just this one account/transaction) -- callers must compute them once
    per period and pass the same values for every transaction, so the
    decision is consistent across the whole bucket total.
    """
    if txn.cash_flow_type not in (
        CashFlowType.SAVINGS_CONTRIBUTION,
        CashFlowType.INVESTMENT_CONTRIBUTION,
    ):
        return False
    account_type = (txn.account_type or "").strip().lower()
    if txn.cash_flow_type == CashFlowType.SAVINGS_CONTRIBUTION:
        on_destination_account = account_type in SAVINGS_ACCOUNT_TYPES
        if savings_coverage:
            return on_destination_account
        return not on_destination_account
    on_destination_account = account_type in INVESTMENT_ACCOUNT_TYPES
    if investment_coverage:
        return on_destination_account
    return not on_destination_account


def is_origin_only_contribution_leg(
    txn: ClassifiedTxn, *, savings_coverage: bool, investment_coverage: bool,
) -> bool:
    """The inverse of `is_canonical_contribution_leg` restricted to
    contribution-shaped transactions -- the excluded origin leg. Used purely
    for completeness reporting (never included in a total).

    Under the coverage-aware rule this is only ever True when the relevant
    destination side DOES have coverage this period -- that is precisely why
    the origin leg was excluded (the destination leg is counted instead).
    When there is no destination coverage, the origin leg IS the canonical
    leg (counted, not excluded), so it never appears here -- see
    CompletenessMetadata.is_complete for why that distinction matters."""
    if txn.cash_flow_type not in (
        CashFlowType.SAVINGS_CONTRIBUTION,
        CashFlowType.INVESTMENT_CONTRIBUTION,
    ):
        return False
    return not is_canonical_contribution_leg(
        txn, savings_coverage=savings_coverage, investment_coverage=investment_coverage,
    )


# ── Plannable Income ─────────────────────────────────────────────────────────

def compute_plannable_income(transactions: list[ClassifiedTxn]) -> Decimal:
    """Plannable Income = sum of every transaction classified as
    `CashFlowType.INCOME` (payroll/direct-deposit — see
    app.domain.transaction_classification tier 3h) within the period, across
    every account.

    This is the sole denominator the engine uses for every target-$/actual-%
    calculation. It intentionally reflects only *observed* cash landing in
    the user's accounts. Coral has no visibility into gross payroll or
    pre-tax payroll deductions (401(k)/ESPP amounts withheld before net pay
    reaches checking) — see `payroll_deduction_signal()` below for how that
    specific, real limitation is surfaced as completeness metadata rather
    than invented or hidden (accounting-invariants.md #10).
    """
    total = sum(
        (t.amount for t in transactions if t.cash_flow_type == CashFlowType.INCOME),
        Decimal("0"),
    )
    return _round_money(total)


def payroll_deduction_signal(transactions: list[ClassifiedTxn]) -> bool:
    """True when the period contains a canonical 401(k)/ESPP contribution
    leg that lives directly on an investment/retirement account.

    Such a transaction is real and correctly counted once (see
    `is_canonical_contribution_leg`), but it is money that was withheld from
    payroll *before* it ever reached checking — so it is NOT reflected in
    `compute_plannable_income()`. Its presence is a concrete, testable signal
    that Plannable Income (and therefore every actual-% figure derived from
    it) may understate the household's true income and investing rate.
    """
    savings_coverage, investment_coverage = compute_transfer_leg_coverage(transactions)
    payroll_categories = {"401(k)", "ESPP"}
    return any(
        t.cash_flow_type == CashFlowType.INVESTMENT_CONTRIBUTION
        and t.category in payroll_categories
        and is_canonical_contribution_leg(
            t, savings_coverage=savings_coverage, investment_coverage=investment_coverage,
        )
        for t in transactions
    )


# ── Bucket / category / merchant aggregation ────────────────────────────────

def _counts_toward_bucket(
    txn: ClassifiedTxn, *, savings_coverage: bool, investment_coverage: bool,
) -> bool:
    """True when this transaction should be included in ANY bucket total —
    the single gate that keeps Needs/Wants spend-netting and
    Savings/Investments contribution-dedup consistent everywhere in this
    module."""
    if txn.master_bucket in _CONSUMPTION_BUCKETS:
        return txn.cash_flow_type in (CashFlowType.EXPENSE, CashFlowType.REFUND)
    if txn.master_bucket in _ACCUMULATION_BUCKETS:
        return is_canonical_contribution_leg(
            txn, savings_coverage=savings_coverage, investment_coverage=investment_coverage,
        )
    return False


def _signed_bucket_amount(txn: ClassifiedTxn) -> Decimal:
    """Amount contribution of one transaction toward its bucket's actual $.

    Needs/Wants: expenses are stored as negative amounts, refunds as
    positive — net effect is `-amount` so a $50 charge contributes +$50 of
    spend and a $10 refund contributes -$10 (invariant #6: refunds reduce
    spending).
    Savings/Investments: a canonical contribution leg is always a genuine
    inflow toward savings/investments, but WHICH side of the ledger records
    it differs under the coverage-aware hybrid rule — positive on a
    destination account (per
    transaction_classification._is_contribution_direction), negative (an
    outflow) when this is the origin-leg fallback for an uncovered bucket
    (see `is_canonical_contribution_leg`). `abs()` normalizes both to the
    real dollar amount that moved; only canonical legs ever reach this
    function (see `_counts_toward_bucket`), so the sign is always resolvable
    this way without re-deriving direction here.
    """
    if txn.master_bucket in _CONSUMPTION_BUCKETS:
        return -txn.amount
    return abs(txn.amount)


def aggregate_bucket_actuals(
    transactions: list[ClassifiedTxn],
) -> dict[MasterBucket, tuple[Decimal, int]]:
    """Actual $ (net, per the rules in `_signed_bucket_amount`) and
    transaction count per master bucket."""
    savings_coverage, investment_coverage = compute_transfer_leg_coverage(transactions)
    all_buckets = _CONSUMPTION_BUCKETS | _ACCUMULATION_BUCKETS
    totals: dict[MasterBucket, Decimal] = {b: Decimal("0") for b in all_buckets}
    counts: dict[MasterBucket, int] = {b: 0 for b in totals}
    for txn in transactions:
        if not _counts_toward_bucket(
            txn, savings_coverage=savings_coverage, investment_coverage=investment_coverage,
        ):
            continue
        totals[txn.master_bucket] += _signed_bucket_amount(txn)
        counts[txn.master_bucket] += 1
    return {b: (_round_money(totals[b]), counts[b]) for b in totals}


def aggregate_category_actuals(
    transactions: list[ClassifiedTxn], bucket: MasterBucket,
) -> dict[str, tuple[Decimal, int]]:
    """Actual $ + count per category within one bucket. NULL/unresolved
    category is grouped under the explicit `UNCATEGORIZED` sentinel — never
    silently dropped (accounting-invariants.md #10)."""
    savings_coverage, investment_coverage = compute_transfer_leg_coverage(transactions)
    totals: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    for txn in transactions:
        if txn.master_bucket != bucket or not _counts_toward_bucket(
            txn, savings_coverage=savings_coverage, investment_coverage=investment_coverage,
        ):
            continue
        key = txn.category or UNCATEGORIZED
        totals[key] = totals.get(key, Decimal("0")) + _signed_bucket_amount(txn)
        counts[key] = counts.get(key, 0) + 1
    return {k: (_round_money(v), counts[k]) for k, v in totals.items()}


class MerchantDriver(BaseModel):
    merchant: str
    bucket: MasterBucket | None = None
    category: str | None = None
    amount: str
    transaction_count: int


def compute_merchant_drivers(
    transactions: list[ClassifiedTxn],
    *,
    bucket: MasterBucket | None = None,
    category: str | None = None,
    top_n: int = 10,
) -> list[MerchantDriver]:
    """Top merchants/descriptions by absolute net $ within an optional
    bucket/category filter. Only transactions that count toward a bucket
    total are considered — a card payment or an origin-only transfer leg
    never appears here."""
    savings_coverage, investment_coverage = compute_transfer_leg_coverage(transactions)
    totals: dict[tuple[str, MasterBucket, str | None], Decimal] = {}
    counts: dict[tuple[str, MasterBucket, str | None], int] = {}
    for txn in transactions:
        if not _counts_toward_bucket(
            txn, savings_coverage=savings_coverage, investment_coverage=investment_coverage,
        ):
            continue
        if bucket is not None and txn.master_bucket != bucket:
            continue
        if category is not None and (txn.category or UNCATEGORIZED) != category:
            continue
        key = (txn.driver_key(), txn.master_bucket, txn.category)
        totals[key] = totals.get(key, Decimal("0")) + _signed_bucket_amount(txn)
        counts[key] = counts.get(key, 0) + 1

    rows = [
        MerchantDriver(
            merchant=k[0], bucket=k[1], category=k[2],
            amount=str(_round_money(v)), transaction_count=counts[k],
        )
        for k, v in totals.items()
    ]
    rows.sort(key=lambda r: abs(Decimal(r.amount)), reverse=True)
    return rows[:top_n]


# ── Completeness metadata ───────────────────────────────────────────────────

class CompletenessMetadata(BaseModel):
    """Explicit statement of what this result does and does not fully
    represent. Never fabricate a number to make this look complete
    (accounting-invariants.md #10) — surface the gap instead."""

    plan_available: bool = True
    plan_version_changed_mid_period: bool = False
    income_observed: bool = True
    unclassified_transaction_count: int = 0
    unclassified_amount: str = "0.00"
    needs_review_count: int = 0
    origin_only_transfer_legs_count: int = 0
    origin_only_transfer_legs_amount: str = "0.00"
    payroll_deduction_signal_detected: bool = False
    notes: list[str] = Field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        # NOTE (docs/coral-redesign/BLOCKED.md, point 4 / Option C): under the
        # coverage-aware hybrid, `origin_only_transfer_legs_count` is ONLY
        # ever nonzero when the relevant destination side DOES have coverage
        # this period — that is precisely why the origin leg was excluded
        # (the destination leg is counted instead; see
        # `is_origin_only_contribution_leg`). So a nonzero count here is, by
        # construction, the healthy "both legs ingested, dedup worked" case —
        # not a data gap — and must NOT flip `is_complete` to False. The
        # previous version of this property treated ANY exclusion as
        # incomplete, which meant `is_complete` was permanently False even
        # when nothing was actually missing. When there truly is no
        # destination coverage, the origin leg is counted (not excluded), so
        # there is nothing left to flag here for that case either — the
        # remaining, accepted gap is the mixed-bucket case (coverage is a
        # per-bucket, not per-institution, proxy — see the module-level
        # docstring above `compute_transfer_leg_coverage`), which this field
        # cannot detect at the per-transaction level under Option C.
        return (
            self.plan_available
            and not self.plan_version_changed_mid_period
            and self.income_observed
            and self.unclassified_transaction_count == 0
            and not self.payroll_deduction_signal_detected
        )


def build_completeness_metadata(
    transactions: list[ClassifiedTxn],
    *,
    plannable_income: Decimal,
    plan_available: bool,
    plan_version_changed_mid_period: bool = False,
) -> CompletenessMetadata:
    # needs_review = PR 03 flagged this row for human attention (ambiguous
    # merchant, low-confidence LLM guess, or no deterministic/heuristic match
    # at all) — tracked globally, whether or not it still landed in a bucket.
    needs_review_txns = [t for t in transactions if t.needs_review]
    needs_review_count = len(needs_review_txns)

    # "Unclassified" (dollars completely invisible from every bucket total)
    # is the strict subset that is BOTH flagged for review AND has no bucket
    # at all. Deliberately NOT the same as master_bucket == UNCLASSIFIED on
    # its own: income, generic transfers, card payments, and account fees are
    # also bucket-less by design (confident, intentional classifications),
    # not gaps in coverage.
    unclassified = [t for t in needs_review_txns if t.master_bucket == MasterBucket.UNCLASSIFIED]
    unclassified_amount = _round_money(sum((abs(t.amount) for t in unclassified), Decimal("0")))

    savings_coverage, investment_coverage = compute_transfer_leg_coverage(transactions)
    origin_only = [
        t for t in transactions
        if is_origin_only_contribution_leg(
            t, savings_coverage=savings_coverage, investment_coverage=investment_coverage,
        )
    ]
    origin_only_amount = _round_money(sum((abs(t.amount) for t in origin_only), Decimal("0")))

    payroll_signal = payroll_deduction_signal(transactions)

    notes: list[str] = []
    if not plan_available:
        notes.append("No financial plan is in effect for this period; targets cannot be computed.")
    if plan_version_changed_mid_period:
        notes.append(
            "The financial plan changed during this period; targets use the plan "
            "effective at the start of the period."
        )
    if plannable_income <= 0:
        notes.append(
            "No income was observed this period; target $ and actual % cannot be computed."
        )
    if unclassified:
        notes.append(
            f"{len(unclassified)} transaction(s) totalling ${unclassified_amount} could not be "
            "classified into a bucket and are excluded from all totals."
        )
    if origin_only:
        # NOTE: deliberately does NOT claim a matching destination transaction
        # was or was not found via cross-statement pairing — this engine never
        # attempts that (see is_canonical_contribution_leg). Under the
        # coverage-aware hybrid, an origin leg only ever lands here when a
        # savings/investment-typed account DOES have ingested coverage this
        # period, which is exactly why the destination leg is preferred — so
        # this is the healthy, expected dedup case, not a data gap.
        notes.append(
            f"{len(origin_only)} transfer(s) totalling ${origin_only_amount} are the "
            "checking/credit side of a savings or investment transfer. Because a "
            "savings/investment account with transaction coverage this period was "
            "found, the destination-account leg is counted instead and these origin "
            "legs are excluded to avoid double counting."
        )
    if payroll_signal:
        notes.append(
            "Payroll-deducted contributions (401(k)/ESPP) were detected on an investment "
            "account. These are withheld before pay reaches checking, so they are not "
            "included in Plannable Income — actual investing % may be understated relative "
            "to true gross income."
        )

    return CompletenessMetadata(
        plan_available=plan_available,
        plan_version_changed_mid_period=plan_version_changed_mid_period,
        income_observed=plannable_income > 0,
        unclassified_transaction_count=len(unclassified),
        unclassified_amount=str(unclassified_amount),
        needs_review_count=needs_review_count,
        origin_only_transfer_legs_count=len(origin_only),
        origin_only_transfer_legs_amount=str(origin_only_amount),
        payroll_deduction_signal_detected=payroll_signal,
        notes=notes,
    )


# ── Result shapes ────────────────────────────────────────────────────────────

class BucketDrift(BaseModel):
    bucket: MasterBucket
    target_percentage: str | None
    actual_percentage: str | None
    target_amount: str | None
    actual_amount: str
    variance_amount: str | None
    variance_percentage_points: str | None
    status: DriftStatus
    transaction_count: int


class CategoryDrift(BaseModel):
    bucket: MasterBucket
    category: str
    target_percentage: str | None
    actual_percentage: str | None
    target_amount: str | None
    actual_amount: str
    variance_amount: str | None
    variance_percentage_points: str | None
    status: DriftStatus
    transaction_count: int


class PlanVsActualResult(BaseModel):
    period: Period
    plan_version_id: str | None
    plan_version_number: int | None
    plan_effective_from: date | None
    plannable_income: str
    buckets: list[BucketDrift]
    completeness: CompletenessMetadata


# ── Target resolution helpers ────────────────────────────────────────────────

def _bucket_target_percentage(
    plan: PlanVersionSnapshot | None, bucket: MasterBucket,
) -> Decimal | None:
    if plan is None:
        return None
    for alloc in plan.allocations:
        if alloc.bucket_name.strip().lower() == bucket.value:
            return Decimal(alloc.percentage)
    return None


def _category_target_percentage(
    plan: PlanVersionSnapshot | None, bucket: MasterBucket, category: str,
) -> Decimal | None:
    if plan is None or category == UNCATEGORIZED:
        return None
    # Case/whitespace-insensitive so a user-authored plan whose suballocation
    # is stored as "emergency fund" still matches the "Emergency Fund"
    # category produced by app.domain.transaction_classification.
    wanted = category.strip().lower()
    for alloc in plan.allocations:
        if alloc.bucket_name.strip().lower() != bucket.value:
            continue
        for sub in alloc.suballocations:
            if sub.name.strip().lower() == wanted:
                return Decimal(sub.percentage)
    return None


def _drift(
    bucket: MasterBucket,
    target_percentage: Decimal | None,
    actual_amount: Decimal,
    plannable_income: Decimal,
    thresholds: StatusThresholds,
) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None, DriftStatus]:
    """Shared target/variance/status math for a bucket or a category row.
    Returns (target_amount, actual_percentage, variance_amount,
    variance_percentage_points, status).

    When no income was observed (`plannable_income <= 0`) the target $ is
    honestly undefined rather than $0.00: a $0 target would render as
    "Target $0 / Actual $500 / +$500 over plan", which is fabricated precision
    for what is almost always missing payroll coverage rather than a genuinely
    income-free month (accounting-invariants.md #10). `actual_amount` is still
    reported in full — only the derived target/variance are withheld.
    """
    target_amount = (
        _round_money(plannable_income * target_percentage / _HUNDRED)
        if target_percentage is not None and plannable_income > 0
        else None
    )
    actual_percentage = (
        _round_pct(actual_amount / plannable_income * _HUNDRED)
        if plannable_income > 0
        else None
    )
    variance_amount = (
        _round_money(actual_amount - target_amount) if target_amount is not None else None
    )
    variance_pp = (
        _round_pct(actual_percentage - target_percentage)
        if actual_percentage is not None and target_percentage is not None
        else None
    )
    status = compute_status(bucket, variance_pp, thresholds)
    return target_amount, actual_percentage, variance_amount, variance_pp, status


# ── Top-level entry points ──────────────────────────────────────────────────

def compute_plan_vs_actual(
    period: Period,
    transactions: list[ClassifiedTxn],
    plan: PlanVersionSnapshot | None,
    *,
    thresholds: StatusThresholds = DEFAULT_STATUS_THRESHOLDS,
    plan_version_changed_mid_period: bool = False,
) -> PlanVsActualResult:
    """Compute the full Needs/Wants/Savings/Investments Plan vs Actual result
    for one period. Pure — no DB access."""
    plannable_income = compute_plannable_income(transactions)
    bucket_actuals = aggregate_bucket_actuals(transactions)

    all_buckets = (
        MasterBucket.NEEDS, MasterBucket.WANTS, MasterBucket.SAVINGS, MasterBucket.INVESTMENTS,
    )
    buckets: list[BucketDrift] = []
    for bucket in all_buckets:
        actual_amount, txn_count = bucket_actuals[bucket]
        target_pct = _bucket_target_percentage(plan, bucket)
        target_amount, actual_pct, variance_amount, variance_pp, status = _drift(
            bucket, target_pct, actual_amount, plannable_income, thresholds,
        )
        buckets.append(BucketDrift(
            bucket=bucket,
            target_percentage=str(target_pct) if target_pct is not None else None,
            actual_percentage=str(actual_pct) if actual_pct is not None else None,
            target_amount=str(target_amount) if target_amount is not None else None,
            actual_amount=str(actual_amount),
            variance_amount=str(variance_amount) if variance_amount is not None else None,
            variance_percentage_points=str(variance_pp) if variance_pp is not None else None,
            status=status,
            transaction_count=txn_count,
        ))

    completeness = build_completeness_metadata(
        transactions,
        plannable_income=plannable_income,
        plan_available=plan is not None,
        plan_version_changed_mid_period=plan_version_changed_mid_period,
    )

    return PlanVsActualResult(
        period=period,
        plan_version_id=plan.id if plan else None,
        plan_version_number=plan.version_number if plan else None,
        plan_effective_from=plan.effective_from if plan else None,
        plannable_income=str(plannable_income),
        buckets=buckets,
        completeness=completeness,
    )


def compute_category_breakdown(
    transactions: list[ClassifiedTxn],
    bucket: MasterBucket,
    plan: PlanVersionSnapshot | None,
    *,
    thresholds: StatusThresholds = DEFAULT_STATUS_THRESHOLDS,
) -> list[CategoryDrift]:
    """Recursive drill-down: category-level rows within one master bucket,
    each with its own target (when the plan defines a suballocation target
    for that category — Savings/Investments only) / actual / variance /
    status, sorted by absolute actual $ descending."""
    plannable_income = compute_plannable_income(transactions)
    category_actuals = aggregate_category_actuals(transactions, bucket)

    rows: list[CategoryDrift] = []
    for category, (actual_amount, txn_count) in category_actuals.items():
        target_pct = _category_target_percentage(plan, bucket, category)
        target_amount, actual_pct, variance_amount, variance_pp, status = _drift(
            bucket, target_pct, actual_amount, plannable_income, thresholds,
        )
        rows.append(CategoryDrift(
            bucket=bucket,
            category=category,
            target_percentage=str(target_pct) if target_pct is not None else None,
            actual_percentage=str(actual_pct) if actual_pct is not None else None,
            target_amount=str(target_amount) if target_amount is not None else None,
            actual_amount=str(actual_amount),
            variance_amount=str(variance_amount) if variance_amount is not None else None,
            variance_percentage_points=str(variance_pp) if variance_pp is not None else None,
            status=status,
            transaction_count=txn_count,
        ))
    rows.sort(key=lambda r: abs(Decimal(r.actual_amount)), reverse=True)
    return rows
