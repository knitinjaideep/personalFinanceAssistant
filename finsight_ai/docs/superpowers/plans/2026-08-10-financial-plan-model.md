# Financial Plan Domain Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Coral a versioned, effective-dated model of the user's *intended* financial allocation (Needs/Wants/Savings/Investments + nested breakdowns), stored in SQLite via the existing SQLModel patterns, seeded with a sensible default, exposed through a pure service API and a small set of FastAPI endpoints — with no changes to chat behavior, parsing, or ingestion.

**Architecture:** Four new SQLModel tables (`financial_plans` → `financial_plan_versions` → `plan_allocations` → `plan_suballocations`, a fixed 2-level tree) added to `app/db/models.py`. A pure-Python service module (`app/services/financial_plan.py`) provides validation, resolution-by-date, and version creation/editing, talking to the DB only through new functions in `app/db/repositories.py` (never raw SQL from the service). A single-master-plan is auto-seeded on first boot. A thin FastAPI router (`app/api/financial_plan.py`) exposes the service.

**Tech Stack:** Python 3.13, SQLModel + SQLAlchemy async (aiosqlite), FastAPI, Pydantic v2, pytest + pytest-asyncio. No new dependencies.

## Global Constraints

- Keep SQLite. No Postgres/Supabase, no new persistence framework.
- No Alembic — this repo has no `alembic.ini` wired up; new tables are picked up automatically by `SQLModel.metadata.create_all()` in `app/db/engine.py::init_db()`. Only *column additions to existing tables* need an entry in `app/db/engine.py`'s `_COLUMN_MIGRATIONS` list — brand-new tables need nothing there.
- Follow existing naming/typing conventions exactly: `*Model` class names, plural-snake `__tablename__`, `str` UUID primary keys via the existing `_uuid()` factory in `app/db/models.py`, `datetime` timestamps via the existing `_now()` factory, percentage/rate values stored as `str`-encoded `Decimal` (matching `apr`, `management_fee_rate` elsewhere) — never `float`.
- Service layer (`app/services/financial_plan.py`) must have zero FastAPI imports. Functions take an `AsyncSession` as their first parameter (mirroring `app/db/repositories.py`), except `seed_default_plan_if_missing()` which opens its own session (mirroring `app/services/availability.py`).
- Do not modify `app/services/chat_router.py`, `app/chat/*`, `app/services/sql_query.py`, or any other chat/streaming code path.
- Do not modify any parser (`app/parsers/**`) or ingestion code (`app/services/ingestion.py`), and do not touch `transactions`/`fees`/`holdings`/`balance_snapshots` tables.
- Default plan values (exact, from the product spec):
  - Needs 50%, Wants 20%, Savings 15%, Investments 15% (sums to 100%)
  - Savings breakdown: Emergency Fund 5%, House / Goals 5%, Child Savings 5% (sums to 15%)
  - Investments breakdown: 401(k) 6%, Roth IRA 4%, ESPP 3%, Taxable Brokerage 2% (sums to 15%)
- Suballocation percentages are of the **total plan**, not of the parent bucket's share (Emergency Fund = 5% of the whole plan, not 5% of Savings' 15%).
- All tests run via the existing `temp_db` pytest fixture in `backend/tests/conftest.py` (isolated file-backed SQLite per test) — never touch the developer's real `finsight.db`.
- Run tests from the `backend/` directory: `cd backend && .venv/bin/python -m pytest tests/test_financial_plan.py -v` (adjust venv path if different; check with `which pytest` inside an activated venv, or use `.venv/bin/pytest` directly as shown).

---

### Task 1: Data model, domain errors, and domain entities

**Files:**
- Modify: `backend/app/db/models.py` (append new section at end of file)
- Modify: `backend/app/domain/errors.py` (append new section at end of file)
- Modify: `backend/app/domain/entities.py` (append new section at end of file)
- Test: `backend/tests/test_financial_plan.py` (new file)

**Interfaces:**
- Produces (consumed by Task 2 onward):
  - DB models: `FinancialPlanModel`, `FinancialPlanVersionModel`, `PlanAllocationModel`, `PlanSuballocationModel` — all in `app.db.models`
  - Errors: `PlanValidationError`, `PlanVersionImmutableError`, `DuplicateEffectiveDateError` — all in `app.domain.errors`, all subclass `CoralError`
  - Entities in `app.domain.entities`:
    - `SuballocationInput(name: str, percentage: Decimal)`
    - `AllocationInput(bucket_name: str, percentage: Decimal, suballocations: list[SuballocationInput])`
    - `SuballocationSnapshot(id: str, name: str, percentage: str, sort_order: int)`
    - `AllocationSnapshot(id: str, bucket_name: str, percentage: str, sort_order: int, suballocations: list[SuballocationSnapshot])`
    - `PlanVersionSnapshot(id: str, plan_id: str, version_number: int, effective_from: date, notes: str | None, allocations: list[AllocationSnapshot])`
    - `PlanVersionSummary(id: str, version_number: int, effective_from: date, notes: str | None)`
    - `PlanVersionCreateRequest(effective_from: date, allocations: list[AllocationInput], notes: str | None = None)`
    - `PlanVersionUpdateRequest(allocations: list[AllocationInput])`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_financial_plan.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v`
Expected: FAIL with `ImportError`/`ModuleNotFoundError` — `FinancialPlanModel` etc. don't exist yet.

- [ ] **Step 3: Add the four models to `backend/app/db/models.py`**

Append at the end of the file (after `DiscoverDetailModel`), with a new section comment matching the file's existing `# ── Section ──` style:

```python
# ── Financial Plan ────────────────────────────────────────────────────────────
#
# The user's INTENDED allocation of income, kept separate from actual
# transactions. Versioned and effective-dated: a plan has many versions, each
# starting on a given date and remaining in effect until the next version's
# effective_from. There is no effective_until column — the active window is
# derived at query time (see FinancialPlanService.get_plan_for_date) so it can
# never drift out of sync with the version list.
#
# Fixed 2-level tree: plan_allocations are top-level buckets (Needs, Wants,
# Savings, Investments, or a custom bucket the user adds later — bucket_name is
# a free string, not an enum). plan_suballocations are optional children of a
# bucket; their percentage is a share of the TOTAL plan (e.g. Emergency Fund =
# 5%), not of the parent bucket's share, so a bucket's suballocations must sum
# to exactly that bucket's own percentage.

class FinancialPlanModel(SQLModel, table=True):
    """Container for the user's financial allocation plan, versioned over time.

    Coral is single-user/local-first, so exactly one active FinancialPlanModel
    row is expected to exist in practice (auto-seeded on first boot).
    """
    __tablename__ = "financial_plans"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = "Master Plan"
    is_active: bool = True
    created_at: datetime = Field(default_factory=_now)

    versions: list["FinancialPlanVersionModel"] = Relationship(back_populates="plan")


class FinancialPlanVersionModel(SQLModel, table=True):
    """A single effective-dated version of a plan's allocations."""
    __tablename__ = "financial_plan_versions"

    id: str = Field(default_factory=_uuid, primary_key=True)
    plan_id: str = Field(foreign_key="financial_plans.id", index=True)
    version_number: int
    effective_from: date = Field(index=True)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)

    plan: Optional[FinancialPlanModel] = Relationship(back_populates="versions")
    allocations: list["PlanAllocationModel"] = Relationship(back_populates="plan_version")


class PlanAllocationModel(SQLModel, table=True):
    """Top-level bucket within a plan version (Needs, Wants, Savings, Investments, or custom)."""
    __tablename__ = "plan_allocations"

    id: str = Field(default_factory=_uuid, primary_key=True)
    plan_version_id: str = Field(foreign_key="financial_plan_versions.id", index=True)
    bucket_name: str
    percentage: str  # Decimal as string, e.g. "50"
    sort_order: int = 0

    plan_version: Optional[FinancialPlanVersionModel] = Relationship(back_populates="allocations")
    suballocations: list["PlanSuballocationModel"] = Relationship(back_populates="allocation")


class PlanSuballocationModel(SQLModel, table=True):
    """Child of a plan_allocation. Percentage is of the TOTAL plan, not of the parent's share."""
    __tablename__ = "plan_suballocations"

    id: str = Field(default_factory=_uuid, primary_key=True)
    allocation_id: str = Field(foreign_key="plan_allocations.id", index=True)
    name: str
    percentage: str  # Decimal as string, e.g. "5"
    sort_order: int = 0

    allocation: Optional[PlanAllocationModel] = Relationship(back_populates="suballocations")
```

No new imports are needed — `date`, `datetime`, `Optional`, `Field`, `Relationship`, `SQLModel`, `_uuid`, `_now` are all already imported/defined at the top of `models.py`.

- [ ] **Step 4: Add the three errors to `backend/app/domain/errors.py`**

Append at the end of the file:

```python

# ── Financial Plan ───────────────────────────────────────────────────────────

class PlanValidationError(CoralError):
    """Plan allocation percentages fail validation (don't sum to 100, duplicates, negatives)."""

class PlanVersionImmutableError(CoralError):
    """Cannot edit a plan version that is already active or was active in the past."""

class DuplicateEffectiveDateError(CoralError):
    """A plan version with this effective_from already exists for this plan."""
```

- [ ] **Step 5: Add the entities to `backend/app/domain/entities.py`**

Append at the end of the file:

```python

# ── Financial Plan ───────────────────────────────────────────────────────────

class SuballocationInput(BaseModel):
    """Input contract for one suballocation row when creating/updating a plan version."""
    name: str
    percentage: Decimal

    _normalize_percentage = field_validator("percentage", mode="before")(_to_decimal)


class AllocationInput(BaseModel):
    """Input contract for one top-level bucket when creating/updating a plan version."""
    bucket_name: str
    percentage: Decimal
    suballocations: list[SuballocationInput] = Field(default_factory=list)

    _normalize_percentage = field_validator("percentage", mode="before")(_to_decimal)


class SuballocationSnapshot(BaseModel):
    """Read-side shape of a suballocation, returned by the service/API."""
    id: str
    name: str
    percentage: str
    sort_order: int


class AllocationSnapshot(BaseModel):
    """Read-side shape of a top-level bucket, returned by the service/API."""
    id: str
    bucket_name: str
    percentage: str
    sort_order: int
    suballocations: list[SuballocationSnapshot] = Field(default_factory=list)


class PlanVersionSnapshot(BaseModel):
    """Full read-side shape of a resolved plan version — what GET/POST/PATCH all return."""
    id: str
    plan_id: str
    version_number: int
    effective_from: date
    notes: str | None = None
    allocations: list[AllocationSnapshot] = Field(default_factory=list)


class PlanVersionSummary(BaseModel):
    """Lightweight listing shape for GET .../versions."""
    id: str
    version_number: int
    effective_from: date
    notes: str | None = None


class PlanVersionCreateRequest(BaseModel):
    effective_from: date
    allocations: list[AllocationInput]
    notes: str | None = None


class PlanVersionUpdateRequest(BaseModel):
    allocations: list[AllocationInput]
```

No new imports are needed — `BaseModel`, `Field`, `field_validator`, `date`, `Decimal`, and `_to_decimal` are all already defined at the top of `entities.py`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/models.py backend/app/domain/errors.py backend/app/domain/entities.py backend/tests/test_financial_plan.py
git commit -m "$(cat <<'EOF'
Add Financial Plan data model, errors, and entities

New financial_plans/financial_plan_versions/plan_allocations/
plan_suballocations tables plus their domain error and Pydantic entity
contracts, following the existing SQLModel/CoralError conventions.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Repository functions

**Files:**
- Modify: `backend/app/db/repositories.py` (add import + new section)
- Test: `backend/tests/test_financial_plan.py` (append)

**Interfaces:**
- Consumes: `FinancialPlanModel`, `FinancialPlanVersionModel`, `PlanAllocationModel`, `PlanSuballocationModel` from Task 1.
- Produces (consumed by Task 3 onward), all in `app.db.repositories` as module-level `async def`:
  - `create_financial_plan(session, **kwargs) -> FinancialPlanModel`
  - `get_active_financial_plan(session) -> FinancialPlanModel | None`
  - `create_plan_version(session, **kwargs) -> FinancialPlanVersionModel`
  - `get_plan_version(session, version_id: str) -> FinancialPlanVersionModel` (raises `EntityNotFoundError` if missing)
  - `get_version_by_effective_date(session, plan_id: str, effective_from: date) -> FinancialPlanVersionModel | None`
  - `get_latest_version_for_date(session, plan_id: str, target_date: date) -> FinancialPlanVersionModel | None`
  - `get_max_version_number(session, plan_id: str) -> int` (0 if none exist)
  - `list_versions_for_plan(session, plan_id: str) -> list[FinancialPlanVersionModel]` (newest `effective_from` first)
  - `create_allocation(session, **kwargs) -> PlanAllocationModel`
  - `create_suballocation(session, **kwargs) -> PlanSuballocationModel`
  - `get_allocations_for_version(session, version_id: str) -> list[PlanAllocationModel]` (ordered by `sort_order`)
  - `get_suballocations_for_allocation(session, allocation_id: str) -> list[PlanSuballocationModel]` (ordered by `sort_order`)
  - `delete_allocations_for_version(session, version_id: str) -> None` (cascades suballocations)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_financial_plan.py`:

```python

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v -k repo`
Expected: FAIL with `AttributeError: module 'app.db.repositories' has no attribute 'create_financial_plan'`.

- [ ] **Step 3: Add the repository functions**

In `backend/app/db/repositories.py`, add the four new models to the existing import block from `app.db.models` (keep alphabetical order matching the existing style):

```python
from app.db.models import (
    AccountModel,
    AmexDetailModel,
    BalanceSnapshotModel,
    ChaseDetailModel,
    DerivedMetricModel,
    DiscoverDetailModel,
    DocumentModel,
    EtradeDetailModel,
    FeeModel,
    FinancialPlanModel,
    FinancialPlanVersionModel,
    HoldingModel,
    InstitutionModel,
    MorganStanleyDetailModel,
    PlanAllocationModel,
    PlanSuballocationModel,
    StatementModel,
    TextChunkModel,
    TransactionModel,
)
```

Then append a new section at the end of the file:

```python

# ── Financial Plan ───────────────────────────────────────────────────────────

async def create_financial_plan(session: AsyncSession, **kwargs: Any) -> FinancialPlanModel:
    plan = FinancialPlanModel(**kwargs)
    session.add(plan)
    await session.flush()
    return plan


async def get_active_financial_plan(session: AsyncSession) -> FinancialPlanModel | None:
    result = await session.execute(
        select(FinancialPlanModel)
        .where(FinancialPlanModel.is_active == True)  # noqa: E712
        .order_by(FinancialPlanModel.created_at.asc())
    )
    return result.scalars().first()


async def create_plan_version(session: AsyncSession, **kwargs: Any) -> FinancialPlanVersionModel:
    version = FinancialPlanVersionModel(**kwargs)
    session.add(version)
    await session.flush()
    return version


async def get_plan_version(session: AsyncSession, version_id: str) -> FinancialPlanVersionModel:
    result = await session.execute(
        select(FinancialPlanVersionModel).where(FinancialPlanVersionModel.id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise EntityNotFoundError("FinancialPlanVersion", version_id)
    return version


async def get_version_by_effective_date(
    session: AsyncSession, plan_id: str, effective_from: date,
) -> FinancialPlanVersionModel | None:
    result = await session.execute(
        select(FinancialPlanVersionModel)
        .where(FinancialPlanVersionModel.plan_id == plan_id)
        .where(FinancialPlanVersionModel.effective_from == effective_from)
    )
    return result.scalar_one_or_none()


async def get_latest_version_for_date(
    session: AsyncSession, plan_id: str, target_date: date,
) -> FinancialPlanVersionModel | None:
    result = await session.execute(
        select(FinancialPlanVersionModel)
        .where(FinancialPlanVersionModel.plan_id == plan_id)
        .where(FinancialPlanVersionModel.effective_from <= target_date)
        .order_by(FinancialPlanVersionModel.effective_from.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_max_version_number(session: AsyncSession, plan_id: str) -> int:
    result = await session.execute(
        select(func.max(FinancialPlanVersionModel.version_number))
        .where(FinancialPlanVersionModel.plan_id == plan_id)
    )
    return result.scalar() or 0


async def list_versions_for_plan(session: AsyncSession, plan_id: str) -> list[FinancialPlanVersionModel]:
    result = await session.execute(
        select(FinancialPlanVersionModel)
        .where(FinancialPlanVersionModel.plan_id == plan_id)
        .order_by(FinancialPlanVersionModel.effective_from.desc())
    )
    return list(result.scalars().all())


async def create_allocation(session: AsyncSession, **kwargs: Any) -> PlanAllocationModel:
    allocation = PlanAllocationModel(**kwargs)
    session.add(allocation)
    await session.flush()
    return allocation


async def create_suballocation(session: AsyncSession, **kwargs: Any) -> PlanSuballocationModel:
    sub = PlanSuballocationModel(**kwargs)
    session.add(sub)
    await session.flush()
    return sub


async def get_allocations_for_version(session: AsyncSession, version_id: str) -> list[PlanAllocationModel]:
    result = await session.execute(
        select(PlanAllocationModel)
        .where(PlanAllocationModel.plan_version_id == version_id)
        .order_by(PlanAllocationModel.sort_order.asc())
    )
    return list(result.scalars().all())


async def get_suballocations_for_allocation(
    session: AsyncSession, allocation_id: str,
) -> list[PlanSuballocationModel]:
    result = await session.execute(
        select(PlanSuballocationModel)
        .where(PlanSuballocationModel.allocation_id == allocation_id)
        .order_by(PlanSuballocationModel.sort_order.asc())
    )
    return list(result.scalars().all())


async def delete_allocations_for_version(session: AsyncSession, version_id: str) -> None:
    """Delete all allocations (and cascade suballocations) for a version — used when
    replacing a not-yet-effective version's allocations in place."""
    allocations = await get_allocations_for_version(session, version_id)
    for alloc in allocations:
        await session.execute(
            text("DELETE FROM plan_suballocations WHERE allocation_id = :aid"),
            {"aid": alloc.id},
        )
    await session.execute(
        text("DELETE FROM plan_allocations WHERE plan_version_id = :vid"),
        {"vid": version_id},
    )
```

This uses `date` — check the top of `repositories.py` already has `from datetime import date` (it does, for the existing `query_transactions`/analytics functions). `func` and `text` are also already imported (`from sqlalchemy import func, text`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v -k repo`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/repositories.py backend/tests/test_financial_plan.py
git commit -m "$(cat <<'EOF'
Add Financial Plan repository functions

CRUD + effective-date resolution queries for financial_plans,
financial_plan_versions, plan_allocations, and plan_suballocations,
following the existing repositories.py pattern.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `validate_plan` pure function

**Files:**
- Create: `backend/app/services/financial_plan.py`
- Test: `backend/tests/test_financial_plan.py` (append)

**Interfaces:**
- Consumes: `AllocationInput`, `SuballocationInput` (Task 1), `PlanValidationError` (Task 1).
- Produces: `validate_plan(allocations: list[AllocationInput]) -> None`, raising `PlanValidationError` on any failure. No DB access — pure function, importable and testable without `temp_db`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_financial_plan.py`:

```python

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v -k validate_plan`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.financial_plan'`.

- [ ] **Step 3: Create `backend/app/services/financial_plan.py`**

```python
"""
Financial Plan service — the user's INTENDED allocation of income, kept
separate from actual transactions. Plans are versioned and effective-dated:
get_plan_for_date always resolves to whichever version was in force on a
given date, so historical months are judged against the plan that was
actually active then, not today's plan.

No FastAPI imports here — this module is called by the API layer
(app.api.financial_plan) but is equally usable from any future non-HTTP
caller (e.g. a chat-domain handler), exactly like app.db.repositories.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.db import repositories as repo
from app.db.engine import get_session
from app.db.models import FinancialPlanVersionModel
from app.domain.entities import (
    AllocationInput,
    AllocationSnapshot,
    PlanVersionSnapshot,
    PlanVersionSummary,
    SuballocationInput,
    SuballocationSnapshot,
)
from app.domain.errors import (
    DuplicateEffectiveDateError,
    EntityNotFoundError,
    PlanValidationError,
    PlanVersionImmutableError,
)

logger = get_logger(__name__)

_HUNDRED = Decimal("100")


def validate_plan(allocations: list[AllocationInput]) -> None:
    """Pure validation, no DB access.

    Rules: top-level percentages sum to exactly 100; each bucket's
    suballocation percentages sum to exactly that bucket's own percentage;
    no negative percentages; no duplicate bucket/suballocation names.
    """
    if not allocations:
        raise PlanValidationError("Plan must have at least one allocation bucket.")

    seen_buckets: set[str] = set()
    total = Decimal("0")

    for alloc in allocations:
        key = alloc.bucket_name.strip().lower()
        if key in seen_buckets:
            raise PlanValidationError(f"Duplicate bucket name: {alloc.bucket_name!r}")
        seen_buckets.add(key)

        if alloc.percentage < 0:
            raise PlanValidationError(f"Bucket {alloc.bucket_name!r} has a negative percentage.")

        total += alloc.percentage

        if alloc.suballocations:
            seen_subs: set[str] = set()
            sub_total = Decimal("0")
            for sub in alloc.suballocations:
                sub_key = sub.name.strip().lower()
                if sub_key in seen_subs:
                    raise PlanValidationError(
                        f"Duplicate suballocation name {sub.name!r} under {alloc.bucket_name!r}."
                    )
                seen_subs.add(sub_key)
                if sub.percentage < 0:
                    raise PlanValidationError(
                        f"Suballocation {sub.name!r} has a negative percentage."
                    )
                sub_total += sub.percentage

            if sub_total != alloc.percentage:
                raise PlanValidationError(
                    f"Suballocations under bucket {alloc.bucket_name!r} sum to {sub_total}, "
                    f"expected {alloc.percentage} to match the {alloc.bucket_name} bucket's own percentage."
                )

    if total != _HUNDRED:
        raise PlanValidationError(f"Allocations sum to {total}%, expected 100%.")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v -k validate_plan`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/financial_plan.py backend/tests/test_financial_plan.py
git commit -m "$(cat <<'EOF'
Add validate_plan pure function for Financial Plan service

Enforces 100% total, per-bucket suballocation sums, no negatives, and
no duplicate names — with no DB access, so it's cheap to test and
reusable from both create and update paths.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Default plan seeding

**Files:**
- Modify: `backend/app/services/financial_plan.py` (append)
- Modify: `backend/app/db/engine.py` (`init_db()`)
- Test: `backend/tests/test_financial_plan.py` (append)

**Interfaces:**
- Consumes: `validate_plan`, repo functions from Tasks 2–3.
- Produces: `PLAN_EPOCH: date` (module constant, `date(2000, 1, 1)`), `seed_default_plan_if_missing() -> None` in `app.services.financial_plan`. Called once from `app.db.engine.init_db()`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_financial_plan.py`:

```python

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v -k default_plan`
Expected: FAIL — `plan` is `None` (nothing seeds the plan yet).

- [ ] **Step 3: Add seeding to `backend/app/services/financial_plan.py`**

Append at the end of the file:

```python

# ── Default plan seeding ──────────────────────────────────────────────────────

# Far enough in the past that the seeded default plan resolves for all
# existing historical transaction data until the user creates a real V2.
PLAN_EPOCH = date(2000, 1, 1)

_DEFAULT_ALLOCATIONS: list[AllocationInput] = [
    AllocationInput(bucket_name="needs", percentage=Decimal("50")),
    AllocationInput(bucket_name="wants", percentage=Decimal("20")),
    AllocationInput(bucket_name="savings", percentage=Decimal("15"), suballocations=[
        SuballocationInput(name="Emergency Fund", percentage=Decimal("5")),
        SuballocationInput(name="House / Goals", percentage=Decimal("5")),
        SuballocationInput(name="Child Savings", percentage=Decimal("5")),
    ]),
    AllocationInput(bucket_name="investments", percentage=Decimal("15"), suballocations=[
        SuballocationInput(name="401(k)", percentage=Decimal("6")),
        SuballocationInput(name="Roth IRA", percentage=Decimal("4")),
        SuballocationInput(name="ESPP", percentage=Decimal("3")),
        SuballocationInput(name="Taxable Brokerage", percentage=Decimal("2")),
    ]),
]


async def _write_allocations(
    session: AsyncSession, version_id: str, allocations: list[AllocationInput],
) -> None:
    for i, alloc in enumerate(allocations):
        allocation = await repo.create_allocation(
            session, plan_version_id=version_id, bucket_name=alloc.bucket_name,
            percentage=str(alloc.percentage), sort_order=i,
        )
        for j, sub in enumerate(alloc.suballocations):
            await repo.create_suballocation(
                session, allocation_id=allocation.id, name=sub.name,
                percentage=str(sub.percentage), sort_order=j,
            )


async def seed_default_plan_if_missing() -> None:
    """Insert the default Master Plan (see PLAN_EPOCH/_DEFAULT_ALLOCATIONS above)
    only if no financial plan exists yet. Safe to call on every boot."""
    async with get_session() as session:
        existing = await repo.get_active_financial_plan(session)
        if existing is not None:
            return

        validate_plan(_DEFAULT_ALLOCATIONS)

        plan = await repo.create_financial_plan(session, name="Master Plan")
        version = await repo.create_plan_version(
            session, plan_id=plan.id, version_number=1,
            effective_from=PLAN_EPOCH, notes="Default seeded plan",
        )
        await _write_allocations(session, version.id, _DEFAULT_ALLOCATIONS)
        logger.info(
            "financial_plan.seeded",
            extra={"plan_id": plan.id, "version_id": version.id},
        )
```

- [ ] **Step 4: Hook seeding into `backend/app/db/engine.py`**

In `init_db()`, right after the `init_fts()` call and before the final `logger.info("db.initialized", ...)` line:

```python
    # 3. Initialize FTS5 virtual table.
    from app.db.fts import init_fts
    await init_fts()

    # 4. Seed the default Financial Plan if none exists yet.
    from app.services.financial_plan import seed_default_plan_if_missing
    await seed_default_plan_if_missing()

    logger.info("db.initialized", path=str(db_path))
```

(Import is local to the function, matching the existing local-import style used for `init_fts` in this same function and for `app.services.llm` in `main.py::_check_ollama_model` — this also sidesteps a circular import, since `financial_plan.py` imports `get_session` from this very module.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v`
Expected: all tests so far pass (models, errors, entities, repo, validate_plan, seeding).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/financial_plan.py backend/app/db/engine.py backend/tests/test_financial_plan.py
git commit -m "$(cat <<'EOF'
Seed default Financial Plan on first boot

Needs 50 / Wants 20 / Savings 15 (Emergency 5, House 5, Child 5) /
Investments 15 (401k 6, Roth IRA 4, ESPP 3, Brokerage 2), effective
from a fixed epoch so it covers all existing historical data until a
real V2 is created. Only seeds when no plan exists yet.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `get_plan_for_date` / `get_current_plan`

**Files:**
- Modify: `backend/app/services/financial_plan.py` (append)
- Test: `backend/tests/test_financial_plan.py` (append)

**Interfaces:**
- Consumes: repo functions from Task 2, seeded default from Task 4.
- Produces: `get_plan_for_date(session, target_date: date) -> PlanVersionSnapshot | None`, `get_current_plan(session) -> PlanVersionSnapshot | None`, and the private helper `_snapshot_from_version(session, version: FinancialPlanVersionModel) -> PlanVersionSnapshot` (used by later tasks too).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_financial_plan.py`:

```python

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v -k get_plan_for_date or get_current_plan`
Expected: FAIL with `AttributeError` — the functions don't exist yet.

- [ ] **Step 3: Add the functions to `backend/app/services/financial_plan.py`**

Append at the end of the file:

```python

# ── Resolution by date ─────────────────────────────────────────────────────────

async def _snapshot_from_version(
    session: AsyncSession, version: FinancialPlanVersionModel,
) -> PlanVersionSnapshot:
    allocations = await repo.get_allocations_for_version(session, version.id)
    allocation_snapshots: list[AllocationSnapshot] = []
    for alloc in allocations:
        subs = await repo.get_suballocations_for_allocation(session, alloc.id)
        allocation_snapshots.append(AllocationSnapshot(
            id=alloc.id,
            bucket_name=alloc.bucket_name,
            percentage=alloc.percentage,
            sort_order=alloc.sort_order,
            suballocations=[
                SuballocationSnapshot(
                    id=sub.id, name=sub.name,
                    percentage=sub.percentage, sort_order=sub.sort_order,
                )
                for sub in subs
            ],
        ))
    return PlanVersionSnapshot(
        id=version.id,
        plan_id=version.plan_id,
        version_number=version.version_number,
        effective_from=version.effective_from,
        notes=version.notes,
        allocations=allocation_snapshots,
    )


async def get_plan_for_date(session: AsyncSession, target_date: date) -> PlanVersionSnapshot | None:
    plan = await repo.get_active_financial_plan(session)
    if plan is None:
        return None
    version = await repo.get_latest_version_for_date(session, plan.id, target_date)
    if version is None:
        return None
    return await _snapshot_from_version(session, version)


async def get_current_plan(session: AsyncSession) -> PlanVersionSnapshot | None:
    return await get_plan_for_date(session, date.today())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v -k "get_plan_for_date or get_current_plan"`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/financial_plan.py backend/tests/test_financial_plan.py
git commit -m "$(cat <<'EOF'
Add plan resolution by effective date

get_plan_for_date walks back to the latest version whose effective_from
is on or before the target date; get_current_plan is today's shortcut.
Historical dates always resolve against the version that was actually
active then.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `create_plan_version`

**Files:**
- Modify: `backend/app/services/financial_plan.py` (append)
- Test: `backend/tests/test_financial_plan.py` (append)

**Interfaces:**
- Consumes: `validate_plan`, `_write_allocations`, `_snapshot_from_version` from Tasks 3–5.
- Produces: `create_plan_version(session, effective_from: date, allocations: list[AllocationInput], notes: str | None = None) -> PlanVersionSnapshot`, raising `PlanValidationError`, `DuplicateEffectiveDateError`, or `EntityNotFoundError` (no active plan — should not happen in practice since one is always seeded, but the function must not silently create a second plan).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_financial_plan.py`:

```python

# ── Task 6: create_plan_version ───────────────────────────────────────────────

from app.domain.errors import DuplicateEffectiveDateError


async def test_create_plan_version_success_increments_version_number(temp_db):
    async with get_session() as session:
        snapshot = await plan_service.create_plan_version(
            session, effective_from=date(2027, 1, 1),
            allocations=[
                AllocationInput(bucket_name="needs", percentage="50"),
                AllocationInput(bucket_name="wants", percentage="20"),
                AllocationInput(bucket_name="savings", percentage="15"),
                AllocationInput(bucket_name="investments", percentage="15"),
            ],
            notes="2027 plan",
        )
    assert snapshot.version_number == 2  # seeded default is version 1
    assert snapshot.effective_from == date(2027, 1, 1)
    assert len(snapshot.allocations) == 4


async def test_create_plan_version_rejects_invalid_percentages(temp_db):
    async with get_session() as session:
        with pytest.raises(PlanValidationError):
            await plan_service.create_plan_version(
                session, effective_from=date(2027, 1, 1),
                allocations=[AllocationInput(bucket_name="needs", percentage="50")],
            )


async def test_create_plan_version_rejects_duplicate_effective_date(temp_db):
    async with get_session() as session:
        with pytest.raises(DuplicateEffectiveDateError):
            await plan_service.create_plan_version(
                session, effective_from=plan_service.PLAN_EPOCH,  # same as seeded V1
                allocations=[AllocationInput(bucket_name="needs", percentage="100")],
            )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v -k create_plan_version`
Expected: FAIL with `AttributeError` — `create_plan_version` doesn't exist on `plan_service` yet.

- [ ] **Step 3: Add the function to `backend/app/services/financial_plan.py`**

Append at the end of the file:

```python

# ── Creating new versions ──────────────────────────────────────────────────────

async def create_plan_version(
    session: AsyncSession,
    effective_from: date,
    allocations: list[AllocationInput],
    notes: str | None = None,
) -> PlanVersionSnapshot:
    """Create a new version on the (single) master plan, effective from the
    given date. Raises DuplicateEffectiveDateError if a version already
    starts on that exact date — resolution would otherwise be ambiguous."""
    validate_plan(allocations)

    plan = await repo.get_active_financial_plan(session)
    if plan is None:
        raise EntityNotFoundError("FinancialPlan", "active")

    existing = await repo.get_version_by_effective_date(session, plan.id, effective_from)
    if existing is not None:
        raise DuplicateEffectiveDateError(
            f"A plan version already exists with effective_from={effective_from}."
        )

    next_number = await repo.get_max_version_number(session, plan.id) + 1
    version = await repo.create_plan_version(
        session, plan_id=plan.id, version_number=next_number,
        effective_from=effective_from, notes=notes,
    )
    await _write_allocations(session, version.id, allocations)
    return await _snapshot_from_version(session, version)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v -k create_plan_version`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/financial_plan.py backend/tests/test_financial_plan.py
git commit -m "$(cat <<'EOF'
Add create_plan_version to Financial Plan service

Validates percentages, assigns the next sequential version_number, and
rejects a duplicate effective_from on the same plan (which would make
date resolution ambiguous).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `update_plan_version` (future-only edits)

**Files:**
- Modify: `backend/app/services/financial_plan.py` (append)
- Test: `backend/tests/test_financial_plan.py` (append)

**Interfaces:**
- Consumes: `validate_plan`, `_write_allocations`, `_snapshot_from_version`, `repo.get_plan_version`, `repo.delete_allocations_for_version`.
- Produces: `update_plan_version(session, version_id: str, allocations: list[AllocationInput]) -> PlanVersionSnapshot`, raising `PlanValidationError` or `PlanVersionImmutableError` (if `version.effective_from <= date.today()`).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_financial_plan.py`:

```python

# ── Task 7: update_plan_version ───────────────────────────────────────────────

from app.domain.errors import PlanVersionImmutableError


async def test_update_future_version_succeeds_and_history_is_unaffected(temp_db):
    async with get_session() as session:
        future = await plan_service.create_plan_version(
            session, effective_from=date(2027, 1, 1),
            allocations=[
                AllocationInput(bucket_name="needs", percentage="50"),
                AllocationInput(bucket_name="wants", percentage="20"),
                AllocationInput(bucket_name="savings", percentage="15"),
                AllocationInput(bucket_name="investments", percentage="15"),
            ],
        )

    async with get_session() as session:
        updated = await plan_service.update_plan_version(
            session, version_id=future.id,
            allocations=[
                AllocationInput(bucket_name="needs", percentage="55"),
                AllocationInput(bucket_name="wants", percentage="15"),
                AllocationInput(bucket_name="savings", percentage="15"),
                AllocationInput(bucket_name="investments", percentage="15"),
            ],
        )
    needs = next(a for a in updated.allocations if a.bucket_name == "needs")
    assert needs.percentage == "55"

    async with get_session() as session:
        # A date before the future version's effective_from must still resolve
        # to the ORIGINAL seeded default (needs=50) — editing V2 must not
        # rewrite what V1 says about the past/present.
        historical = await plan_service.get_plan_for_date(session, date(2026, 8, 15))
        historical_needs = next(a for a in historical.allocations if a.bucket_name == "needs")
        assert historical_needs.percentage == "50"


async def test_update_active_version_raises_immutable_error(temp_db):
    async with get_session() as session:
        plan = await repo.get_active_financial_plan(session)
        active_version = await repo.get_latest_version_for_date(session, plan.id, date.today())

        with pytest.raises(PlanVersionImmutableError):
            await plan_service.update_plan_version(
                session, version_id=active_version.id,
                allocations=[AllocationInput(bucket_name="needs", percentage="100")],
            )


async def test_update_rejects_invalid_percentages(temp_db):
    async with get_session() as session:
        future = await plan_service.create_plan_version(
            session, effective_from=date(2028, 1, 1),
            allocations=[
                AllocationInput(bucket_name="needs", percentage="50"),
                AllocationInput(bucket_name="wants", percentage="20"),
                AllocationInput(bucket_name="savings", percentage="15"),
                AllocationInput(bucket_name="investments", percentage="15"),
            ],
        )

    async with get_session() as session:
        with pytest.raises(PlanValidationError):
            await plan_service.update_plan_version(
                session, version_id=future.id,
                allocations=[AllocationInput(bucket_name="needs", percentage="50")],
            )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v -k update_plan_version or update_active or update_rejects`
Expected: FAIL with `AttributeError` — `update_plan_version` doesn't exist yet.

- [ ] **Step 3: Add the function to `backend/app/services/financial_plan.py`**

Append at the end of the file:

```python

# ── Editing existing versions ──────────────────────────────────────────────────

async def update_plan_version(
    session: AsyncSession,
    version_id: str,
    allocations: list[AllocationInput],
) -> PlanVersionSnapshot:
    """Replace a version's allocations in place. Only permitted while the
    version's effective_from is strictly in the future — a version that is
    already active or was active in the past is immutable, so the only way
    to change what's in effect today onward is create_plan_version() with a
    new effective_from. This is what keeps edits from rewriting history."""
    validate_plan(allocations)

    version = await repo.get_plan_version(session, version_id)
    if version.effective_from <= date.today():
        raise PlanVersionImmutableError(
            f"Plan version {version_id} is active or in the past "
            f"(effective_from={version.effective_from}) and cannot be edited. "
            "Create a new version instead."
        )

    await repo.delete_allocations_for_version(session, version_id)
    await _write_allocations(session, version_id, allocations)
    return await _snapshot_from_version(session, version)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v`
Expected: all tests pass (full service layer complete).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/financial_plan.py backend/tests/test_financial_plan.py
git commit -m "$(cat <<'EOF'
Add update_plan_version with future-only edit enforcement

Editing a version whose effective_from is today or in the past raises
PlanVersionImmutableError — the only way to change what's in effect
going forward is to create a new version, so history can never be
retroactively rewritten.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: API endpoints

**Files:**
- Create: `backend/app/api/financial_plan.py`
- Modify: `backend/app/main.py` (register the router)
- Test: `backend/tests/test_financial_plan.py` (append)

**Interfaces:**
- Consumes: everything from Tasks 1–7 (`app.services.financial_plan`, `app.domain.entities`, `app.domain.errors`).
- Produces: FastAPI router at `prefix="/api/v1/financial-plan"` with handlers `get_current_plan`, `get_plan_by_date`, `list_versions`, `create_version`, `update_version` — all plain `async def`, callable directly in tests exactly like `app.api.documents.document_stats` is in `test_reprocess_and_health.py`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_financial_plan.py`:

```python

# ── Task 8: API endpoints ──────────────────────────────────────────────────────

from fastapi import HTTPException

from app.api.financial_plan import (
    create_version,
    get_current_plan as api_get_current_plan,
    get_plan_by_date,
    list_versions,
    update_version,
)
from app.domain.entities import PlanVersionCreateRequest, PlanVersionUpdateRequest


async def test_api_get_current_plan_returns_seeded_default(temp_db):
    snapshot = await api_get_current_plan()
    assert snapshot.version_number == 1
    bucket_names = {a.bucket_name for a in snapshot.allocations}
    assert bucket_names == {"needs", "wants", "savings", "investments"}


async def test_api_get_plan_by_date_404_before_epoch(temp_db):
    with pytest.raises(HTTPException) as exc_info:
        await get_plan_by_date(target_date=date(1999, 1, 1))
    assert exc_info.value.status_code == 404


async def test_api_list_versions_returns_seeded_version(temp_db):
    versions = await list_versions()
    assert len(versions) == 1
    assert versions[0].version_number == 1


async def test_api_create_version_success(temp_db):
    body = PlanVersionCreateRequest(
        effective_from=date(2027, 1, 1),
        allocations=[
            AllocationInput(bucket_name="needs", percentage="50"),
            AllocationInput(bucket_name="wants", percentage="20"),
            AllocationInput(bucket_name="savings", percentage="15"),
            AllocationInput(bucket_name="investments", percentage="15"),
        ],
    )
    snapshot = await create_version(body)
    assert snapshot.version_number == 2


async def test_api_create_version_duplicate_date_returns_409(temp_db):
    body = PlanVersionCreateRequest(
        effective_from=plan_service.PLAN_EPOCH,
        allocations=[AllocationInput(bucket_name="needs", percentage="100")],
    )
    with pytest.raises(HTTPException) as exc_info:
        await create_version(body)
    assert exc_info.value.status_code == 409


async def test_api_create_version_invalid_percentages_returns_422(temp_db):
    body = PlanVersionCreateRequest(
        effective_from=date(2027, 1, 1),
        allocations=[AllocationInput(bucket_name="needs", percentage="50")],
    )
    with pytest.raises(HTTPException) as exc_info:
        await create_version(body)
    assert exc_info.value.status_code == 422


async def test_api_update_version_future_succeeds(temp_db):
    created = await create_version(PlanVersionCreateRequest(
        effective_from=date(2027, 1, 1),
        allocations=[
            AllocationInput(bucket_name="needs", percentage="50"),
            AllocationInput(bucket_name="wants", percentage="20"),
            AllocationInput(bucket_name="savings", percentage="15"),
            AllocationInput(bucket_name="investments", percentage="15"),
        ],
    ))

    updated = await update_version(created.id, PlanVersionUpdateRequest(
        allocations=[
            AllocationInput(bucket_name="needs", percentage="55"),
            AllocationInput(bucket_name="wants", percentage="15"),
            AllocationInput(bucket_name="savings", percentage="15"),
            AllocationInput(bucket_name="investments", percentage="15"),
        ],
    ))
    needs = next(a for a in updated.allocations if a.bucket_name == "needs")
    assert needs.percentage == "55"


async def test_api_update_active_version_returns_409(temp_db):
    versions = await list_versions()
    active_version_id = versions[0].id

    with pytest.raises(HTTPException) as exc_info:
        await update_version(active_version_id, PlanVersionUpdateRequest(
            allocations=[AllocationInput(bucket_name="needs", percentage="100")],
        ))
    assert exc_info.value.status_code == 409
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v -k api_`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api.financial_plan'`.

- [ ] **Step 3: Create `backend/app/api/financial_plan.py`**

```python
"""
Financial Plan API — the user's INTENDED allocation (Needs/Wants/Savings/
Investments, versioned and effective-dated), kept separate from actual
transactions. All business logic lives in app.services.financial_plan; this
module only opens sessions and translates domain errors to HTTP responses.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.db.engine import get_session
from app.domain.entities import (
    PlanVersionCreateRequest,
    PlanVersionSnapshot,
    PlanVersionSummary,
    PlanVersionUpdateRequest,
)
from app.domain.errors import (
    DuplicateEffectiveDateError,
    EntityNotFoundError,
    PlanValidationError,
    PlanVersionImmutableError,
)
from app.services import financial_plan as plan_service

router = APIRouter(prefix="/api/v1/financial-plan", tags=["financial-plan"])


@router.get("/current", response_model=PlanVersionSnapshot)
async def get_current_plan() -> PlanVersionSnapshot:
    async with get_session() as session:
        snapshot = await plan_service.get_current_plan(session)
    if snapshot is None:
        raise HTTPException(404, "No financial plan is currently in effect.")
    return snapshot


@router.get("", response_model=PlanVersionSnapshot)
async def get_plan_by_date(target_date: date = Query(..., alias="date")) -> PlanVersionSnapshot:
    async with get_session() as session:
        snapshot = await plan_service.get_plan_for_date(session, target_date)
    if snapshot is None:
        raise HTTPException(404, f"No financial plan is in effect on {target_date}.")
    return snapshot


@router.get("/versions", response_model=list[PlanVersionSummary])
async def list_versions() -> list[PlanVersionSummary]:
    async with get_session() as session:
        return await plan_service.list_plan_versions(session)


@router.post("/versions", response_model=PlanVersionSnapshot, status_code=201)
async def create_version(body: PlanVersionCreateRequest) -> PlanVersionSnapshot:
    try:
        async with get_session() as session:
            return await plan_service.create_plan_version(
                session, effective_from=body.effective_from,
                allocations=body.allocations, notes=body.notes,
            )
    except PlanValidationError as exc:
        raise HTTPException(422, exc.message)
    except DuplicateEffectiveDateError as exc:
        raise HTTPException(409, exc.message)
    except EntityNotFoundError as exc:
        raise HTTPException(404, exc.message)


@router.patch("/versions/{version_id}", response_model=PlanVersionSnapshot)
async def update_version(version_id: str, body: PlanVersionUpdateRequest) -> PlanVersionSnapshot:
    try:
        async with get_session() as session:
            return await plan_service.update_plan_version(
                session, version_id=version_id, allocations=body.allocations,
            )
    except PlanValidationError as exc:
        raise HTTPException(422, exc.message)
    except PlanVersionImmutableError as exc:
        raise HTTPException(409, exc.message)
    except EntityNotFoundError as exc:
        raise HTTPException(404, exc.message)
```

Note: `target_date: date = Query(..., alias="date")` keeps the external query parameter named `date` (as in `GET /api/v1/financial-plan?date=2026-08-15`) while avoiding a Python name collision with the `date` type. When tests call `get_plan_by_date(target_date=...)` directly (bypassing FastAPI's dependency injection), they pass a real `date` value for that same parameter, so the `Query(...)` default is simply overridden — no special test setup needed.

Also add `list_plan_versions` to `backend/app/services/financial_plan.py` — it wasn't needed until this task exposes a listing endpoint. Append at the end of the file:

```python

# ── Listing versions ────────────────────────────────────────────────────────────

async def list_plan_versions(session: AsyncSession) -> list[PlanVersionSummary]:
    plan = await repo.get_active_financial_plan(session)
    if plan is None:
        return []
    versions = await repo.list_versions_for_plan(session, plan.id)
    return [
        PlanVersionSummary(
            id=v.id, version_number=v.version_number,
            effective_from=v.effective_from, notes=v.notes,
        )
        for v in versions
    ]
```

- [ ] **Step 4: Register the router in `backend/app/main.py`**

In `create_app()`, add the import and `include_router` call alongside the existing ones:

```python
    from app.api.documents import router as documents_router
    from app.api.chat import router as chat_router
    from app.api.analytics import router as analytics_router
    from app.api.scan import router as scan_router
    from app.api.dashboard import router as dashboard_router
    from app.api.health import router as health_router
    from app.api.catalog import router as catalog_router
    from app.api.financial_plan import router as financial_plan_router

    app.include_router(documents_router)
    app.include_router(chat_router)
    app.include_router(analytics_router)
    app.include_router(scan_router)
    app.include_router(dashboard_router)
    app.include_router(health_router)
    app.include_router(catalog_router)
    app.include_router(financial_plan_router)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_financial_plan.py -v`
Expected: all tests pass, including the new `api_*` ones.

- [ ] **Step 6: Sanity-check the app boots with the new router**

Run: `cd backend && .venv/bin/python -c "from app.main import app; print([r.path for r in app.routes if 'financial-plan' in r.path])"`
Expected: prints a list containing `/api/v1/financial-plan/current`, `/api/v1/financial-plan`, `/api/v1/financial-plan/versions`, `/api/v1/financial-plan/versions/{version_id}` — confirming the router is wired up and importable without circular-import errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/financial_plan.py backend/app/main.py backend/app/services/financial_plan.py backend/tests/test_financial_plan.py
git commit -m "$(cat <<'EOF'
Expose Financial Plan service via FastAPI endpoints

GET /current, GET ?date=, GET /versions, POST /versions, PATCH
/versions/{id} — thin translation layer over app.services.financial_plan,
mapping PlanValidationError->422, DuplicateEffectiveDateError->409,
PlanVersionImmutableError->409, EntityNotFoundError->404.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Documentation

**Files:**
- Create: `docs/FINANCIAL_PLAN_MODEL.md`
- Modify: `CLAUDE.md` (Key Modules + Database sections)

**Interfaces:**
- No code interfaces — this task documents Tasks 1–8 for future readers. No tests (documentation-only task).

- [ ] **Step 1: Write `docs/FINANCIAL_PLAN_MODEL.md`**

```markdown
# Financial Plan Model

Coral's Financial Plan model represents the user's **intended** allocation of
income (Needs/Wants/Savings/Investments, with nested breakdowns), kept
completely separate from **actual** transactions. It is versioned and
effective-dated, so a historical month is always evaluated against whichever
plan version was actually in force during that month — not today's plan.

This model does not yet drive any PLAN-vs-ACTUAL comparison UI or chat
behavior; it is the data layer that future features build on.

## Schema

Four tables, added in `backend/app/db/models.py`:

```
financial_plans
  id, name ("Master Plan"), is_active, created_at
    │ 1
    │
    │ N
financial_plan_versions
  id, plan_id, version_number, effective_from, notes, created_at
    │ 1
    │
    │ N
plan_allocations                 (top-level buckets: Needs, Wants, Savings, Investments, or custom)
  id, plan_version_id, bucket_name, percentage, sort_order
    │ 1
    │
    │ N
plan_suballocations               (children of a bucket, e.g. Emergency Fund under Savings)
  id, allocation_id, name, percentage, sort_order
```

Coral is single-user/local-first, so exactly one `financial_plans` row is
expected to exist in practice — it is the permanent container, versioned over
time rather than replaced.

**Percentages** are stored as `str`-encoded `Decimal` (e.g. `"50"`, `"15"`),
matching how rate-like fields (`apr`, `management_fee_rate`) are already
stored elsewhere in the schema — this avoids the binary-float precision loss
that plain `float` would introduce.

**Suballocation percentages are a share of the total plan, not of the parent
bucket's share.** Emergency Fund = 5% (of the whole plan), not 5% of Savings'
15%. This means a bucket's suballocations must sum to exactly that bucket's
own percentage, and validating the whole plan is a single flat-sum check
rather than a percentage-of-percentage calculation.

**Buckets are free strings, not an enum** (`bucket_name` is a plain `str`
column) — this is what lets a user add a custom bucket (e.g. "Giving") later
without a schema change; the only requirement is that all buckets in a
version still sum to 100%.

**No `effective_until` column.** A version's active window is derived at
query time as `[effective_from, next_version.effective_from)` by
`get_plan_for_date` — storing an end date redundantly would risk it drifting
out of sync whenever versions are inserted or edited.

## Versioning and effective dating

- `get_plan_for_date(session, target_date)` resolves to the plan version with
  the latest `effective_from` that is still `<= target_date`. If no version
  qualifies (the date is before the earliest version), it returns `None`.
- `get_current_plan(session)` is the same, for `date.today()`.
- `create_plan_version(session, effective_from, allocations, notes=None)`
  creates a new version on the master plan. Two versions cannot share the
  same `effective_from` on the same plan — attempting that raises
  `DuplicateEffectiveDateError`, since it would make date resolution
  ambiguous.
- `update_plan_version(session, version_id, allocations)` replaces a
  version's allocations **in place**, but only if that version's
  `effective_from` is strictly in the future. Attempting to edit a version
  that is currently active, or was active in the past, raises
  `PlanVersionImmutableError`. This is the mechanism that guarantees editing
  a not-yet-effective plan never rewrites how past or present months are
  evaluated — the only way to change what's in effect going forward is to
  `create_plan_version` with a new `effective_from`.
- `validate_plan(allocations)` is pure (no DB access): top-level percentages
  must sum to exactly 100; each bucket's suballocations must sum to exactly
  that bucket's own percentage; no negative percentages; no duplicate
  bucket/suballocation names.

## Default plan

Seeded once, automatically, the first time the app boots with no existing
`financial_plans` row (`seed_default_plan_if_missing()`, called from
`app.db.engine.init_db()`):

| Bucket | % | Suballocation | % |
|---|---|---|---|
| Needs | 50 | | |
| Wants | 20 | | |
| Savings | 15 | Emergency Fund | 5 |
| | | House / Goals | 5 |
| | | Child Savings | 5 |
| Investments | 15 | 401(k) | 6 |
| | | Roth IRA | 4 |
| | | ESPP | 3 |
| | | Taxable Brokerage | 2 |

`effective_from` is a fixed epoch (`PLAN_EPOCH = date(2000, 1, 1)`), so the
default plan resolves for all existing historical transaction data until the
user creates a real second version.

## Service API

`backend/app/services/financial_plan.py` — no FastAPI imports, so it is
equally callable from a future non-HTTP caller (e.g. a chat-domain handler
asking "am I within plan?"), exactly like `app.db.repositories`:

- `validate_plan(allocations: list[AllocationInput]) -> None`
- `get_plan_for_date(session, target_date: date) -> PlanVersionSnapshot | None`
- `get_current_plan(session) -> PlanVersionSnapshot | None`
- `list_plan_versions(session) -> list[PlanVersionSummary]`
- `create_plan_version(session, effective_from, allocations, notes=None) -> PlanVersionSnapshot`
- `update_plan_version(session, version_id, allocations) -> PlanVersionSnapshot`
- `seed_default_plan_if_missing() -> None`

## HTTP API

`backend/app/api/financial_plan.py`, registered in `main.py`:

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/financial-plan/current` | Resolved plan for today; 404 if none |
| GET | `/api/v1/financial-plan?date=YYYY-MM-DD` | Resolved plan for that date; 404 if none |
| GET | `/api/v1/financial-plan/versions` | List all versions, newest first |
| POST | `/api/v1/financial-plan/versions` | Create a new version; 422 invalid %, 409 duplicate date |
| PATCH | `/api/v1/financial-plan/versions/{id}` | Edit a future version's allocations; 422 invalid %, 409 if not strictly future |

## Non-goals (this phase)

- No `financial_goal` table (target dollar amounts / dates / progress
  tracking) — nothing consumes it yet.
- No multi-plan / scenario-plan support — one master plan, versioned.
- No recursive/arbitrary-depth allocation tree — fixed 2 levels.
- No PLAN-vs-ACTUAL comparison UI or chat integration.
```

- [ ] **Step 2: Cross-reference the new doc from `CLAUDE.md`**

In `CLAUDE.md`, update the `services/` and `api/` bullets under **Key Modules → Backend** (around line 27–29):

```markdown
- `services/` — ingestion, llm, `chat_router.py` (primary chat pipeline), `query_router.py` (legacy, not live), `intent_classifier.py`, `intent_mapping.py`, `sql_query.py` (13 handlers), `text_search.py`, `vector_search.py`, `answer_builder.py`, `financial_plan.py` (versioned allocation plan, no HTTP coupling), `dashboard/`
- `chat/` — `streaming.py` (SSE), `query_planner.py`, `answer_style.py`, `fact_builder.py`, `insight_builder.py`, `answer_verifier.py`, `guardrails.py`, `retrieval.py`, `services/conversation_context.py`, `evals/`, `domains/affordability/` (7-layer pipeline)
- `api/` — documents, chat, analytics, dashboard, scan, catalog, health, financial-plan routes
```

And update the **Database** section (around line 61–65):

```markdown
## Database
- Canonical tables: institutions, accounts, documents, statements, transactions, fees, holdings, balance_snapshots, text_chunks, derived_metrics
- Financial Plan tables: financial_plans, financial_plan_versions, plan_allocations, plan_suballocations — the user's intended allocation, versioned/effective-dated, kept separate from actual transactions. See [FINANCIAL_PLAN_MODEL.md](docs/FINANCIAL_PLAN_MODEL.md).
- Bank-specific: morgan_stanley_details, chase_details, etrade_details, amex_details, discover_details (Bank of America has no detail table — canonical rows only)
- FTS5 virtual table: text_chunks_fts
- SQL reference: [queries.sql](queries.sql)
```

- [ ] **Step 3: Verify the new doc renders sensibly**

Run: `cd .. && ls -la docs/FINANCIAL_PLAN_MODEL.md` (from `backend/`, so `cd ..` first) and eyeball the file with a quick `head -40 docs/FINANCIAL_PLAN_MODEL.md` — confirm no unclosed code fences or broken tables.

- [ ] **Step 4: Run the full test suite once more to confirm nothing regressed**

Run: `cd backend && .venv/bin/pytest tests/ -v`
Expected: all tests pass, including every pre-existing test file (chat, parsers, reprocess, etc.) — this task touches no runtime code, only docs, so this is a pure regression check.

- [ ] **Step 5: Commit**

```bash
git add docs/FINANCIAL_PLAN_MODEL.md CLAUDE.md
git commit -m "$(cat <<'EOF'
Document the Financial Plan model

Schema, versioning/effective-dating semantics, seed defaults, service
API, and HTTP endpoints. Cross-referenced from CLAUDE.md.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Notes

**Spec coverage** — every requirement from the design spec maps to a task:
- Multiple plan versions / effective dates / active-inactive → Tasks 1, 5, 6, 7
- Master buckets / nested suballocations / editable percentages → Tasks 1, 6, 7
- Validation / total = 100% / suballocation validation → Task 3
- Future custom buckets without overengineering → free-string `bucket_name`, tested in Task 3 (`test_validate_plan_allows_custom_bucket_if_total_still_100`)
- Seed default plan only when none exists → Task 4
- Clean service/repository APIs, not HTTP-coupled → Tasks 2–7 (all in `app.services`/`app.db.repositories`, zero FastAPI imports)
- API endpoints following repo conventions → Task 8
- All 8 required test cases → distributed across Tasks 1, 4, 5, 6, 7 (see each task's test list)
- `docs/FINANCIAL_PLAN_MODEL.md` → Task 9

**Type consistency** — checked `PlanVersionSnapshot`/`AllocationSnapshot`/`SuballocationSnapshot` field names and types match between their definition (Task 1), their construction in `_snapshot_from_version` (Task 5), and their consumption in API tests (Task 8): `percentage` is `str` throughout the read side, `Decimal` throughout the write side (`AllocationInput`/`SuballocationInput`), with no mixing.

**No placeholders** — every step has complete, runnable code; no "add error handling here" or "similar to Task N" shortcuts.
