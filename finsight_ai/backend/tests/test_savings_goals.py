"""
Tests for the Savings Goal Engine (PR 13): domain model, service layer, and
API. Mirrors backend/tests/test_financial_plan.py's structure (task-numbered
groups, `temp_db` fixture).

Covers (see docs/coral-redesign/pr-13-savings-goals.md):
  - goal creation / validation (target required, target_months_of_expenses
    only meaningful for emergency_fund)
  - one account backing multiple goals; one goal spanning multiple accounts
  - status transitions (not_started/behind/on_track/complete) against
    realistic contribution transactions
  - emergency-fund target_months_of_expenses support
  - the goal-completion recommendation (fires only when complete, never
    auto-redirects money)
  - completeness/honesty when a mapped account has no parseable data or
    effective_date predates observed history
  - the three default goals seed on boot at 5/5/5, matching SAVINGS_CATEGORIES
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.db import repositories as repo
from app.db.engine import get_session


async def _make_account(session, *, institution_type="chase", account_type="checking", suffix="1"):
    inst = await repo.get_or_create_institution(session, institution_type, institution_type.title())
    acct = await repo.get_or_create_account(
        session, institution_id=inst.id, institution_type=institution_type,
        account_number_masked=f"****{suffix}", account_type=account_type,
    )
    doc = await repo.create_document(
        session, original_filename="s.pdf", stored_filename="s.pdf",
        file_path="/tmp/s.pdf", file_size_bytes=1, mime_type="application/pdf",
        status="parsed", institution_type=institution_type,
    )
    stmt = await repo.create_statement(
        session, document_id=doc.id, institution_id=inst.id, institution_type=institution_type,
        account_id=acct.id, account_type=account_type, statement_type="bank",
        period_start=date(2026, 1, 1), period_end=date(2026, 12, 31),
        extraction_status="success", overall_confidence=0.9, warnings="[]",
    )
    return acct, stmt


async def _add_txn(
    session, account_id, statement_id, *, txn_date, description, amount,
    transaction_type="transfer",
):
    await repo.bulk_create_transactions(session, [{
        "account_id": account_id, "statement_id": statement_id,
        "transaction_date": txn_date, "description": description,
        "amount": amount, "transaction_type": transaction_type,
    }])


# ── Task 1: pure domain module ────────────────────────────────────────────────

def test_goal_type_to_category_matches_savings_categories():
    from app.domain.savings_goals import GOAL_TYPE_TO_CATEGORY, GoalType
    from app.domain.transaction_classification import SAVINGS_CATEGORIES

    assert set(GOAL_TYPE_TO_CATEGORY.values()) == set(SAVINGS_CATEGORIES)
    assert GOAL_TYPE_TO_CATEGORY[GoalType.EMERGENCY_FUND] == "Emergency Fund"
    assert GOAL_TYPE_TO_CATEGORY[GoalType.HOUSE_GOALS] == "House / Goals"
    assert GOAL_TYPE_TO_CATEGORY[GoalType.CHILD_SAVINGS] == "Child Savings"


def test_resolve_category_name_builtin_ignores_override():
    from app.domain.savings_goals import GoalType, resolve_category_name

    # A built-in goal_type always uses the canonical name, even if a caller
    # passes something else — never silently drifts from the classifier.
    assert resolve_category_name(GoalType.EMERGENCY_FUND, "Whatever") == "Emergency Fund"


def test_resolve_category_name_custom_requires_explicit_category():
    from app.domain.savings_goals import GoalType, resolve_category_name

    with pytest.raises(ValueError, match="custom"):
        resolve_category_name(GoalType.CUSTOM, None)
    assert resolve_category_name(GoalType.CUSTOM, "Vacation Fund") == "Vacation Fund"


def test_validate_goal_input_requires_at_least_one_target():
    from app.domain.savings_goals import GoalType, validate_goal_input

    with pytest.raises(ValueError, match="target_amount"):
        validate_goal_input(
            goal_type=GoalType.EMERGENCY_FUND, target_amount=None,
            target_percentage_of_income=None, target_months_of_expenses=None,
        )


def test_validate_goal_input_rejects_months_of_expenses_on_non_emergency_goal():
    from app.domain.savings_goals import GoalType, validate_goal_input

    with pytest.raises(ValueError, match="emergency_fund"):
        validate_goal_input(
            goal_type=GoalType.HOUSE_GOALS, target_amount=Decimal("1000"),
            target_percentage_of_income=None, target_months_of_expenses=Decimal("6"),
        )


def test_validate_goal_input_allows_months_of_expenses_on_emergency_fund():
    from app.domain.savings_goals import GoalType, validate_goal_input

    validate_goal_input(
        goal_type=GoalType.EMERGENCY_FUND, target_amount=Decimal("15000"),
        target_percentage_of_income=None, target_months_of_expenses=Decimal("6"),
    )  # must not raise


def test_validate_goal_input_rejects_negative_targets():
    from app.domain.savings_goals import GoalType, validate_goal_input

    with pytest.raises(ValueError, match="negative"):
        validate_goal_input(
            goal_type=GoalType.EMERGENCY_FUND, target_amount=Decimal("-1"),
            target_percentage_of_income=None, target_months_of_expenses=None,
        )


# ── compute_goal_status ──────────────────────────────────────────────────────

def test_compute_goal_status_not_started():
    from app.domain.savings_goals import GoalStatus, compute_goal_status

    status = compute_goal_status(
        target_amount=Decimal("1000"), current_amount=Decimal("0"),
        most_recent_contribution_date=None, as_of=date(2026, 8, 15),
    )
    assert status == GoalStatus.NOT_STARTED


def test_compute_goal_status_on_track_with_recent_contribution():
    from app.domain.savings_goals import GoalStatus, compute_goal_status

    status = compute_goal_status(
        target_amount=Decimal("1000"), current_amount=Decimal("400"),
        most_recent_contribution_date=date(2026, 8, 1), as_of=date(2026, 8, 15),
    )
    assert status == GoalStatus.ON_TRACK


def test_compute_goal_status_behind_when_stalled():
    from app.domain.savings_goals import GoalStatus, compute_goal_status

    status = compute_goal_status(
        target_amount=Decimal("1000"), current_amount=Decimal("400"),
        most_recent_contribution_date=date(2026, 1, 1), as_of=date(2026, 8, 15),
    )
    assert status == GoalStatus.BEHIND


def test_compute_goal_status_complete_when_target_reached():
    from app.domain.savings_goals import GoalStatus, compute_goal_status

    status = compute_goal_status(
        target_amount=Decimal("1000"), current_amount=Decimal("1200"),
        most_recent_contribution_date=date(2020, 1, 1), as_of=date(2026, 8, 15),
    )
    assert status == GoalStatus.COMPLETE


def test_compute_goal_status_never_complete_without_dollar_target():
    """A goal defined only by target_percentage_of_income (no $ target) can
    never be fabricated as 'complete' — accounting-invariants.md #10."""
    from app.domain.savings_goals import GoalStatus, compute_goal_status

    status = compute_goal_status(
        target_amount=None, current_amount=Decimal("999999"),
        most_recent_contribution_date=date(2026, 8, 10), as_of=date(2026, 8, 15),
    )
    assert status == GoalStatus.ON_TRACK


# ── completeness / completion recommendation ────────────────────────────────

def test_assess_goal_completeness_flags_unparseable_account():
    from app.domain.savings_goals import GoalAccountMapping, assess_goal_completeness

    mapping = GoalAccountMapping(institution_slug="marcus", account_slug="emergency_fund")
    result = assess_goal_completeness(
        [mapping], effective_date=date(2026, 1, 1),
        earliest_observed_transaction_date=date(2026, 1, 1),
        contribution_transaction_count=1,
        unparseable_mappings=[mapping], unknown_mappings=[],
    )
    assert result.all_mapped_accounts_parseable is False
    assert result.is_complete is False
    assert any("parser" in n for n in result.notes)


def test_assess_goal_completeness_flags_effective_date_predating_history():
    from app.domain.savings_goals import GoalAccountMapping, assess_goal_completeness

    mapping = GoalAccountMapping(institution_slug="chase", account_slug="checking")
    result = assess_goal_completeness(
        [mapping], effective_date=date(2000, 1, 1),
        earliest_observed_transaction_date=date(2026, 1, 1),
        contribution_transaction_count=2,
        unparseable_mappings=[], unknown_mappings=[],
    )
    assert result.effective_date_predates_observed_history is True
    assert result.is_complete is False


def test_assess_goal_completeness_honest_when_fully_covered():
    from app.domain.savings_goals import GoalAccountMapping, assess_goal_completeness

    mapping = GoalAccountMapping(institution_slug="chase", account_slug="checking")
    result = assess_goal_completeness(
        [mapping], effective_date=date(2026, 1, 1),
        earliest_observed_transaction_date=date(2025, 1, 1),
        contribution_transaction_count=3,
        unparseable_mappings=[], unknown_mappings=[],
    )
    assert result.is_complete is True
    # The only note is the standing attribution caveat — no data-gap notes.
    assert not any("parser" in n for n in result.notes)
    assert not any("predates" in n for n in result.notes)
    assert not any("unknown catalog entry" in n for n in result.notes)
    assert not any("could not be attributed" in n for n in result.notes)


def test_build_completion_recommendation_only_fires_when_complete():
    from app.domain.savings_goals import GoalStatus, build_completion_recommendation

    not_complete = build_completion_recommendation(
        goal_id="g1", goal_name="Emergency Fund", status=GoalStatus.ON_TRACK,
        target_amount=Decimal("1000"), current_amount=Decimal("400"),
    )
    assert not_complete is None

    complete = build_completion_recommendation(
        goal_id="g1", goal_name="Emergency Fund", status=GoalStatus.COMPLETE,
        target_amount=Decimal("1000"), current_amount=Decimal("1200"),
    )
    assert complete is not None
    assert complete.requires_user_approval is True
    assert complete.goal_id == "g1"


# ── Task 2: DB model ───────────────────────────────────────────────────────────

async def test_savings_goal_model_create_and_read(temp_db):
    from app.db.models import SavingsGoalModel

    async with get_session() as session:
        goal = SavingsGoalModel(
            name="Test Goal", goal_type="emergency_fund", category_name="Emergency Fund",
            target_percentage_of_income="5", effective_date=date(2026, 1, 1),
        )
        session.add(goal)
        await session.flush()
        goal_id = goal.id

    async with get_session() as session:
        loaded = await repo.get_savings_goal(session, goal_id)
        assert loaded.name == "Test Goal"
        assert loaded.category_name == "Emergency Fund"
        assert loaded.account_mappings_json == "[]"


# ── Task 3: repository functions ──────────────────────────────────────────────

async def test_repo_create_list_and_get_savings_goal(temp_db):
    # temp_db's init_db() already seeds the 3 default goals — verify our two
    # new ones are additionally created and orderable, without assuming an
    # otherwise-empty table.
    async with get_session() as session:
        await repo.create_savings_goal(
            session, name="G1", goal_type="emergency_fund", category_name="Emergency Fund",
            target_percentage_of_income="5", account_mappings_json="[]",
            priority=10, effective_date=date(2026, 1, 1),
        )
        await repo.create_savings_goal(
            session, name="G2", goal_type="house_goals", category_name="House / Goals",
            target_percentage_of_income="5", account_mappings_json="[]",
            priority=11, effective_date=date(2026, 1, 1),
        )

    async with get_session() as session:
        goals = await repo.list_savings_goals(session)
        custom_names = [g.name for g in goals if g.name in ("G1", "G2")]
        assert custom_names == ["G1", "G2"]  # priority ascending
        assert len(goals) == 5  # 3 seeded defaults + G1 + G2


async def test_repo_get_savings_goal_raises_for_unknown_id(temp_db):
    from app.domain.errors import EntityNotFoundError

    async with get_session() as session:
        with pytest.raises(EntityNotFoundError):
            await repo.get_savings_goal(session, "does-not-exist")


async def test_repo_get_earliest_transaction_date(temp_db):
    async with get_session() as session:
        assert await repo.get_earliest_transaction_date(session) is None

        acct, stmt = await _make_account(session)
        await _add_txn(
            session, acct.id, stmt.id, txn_date=date(2026, 3, 5),
            description="TRANSFER TO MARCUS SAVINGS EMERGENCY FUND", amount="-500.00",
        )
        await _add_txn(
            session, acct.id, stmt.id, txn_date=date(2026, 1, 10),
            description="TRANSFER TO MARCUS SAVINGS EMERGENCY FUND", amount="-200.00",
        )

    async with get_session() as session:
        earliest = await repo.get_earliest_transaction_date(session)
        assert earliest == date(2026, 1, 10)


# ── Task 4: service-layer create_goal validation ────────────────────────────

async def test_service_create_goal_persists_and_resolves_category(temp_db):
    from app.domain.savings_goals import GoalType
    from app.services import savings_goals as service

    async with get_session() as session:
        goal = await service.create_goal(
            session, name="My Emergency Fund", goal_type=GoalType.EMERGENCY_FUND,
            effective_date=date(2026, 1, 1), target_percentage_of_income=Decimal("5"),
        )
        assert goal.category_name == "Emergency Fund"


async def test_service_create_goal_rejects_missing_target(temp_db):
    from app.domain.errors import SavingsGoalValidationError
    from app.domain.savings_goals import GoalType
    from app.services import savings_goals as service

    async with get_session() as session:
        with pytest.raises(SavingsGoalValidationError):
            await service.create_goal(
                session, name="No target", goal_type=GoalType.EMERGENCY_FUND,
                effective_date=date(2026, 1, 1),
            )


async def test_service_create_custom_goal_requires_category_name(temp_db):
    from app.domain.errors import SavingsGoalValidationError
    from app.domain.savings_goals import GoalType
    from app.services import savings_goals as service

    async with get_session() as session:
        with pytest.raises(SavingsGoalValidationError):
            await service.create_goal(
                session, name="Vacation", goal_type=GoalType.CUSTOM,
                effective_date=date(2026, 1, 1), target_amount=Decimal("3000"),
            )


# ── Task 5: default goal seeding ──────────────────────────────────────────────

async def test_default_goals_seed_on_init_at_5_5_5(temp_db):
    from app.domain.transaction_classification import SAVINGS_CATEGORIES

    async with get_session() as session:
        goals = await repo.list_savings_goals(session)

    assert len(goals) == 3
    assert {g.category_name for g in goals} == set(SAVINGS_CATEGORIES)
    for g in goals:
        assert g.target_percentage_of_income == "5"


async def test_seed_default_goals_is_idempotent(temp_db):
    from app.services.savings_goals import seed_default_goals_if_missing

    await seed_default_goals_if_missing()  # temp_db already seeded once via init_db()

    async with get_session() as session:
        goals = await repo.list_savings_goals(session)
    assert len(goals) == 3


# ── Task 6: progress computation ──────────────────────────────────────────────

async def test_one_account_backs_multiple_goals(temp_db):
    """Two distinct goals may both list the same account_mapping."""
    from app.domain.savings_goals import GoalAccountMapping, GoalType
    from app.services import savings_goals as service

    mapping = GoalAccountMapping(institution_slug="marcus", account_slug="emergency_fund")
    async with get_session() as session:
        g1 = await service.create_goal(
            session, name="Emergency Buffer", goal_type=GoalType.EMERGENCY_FUND,
            effective_date=date(2026, 1, 1), target_amount=Decimal("10000"),
            account_mappings=[mapping],
        )
        g2 = await service.create_goal(
            session, name="Rainy Day", goal_type=GoalType.CUSTOM, category_name="Rainy Day",
            effective_date=date(2026, 1, 1), target_amount=Decimal("2000"),
            account_mappings=[mapping],
        )

    async with get_session() as session:
        p1 = await service.get_goal_progress(session, g1.id)
        p2 = await service.get_goal_progress(session, g2.id)
    assert p1.account_mappings == [mapping]
    assert p2.account_mappings == [mapping]


async def test_one_goal_spans_multiple_accounts(temp_db):
    from app.domain.savings_goals import GoalAccountMapping, GoalType
    from app.services import savings_goals as service

    mappings = [
        GoalAccountMapping(institution_slug="marcus", account_slug="emergency_fund"),
        GoalAccountMapping(institution_slug="529", account_slug="college_savings"),
    ]
    async with get_session() as session:
        goal = await service.create_goal(
            session, name="Combined Goal", goal_type=GoalType.CUSTOM,
            category_name="Combined", effective_date=date(2026, 1, 1),
            target_amount=Decimal("5000"), account_mappings=mappings,
        )

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal.id)
    assert len(progress.account_mappings) == 2
    # Neither Marcus nor 529 has a parser — both flagged, never silently ignored.
    assert progress.data_completeness.all_mapped_accounts_parseable is False
    assert len(progress.data_completeness.unparseable_account_mappings) == 2


async def test_goal_progress_not_started_with_no_transactions(temp_db):
    from app.domain.savings_goals import GoalStatus, GoalType
    from app.services import savings_goals as service

    async with get_session() as session:
        goal = await service.create_goal(
            session, name="Fresh Goal", goal_type=GoalType.EMERGENCY_FUND,
            effective_date=date(2026, 1, 1), target_amount=Decimal("6000"),
        )

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal.id, as_of=date(2026, 8, 15))
    assert progress.current_amount == "0.00"
    assert progress.current_amount_source == "computed_from_contributions"
    assert progress.status == GoalStatus.NOT_STARTED
    assert progress.completion_recommendation is None


async def test_goal_progress_on_track_then_complete_with_realistic_contributions(temp_db):
    from app.domain.savings_goals import GoalStatus, GoalType
    from app.services import savings_goals as service

    async with get_session() as session:
        goal = await service.create_goal(
            session, name="Emergency Fund", goal_type=GoalType.EMERGENCY_FUND,
            effective_date=date(2026, 1, 1), target_amount=Decimal("1000"),
        )
        goal_id = goal.id

        acct, stmt = await _make_account(session)
        # Recent contribution (within the 60-day stall window of as_of).
        await _add_txn(
            session, acct.id, stmt.id, txn_date=date(2026, 7, 20),
            description="TRANSFER TO MARCUS SAVINGS EMERGENCY FUND", amount="-400.00",
        )

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal_id, as_of=date(2026, 8, 15))
    assert progress.current_amount == "400.00"
    assert progress.status == GoalStatus.ON_TRACK
    assert progress.completion_recommendation is None

    # Top it up to reach the target.
    async with get_session() as session:
        await _add_txn(
            session, acct.id, stmt.id, txn_date=date(2026, 8, 1),
            description="TRANSFER TO MARCUS SAVINGS EMERGENCY FUND", amount="-600.00",
        )

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal_id, as_of=date(2026, 8, 15))
    assert progress.current_amount == "1000.00"
    assert progress.status == GoalStatus.COMPLETE
    assert progress.completion_recommendation is not None
    assert progress.completion_recommendation.requires_user_approval is True


async def test_goal_progress_behind_when_contributions_stalled(temp_db):
    from app.domain.savings_goals import GoalStatus, GoalType
    from app.services import savings_goals as service

    async with get_session() as session:
        goal = await service.create_goal(
            session, name="House Fund", goal_type=GoalType.HOUSE_GOALS,
            effective_date=date(2026, 1, 1), target_amount=Decimal("50000"),
        )
        goal_id = goal.id

        acct, stmt = await _make_account(session, suffix="9")
        # Only contribution was 5 months before as_of — well past the 60-day
        # stall window.
        await _add_txn(
            session, acct.id, stmt.id, txn_date=date(2026, 2, 1),
            description="TRANSFER TO HOUSE FUND", amount="-1000.00",
        )

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal_id, as_of=date(2026, 8, 15))
    assert progress.current_amount == "1000.00"
    assert progress.status == GoalStatus.BEHIND


async def test_emergency_fund_target_months_of_expenses_roundtrip(temp_db):
    from app.domain.savings_goals import GoalType
    from app.services import savings_goals as service

    async with get_session() as session:
        goal = await service.create_goal(
            session, name="6mo Emergency Fund", goal_type=GoalType.EMERGENCY_FUND,
            effective_date=date(2026, 1, 1), target_amount=Decimal("18000"),
            target_months_of_expenses=Decimal("6"),
        )
        goal_id = goal.id

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal_id)
    assert progress.target_months_of_expenses == "6"


async def test_goal_progress_flags_effective_date_predating_observed_history(temp_db):
    from app.domain.savings_goals import GoalType
    from app.services import savings_goals as service

    async with get_session() as session:
        acct, stmt = await _make_account(session, suffix="7")
        await _add_txn(
            session, acct.id, stmt.id, txn_date=date(2026, 6, 1),
            description="TRANSFER TO MARCUS SAVINGS EMERGENCY FUND", amount="-100.00",
        )

    async with get_session() as session:
        # effective_date long before the earliest ingested transaction.
        goal = await service.create_goal(
            session, name="Old Goal", goal_type=GoalType.EMERGENCY_FUND,
            effective_date=date(2020, 1, 1), target_amount=Decimal("5000"),
        )
        goal_id = goal.id

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal_id, as_of=date(2026, 8, 15))
    assert progress.data_completeness.effective_date_predates_observed_history is True
    assert progress.data_completeness.is_complete is False
    assert any("predates" in n for n in progress.data_completeness.notes)


async def test_goal_progress_completion_recommendation_never_auto_redirects(temp_db):
    """The recommendation is descriptive only — it never mutates the plan or
    any goal/account, and only ever appears when the goal is actually complete."""
    from app.domain.savings_goals import GoalStatus, GoalType
    from app.services import savings_goals as service

    async with get_session() as session:
        goal = await service.create_goal(
            session, name="Small Goal", goal_type=GoalType.CHILD_SAVINGS,
            effective_date=date(2026, 1, 1), target_amount=Decimal("500"),
        )
        goal_id = goal.id

        acct, stmt = await _make_account(session, suffix="5")
        await _add_txn(
            session, acct.id, stmt.id, txn_date=date(2026, 8, 1),
            description="529 COLLEGE SAVINGS CONTRIBUTION", amount="-600.00",
        )

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal_id, as_of=date(2026, 8, 15))
    assert progress.status == GoalStatus.COMPLETE
    rec = progress.completion_recommendation
    assert rec is not None
    assert rec.requires_user_approval is True
    assert rec.suggested_action == "review_plan_reallocation"

    # No side effect: re-fetching the goal shows the same target_amount —
    # nothing was silently redirected/mutated.
    async with get_session() as session:
        raw = await repo.get_savings_goal(session, goal_id)
    assert raw.target_amount == "500"


async def test_goal_progress_window_excludes_contributions_outside_effective_date_and_as_of(
    temp_db,
):
    """The cumulative window is inclusive [effective_date, as_of] — money moved
    before the goal existed, or after the as-of snapshot, must not appear."""
    from app.domain.savings_goals import GoalType
    from app.services import savings_goals as service

    async with get_session() as session:
        goal = await service.create_goal(
            session, name="Windowed EF", goal_type=GoalType.EMERGENCY_FUND,
            effective_date=date(2026, 4, 1), target_amount=Decimal("10000"),
        )
        goal_id = goal.id

        acct, stmt = await _make_account(session, suffix="21")
        for txn_date, amount in (
            (date(2026, 3, 31), "-100.00"),   # before effective_date
            (date(2026, 4, 1), "-250.00"),    # inclusive lower bound
            (date(2026, 6, 30), "-250.00"),   # inclusive upper bound
            (date(2026, 7, 1), "-999.00"),    # after as_of
        ):
            await _add_txn(
                session, acct.id, stmt.id, txn_date=txn_date,
                description="TRANSFER TO MARCUS SAVINGS EMERGENCY FUND", amount=amount,
            )

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal_id, as_of=date(2026, 6, 30))
    assert progress.current_amount == "500.00"
    assert progress.data_completeness.contribution_transaction_count == 2


async def test_goal_progress_flags_unknown_catalog_mapping(temp_db):
    from app.domain.savings_goals import GoalAccountMapping, GoalType
    from app.services import savings_goals as service

    bogus = GoalAccountMapping(institution_slug="not_a_bank", account_slug="nope")
    async with get_session() as session:
        goal = await service.create_goal(
            session, name="Bad Mapping", goal_type=GoalType.HOUSE_GOALS,
            effective_date=date(2026, 1, 1), target_amount=Decimal("1000"),
            account_mappings=[bogus],
        )
        goal_id = goal.id

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal_id, as_of=date(2026, 8, 15))
    assert progress.data_completeness.unknown_account_mappings == [bogus]
    assert progress.data_completeness.is_complete is False
    assert any("unknown catalog entry" in n for n in progress.data_completeness.notes)


async def test_goal_progress_reports_savings_it_cannot_attribute_to_any_goal(temp_db):
    """A generic "TRANSFER TO MARCUS SAVINGS" line carries no sub-goal keyword,
    so it lands in no goal's category. That money is real — it must be
    surfaced as a data gap, never silently dropped."""
    from app.domain.savings_goals import GoalType
    from app.services import savings_goals as service

    async with get_session() as session:
        goal = await service.create_goal(
            session, name="EF", goal_type=GoalType.EMERGENCY_FUND,
            effective_date=date(2026, 1, 1), target_amount=Decimal("10000"),
        )
        goal_id = goal.id

        acct, stmt = await _make_account(session, suffix="22")
        await _add_txn(
            session, acct.id, stmt.id, txn_date=date(2026, 8, 1),
            description="TRANSFER TO MARCUS SAVINGS EMERGENCY FUND", amount="-300.00",
        )
        await _add_txn(
            session, acct.id, stmt.id, txn_date=date(2026, 8, 2),
            description="ONLINE TRANSFER TO SAVINGS ACCOUNT", amount="-1200.00",
        )

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal_id, as_of=date(2026, 8, 15))
    assert progress.current_amount == "300.00"
    completeness = progress.data_completeness
    assert completeness.unattributed_savings_contribution_count == 1
    assert completeness.unattributed_savings_contribution_amount == "1200.00"
    assert completeness.is_complete is False


async def test_percentage_goal_reports_dollar_target_variance_and_behind_status(temp_db):
    """Dollar-first Target/Actual/Variance for a percentage-of-income goal,
    derived only from observed income — and a plan shortfall reads `behind`
    even though the contribution is recent."""
    from app.domain.savings_goals import GoalStatus, GoalType, TargetAmountSource
    from app.services import savings_goals as service

    async with get_session() as session:
        goal = await service.create_goal(
            session, name="EF 5%", goal_type=GoalType.EMERGENCY_FUND,
            effective_date=date(2026, 1, 1), target_percentage_of_income=Decimal("5"),
        )
        goal_id = goal.id

        acct, stmt = await _make_account(session, suffix="23")
        await _add_txn(
            session, acct.id, stmt.id, txn_date=date(2026, 8, 1),
            description="PAYROLL DIRECT DEPOSIT", amount="10000.00",
            transaction_type="deposit",
        )
        await _add_txn(
            session, acct.id, stmt.id, txn_date=date(2026, 8, 2),
            description="TRANSFER TO MARCUS SAVINGS EMERGENCY FUND", amount="-100.00",
        )

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal_id, as_of=date(2026, 8, 15))
    assert progress.plannable_income == "10000.00"
    assert progress.target_amount_effective == "500.00"
    assert progress.target_amount_source == (
        TargetAmountSource.DERIVED_FROM_PERCENTAGE_OF_OBSERVED_INCOME
    )
    assert progress.variance_amount == "-400.00"
    assert progress.status == GoalStatus.BEHIND


async def test_percentage_goal_without_observed_income_has_no_fabricated_target(temp_db):
    from app.domain.savings_goals import GoalType, TargetAmountSource
    from app.services import savings_goals as service

    async with get_session() as session:
        goal = await service.create_goal(
            session, name="EF 5% no income", goal_type=GoalType.EMERGENCY_FUND,
            effective_date=date(2026, 1, 1), target_percentage_of_income=Decimal("5"),
        )
        goal_id = goal.id

        acct, stmt = await _make_account(session, suffix="24")
        await _add_txn(
            session, acct.id, stmt.id, txn_date=date(2026, 8, 2),
            description="TRANSFER TO MARCUS SAVINGS EMERGENCY FUND", amount="-100.00",
        )

    async with get_session() as session:
        progress = await service.get_goal_progress(session, goal_id, as_of=date(2026, 8, 15))
    assert progress.plannable_income == "0.00"
    assert progress.target_amount_effective is None
    assert progress.target_amount_source == TargetAmountSource.NONE
    assert progress.variance_amount is None
    assert progress.data_completeness.percentage_target_income_observed is False


async def test_goal_progress_on_empty_database_is_reported_incomplete(temp_db):
    """$0 with no ingested data must not read as "complete, nothing saved"."""
    from app.services import savings_goals as service

    async with get_session() as session:
        progresses = await service.list_goal_progress(session, as_of=date(2026, 8, 15))

    for progress in progresses:
        assert progress.current_amount == "0.00"
        assert progress.data_completeness.any_observed_transaction_history is False
        assert progress.data_completeness.is_complete is False


async def test_list_goal_progress_returns_all_goals(temp_db):
    from app.services import savings_goals as service

    async with get_session() as session:
        progresses = await service.list_goal_progress(session, as_of=date(2026, 8, 15))
    assert len(progresses) == 3  # the seeded defaults


# ── Task 7: API layer ─────────────────────────────────────────────────────────

async def test_api_list_goals_returns_seeded_defaults(temp_db):
    from app.api.savings_goals import list_goals

    result = await list_goals()
    assert len(result) == 3


def test_savings_goals_router_is_mounted_on_the_app():
    """Guards the router registration in app.main.create_app — without it the
    endpoints exist but are unreachable."""
    from app.main import create_app

    paths = {route.path for route in create_app().routes}
    assert "/api/v1/savings-goals" in paths
    assert "/api/v1/savings-goals/{goal_id}" in paths


async def test_api_get_goal_404_for_unknown_id(temp_db):
    from fastapi import HTTPException

    from app.api.savings_goals import get_goal

    with pytest.raises(HTTPException) as exc_info:
        await get_goal("does-not-exist")
    assert exc_info.value.status_code == 404


async def test_api_create_goal_success(temp_db):
    from app.api.savings_goals import SavingsGoalCreateRequest, create_goal
    from app.domain.savings_goals import GoalType

    body = SavingsGoalCreateRequest(
        name="Vacation Fund", goal_type=GoalType.CUSTOM, category_name="Vacation",
        effective_date=date(2026, 1, 1), target_amount="3000",
    )
    result = await create_goal(body)
    assert result.name == "Vacation Fund"
    assert result.category_name == "Vacation"


async def test_api_create_goal_invalid_returns_422(temp_db):
    from fastapi import HTTPException

    from app.api.savings_goals import SavingsGoalCreateRequest, create_goal
    from app.domain.savings_goals import GoalType

    body = SavingsGoalCreateRequest(
        name="No target", goal_type=GoalType.EMERGENCY_FUND, effective_date=date(2026, 1, 1),
    )
    with pytest.raises(HTTPException) as exc_info:
        await create_goal(body)
    assert exc_info.value.status_code == 422


async def test_api_create_goal_rejects_non_numeric_target_with_422(temp_db):
    """A malformed money string is a client error, not a 500."""
    from fastapi import HTTPException

    from app.api.savings_goals import SavingsGoalCreateRequest, create_goal
    from app.domain.savings_goals import GoalType

    body = SavingsGoalCreateRequest(
        name="Bad target", goal_type=GoalType.EMERGENCY_FUND,
        effective_date=date(2026, 1, 1), target_amount="not-a-number",
    )
    with pytest.raises(HTTPException) as exc_info:
        await create_goal(body)
    assert exc_info.value.status_code == 422


async def test_api_create_goal_rejects_months_of_expenses_on_non_emergency_goal(temp_db):
    from fastapi import HTTPException

    from app.api.savings_goals import SavingsGoalCreateRequest, create_goal
    from app.domain.savings_goals import GoalType

    body = SavingsGoalCreateRequest(
        name="House", goal_type=GoalType.HOUSE_GOALS, effective_date=date(2026, 1, 1),
        target_amount="50000", target_months_of_expenses="6",
    )
    with pytest.raises(HTTPException) as exc_info:
        await create_goal(body)
    assert exc_info.value.status_code == 422
