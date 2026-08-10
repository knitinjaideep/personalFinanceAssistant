# Financial Plan Domain Model — Design

Date: 2026-08-10
Status: Approved, ready for implementation planning

## Goal

Coral needs to represent the user's *intended* allocation of income (Needs/Wants/Savings/Investments, with nested breakdowns) separately from *actual* transactions. Plans must be versioned and effective-dated, so historical months are always evaluated against whichever plan version was in force at that time, and editing a not-yet-effective future version never rewrites how past months are judged.

This phase builds the domain model, persistence, service API, and HTTP endpoints only. It does **not** build the PLAN-vs-ACTUAL comparison UI, does not touch the chatbot, and does not touch existing parsing/ingestion/transaction tables.

## Explicit non-goals for this PR

- No frontend UI beyond what's needed to sanity-check the API manually (no redesigned dashboard, no static plan constants in the frontend).
- No `financial_goal` table (target dollar amounts / target dates / progress tracking). Deferred — nothing in this phase computes progress against a goal, so building the table now would be unused schema. Revisit when a feature actually consumes it.
- No multi-plan support (no scenario planning, no "which plan is active" selection). Coral is single-user/local-first; one `financial_plans` row is the permanent container, versioned over time.
- No recursive/arbitrary-depth allocation tree. Fixed 2 levels: `plan_allocations` (top-level buckets) → `plan_suballocations` (children). Matches every example given (Needs/Wants have no children; Savings/Investments each have exactly one level of children).
- No Alembic. The repo has no `alembic.ini`/migrations wired up despite the dependency being installed transitively — the existing pattern (`app/db/engine.py::_apply_migrations`, idempotent `ALTER TABLE ... ADD COLUMN` driven by a `_COLUMN_MIGRATIONS` list) is what's actually live, so new tables just need `create_all` (SQLModel picks up new table classes automatically) — no migration entries needed for brand-new tables, only for future column additions to them.
- No changes to `chat_router.py`, `sql_query.py`, or any chat/streaming code path.

## Decisions made during brainstorming (see conversation for rationale)

1. **Single master plan, versioned over time** — not multiple named/scenario plans.
2. **Percentages only, no goal-tracking dollar amounts** — `financial_goal` deferred.
3. **Fixed 2-level tree** — `plan_allocations` (buckets) + `plan_suballocations` (children of a bucket), not a self-referencing recursive structure.

## 1. Data model (`app/db/models.py`)

Follows the existing convention exactly: `*Model` class name, plural-snake `__tablename__`, `str` UUID primary keys via the existing `_uuid()` factory, `datetime` timestamps via `_now()`, and monetary/rate-like values stored as `str`-encoded `Decimal` (matching `apr`, `management_fee_rate`, `performance_ytd` elsewhere) rather than `float`, to avoid the same binary-float precision problems the codebase already avoids for money.

```python
class FinancialPlanModel(SQLModel, table=True):
    __tablename__ = "financial_plans"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = "Master Plan"
    is_active: bool = True
    created_at: datetime = Field(default_factory=_now)

    versions: list["FinancialPlanVersionModel"] = Relationship(back_populates="plan")


class FinancialPlanVersionModel(SQLModel, table=True):
    __tablename__ = "financial_plan_versions"

    id: str = Field(default_factory=_uuid, primary_key=True)
    plan_id: str = Field(foreign_key="financial_plans.id", index=True)
    version_number: int  # sequential per plan, starting at 1
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
    bucket_name: str  # free string — NOT an enum, this is what makes custom buckets free
    percentage: str  # Decimal as string, e.g. "50", "20", "15", "15"
    sort_order: int = 0

    plan_version: Optional[FinancialPlanVersionModel] = Relationship(back_populates="allocations")
    suballocations: list["PlanSuballocationModel"] = Relationship(back_populates="allocation")


class PlanSuballocationModel(SQLModel, table=True):
    """Child of a plan_allocation. Percentage is of the TOTAL plan, not of the parent's share."""
    __tablename__ = "plan_suballocations"

    id: str = Field(default_factory=_uuid, primary_key=True)
    allocation_id: str = Field(foreign_key="plan_allocations.id", index=True)
    name: str  # e.g. "Emergency Fund"
    percentage: str  # Decimal as string, e.g. "5"
    sort_order: int = 0

    allocation: Optional[PlanAllocationModel] = Relationship(back_populates="suballocations")
```

**No `effective_until` column.** A version's "active window" is derived at query time as `[effective_from, next_version.effective_from)` — storing an end date redundantly risks it drifting out of sync when versions are inserted/edited. `get_plan_for_date` computes this by finding the latest version with `effective_from <= target_date`.

**Suballocation percentage semantics**: `PlanSuballocationModel.percentage` is a share of the *whole plan* (e.g. Emergency Fund = `"5"`, House/Goals = `"5"`, Child Savings = `"5"`), not a share of the parent bucket. This matches the example directly (Savings=15% and its three children sum to 15) and makes validation a single flat-sum check instead of a percentage-of-percentage calculation.

## 2. Seeding (`app/db/engine.py` + `app/services/financial_plan.py`)

`init_db()` gets one new line after `create_all` and `init_fts()`:

```python
from app.services.financial_plan import seed_default_plan_if_missing
await seed_default_plan_if_missing()
```

`seed_default_plan_if_missing()` opens its own session (matching the `availability.py` pattern), checks `SELECT COUNT(*) FROM financial_plans`, and does nothing if any row exists. If none exists, it inserts:

- `FinancialPlanModel(name="Master Plan")`
- One `FinancialPlanVersionModel(version_number=1, effective_from=PLAN_EPOCH)`, where `PLAN_EPOCH = date(2000, 1, 1)` is a module-level constant — far enough in the past that the default plan resolves for all existing historical transaction data until the user creates a real V2.
- Four `PlanAllocationModel` rows: `needs` (50), `wants` (20), `savings` (15), `investments` (15)
- Three `PlanSuballocationModel` rows under `savings`: `Emergency Fund` (5), `House / Goals` (5), `Child Savings` (5)
- Four `PlanSuballocationModel` rows under `investments`: `401(k)` (6), `Roth IRA` (4), `ESPP` (3), `Taxable Brokerage` (2)

This is seed data, not a static frontend constant — it lives in the DB and is only ever written once, at first boot with an empty table.

## 3. Service layer (`app/services/financial_plan.py`)

No FastAPI imports. Functions take an `AsyncSession` as their first parameter, mirroring `repositories.py`, so the API layer opens a session (`async with get_session() as session:`) and passes it through — this is what "not coupled to HTTP" means concretely: the service is equally callable from a future chat-domain handler (e.g. an affordability-style pipeline asking "am I within plan?") without touching FastAPI at all.

```python
async def get_plan_for_date(session, target_date: date) -> PlanSnapshot | None
async def get_current_plan(session) -> PlanSnapshot | None
async def list_plan_versions(session, plan_id: str | None = None) -> list[PlanVersionSummary]
async def create_plan_version(
    session, plan_id: str, effective_from: date,
    allocations: list[AllocationInput], notes: str | None = None,
) -> PlanSnapshot
async def update_plan_version(
    session, version_id: str, allocations: list[AllocationInput],
) -> PlanSnapshot
def validate_plan(allocations: list[AllocationInput]) -> None  # raises PlanValidationError
async def seed_default_plan_if_missing(session=None) -> None
```

Where `AllocationInput` is a small dataclass/Pydantic shape carrying `bucket_name`, `percentage`, and a list of `(name, percentage)` suballocation tuples — defined in `domain/entities.py` alongside the other pure Pydantic contracts. `PlanSnapshot` is the read-side shape: the version plus its fully nested allocations/suballocations, returned by both `get_plan_for_date`/`get_current_plan` and the mutating calls (so the API can return the same shape from GET and POST/PATCH).

**Versioning rules enforced here:**

- `get_plan_for_date`: `SELECT * FROM financial_plan_versions WHERE plan_id = :active_plan_id AND effective_from <= :target_date ORDER BY effective_from DESC LIMIT 1`. Returns `None` if no version has an `effective_from` on or before the target date (API translates to 404).
- `create_plan_version`: `version_number = max(existing) + 1`. Rejects a duplicate `effective_from` for the same plan with `DuplicateEffectiveDateError` — two versions can't both claim to start on the same day, which would make resolution ambiguous.
- `update_plan_version`: **only permitted when the version's `effective_from` is strictly after `date.today()`.** Attempting to edit a version that is currently active or was active in the past raises `PlanVersionImmutableError`. This is the mechanism that satisfies "editing a future plan doesn't rewrite history" — the only way to change what's in effect today onward is to `create_plan_version` with a new `effective_from`, leaving every prior version's rows untouched.
- `validate_plan`: pure, no DB access.
  - Top-level `percentage` values must sum to exactly `Decimal("100")`.
  - Each bucket's suballocation percentages, if any, must sum to exactly that bucket's own `percentage`.
  - No negative percentages; zero is allowed (a temporarily-disabled custom bucket).
  - No duplicate `bucket_name` values within a version; no duplicate suballocation `name` within a bucket.
  - Raises `PlanValidationError` with a message identifying which rule failed.

## 4. Domain errors (`app/domain/errors.py`)

New section, same pattern as existing sections (plain `CoralError` subclasses, some carrying structured `details`):

```python
# ── Financial Plan ───────────────────────────────────────────────────────────

class PlanValidationError(CoralError):
    """Plan allocation percentages fail validation (don't sum to 100, duplicates, negatives)."""

class PlanVersionImmutableError(CoralError):
    """Cannot edit a plan version that is already active or was active in the past."""

class DuplicateEffectiveDateError(CoralError):
    """A plan version with this effective_from already exists for this plan."""
```

`EntityNotFoundError` (already exists) is reused for "no plan/version found" cases — no new not-found type needed.

## 5. API (`app/api/financial_plan.py`, registered in `main.py`)

Same shape as `catalog.py`: plain `APIRouter`, functions open their own session via `get_session()`, domain errors caught and translated to `HTTPException`.

```
GET   /api/v1/financial-plan/current
      → current PlanSnapshot, 404 if none resolves for today

GET   /api/v1/financial-plan?date=YYYY-MM-DD
      → PlanSnapshot active on that date, 404 if none resolves

GET   /api/v1/financial-plan/versions
      → list of PlanVersionSummary (id, version_number, effective_from, notes) for the master plan, newest first

POST  /api/v1/financial-plan/versions
      → body: { effective_from, allocations: [...], notes? }
      → creates a new version on the master plan; 422 on validation failure (bad percentages),
        409 on duplicate effective_from

PATCH /api/v1/financial-plan/versions/{version_id}
      → body: { allocations: [...] }
      → 409 if the version is not strictly in the future (PlanVersionImmutableError)
```

`prefix="/api/v1/financial-plan"`, `tags=["financial-plan"]` — matches the singular-resource naming already used for `dashboard`/`catalog` rather than a plural collection name, since "the plan" reads as one long-lived resource with a version history, not a bag of independent records.

## 6. Tests (`backend/tests/test_financial_plan.py`)

Reuses the existing `temp_db` fixture (isolated file-backed SQLite per test). Covers, at minimum, every case from the requirements:

1. Default plan seeds on first `init_db()` and totals exactly 100%.
2. Savings suballocations total exactly 15%.
3. Investments suballocations total exactly 15%.
4. `get_plan_for_date` resolves the correct version for a date between two versions' `effective_from`.
5. Historical resolution: querying a date before any version's `effective_from` returns `None`/404; querying a date covered by an old version returns that old version even after a newer one exists.
6. Invalid percentages (sums ≠ 100, negative values, mismatched suballocation sum) are rejected by `validate_plan` / surfaced as 422 from the POST endpoint.
7. Overlapping/duplicate `effective_from` on `create_plan_version` raises `DuplicateEffectiveDateError` (409 at the API layer).
8. Editing a future version via `update_plan_version` succeeds and does not change what `get_plan_for_date` returns for dates in the past/present; attempting to edit a past-or-active version raises `PlanVersionImmutableError` (409 at the API layer).

## 7. Documentation

`docs/FINANCIAL_PLAN_MODEL.md` — new file, describing: the 4-table model and why suballocation percentages are "of total" rather than "of parent," the effective-dating/versioning semantics (including the immutability rule), the seed defaults, the service API surface, and the HTTP endpoints. Cross-referenced from `CLAUDE.md`'s Key Modules section the same way `README_ARCHITECTURE.md` is.
