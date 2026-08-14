"""
Coral Overview page domain logic — pure, deterministic, DB-free.

Consumes the already-computed output of app.domain.plan_vs_actual
(`PlanVsActualResult` + optional `CategoryDrift` rows) and derives everything
the Overview page (docs/coral-redesign/pr-06-overview.md) needs beyond the
raw Plan vs Actual table:

  - `FinancialStatus`     — the one-sentence "How am I doing?" header.
  - `CoralInsight` (<=3)  — ranked, deterministic observations.
  - `NextMonthPlanItem` (<=3) — a small, deterministic "what to adjust next
    period" preview. This is intentionally NOT the full Next Month Planner
    (that is PR14 / Milestone M6, docs/coral-redesign/pr-14-next-month-planner.md)
    — no multi-month projection, no user-editable state, no persistence.
  - `MonthlyFlowSummary`  — one row per calendar month for the Income vs
    Spent vs Saved/Invested grouped bar chart.

Nothing in this module touches the database or calls an LLM. Every number
here is derived arithmetic (sums, comparisons, sign flips) over numbers the
Plan vs Actual engine already computed with Decimal — this module never
recomputes a target/actual/variance itself (accounting-invariants.md #10:
never fabricate a number). An LLM may later restyle the `title`/`description`
strings produced here, but the underlying facts (bucket, amounts, status,
ranking) are fixed before any LLM ever sees them — see
.claude/skills/coral-redesign/SKILL.md, "Coral Insights: An LLM can explain
facts but must not manufacture the facts."
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain.plan_vs_actual import (
    BucketDrift,
    CategoryDrift,
    CompletenessMetadata,
    DriftStatus,
    Period,
    PlanVsActualResult,
)
from app.domain.transaction_classification import MasterBucket

StatusTone = Literal["good", "warning", "danger", "neutral"]

# Below this absolute dollar variance, a drift is treated as noise rather
# than an actionable/insight-worthy deviation — dollar-first materiality
# floor, deliberately separate from (and smaller-grained than) the
# percentage-point DriftStatus thresholds in app.domain.plan_vs_actual, which
# already gate OFF_TRACK/WATCH. This floor only affects the "genuinely ahead"
# (good, non-adverse) classification and the Coral Insights/Next Month Plan
# candidate pools, never the status itself.
MATERIALITY_DOLLARS = Decimal("10.00")

_BUCKET_LABEL: dict[MasterBucket, str] = {
    MasterBucket.NEEDS: "Needs",
    MasterBucket.WANTS: "Wants",
    MasterBucket.SAVINGS: "Savings",
    MasterBucket.INVESTMENTS: "Investments",
}

# Deterministic, documented tie-break order — only ever consulted after
# dollar impact, percentage-point deviation, and transaction-count
# confidence all tie (see _sort_key).
_BUCKET_PRIORITY: dict[MasterBucket, int] = {
    MasterBucket.NEEDS: 0,
    MasterBucket.WANTS: 1,
    MasterBucket.SAVINGS: 2,
    MasterBucket.INVESTMENTS: 3,
}

_CONSUMPTION_BUCKETS = frozenset({MasterBucket.NEEDS, MasterBucket.WANTS})


def _fmt_money(value: Decimal) -> str:
    """Local, self-contained formatter (no cross-layer import into
    services/dashboard/utils — domain modules must not depend on the
    services layer). Whole-dollar amounts drop the trailing ".00" for
    readable prose; fractional amounts keep 2 decimals."""
    value = value.quantize(Decimal("0.01"))
    if value == value.to_integral_value():
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def _fmt_points(value: Decimal) -> str:
    """Percentage points for the supporting clause of an insight sentence —
    whole values drop the ".00" ("13 pts", not "13.00 pts"). Purely
    presentational; the underlying Decimal is never rounded away."""
    if value == value.to_integral_value():
        return f"{value.quantize(Decimal('1'))}"
    return f"{value}"


def _dec_or_none(v: str | None) -> Decimal | None:
    return Decimal(v) if v is not None else None


# ── Unified drift candidate (bucket-level or category-level) ───────────────

class DriftCandidate(BaseModel):
    """One row that could become a Coral Insight / Next Month Plan item —
    either a master-bucket row (`BucketDrift`) or a category row within
    Savings/Investments (`CategoryDrift`, the only buckets whose categories
    have plan-defined suballocation targets — see
    app.domain.plan_vs_actual._category_target_percentage)."""

    model_config = ConfigDict(frozen=True)

    scope: Literal["bucket", "category"]
    bucket: MasterBucket
    category: str | None
    label: str
    target_amount: Decimal | None
    actual_amount: Decimal
    variance_amount: Decimal | None
    variance_percentage_points: Decimal | None
    status: DriftStatus
    transaction_count: int


def _from_bucket_drift(b: BucketDrift) -> DriftCandidate:
    return DriftCandidate(
        scope="bucket", bucket=b.bucket, category=None, label=_BUCKET_LABEL[b.bucket],
        target_amount=_dec_or_none(b.target_amount),
        actual_amount=Decimal(b.actual_amount),
        variance_amount=_dec_or_none(b.variance_amount),
        variance_percentage_points=_dec_or_none(b.variance_percentage_points),
        status=b.status, transaction_count=b.transaction_count,
    )


def _from_category_drift(c: CategoryDrift) -> DriftCandidate:
    return DriftCandidate(
        scope="category", bucket=c.bucket, category=c.category, label=c.category,
        target_amount=_dec_or_none(c.target_amount),
        actual_amount=Decimal(c.actual_amount),
        variance_amount=_dec_or_none(c.variance_amount),
        variance_percentage_points=_dec_or_none(c.variance_percentage_points),
        status=c.status, transaction_count=c.transaction_count,
    )


def build_drift_candidates(
    result: PlanVsActualResult, category_rows: list[CategoryDrift] | None = None,
) -> list[DriftCandidate]:
    """The full candidate pool: the 4 master buckets plus (optionally) any
    category-level rows the caller supplies — the Overview service passes
    the Savings + Investments category breakdowns (Needs/Wants have no
    category-level plan targets, so their category rows would only ever be
    `DriftStatus.UNKNOWN` and are intentionally not fetched by the caller)."""
    candidates = [_from_bucket_drift(b) for b in result.buckets]
    if category_rows:
        candidates.extend(_from_category_drift(c) for c in category_rows)
    return candidates


def _adverse_amount(c: DriftCandidate) -> Decimal:
    """Signed "badness" of this candidate's variance: positive means adverse
    (overspend for Needs/Wants, shortfall for Savings/Investments), negative
    means favorable. Mirrors the sign convention in
    app.domain.plan_vs_actual.compute_status."""
    variance = c.variance_amount if c.variance_amount is not None else Decimal("0")
    return variance if c.bucket in _CONSUMPTION_BUCKETS else -variance


def _is_actionable(c: DriftCandidate) -> bool:
    """True when this candidate is adversely off plan (`compute_status` only
    ever returns WATCH/OFF_TRACK for adverse drift — overspend for
    Needs/Wants, shortfall for Savings/Investments). Favorable drift
    (underspending, over-saving) is real and worth showing, but it is never
    something the user needs to act on."""
    return c.status in (DriftStatus.OFF_TRACK, DriftStatus.WATCH)


def _sort_key(c: DriftCandidate) -> tuple:
    """Actionable-first, then dollar-first ranking (impact), then
    percentage-point deviation, then transaction-count confidence, then a
    fixed bucket-priority/label tie-break for full determinism — per the
    coral-redesign skill's "Rank for: impact / deviation / confidence /
    actionability".

    Actionability leads because a purely dollar-first sort lets favorable
    variances crowd out the drift the page is actually warning about: a
    period with no classified spending yet reads "Needs is $5,000 under
    target — nice work" ahead of "Savings is $1,500 behind target", directly
    contradicting the status header above it. Within each group the ranking
    is still dollar-first, matching the skill's "Dollar-first communication".
    This also keeps Coral Insights ordered consistently with the Next Month
    Plan, which already partitions action-needed ahead of maintain items.
    """
    variance = abs(c.variance_amount) if c.variance_amount is not None else Decimal("-1")
    pp = (
        abs(c.variance_percentage_points)
        if c.variance_percentage_points is not None
        else Decimal("-1")
    )
    return (
        0 if _is_actionable(c) else 1,
        -variance, -pp, -c.transaction_count, _BUCKET_PRIORITY.get(c.bucket, 99), c.label,
    )


def _known_material_candidates(
    candidates: list[DriftCandidate], *, materiality: Decimal = MATERIALITY_DOLLARS,
) -> tuple[list[DriftCandidate], list[DriftCandidate]]:
    """Returns `(material, known)`. `known` excludes DriftStatus.UNKNOWN rows
    (incomplete-data honesty — accounting-invariants.md #10: never present a
    confident-looking insight built on an undefined variance). `material`
    additionally excludes known rows whose dollar variance is below the
    materiality floor."""
    known = [
        c for c in candidates if c.status != DriftStatus.UNKNOWN and c.variance_amount is not None
    ]
    material = [c for c in known if abs(c.variance_amount) >= materiality]  # type: ignore[arg-type]
    return material, known


class _SelectionGuard:
    """Shared per-bucket selection guard for Coral Insights and the Next
    Month Plan.

    Two rules, both about not telling the user the same thing twice:

      - diversity: at most `max_per_bucket` picks from any one master bucket,
        so one bucket's several off-target categories can't crowd out every
        other bucket.
      - no parent/child overlap: never pick BOTH a bucket-level row and one
        of that same bucket's own category rows. A category row's dollars are
        a subset of its bucket's dollars, so picking both describes the same
        shortfall twice ("Savings is $1,490 behind" + "House / Goals is $490
        behind") and, in the Next Month Plan, would present two
        `estimated_impact` figures that a user could reasonably add together
        for a single gap. Whichever scope ranks higher wins; the other scope
        is suppressed for that bucket.
    """

    def __init__(self, *, max_per_bucket: int) -> None:
        self._max_per_bucket = max_per_bucket
        self._counts: dict[MasterBucket, int] = {}
        self._scopes: dict[MasterBucket, str] = {}

    def accepts(self, c: DriftCandidate) -> bool:
        if self._counts.get(c.bucket, 0) >= self._max_per_bucket:
            return False
        picked_scope = self._scopes.get(c.bucket)
        return picked_scope is None or picked_scope == c.scope

    def record(self, c: DriftCandidate) -> None:
        self._counts[c.bucket] = self._counts.get(c.bucket, 0) + 1
        self._scopes[c.bucket] = c.scope


def select_ranked_candidates(
    candidates: list[DriftCandidate],
    *,
    max_items: int = 3,
    max_per_bucket: int = 2,
    materiality: Decimal = MATERIALITY_DOLLARS,
) -> tuple[list[DriftCandidate], list[DriftCandidate]]:
    """Rank + cap candidates for Coral Insights: actionable-then-dollar-first
    sort (`_sort_key`), capped at `max_items` (the skill's "Maximum three"),
    filtered through `_SelectionGuard` (per-bucket diversity + no
    bucket/own-category overlap). Returns `(picked, known)` — `known` is
    handed back so the caller can distinguish "nothing material" (fall back
    to a single honest on-track summary) from "no data at all" (empty)."""
    material, known = _known_material_candidates(candidates, materiality=materiality)
    material = sorted(material, key=_sort_key)
    guard = _SelectionGuard(max_per_bucket=max_per_bucket)
    picked: list[DriftCandidate] = []
    for c in material:
        if not guard.accepts(c):
            continue
        picked.append(c)
        guard.record(c)
        if len(picked) >= max_items:
            break
    return picked, known


# ── Coral Insights ──────────────────────────────────────────────────────────

class CoralInsight(BaseModel):
    title: str
    description: str
    tone: StatusTone
    bucket: MasterBucket | None
    category: str | None = None
    variance_amount: str | None
    target_amount: str | None
    # None for the synthesized "everything is on track" summary, which is not
    # about one bucket and therefore has no actual $ of its own — reporting
    # "0.00" there would be a fabricated number
    # (accounting-invariants.md #10).
    actual_amount: str | None


def _describe_insight(c: DriftCandidate) -> tuple[str, str, StatusTone]:
    adverse = _adverse_amount(c)
    consumption = c.bucket in _CONSUMPTION_BUCKETS
    target_txt = _fmt_money(c.target_amount) if c.target_amount is not None else "no defined target"
    actual_txt = _fmt_money(c.actual_amount)
    pp = c.variance_percentage_points

    if c.status in (DriftStatus.OFF_TRACK, DriftStatus.WATCH):
        # compute_status() only ever flags OFF_TRACK/WATCH when `adverse`
        # exceeds a positive percentage-point threshold, so `adverse` is
        # guaranteed > 0 here — see app.domain.plan_vs_actual.compute_status.
        amt = _fmt_money(adverse)
        if consumption:
            title = f"Overspending in {c.label}"
            desc = f"{c.label} is {amt} over your {target_txt} target this period."
        else:
            noun = "Under-saving for" if c.bucket == MasterBucket.SAVINGS else "Behind on"
            title = f"{noun} {c.label}"
            desc = f"{c.label} is {amt} behind your {target_txt} target this period."
        tone: StatusTone = "danger" if c.status == DriftStatus.OFF_TRACK else "warning"
    elif adverse <= -MATERIALITY_DOLLARS:
        amt = _fmt_money(-adverse)
        if consumption:
            title = f"Under budget in {c.label}"
            desc = f"{c.label} is {amt} under your {target_txt} target this period — nice work."
        else:
            title = f"Ahead on {c.label}"
            desc = f"{c.label} is {amt} ahead of your {target_txt} target this period."
        tone = "good"
    else:
        title = f"On track for {c.label}"
        desc = f"{c.label} is on track this period — {actual_txt} against a {target_txt} target."
        tone = "good"

    if pp is not None and pp != 0:
        # `pp` (variance_percentage_points = actual% - target%) is a plain,
        # bucket-type-independent "over/under the target percentage" signal
        # — unlike `adverse`, which flips sign for accumulation buckets
        # (Savings/Investments) so it can mean "good"/"bad". Using `adverse`
        # here previously produced backwards wording, e.g. "Ahead on
        # Savings ... (40 pts under target)" for a bucket that was actually
        # OVER its target percentage.
        direction = "over" if pp > 0 else "under"
        desc += f" ({_fmt_points(abs(pp))} pts {direction} target)."
    return title, desc, tone


def build_insights(candidates: list[DriftCandidate]) -> list[CoralInsight]:
    """Rank candidate observations and cap at 3 (coral-redesign skill:
    "Maximum three high-value insights"). When nothing is materially off
    (every known bucket/category is within the noise floor) this returns a
    single honest "on track" summary rather than an empty section — that
    summary states a true, already-computed fact (every tracked bucket is
    within range) and never invents a number. When there is no usable data
    at all (e.g. no income observed this period), returns an empty list —
    the caller/frontend renders the first-time/empty state instead."""
    picked, known = select_ranked_candidates(candidates)
    if picked:
        insights = []
        for c in picked:
            title, desc, tone = _describe_insight(c)
            insights.append(CoralInsight(
                title=title, description=desc, tone=tone, bucket=c.bucket, category=c.category,
                variance_amount=str(c.variance_amount) if c.variance_amount is not None else None,
                target_amount=str(c.target_amount) if c.target_amount is not None else None,
                actual_amount=str(c.actual_amount),
            ))
        return insights
    if not known:
        return []
    return [CoralInsight(
        title="On track this period",
        description="Every tracked bucket is within its target range this period.",
        tone="good", bucket=None, category=None,
        variance_amount=None, target_amount=None, actual_amount=None,
    )]


# ── Next Month Plan (lightweight preview — see module docstring) ───────────

NextMonthActionType = Literal[
    "reduce_category", "increase_savings_goal", "increase_investment_contribution",
    "maintain_contribution",
]


class NextMonthPlanItem(BaseModel):
    title: str
    description: str
    estimated_impact: str  # dollar amount, unsigned
    action_type: NextMonthActionType
    bucket: MasterBucket
    category: str | None = None
    priority: int


def _plan_item_for(c: DriftCandidate, *, priority: int) -> NextMonthPlanItem:
    adverse = _adverse_amount(c)
    consumption = c.bucket in _CONSUMPTION_BUCKETS
    if c.status in (DriftStatus.OFF_TRACK, DriftStatus.WATCH):
        amt = _fmt_money(adverse)
        if consumption:
            return NextMonthPlanItem(
                title=f"Reduce {c.label} by {amt} next period",
                description=(
                    f"{c.label} ran {amt} over target this period; trimming spending "
                    "here would bring you back on plan."
                ),
                estimated_impact=str(adverse.quantize(Decimal("0.01"))),
                action_type="reduce_category",
                bucket=c.bucket, category=c.category, priority=priority,
            )
        action: NextMonthActionType = (
            "increase_savings_goal"
            if c.bucket == MasterBucket.SAVINGS
            else "increase_investment_contribution"
        )
        return NextMonthPlanItem(
            title=f"Add {amt} more to {c.label}",
            description=(
                f"{c.label} is {amt} behind target this period; contributing a bit "
                "more next period closes the gap."
            ),
            estimated_impact=str(adverse.quantize(Decimal("0.01"))),
            action_type=action,
            bucket=c.bucket, category=c.category, priority=priority,
        )
    # Positive reinforcement path: a consistently on-track accumulation
    # bucket/category. `adverse <= 0` here by construction (callers only
    # route ON_TRACK, non-consumption candidates into this branch).
    amount = c.target_amount if c.target_amount is not None else c.actual_amount
    return NextMonthPlanItem(
        title=f"Keep contributing to {c.label}",
        description=(
            f"{c.label} is on track — stay consistent at {_fmt_money(amount)} next period."
        ),
        estimated_impact=str(amount.quantize(Decimal("0.01"))),
        action_type="maintain_contribution",
        bucket=c.bucket, category=c.category, priority=priority,
    )


def build_next_month_plan(
    candidates: list[DriftCandidate], *, max_items: int = 3, max_per_bucket: int = 2,
) -> list[NextMonthPlanItem]:
    """Small, deterministic "what to adjust next period" preview — explicitly
    NOT PR14's full Next Month Planner (no multi-month trend/projection, no
    savings-goal/investment-gap modeling beyond this period's own variance,
    not user-editable/persisted). Does not try to close every historical
    shortfall in one step — see PR14 work order's "do not always try to make
    up every historical shortfall next month"; each recommendation targets
    only this period's own observed gap or maintenance of an already-on-track
    contribution, one period at a time."""
    material, _ = _known_material_candidates(candidates)

    action_needed = [c for c in material if c.status in (DriftStatus.OFF_TRACK, DriftStatus.WATCH)]
    maintain_worthy = [
        c for c in material
        if c.status == DriftStatus.ON_TRACK and c.bucket not in _CONSUMPTION_BUCKETS
    ]

    action_needed.sort(key=_sort_key)
    maintain_worthy.sort(key=_sort_key)

    items: list[NextMonthPlanItem] = []
    guard = _SelectionGuard(max_per_bucket=max_per_bucket)

    def _take(pool: list[DriftCandidate]) -> None:
        for c in pool:
            if len(items) >= max_items:
                return
            if not guard.accepts(c):
                continue
            items.append(_plan_item_for(c, priority=len(items) + 1))
            guard.record(c)

    _take(action_needed)
    if len(items) < max_items:
        _take(maintain_worthy)
    return items


# ── Financial status header ─────────────────────────────────────────────────

class FinancialStatus(BaseModel):
    headline: str
    body: str
    tone: StatusTone
    data_available: bool


def _driver_sentence(candidates: list[DriftCandidate]) -> str:
    parts: list[str] = []
    for c in sorted(candidates, key=_sort_key)[:2]:
        adverse = _adverse_amount(c)
        amt = _fmt_money(adverse if adverse > 0 else -adverse)
        if c.bucket in _CONSUMPTION_BUCKETS:
            parts.append(f"{c.label} is running {amt} above plan")
        else:
            parts.append(f"{c.label} is {amt} behind target")
    return " and ".join(parts) + "." if parts else ""


def build_financial_status(
    bucket_candidates: list[DriftCandidate], completeness: CompletenessMetadata,
) -> FinancialStatus:
    """The Overview page's one-sentence "How am I doing?" header (PR06
    structure item 1). Deliberately scoped to the 4 master buckets only
    (not categories) — the header answers "how is my month going overall",
    not a category-level drill-down. Uses "this period" rather than "this
    month" throughout since the selected period may span multiple months
    (PR 05 Global Period Filter)."""
    if not completeness.income_observed:
        return FinancialStatus(
            headline="Not enough data yet this period.",
            body=(
                "Coral didn't detect any income for the selected period, so spending "
                "can't be compared to your plan yet. Try a different period, or check "
                "that your latest statements are uploaded."
            ),
            tone="neutral", data_available=False,
        )

    known = [c for c in bucket_candidates if c.status != DriftStatus.UNKNOWN]
    off_track = [c for c in known if c.status == DriftStatus.OFF_TRACK]
    watch = [c for c in known if c.status == DriftStatus.WATCH]

    if off_track:
        return FinancialStatus(
            headline="You're off plan this period.",
            body=(
                _driver_sentence(off_track + watch)
                or "One or more buckets have drifted meaningfully from target."
            ),
            tone="danger", data_available=True,
        )
    if watch:
        return FinancialStatus(
            headline="You're slightly off plan this period.",
            body=_driver_sentence(watch) or "A bucket or two is drifting from target.",
            tone="warning", data_available=True,
        )
    if not known:
        return FinancialStatus(
            headline="Not enough data yet this period.",
            body=(
                "Coral doesn't have enough classified transactions yet to judge "
                "this period against your plan."
            ),
            tone="neutral", data_available=False,
        )
    return FinancialStatus(
        headline="You're on plan this period.",
        body="Every bucket is within its target range this period. Nice work.",
        tone="good", data_available=True,
    )


# ── Monthly flow summary (Income vs Spent vs Saved/Invested chart) ─────────

class MonthlyFlowSummary(BaseModel):
    """One grouped-bar-chart cluster: Income vs Spent vs Saved/Invested for
    one calendar month (or one partial-month segment at the edges of a
    range — see Period.split_by_calendar_month)."""

    period_label: str
    start: date
    end: date
    income: str
    spent: str
    saved_invested: str
    income_observed: bool


def summarize_monthly_flow(result: PlanVsActualResult) -> MonthlyFlowSummary:
    """Derives the 3-series chart row from an already-computed
    PlanVsActualResult — no new financial math beyond addition of two
    already-computed bucket actuals (Needs+Wants, Savings+Investments)."""
    by_bucket = {b.bucket: Decimal(b.actual_amount) for b in result.buckets}
    spent = (
        by_bucket.get(MasterBucket.NEEDS, Decimal("0"))
        + by_bucket.get(MasterBucket.WANTS, Decimal("0"))
    )
    saved_invested = (
        by_bucket.get(MasterBucket.SAVINGS, Decimal("0"))
        + by_bucket.get(MasterBucket.INVESTMENTS, Decimal("0"))
    )
    return MonthlyFlowSummary(
        period_label=result.period.label,
        start=result.period.start,
        end=result.period.end,
        income=result.plannable_income,
        spent=str(spent.quantize(Decimal("0.01"))),
        saved_invested=str(saved_invested.quantize(Decimal("0.01"))),
        income_observed=result.completeness.income_observed,
    )


# ── Top-level composer ──────────────────────────────────────────────────────

class OverviewInsightsResult(BaseModel):
    period: Period
    status: FinancialStatus
    insights: list[CoralInsight]
    next_month_plan: list[NextMonthPlanItem]
    completeness: CompletenessMetadata


def build_overview_insights(
    result: PlanVsActualResult, category_rows: list[CategoryDrift] | None = None,
) -> OverviewInsightsResult:
    """Top-level pure composer — app.services.overview's sole call into this
    module. `category_rows` should be the Savings + Investments category
    breakdowns for the same period (Needs/Wants have no category-level plan
    targets, see build_drift_candidates)."""
    candidates = build_drift_candidates(result, category_rows)
    bucket_candidates = [c for c in candidates if c.scope == "bucket"]

    return OverviewInsightsResult(
        period=result.period,
        status=build_financial_status(bucket_candidates, result.completeness),
        insights=build_insights(candidates),
        next_month_plan=build_next_month_plan(candidates),
        completeness=result.completeness,
    )
