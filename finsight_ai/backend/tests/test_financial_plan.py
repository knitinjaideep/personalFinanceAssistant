"""
Tests for the Financial Plan domain model: schema, service layer, and API.

Covers (see docs/FINANCIAL_PLAN_MODEL.md for the full model description):
  - default plan seeds on first boot and totals 100%
  - savings/investments suballocations total their parent's share
  - effective-dated version resolution, including historical lookups
  - invalid percentages are rejected
  - duplicate/overlapping effective dates are rejected
  - editing a future version never rewrites history; editing an
    active/past version is refused
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import select

from app.db import repositories as repo
from app.db.engine import get_session


# ── Task 1: models, errors, entities ──────────────────────────────────────────

async def test_financial_plan_models_create_and_relate(temp_db):
    from app.db.models import (
        FinancialPlanModel,
        FinancialPlanVersionModel,
        PlanAllocationModel,
        PlanSuballocationModel,
    )

    async with get_session() as session:
        plan = FinancialPlanModel(name="Test Plan")
        session.add(plan)
        await session.flush()

        version = FinancialPlanVersionModel(
            plan_id=plan.id, version_number=1, effective_from=date(2026, 8, 1),
        )
        session.add(version)
        await session.flush()

        savings = PlanAllocationModel(
            plan_version_id=version.id, bucket_name="savings", percentage="15", sort_order=2,
        )
        session.add(savings)
        await session.flush()

        sub = PlanSuballocationModel(
            allocation_id=savings.id, name="Emergency Fund", percentage="5", sort_order=0,
        )
        session.add(sub)
        await session.flush()

        plan_id, version_id, alloc_id, sub_id = plan.id, version.id, savings.id, sub.id

    async with get_session() as session:
        loaded_plan = (await session.execute(
            select(FinancialPlanModel).where(FinancialPlanModel.id == plan_id)
        )).scalar_one()
        assert loaded_plan.name == "Test Plan"
        assert loaded_plan.is_active is True

        loaded_version = (await session.execute(
            select(FinancialPlanVersionModel).where(FinancialPlanVersionModel.id == version_id)
        )).scalar_one()
        assert loaded_version.plan_id == plan_id
        assert loaded_version.effective_from == date(2026, 8, 1)

        loaded_alloc = (await session.execute(
            select(PlanAllocationModel).where(PlanAllocationModel.id == alloc_id)
        )).scalar_one()
        assert loaded_alloc.bucket_name == "savings"
        assert loaded_alloc.percentage == "15"

        loaded_sub = (await session.execute(
            select(PlanSuballocationModel).where(PlanSuballocationModel.id == sub_id)
        )).scalar_one()
        assert loaded_sub.allocation_id == alloc_id
        assert loaded_sub.percentage == "5"


def test_plan_errors_are_coral_errors():
    from app.domain.errors import (
        CoralError,
        DuplicateEffectiveDateError,
        PlanValidationError,
        PlanVersionImmutableError,
    )

    assert issubclass(PlanValidationError, CoralError)
    assert issubclass(PlanVersionImmutableError, CoralError)
    assert issubclass(DuplicateEffectiveDateError, CoralError)


def test_allocation_input_coerces_percentage_to_decimal():
    from app.domain.entities import AllocationInput, SuballocationInput

    alloc = AllocationInput(
        bucket_name="savings", percentage="15",
        suballocations=[SuballocationInput(name="Emergency Fund", percentage="5")],
    )
    assert alloc.percentage == Decimal("15")
    assert alloc.suballocations[0].percentage == Decimal("5")


# ── Task 2: repository functions ──────────────────────────────────────────────

async def test_repo_create_and_get_active_plan(temp_db):
    # Note: seeding creates the default "Master Plan" during init_db(),
    # so we verify it exists and is active, rather than creating a duplicate.
    async with get_session() as session:
        active = await repo.get_active_financial_plan(session)
        assert active is not None
        assert active.name == "Master Plan"
        assert active.is_active is True


async def test_repo_version_and_allocation_crud(temp_db):
    async with get_session() as session:
        plan = await repo.create_financial_plan(session, name="P")
        version = await repo.create_plan_version(
            session, plan_id=plan.id, version_number=1, effective_from=date(2026, 8, 1),
        )
        alloc = await repo.create_allocation(
            session, plan_version_id=version.id, bucket_name="needs", percentage="50", sort_order=0,
        )
        await repo.create_suballocation(
            session, allocation_id=alloc.id, name="Rent", percentage="30", sort_order=0,
        )
        version_id, alloc_id = version.id, alloc.id

    async with get_session() as session:
        allocations = await repo.get_allocations_for_version(session, version_id)
        assert len(allocations) == 1
        assert allocations[0].bucket_name == "needs"

        subs = await repo.get_suballocations_for_allocation(session, alloc_id)
        assert len(subs) == 1
        assert subs[0].name == "Rent"

        fetched_version = await repo.get_plan_version(session, version_id)
        assert fetched_version.id == version_id


async def test_repo_get_plan_version_raises_for_unknown_id(temp_db):
    from app.domain.errors import EntityNotFoundError

    async with get_session() as session:
        with pytest.raises(EntityNotFoundError):
            await repo.get_plan_version(session, "does-not-exist")


async def test_repo_get_version_by_effective_date_and_latest_for_date(temp_db):
    async with get_session() as session:
        plan = await repo.create_financial_plan(session, name="P")
        v1 = await repo.create_plan_version(
            session, plan_id=plan.id, version_number=1, effective_from=date(2026, 1, 1),
        )
        v2 = await repo.create_plan_version(
            session, plan_id=plan.id, version_number=2, effective_from=date(2027, 1, 1),
        )
        plan_id, v1_id, v2_id = plan.id, v1.id, v2.id

    async with get_session() as session:
        exact = await repo.get_version_by_effective_date(session, plan_id, date(2027, 1, 1))
        assert exact.id == v2_id

        missing = await repo.get_version_by_effective_date(session, plan_id, date(2026, 6, 1))
        assert missing is None

        latest_mid_2026 = await repo.get_latest_version_for_date(session, plan_id, date(2026, 6, 1))
        assert latest_mid_2026.id == v1_id

        latest_2027 = await repo.get_latest_version_for_date(session, plan_id, date(2027, 6, 1))
        assert latest_2027.id == v2_id

        before_any = await repo.get_latest_version_for_date(session, plan_id, date(2025, 1, 1))
        assert before_any is None

        assert await repo.get_max_version_number(session, plan_id) == 2

        versions = await repo.list_versions_for_plan(session, plan_id)
        assert [v.id for v in versions] == [v2_id, v1_id]  # newest first


async def test_repo_delete_allocations_for_version_cascades_suballocations(temp_db):
    async with get_session() as session:
        plan = await repo.create_financial_plan(session, name="P")
        version = await repo.create_plan_version(
            session, plan_id=plan.id, version_number=1, effective_from=date(2026, 1, 1),
        )
        alloc = await repo.create_allocation(
            session, plan_version_id=version.id, bucket_name="savings", percentage="15", sort_order=0,
        )
        await repo.create_suballocation(
            session, allocation_id=alloc.id, name="Emergency Fund", percentage="15", sort_order=0,
        )
        version_id, alloc_id = version.id, alloc.id

    async with get_session() as session:
        await repo.delete_allocations_for_version(session, version_id)

    async with get_session() as session:
        assert await repo.get_allocations_for_version(session, version_id) == []
        assert await repo.get_suballocations_for_allocation(session, alloc_id) == []


# ── Task 3: validate_plan ──────────────────────────────────────────────────────

from app.domain.entities import AllocationInput, SuballocationInput
from app.domain.errors import PlanValidationError
from app.services import financial_plan as plan_service


def _default_allocations() -> list[AllocationInput]:
    return [
        AllocationInput(bucket_name="needs", percentage="50"),
        AllocationInput(bucket_name="wants", percentage="20"),
        AllocationInput(bucket_name="savings", percentage="15", suballocations=[
            SuballocationInput(name="Emergency Fund", percentage="5"),
            SuballocationInput(name="House / Goals", percentage="5"),
            SuballocationInput(name="Child Savings", percentage="5"),
        ]),
        AllocationInput(bucket_name="investments", percentage="15", suballocations=[
            SuballocationInput(name="401(k)", percentage="6"),
            SuballocationInput(name="Roth IRA", percentage="4"),
            SuballocationInput(name="ESPP", percentage="3"),
            SuballocationInput(name="Taxable Brokerage", percentage="2"),
        ]),
    ]


def test_validate_plan_accepts_the_default_allocation():
    plan_service.validate_plan(_default_allocations())  # must not raise


def test_validate_plan_rejects_total_not_100():
    allocations = _default_allocations()
    allocations[0].percentage = Decimal("40")  # total now 90
    with pytest.raises(PlanValidationError, match="100"):
        plan_service.validate_plan(allocations)


def test_validate_plan_rejects_suballocation_mismatch():
    allocations = _default_allocations()
    allocations[2].suballocations[0].percentage = Decimal("10")  # savings subs now sum to 20
    with pytest.raises(PlanValidationError, match="savings"):
        plan_service.validate_plan(allocations)


def test_validate_plan_rejects_negative_percentage():
    allocations = _default_allocations()
    allocations[0].percentage = Decimal("-10")
    with pytest.raises(PlanValidationError, match="negative"):
        plan_service.validate_plan(allocations)


def test_validate_plan_rejects_duplicate_bucket_names():
    allocations = _default_allocations()
    allocations.append(AllocationInput(bucket_name="needs", percentage="0"))
    with pytest.raises(PlanValidationError, match="Duplicate"):
        plan_service.validate_plan(allocations)


def test_validate_plan_rejects_duplicate_suballocation_names():
    allocations = _default_allocations()
    allocations[2].suballocations.append(SuballocationInput(name="Emergency Fund", percentage="0"))
    with pytest.raises(PlanValidationError, match="Duplicate"):
        plan_service.validate_plan(allocations)


def test_validate_plan_allows_custom_bucket_if_total_still_100():
    allocations = [
        AllocationInput(bucket_name="needs", percentage="45"),
        AllocationInput(bucket_name="wants", percentage="20"),
        AllocationInput(bucket_name="savings", percentage="15"),
        AllocationInput(bucket_name="investments", percentage="15"),
        AllocationInput(bucket_name="giving", percentage="5"),
    ]
    plan_service.validate_plan(allocations)  # must not raise


# ── Task 4: default plan seeding ──────────────────────────────────────────────

async def test_default_plan_seeds_on_init_and_totals_100(temp_db):
    async with get_session() as session:
        plan = await repo.get_active_financial_plan(session)
        assert plan is not None
        assert plan.name == "Master Plan"

        version = await repo.get_latest_version_for_date(session, plan.id, date.today())
        assert version is not None

        allocations = await repo.get_allocations_for_version(session, version.id)
        total = sum(Decimal(a.percentage) for a in allocations)
        assert total == Decimal("100")


async def test_default_plan_savings_and_investments_subtotals(temp_db):
    async with get_session() as session:
        plan = await repo.get_active_financial_plan(session)
        version = await repo.get_latest_version_for_date(session, plan.id, date.today())
        allocations = {
            a.bucket_name: a for a in await repo.get_allocations_for_version(session, version.id)
        }

        savings_subs = await repo.get_suballocations_for_allocation(session, allocations["savings"].id)
        assert sum(Decimal(s.percentage) for s in savings_subs) == Decimal("15")
        assert Decimal(allocations["savings"].percentage) == Decimal("15")

        inv_subs = await repo.get_suballocations_for_allocation(session, allocations["investments"].id)
        assert sum(Decimal(s.percentage) for s in inv_subs) == Decimal("15")
        assert Decimal(allocations["investments"].percentage) == Decimal("15")


async def test_seed_is_idempotent_and_does_not_duplicate(temp_db):
    from app.db.models import FinancialPlanModel

    # temp_db's init_db() already seeded once; calling again must be a no-op.
    await plan_service.seed_default_plan_if_missing()

    async with get_session() as session:
        result = await session.execute(select(FinancialPlanModel))
        assert len(result.scalars().all()) == 1


# ── Task 5: get_plan_for_date / get_current_plan ──────────────────────────────

async def test_get_current_plan_returns_seeded_default(temp_db):
    async with get_session() as session:
        snapshot = await plan_service.get_current_plan(session)
    assert snapshot is not None
    bucket_names = {a.bucket_name for a in snapshot.allocations}
    assert bucket_names == {"needs", "wants", "savings", "investments"}


async def test_get_plan_for_date_before_epoch_returns_none(temp_db):
    async with get_session() as session:
        snapshot = await plan_service.get_plan_for_date(session, date(1999, 1, 1))
    assert snapshot is None


async def test_get_plan_for_date_resolves_historical_version_correctly(temp_db):
    # Seed a second version starting 2027-01-01, directly via the repo layer
    # (create_plan_version the *service* function doesn't exist until Task 6).
    async with get_session() as session:
        plan = await repo.get_active_financial_plan(session)
        v2 = await repo.create_plan_version(
            session, plan_id=plan.id, version_number=2, effective_from=date(2027, 1, 1),
        )
        await repo.create_allocation(
            session, plan_version_id=v2.id, bucket_name="needs", percentage="60", sort_order=0,
        )

    async with get_session() as session:
        # August 2026 must still resolve to the ORIGINAL default plan (V1).
        aug_2026 = await plan_service.get_plan_for_date(session, date(2026, 8, 15))
        needs = next(a for a in aug_2026.allocations if a.bucket_name == "needs")
        assert needs.percentage == "50"

        # Any date on/after 2027-01-01 resolves to V2.
        jan_2027 = await plan_service.get_plan_for_date(session, date(2027, 3, 1))
        needs_v2 = next(a for a in jan_2027.allocations if a.bucket_name == "needs")
        assert needs_v2.percentage == "60"
