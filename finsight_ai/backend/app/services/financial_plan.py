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
                    f"Suballocations under {alloc.bucket_name!r} sum to {sub_total}, "
                    f"expected {alloc.percentage}."
                )

    if total != _HUNDRED:
        raise PlanValidationError(f"Allocations sum to {total}%, expected 100%.")


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
