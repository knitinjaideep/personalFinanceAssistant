"""
Savings Goal domain model — pure, deterministic, DB-free (PR 13).

A savings goal tracks progress toward a target (dollars and/or % of income),
scoped to one or more EXPLICITLY-mapped accounts (never inferred from account
name — see `GoalAccountMapping`). This module never touches the database and
never calls an LLM.

Design decision (docs/coral-redesign/pr-13-savings-goals.md, resolved by
research — see the PR13 work order): a goal's `current_amount` is
conceptually a cumulative balance ("how much have I saved toward this goal so
far"), but Coral has no bank-verified balance data for any savings account
today (Marcus HYSA + 529 are catalog-only stubs with no parser — see
app.config.statement_catalog.ACCOUNT_CATALOG). So `current_amount` here is
always a DERIVED, Coral-computed cumulative sum of the goal's mapped
`savings_contribution`-classified transactions since `effective_date` — never
a fabricated bank balance. This module labels that distinction explicitly
(`current_amount_source`) and every goal carries `GoalCompletenessMetadata`
so a consumer can tell the difference between "$0 saved" and "Coral cannot
see this account's data" (accounting-invariants.md #10).

app.services.savings_goals wires this pure engine to the database (loading
transactions, resolving the catalog, persistence).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── Goal type / category mapping ────────────────────────────────────────────
#
# Matches app.domain.transaction_classification.SAVINGS_CATEGORIES exactly —
# the same three names the classification engine already assigns to
# `classification_category` for keyword-matched Savings contributions, and
# the same three names financial_plan.py's `_DEFAULT_ALLOCATIONS` seeds as
# plan_suballocations under the Savings bucket (5%/5%/5%). Reusing these
# strings means a goal seeded here maps onto already-classified transactions
# with zero new classification work.

class GoalType(str, Enum):
    EMERGENCY_FUND = "emergency_fund"
    HOUSE_GOALS = "house_goals"
    CHILD_SAVINGS = "child_savings"
    CUSTOM = "custom"


GOAL_TYPE_TO_CATEGORY: dict[GoalType, str] = {
    GoalType.EMERGENCY_FUND: "Emergency Fund",
    GoalType.HOUSE_GOALS: "House / Goals",
    GoalType.CHILD_SAVINGS: "Child Savings",
}


class GoalStatus(str, Enum):
    NOT_STARTED = "not_started"
    BEHIND = "behind"
    ON_TRACK = "on_track"
    COMPLETE = "complete"


# ── Account mapping ──────────────────────────────────────────────────────────

class GoalAccountMapping(BaseModel):
    """Explicit reference to one app.config.statement_catalog account entry.

    A goal is deliberately never inferred purely from an account's name —
    every account this goal draws from must be listed here. One account may
    back multiple goals (append the same mapping to more than one goal); one
    goal may span multiple accounts (multiple entries on one goal).
    """

    institution_slug: str
    account_slug: str

    model_config = ConfigDict(frozen=True)


# ── Status thresholds ────────────────────────────────────────────────────────

class GoalStatusThresholds(BaseModel):
    """Centralized, configurable status thresholds — no scattered magic
    numbers (mirrors app.domain.plan_vs_actual.StatusThresholds).

    Coral has no deadline field for a savings goal (the work order's field
    list has no target_date), so "on pace" toward a pure $ target cannot be
    judged against a horizon. Two deterministic signals are used instead:

      1. Plan shortfall (preferred, and the only one anchored to the plan):
         when the goal carries a `target_percentage_of_income` AND Coral has
         observed income over the same window, the required $ is
         `income x pct / 100` — a goal below that is `behind`. This is the
         PLAN -> ACTUAL -> DRIFT anchor and uses only observed values.
      2. Stall fallback (used when no percentage target is measurable): a
         goal that has not reached its target is `behind` when no
         contribution toward it has been observed within
         `stall_lookback_days` (default 60 — about two monthly contribution
         cycles).

    Both are documented, deliberately simple defaults — never a fabricated
    deadline.
    """

    stall_lookback_days: int = 60

    model_config = ConfigDict(frozen=True)


DEFAULT_GOAL_STATUS_THRESHOLDS = GoalStatusThresholds()

_CENTS = Decimal("0.01")
_HUNDRED = Decimal("100")


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


# ── Input validation ─────────────────────────────────────────────────────────

def resolve_category_name(goal_type: GoalType, category_name: str | None) -> str:
    """Resolve the classification_category a goal accumulates from.

    The three built-in goal types always use the exact SAVINGS_CATEGORIES
    name (ignoring any caller-supplied override, so a goal's category can
    never silently drift from what the classification engine actually
    assigns). A custom goal must supply its own `category_name` explicitly.
    """
    if goal_type in GOAL_TYPE_TO_CATEGORY:
        return GOAL_TYPE_TO_CATEGORY[goal_type]
    if not category_name or not category_name.strip():
        raise ValueError("category_name is required for a custom goal_type.")
    return category_name.strip()


def validate_goal_input(
    *,
    goal_type: GoalType,
    target_amount: Decimal | None,
    target_percentage_of_income: Decimal | None,
    target_months_of_expenses: Decimal | None,
) -> None:
    """Pure validation, no DB access. Raises ValueError on failure — the
    service layer wraps this in SavingsGoalValidationError.

    Rules:
      - at least one of target_amount / target_percentage_of_income must be
        set (a goal with neither can never compute a meaningful status);
      - target_months_of_expenses is only meaningful for
        goal_type == EMERGENCY_FUND;
      - no negative targets.
    """
    if target_amount is None and target_percentage_of_income is None:
        raise ValueError(
            "A savings goal must define at least one of target_amount or "
            "target_percentage_of_income."
        )
    if target_amount is not None and target_amount < 0:
        raise ValueError("target_amount must not be negative.")
    if target_percentage_of_income is not None and target_percentage_of_income < 0:
        raise ValueError("target_percentage_of_income must not be negative.")
    if target_months_of_expenses is not None:
        if target_months_of_expenses < 0:
            raise ValueError("target_months_of_expenses must not be negative.")
        if goal_type != GoalType.EMERGENCY_FUND:
            raise ValueError(
                "target_months_of_expenses is only meaningful for "
                "goal_type == 'emergency_fund'."
            )


class TargetAmountSource(str, Enum):
    """Where a goal's effective $ target came from — always labeled, never
    presented as an unqualified user-authored number."""

    EXPLICIT = "explicit"
    DERIVED_FROM_PERCENTAGE_OF_OBSERVED_INCOME = "derived_from_percentage_of_observed_income"
    NONE = "none"


def derive_percentage_target_amount(
    target_percentage_of_income: Decimal | None, plannable_income: Decimal | None,
) -> Decimal | None:
    """The $ a `target_percentage_of_income` goal should have accumulated over
    the window `plannable_income` was observed across.

    Returns None (never 0, never a guess) when the percentage or the income
    denominator is missing/non-positive — Coral cannot see gross payroll, so
    an unobserved income window must degrade to "no measurable target"
    rather than to a fabricated $0 target (accounting-invariants.md #10).
    """
    if target_percentage_of_income is None or target_percentage_of_income <= 0:
        return None
    if plannable_income is None or plannable_income <= 0:
        return None
    return _round_money(plannable_income * target_percentage_of_income / _HUNDRED)


def resolve_effective_target_amount(
    *,
    target_amount: Decimal | None,
    target_percentage_of_income: Decimal | None,
    plannable_income: Decimal | None,
) -> tuple[Decimal | None, TargetAmountSource]:
    """The single $ target a goal is judged against, plus its provenance.

    An explicitly-authored `target_amount` always wins (user intent beats a
    derived number). Otherwise fall back to the plan-anchored
    percentage-of-observed-income target. Otherwise there is no measurable
    target at all — say so, do not invent one.
    """
    if target_amount is not None:
        return target_amount, TargetAmountSource.EXPLICIT
    derived = derive_percentage_target_amount(target_percentage_of_income, plannable_income)
    if derived is not None:
        return derived, TargetAmountSource.DERIVED_FROM_PERCENTAGE_OF_OBSERVED_INCOME
    return None, TargetAmountSource.NONE


def compute_goal_status(
    *,
    target_amount: Decimal | None,
    current_amount: Decimal,
    most_recent_contribution_date: date | None,
    as_of: date,
    target_percentage_of_income: Decimal | None = None,
    plannable_income: Decimal | None = None,
    thresholds: GoalStatusThresholds = DEFAULT_GOAL_STATUS_THRESHOLDS,
) -> GoalStatus:
    """Resolve a GoalStatus from observed progress.

    - `complete`: only ever returned when an EXPLICIT $ target exists AND has
      been reached or exceeded — never fabricated when target_amount is None
      (accounting-invariants.md #10). A goal defined only by
      target_percentage_of_income is an ongoing rate commitment, not a
      finish line, so it is never "completed" here even when its derived
      percentage target is exceeded.
    - `not_started`: no contribution has ever been observed
      (current_amount <= 0).
    - `behind`: either the goal is short of its measurable
      percentage-of-income target for this window (the plan-anchored
      signal), or — when no percentage target is measurable — no
      contribution has landed within `thresholds.stall_lookback_days` of
      `as_of`.
    - `on_track`: some progress exists, no measurable plan shortfall, and a
      contribution landed within the lookback window.
    """
    if target_amount is not None and target_amount > 0 and current_amount >= target_amount:
        return GoalStatus.COMPLETE
    if current_amount <= 0:
        return GoalStatus.NOT_STARTED

    # Plan-anchored shortfall: prefer a real, observed target over recency.
    # Without this, a goal receiving $1/month would report `on_track` against
    # a 5%-of-income plan target — the exact "looks fine while off plan"
    # failure the redesign's PLAN -> ACTUAL -> DRIFT principle exists to
    # prevent.
    percentage_target = derive_percentage_target_amount(
        target_percentage_of_income, plannable_income,
    )
    if percentage_target is not None and current_amount < percentage_target:
        return GoalStatus.BEHIND

    if most_recent_contribution_date is None:
        return GoalStatus.BEHIND
    days_since_last_contribution = (as_of - most_recent_contribution_date).days
    if days_since_last_contribution > thresholds.stall_lookback_days:
        return GoalStatus.BEHIND
    return GoalStatus.ON_TRACK


# ── Completeness metadata ───────────────────────────────────────────────────

class GoalCompletenessMetadata(BaseModel):
    """Explicit statement of what this goal's `current_amount` does and does
    not fully represent. Never fabricate a number to make this look complete
    (accounting-invariants.md #10) — surface the gap instead."""

    all_mapped_accounts_parseable: bool = True
    unparseable_account_mappings: list[GoalAccountMapping] = Field(default_factory=list)
    unknown_account_mappings: list[GoalAccountMapping] = Field(default_factory=list)
    earliest_observed_transaction_date: date | None = None
    # False when Coral has not ingested a single transaction yet — a $0
    # current_amount then means "no data", not "nothing saved".
    any_observed_transaction_history: bool = True
    effective_date_predates_observed_history: bool = False
    contribution_transaction_count: int = 0
    # Savings contributions Coral observed in this window but could not
    # attribute to ANY goal category (e.g. a generic "TRANSFER TO MARCUS
    # SAVINGS" line with no sub-goal keyword). This money is real and is
    # missing from every goal's current_amount — surface it, never silently
    # drop it (accounting-invariants.md #10).
    unattributed_savings_contribution_count: int = 0
    unattributed_savings_contribution_amount: str = "0.00"
    # None when the goal has no percentage target (not applicable); False
    # when it has one but no income was observed over the window, so the
    # plan-anchored target is unmeasurable and status falls back to the
    # stall rule.
    percentage_target_income_observed: bool | None = None
    notes: list[str] = Field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True only when `current_amount` is the whole observable picture.

        Deliberately narrow (cf. the PR04 fix recorded in
        docs/coral-redesign/BLOCKED.md decision 1, point 4): each condition
        below is a real reason current_amount may understate reality, not a
        cosmetic flag. `percentage_target_income_observed` is intentionally
        excluded — it affects `status`, not the completeness of the
        accumulated dollars — and is surfaced as its own field/note instead.
        """
        return (
            self.all_mapped_accounts_parseable
            and not self.unknown_account_mappings
            and self.any_observed_transaction_history
            and not self.effective_date_predates_observed_history
            and self.unattributed_savings_contribution_count == 0
        )


def assess_goal_completeness(
    account_mappings: list[GoalAccountMapping],
    *,
    effective_date: date,
    earliest_observed_transaction_date: date | None,
    contribution_transaction_count: int,
    unparseable_mappings: list[GoalAccountMapping],
    unknown_mappings: list[GoalAccountMapping],
    unattributed_savings_contribution_count: int = 0,
    unattributed_savings_contribution_amount: Decimal | None = None,
    percentage_target_income_observed: bool | None = None,
) -> GoalCompletenessMetadata:
    """Pure assembly of `GoalCompletenessMetadata`. Catalog lookups
    (parseable/unknown classification of each mapping) are resolved by the
    caller (app.services.savings_goals) since this module has no DB/config
    coupling — the caller passes back the already-partitioned mapping lists.
    """
    predates_history = (
        earliest_observed_transaction_date is not None
        and effective_date < earliest_observed_transaction_date
    )
    any_history = earliest_observed_transaction_date is not None

    notes: list[str] = []
    # Always state the attribution basis. `account_mappings` records WHERE a
    # goal's money is held, but attribution of observed contributions is by
    # classification CATEGORY, not by account: under the coverage-aware
    # transfer-leg rule (docs/coral-redesign/BLOCKED.md decision 1, Option C)
    # the counted leg usually lives on the checking account the money left,
    # not on the savings account it landed in, so filtering by the mapped
    # account would report $0. Two goals sharing one category therefore
    # accumulate the same transactions.
    notes.append(
        "current_amount sums every savings contribution Coral classified under this "
        "goal's category within the goal's window, on any ingested account — account "
        "mappings record where the money is held, they do not scope this sum. "
        "Withdrawals back out of savings are classified as transfers, not negative "
        "contributions, so they are not subtracted here."
    )
    if not account_mappings:
        notes.append(
            "No account mapping is defined for this goal; Coral cannot say which "
            "account holds it."
        )
    if not any_history:
        notes.append(
            "Coral has not ingested any transactions yet, so current_amount is $0 for "
            "lack of data — not because nothing was saved."
        )
    if unattributed_savings_contribution_count:
        notes.append(
            f"{unattributed_savings_contribution_count} savings contribution(s) totalling "
            f"${unattributed_savings_contribution_amount} were observed in this window but "
            "could not be attributed to any specific goal (no sub-goal keyword in the "
            "statement description); some of that money may belong to this goal."
        )
    if percentage_target_income_observed is False:
        notes.append(
            "No income was observed in this goal's window, so its "
            "target_percentage_of_income cannot be converted to a dollar target; status "
            "falls back to contribution recency only."
        )
    if unparseable_mappings:
        names = ", ".join(f"{m.institution_slug}/{m.account_slug}" for m in unparseable_mappings)
        notes.append(
            f"No statement parser exists yet for: {names}. Coral cannot read these "
            "accounts' statements directly; observed contributions are inferred only "
            "from transfer-leg transactions on other ingested accounts (e.g. the "
            "checking-side transfer out), so current_amount may understate the true "
            "balance."
        )
    if unknown_mappings:
        names = ", ".join(f"{m.institution_slug}/{m.account_slug}" for m in unknown_mappings)
        notes.append(f"Account mapping references an unknown catalog entry: {names}.")
    if predates_history:
        notes.append(
            f"This goal's effective_date ({effective_date.isoformat()}) predates Coral's "
            f"earliest ingested transaction ({earliest_observed_transaction_date.isoformat()}); "
            "current_amount may be understated because contribution history before that "
            "date was never observed."
        )
    if contribution_transaction_count == 0:
        notes.append("No contribution transactions have been observed for this goal yet.")

    return GoalCompletenessMetadata(
        all_mapped_accounts_parseable=not unparseable_mappings,
        unparseable_account_mappings=unparseable_mappings,
        unknown_account_mappings=unknown_mappings,
        earliest_observed_transaction_date=earliest_observed_transaction_date,
        any_observed_transaction_history=any_history,
        effective_date_predates_observed_history=predates_history,
        contribution_transaction_count=contribution_transaction_count,
        unattributed_savings_contribution_count=unattributed_savings_contribution_count,
        unattributed_savings_contribution_amount=str(
            _round_money(unattributed_savings_contribution_amount or Decimal("0"))
        ),
        percentage_target_income_observed=percentage_target_income_observed,
        notes=notes,
    )


# ── Completion recommendation ───────────────────────────────────────────────
#
# Narrow, deterministic, NON-PERSISTED — per the work order: "Do not
# automatically redirect money when a goal is complete. Generate a
# recommendation and require user approval for plan changes." This is
# intentionally the only recommendation shape PR13 builds; a general
# recommendation/approval-workflow engine is PR14's scope (Next Month
# Planner), which lists "Savings goals" as one of ITS inputs — PR13 only
# needs to expose goal status/data as a clean input for that, plus this one
# explicitly-called-out completion case.

class GoalCompletionRecommendation(BaseModel):
    goal_id: str
    goal_name: str
    message: str
    suggested_action: str = "review_plan_reallocation"
    requires_user_approval: bool = True


def build_completion_recommendation(
    *, goal_id: str, goal_name: str, status: GoalStatus, target_amount: Decimal | None,
    current_amount: Decimal,
) -> GoalCompletionRecommendation | None:
    """Returns a recommendation ONLY when `status == GoalStatus.COMPLETE`.
    Never mutates the plan or any account — the caller must never
    auto-apply `suggested_action` without explicit user approval."""
    if status != GoalStatus.COMPLETE:
        return None
    return GoalCompletionRecommendation(
        goal_id=goal_id,
        goal_name=goal_name,
        message=(
            f"'{goal_name}' has reached its target (${current_amount} of "
            f"${target_amount}). Contributions are not being redirected "
            "automatically — review your plan and choose where future "
            "contributions to this goal should go."
        ),
        suggested_action="review_plan_reallocation",
        requires_user_approval=True,
    )


# ── Read-side shapes (used by app.services.savings_goals) ──────────────────

class SavingsGoalProgress(BaseModel):
    """Full computed shape of one goal, as returned by the service/API
    layer. `current_amount` is always `current_amount_source`-labeled —
    never presented as an unqualified bank balance."""

    id: str
    name: str
    goal_type: GoalType
    category_name: str
    target_amount: str | None = None
    target_percentage_of_income: str | None = None
    target_months_of_expenses: str | None = None
    account_mappings: list[GoalAccountMapping] = Field(default_factory=list)
    priority: int = 0
    effective_date: date
    current_amount: str
    current_amount_source: str = "computed_from_contributions"
    as_of: date
    # Dollar-first Target / Actual / Variance (design-rules.md): the single $
    # target the goal is judged against, always provenance-labeled, plus the
    # observed income denominator behind a derived target. `variance_amount`
    # follows the same convention as plan_vs_actual.BucketDrift —
    # actual minus target, so negative = short of target.
    plannable_income: str = "0.00"
    target_amount_effective: str | None = None
    target_amount_source: TargetAmountSource = TargetAmountSource.NONE
    variance_amount: str | None = None
    status: GoalStatus
    data_completeness: GoalCompletenessMetadata
    completion_recommendation: GoalCompletionRecommendation | None = None

    @field_validator("current_amount", mode="before")
    @classmethod
    def _stringify(cls, v: object) -> str:
        return str(v)
