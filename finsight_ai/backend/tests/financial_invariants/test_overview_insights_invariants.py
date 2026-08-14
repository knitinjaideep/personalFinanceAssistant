"""
Financial invariant tests for the Overview page domain logic (PR 06 —
app.domain.overview_insights). Pure domain-level tests only (no DB) — mirrors
the pattern in test_plan_vs_actual_invariants.py, building synthetic
ClassifiedTxn lists and feeding them through the real
app.domain.plan_vs_actual engine before handing the result to
overview_insights, so these tests exercise real Decimal-computed variances,
never hand-authored ones.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal

from app.domain.entities import AllocationSnapshot, PlanVersionSnapshot, SuballocationSnapshot
from app.domain.overview_insights import (
    DriftStatus,
    MasterBucket,
    build_drift_candidates,
    build_financial_status,
    build_insights,
    build_next_month_plan,
    build_overview_insights,
    select_ranked_candidates,
)
from app.domain.plan_vs_actual import (
    ClassifiedTxn,
    Period,
    compute_category_breakdown,
    compute_plan_vs_actual,
)
from app.domain.transaction_classification import CashFlowType

PERIOD = Period.for_month(2026, 8)


def _default_plan() -> PlanVersionSnapshot:
    """Mirrors app.services.financial_plan._DEFAULT_ALLOCATIONS (50/20/15/15)."""
    return PlanVersionSnapshot(
        id="v1", plan_id="p1", version_number=1, effective_from=date(2026, 1, 1),
        allocations=[
            AllocationSnapshot(id="a1", bucket_name="needs", percentage="50", sort_order=0),
            AllocationSnapshot(id="a2", bucket_name="wants", percentage="20", sort_order=1),
            AllocationSnapshot(
                id="a3", bucket_name="savings", percentage="15", sort_order=2,
                suballocations=[
                    SuballocationSnapshot(
                        id="s1", name="Emergency Fund", percentage="5", sort_order=0
                    ),
                    SuballocationSnapshot(
                        id="s2", name="House / Goals", percentage="5", sort_order=1
                    ),
                    SuballocationSnapshot(
                        id="s3", name="Child Savings", percentage="5", sort_order=2
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
                        id="s7", name="Taxable Brokerage", percentage="2", sort_order=3
                    ),
                ],
            ),
        ],
    )


def _txn(
    txn_id: str, amount: str, bucket: MasterBucket, flow: CashFlowType,
    *, category: str | None = None, account_type: str | None = "checking", day: int = 15,
) -> ClassifiedTxn:
    return ClassifiedTxn(
        transaction_id=txn_id, account_id=f"acct-{account_type}", account_type=account_type,
        transaction_date=date(2026, 8, day), amount=Decimal(amount), master_bucket=bucket,
        category=category, cash_flow_type=flow,
    )


def _build_result(transactions: list[ClassifiedTxn], plan=None):
    plan = plan if plan is not None else _default_plan()
    return compute_plan_vs_actual(PERIOD, transactions, plan)


def _category_rows(transactions: list[ClassifiedTxn], plan=None):
    plan = plan if plan is not None else _default_plan()
    return (
        compute_category_breakdown(transactions, MasterBucket.SAVINGS, plan)
        + compute_category_breakdown(transactions, MasterBucket.INVESTMENTS, plan)
    )


# ── Cap invariants: never more than 3 ───────────────────────────────────────

def test_insights_never_exceed_three():
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        # Needs way over.
        _txn("t2", "-6000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        # Wants way over.
        _txn("t3", "-3000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
        # Savings way short (no contribution at all).
        # Investments way short (no contribution at all).
    ]
    result = _build_result(txns)
    candidates = build_drift_candidates(result, _category_rows(txns))
    insights = build_insights(candidates)
    assert len(insights) <= 3


def test_next_month_plan_never_exceeds_three():
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-6000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        _txn("t3", "-3000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
    ]
    result = _build_result(txns)
    candidates = build_drift_candidates(result, _category_rows(txns))
    plan_items = build_next_month_plan(candidates)
    assert len(plan_items) <= 3


# ── Incomplete-data honesty: no income observed -> no fabricated insights ──

def test_no_income_observed_yields_no_fabricated_insights_or_plan():
    txns = [
        _txn("t1", "-50.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Groceries"),
    ]
    result = _build_result(txns)
    assert result.completeness.income_observed is False

    overview = build_overview_insights(result, _category_rows(txns))
    assert overview.status.data_available is False
    assert overview.insights == []
    assert overview.next_month_plan == []


def test_all_unknown_status_never_fabricates_insight():
    """If plan is unavailable, every bucket is DriftStatus.UNKNOWN — no
    insight should be fabricated from an undefined variance."""
    txns = [
        _txn("t1", "-5000.00", MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-100.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Groceries"),
    ]
    result = compute_plan_vs_actual(PERIOD, txns, None)  # no plan in effect
    assert all(b.status == DriftStatus.UNKNOWN for b in result.buckets)
    overview = build_overview_insights(result, [])
    assert overview.insights == []
    assert overview.next_month_plan == []


# ── Dollar-first ranking ─────────────────────────────────────────────────────

def test_ranking_is_dollar_first_not_percentage_first():
    """A bucket with a larger absolute dollar variance must outrank a bucket
    with a smaller dollar variance even if the smaller one has a larger
    percentage-point deviation — the coral-redesign skill's "Dollar-first
    communication" principle applied to ranking, not just wording."""
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        # Needs, Savings, and Investments all exactly on target (50%/15%/15%
        # of 10000) -> zero variance each, so none can compete for the top
        # rank; only Wants has a real, material variance.
        _txn("t2", "-5000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        _txn("t4", "1500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
             category="Emergency Fund", account_type="savings"),
        _txn("t5", "1500.00", MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_CONTRIBUTION,
             category="401(k)", account_type="brokerage"),
        # Wants target = 20% * 10000 = 2000. Overspend by $900 -> 9pp over.
        _txn("t3", "-2900.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
    ]
    result = _build_result(txns)
    needs = next(b for b in result.buckets if b.bucket == MasterBucket.NEEDS)
    savings = next(b for b in result.buckets if b.bucket == MasterBucket.SAVINGS)
    investments = next(b for b in result.buckets if b.bucket == MasterBucket.INVESTMENTS)
    wants = next(b for b in result.buckets if b.bucket == MasterBucket.WANTS)
    assert needs.variance_amount == "0.00"
    assert savings.variance_amount == "0.00"
    assert investments.variance_amount == "0.00"
    assert wants.variance_amount == "900.00"

    candidates = build_drift_candidates(result, [])
    picked, _ = select_ranked_candidates(candidates, max_items=1)
    assert picked[0].bucket == MasterBucket.WANTS


# ── Diversity guard: one bucket cannot dominate every slot ──────────────────

def _three_savings_categories_txns() -> list[ClassifiedTxn]:
    """Savings contributions split across all three Savings categories such
    that the BUCKET total lands exactly on its 15% target (so the
    bucket-level row is immaterial and drops out of the candidate pool),
    leaving three genuinely competing category-level candidates in one
    bucket — the only shape that exercises the per-bucket diversity guard
    non-vacuously."""
    income = Decimal("10000.00")
    return [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-5000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        _txn("t3", "-2000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
        # Savings: 1000 + 400 + 100 = 1500 = the 15% bucket target exactly.
        _txn("t4", "1000.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
             category="Emergency Fund", account_type="savings"),
        _txn("t5", "400.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
             category="House / Goals", account_type="savings"),
        _txn("t6", "100.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
             category="Child Savings", account_type="savings"),
        _txn("t7", "1500.00", MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_CONTRIBUTION,
             category="401(k)", account_type="brokerage"),
    ]


def test_diversity_guard_caps_per_bucket_contributions():
    txns = _three_savings_categories_txns()
    result = _build_result(txns)
    savings_bucket = next(b for b in result.buckets if b.bucket == MasterBucket.SAVINGS)
    assert savings_bucket.variance_amount == "0.00"  # bucket row is immaterial

    candidates = build_drift_candidates(result, _category_rows(txns))
    savings_categories = [
        c for c in candidates if c.scope == "category" and c.bucket == MasterBucket.SAVINGS
    ]
    assert len(savings_categories) == 3  # three real competitors in one bucket

    # max_items deliberately > 3 here so the cap, not the "maximum three"
    # rule, is what excludes the third Savings category.
    picked, _ = select_ranked_candidates(candidates, max_items=4, max_per_bucket=2)
    counts = Counter(c.bucket for c in picked)
    assert counts[MasterBucket.SAVINGS] == 2
    assert all(n <= 2 for n in counts.values())
    assert len(picked) == 3  # a 4th slot was available but the guard blocked it


# ── No parent/child double-telling of the same dollars ─────────────────────

def _overlapping_savings_shortfall_txns() -> list[ClassifiedTxn]:
    """A Savings shortfall visible BOTH at bucket level (-$1,490 vs the 15%
    target) and at category level (-$490 for House / Goals vs its 5%
    sub-target) — the same missing dollars, described at two depths."""
    income = Decimal("10000.00")
    return [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-5000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        _txn("t3", "-2000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
        _txn("t4", "10.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
             category="House / Goals", account_type="savings"),
        _txn("t5", "1500.00", MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_CONTRIBUTION,
             category="401(k)", account_type="brokerage"),
    ]


def test_insights_never_pair_a_bucket_with_its_own_category():
    """A category's dollars are a subset of its bucket's dollars, so surfacing
    both as separate insights describes the same shortfall twice and burns
    two of only three slots on one fact."""
    txns = _overlapping_savings_shortfall_txns()
    result = _build_result(txns)
    candidates = build_drift_candidates(result, _category_rows(txns))

    # Both depths really are in the candidate pool and both really are adverse.
    assert any(c.scope == "bucket" and c.bucket == MasterBucket.SAVINGS for c in candidates)
    assert any(c.scope == "category" and c.bucket == MasterBucket.SAVINGS for c in candidates)

    picked, _ = select_ranked_candidates(candidates, max_items=3, max_per_bucket=2)
    scopes_per_bucket: dict[MasterBucket, set[str]] = {}
    for c in picked:
        scopes_per_bucket.setdefault(c.bucket, set()).add(c.scope)
    assert all(len(scopes) == 1 for scopes in scopes_per_bucket.values())


def test_next_month_plan_never_double_counts_the_same_gap():
    """The plan's `estimated_impact` figures must be addable: a user must
    never see "Add $1,490 to Savings" alongside "Add $490 to House / Goals"
    for a single $1,490 gap."""
    txns = _overlapping_savings_shortfall_txns()
    result = _build_result(txns)
    candidates = build_drift_candidates(result, _category_rows(txns))

    items = build_next_month_plan(candidates)
    savings_items = [i for i in items if i.bucket == MasterBucket.SAVINGS]
    assert len(savings_items) == 1
    assert savings_items[0].category is None  # the bucket-level gap, not a subset of it
    assert Decimal(savings_items[0].estimated_impact) == Decimal("1490.00")


# ── Ranking: actionable drift outranks favorable drift ─────────────────────

def test_actionable_drift_outranks_larger_favorable_drift():
    """A period with income but no classified spending yet is OFF plan
    (Savings/Investments both fully short) while Needs/Wants show large
    "under budget" favorable variances. The insights must lead with the
    actionable shortfalls rather than congratulating the user twice and
    contradicting the status header."""
    income = Decimal("10000.00")
    txns = [_txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME)]
    result = _build_result(txns)
    needs = next(b for b in result.buckets if b.bucket == MasterBucket.NEEDS)
    savings = next(b for b in result.buckets if b.bucket == MasterBucket.SAVINGS)
    # The favorable Needs variance is the LARGEST dollar figure on the page...
    assert abs(Decimal(needs.variance_amount)) > abs(Decimal(savings.variance_amount))
    assert needs.status == DriftStatus.ON_TRACK
    assert savings.status == DriftStatus.OFF_TRACK

    candidates = build_drift_candidates(result, [])
    insights = build_insights(candidates)
    # ...yet the adverse buckets lead, and the header agrees with them.
    assert [i.tone for i in insights[:2]] == ["danger", "danger"]
    assert {i.bucket for i in insights[:2]} == {MasterBucket.SAVINGS, MasterBucket.INVESTMENTS}
    status = build_financial_status(
        [c for c in candidates if c.scope == "bucket"], result.completeness
    )
    assert status.tone == "danger"


# ── Materiality floor: tiny drift doesn't crowd out real insights ──────────

def test_on_track_month_yields_single_honest_summary_not_fabricated_noise():
    """Bucket-level-only candidate pool (no category breakdown passed) — this
    isolates the "every bucket is on track" fallback behavior from
    category-level drift, which is covered separately by
    test_diversity_guard_caps_per_bucket_contributions and the mixed-status
    ranking tests above."""
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-5000.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
        _txn("t3", "-2000.00", MasterBucket.WANTS, CashFlowType.EXPENSE, category="Dining"),
        _txn("t4", "1500.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
             category="Emergency Fund", account_type="savings"),
        _txn("t5", "1500.00", MasterBucket.INVESTMENTS, CashFlowType.INVESTMENT_CONTRIBUTION,
             category="401(k)", account_type="brokerage"),
    ]
    result = _build_result(txns)
    assert all(b.status == DriftStatus.ON_TRACK for b in result.buckets)

    candidates = build_drift_candidates(result, category_rows=None)
    insights = build_insights(candidates)
    assert len(insights) == 1
    assert insights[0].tone == "good"
    assert insights[0].bucket is None  # synthesized summary, not one specific bucket


# ── Insight wording: "over/under target" pp phrasing is bucket-type-agnostic ──

def test_insight_pp_wording_says_over_for_an_ahead_accumulation_bucket():
    """A Savings/Investments bucket that is AHEAD of its target percentage
    must say "over target" in the supporting pp clause, not "under" —
    regression test for a sign bug where the accumulation-bucket "adverse"
    flip (used correctly for the good/bad tone) leaked into the plain
    over/under-target wording, which must always follow the raw
    variance_percentage_points sign instead."""
    from app.domain.overview_insights import build_insights

    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        # Savings target = 15% * 10000 = 1500. Contribute way more -> actual%
        # is well OVER target% (ahead, in the good direction).
        _txn("t2", "5000.00", MasterBucket.SAVINGS, CashFlowType.SAVINGS_CONTRIBUTION,
             category="Emergency Fund", account_type="savings"),
    ]
    result = _build_result(txns)
    savings = next(b for b in result.buckets if b.bucket == MasterBucket.SAVINGS)
    assert Decimal(savings.variance_percentage_points) > 0  # actual% is above target%

    candidates = build_drift_candidates(result, [])
    insights = build_insights(candidates)
    savings_insight = next(i for i in insights if i.bucket == MasterBucket.SAVINGS)
    assert "over target" in savings_insight.description
    assert "under target" not in savings_insight.description


# ── Financial status header never claims certainty it doesn't have ─────────

def test_financial_status_headline_matches_worst_bucket_status():
    income = Decimal("10000.00")
    txns = [
        _txn("t1", str(income), MasterBucket.UNCLASSIFIED, CashFlowType.INCOME),
        _txn("t2", "-6500.00", MasterBucket.NEEDS, CashFlowType.EXPENSE, category="Housing"),
    ]
    result = _build_result(txns)
    candidates = build_drift_candidates(result, [])
    bucket_candidates = [c for c in candidates if c.scope == "bucket"]
    status = build_financial_status(bucket_candidates, result.completeness)
    assert status.tone == "danger"
    assert "off plan" in status.headline.lower()
    assert status.data_available is True


# ── Period.split_by_calendar_month: exact, gapless coverage ─────────────────

def test_split_by_calendar_month_single_month_is_identity():
    p = Period.for_month(2026, 8)
    segments = p.split_by_calendar_month()
    assert len(segments) == 1
    assert segments[0].start == p.start
    assert segments[0].end == p.end


def test_split_by_calendar_month_covers_range_with_no_gaps_or_overlaps():
    p = Period.for_range(date(2026, 6, 15), date(2026, 9, 3))
    segments = p.split_by_calendar_month()
    assert len(segments) == 4  # partial Jun, full Jul, full Aug, partial Sep
    assert segments[0].start == date(2026, 6, 15)
    assert segments[-1].end == date(2026, 9, 3)
    for prev, nxt in zip(segments[:-1], segments[1:], strict=True):
        # Contiguous: next segment starts exactly one day after prev ends.
        assert (nxt.start - prev.end).days == 1


def test_split_by_calendar_month_handles_leap_february_and_year_boundary():
    """A 6-month window starting mid-month and crossing both a year boundary
    and a leap-year February: every month end must be that month's real last
    day (29 for Feb 2028), with no gaps, overlaps, or off-by-one days."""
    p = Period.for_range(date(2027, 11, 20), date(2028, 4, 10))
    segments = p.split_by_calendar_month()

    assert [s.label for s in segments] == [
        "2027-11", "2027-12", "2028-01", "2028-02", "2028-03", "2028-04",
    ]
    assert segments[0].start == date(2027, 11, 20)  # partial first month preserved
    assert segments[0].end == date(2027, 11, 30)
    assert segments[3].start == date(2028, 2, 1)
    assert segments[3].end == date(2028, 2, 29)  # leap day included, not truncated
    assert segments[-1].end == date(2028, 4, 10)  # partial last month preserved

    for prev, nxt in zip(segments[:-1], segments[1:], strict=True):
        assert (nxt.start - prev.end).days == 1
    total_days = sum((s.end - s.start).days + 1 for s in segments)
    assert total_days == (p.end - p.start).days + 1  # exact cover, no double count
