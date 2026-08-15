"""
Savings Goal service — wires the pure domain engine in
app.domain.savings_goals to the database (PR 13).

Responsibilities:
  - validate + persist goals (app.db.models.SavingsGoalModel)
  - seed the three default goals (Emergency Fund / House / Goals / Child
    Savings) matching the plan's seeded Savings suballocations, mirroring
    app.services.financial_plan.seed_default_plan_if_missing()
  - compute a goal's progress: reuse
    app.services.plan_vs_actual._load_classified_transactions (the same
    primitive investment_plan.py already reuses) + the pure
    domain.plan_vs_actual.compute_transaction_drivers filter to sum a goal's
    mapped savings_contribution transactions since its effective_date —
    never a parallel transaction-aggregation path
  - resolve each goal's account_mappings against
    app.config.statement_catalog to build honest completeness metadata

No FastAPI imports here — usable from any caller, exactly like
app.services.financial_plan and app.services.plan_vs_actual.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.statement_catalog import CATALOG_BY_SLUGS
from app.core.logger import get_logger
from app.db import repositories as repo
from app.db.models import SavingsGoalModel
from app.domain.errors import SavingsGoalValidationError
from app.domain.plan_vs_actual import (
    UNCATEGORIZED,
    ClassifiedTxn,
    Period,
    TransactionDrift,
    compute_plannable_income,
    compute_transaction_drivers,
)
from app.domain.savings_goals import (
    GoalAccountMapping,
    GoalType,
    SavingsGoalProgress,
    assess_goal_completeness,
    build_completion_recommendation,
    compute_goal_status,
    resolve_category_name,
    resolve_effective_target_amount,
    validate_goal_input,
)
from app.domain.transaction_classification import MasterBucket
from app.services import plan_vs_actual as plan_vs_actual_service

logger = get_logger(__name__)

# Far enough in the past that the seeded default goals' cumulative window
# covers all existing historical transaction data — mirrors
# app.services.financial_plan.PLAN_EPOCH exactly (same rationale: the
# default plan is effective from this same date, so a goal's "since
# effective_date" window naturally aligns with "since the plan began").
#
# Known and accepted consequence (reviewed, deliberately not "fixed"): a
# seeded goal's effective_date will always predate Coral's earliest ingested
# transaction, so `data_completeness.effective_date_predates_observed_history`
# is True — i.e. a seeded goal never reports `is_complete`. That is the honest
# answer: Coral genuinely cannot see how much was saved before the first
# ingested statement, and it must not imply otherwise
# (accounting-invariants.md #10). Seeding "today" instead would silently drop
# every already-ingested historical contribution from current_amount — a real
# financial-number regression traded for a cosmetically cleaner flag. Users
# who want a bounded, complete window set an explicit effective_date on
# their own goal.
GOAL_EPOCH = date(2000, 1, 1)


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Account mapping (de)serialization ───────────────────────────────────────

def _mappings_to_json(mappings: list[GoalAccountMapping]) -> str:
    return json.dumps([m.model_dump() for m in mappings])


def _mappings_from_json(raw: str | None) -> list[GoalAccountMapping]:
    if not raw:
        return []
    return [GoalAccountMapping(**m) for m in json.loads(raw)]


def _partition_mappings(
    mappings: list[GoalAccountMapping],
) -> tuple[list[GoalAccountMapping], list[GoalAccountMapping]]:
    """Split mappings into (unparseable, unknown) against the statement
    catalog — a mapping missing from the catalog entirely is `unknown`
    (honest: Coral cannot even verify the account exists), distinct from a
    catalog entry that exists but has `parseable=False`."""
    unparseable: list[GoalAccountMapping] = []
    unknown: list[GoalAccountMapping] = []
    for m in mappings:
        entry = CATALOG_BY_SLUGS.get((m.institution_slug, m.account_slug))
        if entry is None:
            unknown.append(m)
        elif not entry.parseable:
            unparseable.append(m)
    return unparseable, unknown


# ── Default goals ────────────────────────────────────────────────────────────
#
# Mirrors financial_plan.py's _DEFAULT_ALLOCATIONS: seeds the same three
# Savings suballocation names at the same 5%/5%/5% target_percentage_of_income
# (deliberately NOT a fabricated dollar target — the plan only defines
# percentages, so a $ target would be invented; see accounting-invariants
# #10 and design-rules "must not become permanent hard-coded presentation
# constants where a stored plan exists").
#
# Account mappings below are explicit, human-authored associations to
# distinguishable catalog accounts (never inferred from account-name
# matching at read time) — Emergency Fund -> the Marcus account literally
# named "Emergency Fund"; Child Savings -> the 529 college-savings account;
# House / Goals -> the Morgan Stanley "house_downpayment" account (reviewed:
# `AccountCatalogEntry.bucket` is the statement-folder/nav grouping, NOT a
# financial classification — credit cards live under "investments" too — so
# an account labelled "House Downpayment" is the right target for the House /
# Goals savings goal regardless of its bucket). If any of these ever prove
# wrong for a given household, they are just the seeded starting point —
# nothing here prevents editing account_mappings later.

_DEFAULT_GOALS: list[dict] = [
    {
        "name": "Emergency Fund",
        "goal_type": GoalType.EMERGENCY_FUND,
        "target_percentage_of_income": Decimal("5"),
        "account_mappings": [
            GoalAccountMapping(institution_slug="marcus", account_slug="emergency_fund"),
        ],
        "priority": 0,
    },
    {
        "name": "House / Goals",
        "goal_type": GoalType.HOUSE_GOALS,
        "target_percentage_of_income": Decimal("5"),
        "account_mappings": [
            GoalAccountMapping(institution_slug="morgan_stanley", account_slug="house_downpayment"),
        ],
        "priority": 1,
    },
    {
        "name": "Child Savings",
        "goal_type": GoalType.CHILD_SAVINGS,
        "target_percentage_of_income": Decimal("5"),
        "account_mappings": [
            GoalAccountMapping(institution_slug="529", account_slug="college_savings"),
        ],
        "priority": 2,
    },
]


async def seed_default_goals_if_missing() -> None:
    """Insert the three default goals only if no savings goal exists yet.
    Safe to call on every boot (mirrors seed_default_plan_if_missing)."""
    from app.db.engine import get_session

    async with get_session() as session:
        existing = await repo.list_savings_goals(session)
        if existing:
            return
        for spec in _DEFAULT_GOALS:
            await create_goal(
                session,
                name=spec["name"],
                goal_type=spec["goal_type"],
                target_percentage_of_income=spec["target_percentage_of_income"],
                account_mappings=spec["account_mappings"],
                priority=spec["priority"],
                effective_date=GOAL_EPOCH,
            )
        logger.info("savings_goals.seeded", extra={"count": len(_DEFAULT_GOALS)})


# ── Create ───────────────────────────────────────────────────────────────────

async def create_goal(
    session: AsyncSession,
    *,
    name: str,
    goal_type: GoalType,
    effective_date: date,
    category_name: str | None = None,
    target_amount: Decimal | None = None,
    target_percentage_of_income: Decimal | None = None,
    target_months_of_expenses: Decimal | None = None,
    account_mappings: list[GoalAccountMapping] | None = None,
    priority: int = 0,
) -> SavingsGoalModel:
    """Validate and persist a new savings goal."""
    mappings = account_mappings or []
    try:
        resolved_category = resolve_category_name(goal_type, category_name)
        validate_goal_input(
            goal_type=goal_type,
            target_amount=target_amount,
            target_percentage_of_income=target_percentage_of_income,
            target_months_of_expenses=target_months_of_expenses,
        )
    except ValueError as exc:
        raise SavingsGoalValidationError(str(exc)) from exc

    return await repo.create_savings_goal(
        session,
        name=name,
        goal_type=goal_type.value,
        category_name=resolved_category,
        target_amount=str(target_amount) if target_amount is not None else None,
        target_percentage_of_income=(
            str(target_percentage_of_income) if target_percentage_of_income is not None else None
        ),
        target_months_of_expenses=(
            str(target_months_of_expenses) if target_months_of_expenses is not None else None
        ),
        account_mappings_json=_mappings_to_json(mappings),
        priority=priority,
        effective_date=effective_date,
    )


# ── Progress computation ─────────────────────────────────────────────────────

def _monthly_savings_drivers(
    transactions: list[ClassifiedTxn], *, category: str,
) -> list[TransactionDrift]:
    """Savings contributions for one category, resolved ONE CALENDAR MONTH AT
    A TIME with the shared `compute_transaction_drivers` primitive.

    Why per month rather than one call over the whole cumulative window: the
    transfer-leg gate that primitive applies is coverage-aware
    (docs/coral-redesign/BLOCKED.md decision 1, Option C) and coverage is
    evaluated over whatever transaction list it is handed. Plan vs Actual
    always hands it a single month, so evaluating a multi-year goal window in
    one shot could resolve coverage differently and make a goal's cumulative
    total disagree with the sum of the monthly numbers shown on
    Overview/Banking. Concretely, once a savings-side parser lands mid-history
    the whole-window call would treat every earlier month as "covered" and
    silently drop its origin legs. Slicing by month makes the goal total
    exactly the sum of the per-month Plan vs Actual actuals, by construction.

    Purely in memory — the transactions are loaded once.
    """
    by_month: dict[tuple[int, int], list[ClassifiedTxn]] = {}
    for txn in transactions:
        by_month.setdefault(
            (txn.transaction_date.year, txn.transaction_date.month), [],
        ).append(txn)
    drivers: list[TransactionDrift] = []
    for key in sorted(by_month):
        drivers.extend(compute_transaction_drivers(
            by_month[key], bucket=MasterBucket.SAVINGS, category=category,
        ))
    return drivers


async def _compute_progress(
    session: AsyncSession,
    goal: SavingsGoalModel,
    *,
    as_of: date,
    window_cache: dict[tuple[date, date], list[ClassifiedTxn]] | None = None,
) -> SavingsGoalProgress:
    """`window_cache` lets `list_goal_progress` load each distinct
    [effective_date, as_of] window once instead of once per goal (the three
    seeded goals all share GOAL_EPOCH). Purely a read cache — the loaded rows
    are identical for every goal sharing a window."""
    mappings = _mappings_from_json(goal.account_mappings_json)
    unparseable, unknown = _partition_mappings(mappings)

    goal_type = GoalType(goal.goal_type)
    target_amount = Decimal(goal.target_amount) if goal.target_amount else None

    # Cumulative window: since the goal's effective_date, through `as_of`.
    # Reuses the exact same period-scoped transaction loader/classifier as
    # Plan vs Actual (PR 04) and Investment Contribution Model (PR 11) — no
    # parallel aggregation path.
    contribution_amount = Decimal("0")
    most_recent_contribution_date: date | None = None
    contribution_count = 0
    plannable_income = Decimal("0")
    unattributed_count = 0
    unattributed_amount = Decimal("0")
    if goal.effective_date <= as_of:
        window = (goal.effective_date, as_of)
        transactions = None if window_cache is None else window_cache.get(window)
        if transactions is None:
            transactions = await plan_vs_actual_service._load_classified_transactions(
                session, Period.for_range(goal.effective_date, as_of),
            )
            if window_cache is not None:
                window_cache[window] = transactions
        drivers = _monthly_savings_drivers(transactions, category=goal.category_name)
        contribution_count = len(drivers)
        if drivers:
            contribution_amount = sum((Decimal(d.amount) for d in drivers), Decimal("0"))
            most_recent_contribution_date = max(d.transaction_date for d in drivers)

        # Same window, same primitives: the income denominator for a
        # percentage-of-income target, and the savings contributions Coral
        # saw but could not attribute to any goal category.
        plannable_income = compute_plannable_income(transactions)
        unattributed = _monthly_savings_drivers(transactions, category=UNCATEGORIZED)
        unattributed_count = len(unattributed)
        unattributed_amount = sum((Decimal(d.amount) for d in unattributed), Decimal("0"))

    earliest_observed = await repo.get_earliest_transaction_date(session)

    target_percentage = (
        Decimal(goal.target_percentage_of_income)
        if goal.target_percentage_of_income else None
    )
    effective_target, target_source = resolve_effective_target_amount(
        target_amount=target_amount,
        target_percentage_of_income=target_percentage,
        plannable_income=plannable_income,
    )

    completeness = assess_goal_completeness(
        mappings,
        effective_date=goal.effective_date,
        earliest_observed_transaction_date=earliest_observed,
        contribution_transaction_count=contribution_count,
        unparseable_mappings=unparseable,
        unknown_mappings=unknown,
        unattributed_savings_contribution_count=unattributed_count,
        unattributed_savings_contribution_amount=unattributed_amount,
        percentage_target_income_observed=(
            None if target_percentage is None else plannable_income > 0
        ),
    )

    status = compute_goal_status(
        target_amount=target_amount,
        current_amount=contribution_amount,
        most_recent_contribution_date=most_recent_contribution_date,
        as_of=as_of,
        target_percentage_of_income=target_percentage,
        plannable_income=plannable_income,
    )

    recommendation = build_completion_recommendation(
        goal_id=goal.id, goal_name=goal.name, status=status,
        target_amount=target_amount, current_amount=contribution_amount,
    )

    return SavingsGoalProgress(
        id=goal.id,
        name=goal.name,
        goal_type=goal_type,
        category_name=goal.category_name,
        target_amount=goal.target_amount,
        target_percentage_of_income=goal.target_percentage_of_income,
        target_months_of_expenses=goal.target_months_of_expenses,
        account_mappings=mappings,
        priority=goal.priority,
        effective_date=goal.effective_date,
        current_amount=str(_round_money(contribution_amount)),
        current_amount_source="computed_from_contributions",
        as_of=as_of,
        plannable_income=str(_round_money(plannable_income)),
        target_amount_effective=(
            str(_round_money(effective_target)) if effective_target is not None else None
        ),
        target_amount_source=target_source,
        variance_amount=(
            str(_round_money(contribution_amount - effective_target))
            if effective_target is not None else None
        ),
        status=status,
        data_completeness=completeness,
        completion_recommendation=recommendation,
    )


async def get_goal_progress(
    session: AsyncSession, goal_id: str, *, as_of: date | None = None,
) -> SavingsGoalProgress:
    """Progress for one goal, resolved through `as_of` (defaults to today)."""
    goal = await repo.get_savings_goal(session, goal_id)
    return await _compute_progress(session, goal, as_of=as_of or date.today())


async def list_goal_progress(
    session: AsyncSession, *, as_of: date | None = None,
) -> list[SavingsGoalProgress]:
    """Every goal's progress, sorted by priority (ascending) then creation
    order — the same ordering repo.list_savings_goals already applies."""
    resolved_as_of = as_of or date.today()
    goals = await repo.list_savings_goals(session)
    window_cache: dict[tuple[date, date], list[ClassifiedTxn]] = {}
    return [
        await _compute_progress(
            session, g, as_of=resolved_as_of, window_cache=window_cache,
        )
        for g in goals
    ]
