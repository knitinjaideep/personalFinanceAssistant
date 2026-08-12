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
plan_allocations                 (top-level buckets: needs, wants, savings, investments, or custom)
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
bucket's share.** Emergency Fund = 5% (of the whole plan), not 5% of savings'
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
| needs | 50 | | |
| wants | 20 | | |
| savings | 15 | Emergency Fund | 5 |
| | | House / Goals | 5 |
| | | Child Savings | 5 |
| investments | 15 | 401(k) | 6 |
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
