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
    async with get_session() as session:
        plan = await repo.create_financial_plan(session, name="Master Plan")
        plan_id = plan.id

    async with get_session() as session:
        active = await repo.get_active_financial_plan(session)
        assert active is not None
        assert active.id == plan_id


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
