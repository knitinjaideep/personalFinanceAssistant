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
