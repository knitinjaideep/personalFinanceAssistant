# Next Month Planner

This is the PR 14 (M6 — Coral redesign) deliverable: deterministic "what to do
next period" recommendations, ranked and capped at 3, built entirely on top
of already-computed, already-tested outputs — Plan vs Actual (PR 04),
Savings Goals (PR 13), and the Investment Contribution Model (PR 11). It
never recomputes a target, actual, or variance itself, and never calls an
LLM to produce a number (`.claude/skills/coral-redesign/references/
accounting-invariants.md` #10; coral-redesign SKILL, "An LLM can explain
facts but must not manufacture the facts").

**This is not an autonomous agent.** Nothing here writes to any plan,
allocation, account, or transaction table. Every recommendation is a
read-only suggestion; PR13's goal-completion recommendation (surfaced here,
not duplicated) already establishes that any structural plan change requires
explicit user approval, and this module carries that discipline forward.

## Module layout

- `app/domain/next_month_planner.py` — pure, DB-free composition engine.
  Consumes an already-computed `PlanVsActualResult`, the Savings bucket's
  `CategoryDrift` rows, `MerchantDriver` rows, a list of `SavingsGoalProgress`,
  and an `InvestmentContributionPlanResult`, and returns a ranked,
  capped-at-3 `NextMonthPlanResult`. Fully unit-testable without a database.
- `app/services/next_month_planner.py` — wires the engine to the database:
  fetches the three input sources via their own existing service functions
  (`app.services.plan_vs_actual`, `app.services.savings_goals`,
  `app.services.investment_plan`) and calls the domain builder. No FastAPI
  imports, matching every other service module in this package.
- `app/api/next_month_planner.py` — one thin route,
  `GET /api/v1/next-month-plan`, reusing `app.api.plan_vs_actual._resolve_period`
  for the shared PR 05 period contract (`start_date`+`end_date` or
  `year`+`month`, both-or-neither).

## Why one endpoint, not three

The work order lists three consumers ("Expose to: Overview -> Next Month
Plan, Banking -> insights/actions, Investments -> contribution plan"). All
three can read the SAME ranked list: every `Recommendation` carries
`action_type` and `bucket`, so a page that only cares about investment
contributions can filter client-side for
`action_type in {increase_investment_contribution, maintain_contribution}`
without a second backend concept. Overview renders the full ranked list.
Banking filters for Needs/Wants/Savings and review-oriented actions.
Investments filters for investment contribution actions. All three surfaces
read the same endpoint and expose the same `source_facts` contract where the
user is closest to action.

## Inputs (all already-honest, never rebuilt here)

1. **Current-period Plan vs Actual** (`app.domain.plan_vs_actual`) —
   `BucketDrift` for Needs/Wants. Needs/Wants have no plan-defined
   category-level targets (see `docs/coral-redesign/BLOCKED.md` decision 2,
   Option B, resolved 2026-08-15), so a `reduce_category` recommendation is
   always anchored at the BUCKET level, and a category/merchant can only ever
   be cited as a *contributor* to that bucket's drift (via
   `compute_merchant_drivers`), never given its own fabricated target.
   `CategoryDrift` for Savings, which DOES have plan-defined suballocation
   targets (Emergency Fund / House-Goals / Child Savings), is the anchor for
   `increase_savings_goal`.
2. **Savings goal progress** (`app.services.savings_goals.list_goal_progress`)
   — goal-level `status`, `data_completeness`, and PR13's own
   `completion_recommendation` (surfaced verbatim as `adjust_plan`, never
   re-derived).
3. **Investment contribution gaps**
   (`app.services.investment_plan.get_investment_contribution_plan`) — each
   vehicle's `recommended_next_month_delta` is read verbatim
   (`abs(variance_amount)` when short of target, `"0.00"` otherwise — already
   computed and tested by PR 11) and used directly as `estimated_impact` for
   `increase_investment_contribution`. This module never recomputes an
   investment delta.

## The 7 action types — 6 built, 1 deferred

| Action type | Built? | Source |
|---|---|---|
| `reduce_category` | Yes | Needs/Wants `BucketDrift` (bucket-anchored) |
| `review_merchant` | Yes | `compute_merchant_drivers` + the concentration-ratio pattern from `app.domain.banking_insights._merchant_insights` |
| `increase_savings_goal` | Yes | Savings `CategoryDrift` (real or synthesized — see below), cross-referenced with `SavingsGoalProgress` |
| `adjust_plan` | Yes | `SavingsGoalProgress.completion_recommendation` (PR 13, surfaced not duplicated) |
| `increase_investment_contribution` | Yes | `InvestmentContributionVehicle.recommended_next_month_delta` (verbatim) |
| `maintain_contribution` | Yes | `InvestmentContributionVehicle` rows with `status == on_track` |
| `review_subscription` | **No — deferred** | see below |

**Why `review_subscription` is deferred:** it requires detecting a recurring
charge and its trend across multiple months. No reusable multi-month
trend-detection primitive exists anywhere in the domain layer today — this is
the exact same gap that left PR10's `unusual_spending_spike` and
`recurring_charge_increase` insight types declared but never built. Building
one bespoke to this PR, untested against real multi-month data and without
its own dedicated review, would be exactly the kind of new, unaudited
financial computation this module otherwise refuses to do. `RecommendationActionType.REVIEW_SUBSCRIPTION`
is declared in the enum for API forward-compatibility but this module never
emits it — the same "declare but don't fabricate" discipline PR10 already
established for its own two unbuilt insight types.

## The "don't make up the full historical shortfall" rule

Every `estimated_impact` in this module is **this period's own** target-vs-
actual gap — never a cumulative historical shortfall. This is carried
forward exactly from the precedent already set by
`app.domain.overview_insights.build_next_month_plan` (its own `estimated_impact`
is documented as "this period's own gap, not cumulative historical debt").

This matters most for savings goals: `SavingsGoalProgress.variance_amount` is
deliberately **cumulative** since the goal's `effective_date` (which, for the
three seeded default goals, is `GOAL_EPOCH = 2000-01-01` — see
`app.services.savings_goals` module docstring). Using that number directly as
`estimated_impact` would recommend "make up a decade of shortfall in one
month," which is explicitly the behavior the work order forbids. Instead,
`increase_savings_goal` recommendations are anchored on the Savings bucket's
per-period `CategoryDrift` row for that goal's category — the exact number
Plan vs Actual already shows for "this period" — never on the goal's own
cumulative fields.

One wrinkle: `compute_category_breakdown` only emits a `CategoryDrift` row for
a category that has at least one transaction in the period (see
`aggregate_category_actuals`). A goal that received **zero** contributions
this period — arguably the most common "behind" case — would otherwise be
invisible to the planner entirely. `_synthetic_savings_category_row()`
handles this by computing `target = plannable_income * target_percentage /
100` (the identical formula `app.domain.plan_vs_actual._drift` already uses
for every other target-percentage row) against the goal's own
`target_percentage_of_income`, with `actual = 0`. This is not a new financial
calculation — it is the same formula, applied to an already-authoritative
percentage, only when the real engine produced no row to reuse. It returns
`None` (skip, never fabricate) when the goal has no measurable percentage
target or no income was observed this period.

Similarly, `adjust_plan` (goal completion) always cites **this period's**
target for that category (from the same `CategoryDrift` row) as
`estimated_impact`, never the goal's cumulative `current_amount` /
`target_amount_effective` — citing those would misrepresent the scale of
"how much could be redirected next period" by orders of magnitude for an
old goal.

## Ranking formula

`impact x deviation x confidence x actionability` — the coral-redesign
SKILL's own "Coral Insights" formula, generalized from
`app.domain.banking_insights._score` (cited in this codebase as the module
that most literally implements the skill's formula) and reused verbatim as
the canonical ranking function across all three input sources in this
module, rather than `overview_insights._sort_key`'s narrower, single-purpose
dollar-first tuple ordering (which exists specifically for on-page insight
cards, not cross-source recommendation ranking).

- **impact** — the (always period-scoped, never cumulative) dollar gap.
- **deviation** — how far off target as a percentage-point / concentration-
  ratio multiplier (e.g. a merchant's share of its bucket's spend).
- **confidence** — `_confidence_for_count()` (transaction-count-based,
  mirrors `app.domain.banking_insights._confidence_for_transactions`)
  multiplied by `_completeness_multiplier()` (see below).
- **actionability** — a fixed weight per candidate shape (e.g. `1.00` for a
  direct spend cut, `0.40` for a "keep doing what you're doing" maintenance
  nudge, `0.60` for a plan-review suggestion that needs explicit approval).

## Completeness-composition policy

Every underlying number is already honestly labeled by its own source
(`CompletenessMetadata.is_complete`, `GoalCompletenessMetadata.is_complete`,
`ContributionDataCompleteness.is_complete`). This module's own job is only to
compose candidates from three different sources into one ranked list without
either fabricating anything or letting an incomplete source quietly win:

1. **A recommendation is never emitted when its source has no measurable
   number at all.** A `BucketDrift` with `status == UNKNOWN` (e.g. no income
   observed this period) is excluded by every candidate builder before it
   ever reaches ranking. A `CategoryDrift`/synthesized row with
   `target_amount is None` is skipped. An `adjust_plan` candidate is skipped
   when the goal's category has no measurable per-period target. This is
   "skip the candidate," never "invent a number."
2. **A recommendation whose source DOES have a number, but that source
   reports itself incomplete, is still emitted — but never silently.** The
   gap is always spelled out in `source_facts` (a `"Data completeness
   caveat"` fact quoting the source's own `notes`) AND the candidate's
   `confidence` term is discounted via `_completeness_multiplier()`
   (`1.00` when complete, `0.60` when not) before ranking. This discount is
   real, not cosmetic — it lowers `rank_score` exactly like a genuine
   low-confidence signal would, which is the concrete mechanism that
   prevents an incomplete source's candidate from silently outranking a
   complete source's candidate. `Recommendation.incomplete_source` mirrors
   this for any consumer that wants to render a visual caveat without
   parsing `source_facts`.

## Selection: max 3, no repeated action type, no repeated bucket

After ranking, candidates are picked greedily: at most one recommendation
per `action_type` (never repeat the same kind of advice across all 3 slots)
and at most one recommendation per `bucket` (a bucket-scoped and a
category-scoped recommendation on the same bucket describe overlapping
dollars — the same anti-double-counting discipline as
`app.domain.overview_insights._SelectionGuard`, generalized here across
action types rather than just scope). `MAX_RECOMMENDATIONS = 3` is not
caller-configurable, per the work order and every other insights surface in
this redesign.

## `Recommendation` fields

| Field | Notes |
|---|---|
| `title` | Short, dollar-first headline. |
| `reason` | One or two sentences explaining the gap. For `adjust_plan`, this is PR13's own `GoalCompletionRecommendation.message`, quoted verbatim. |
| `estimated_impact` | Unsigned dollar string. Always this period's own gap (see above). |
| `priority` | 1-based, assigned after ranking (1 = highest). |
| `action_type` | One of `RecommendationActionType`. |
| `source_facts` | List of `{label, value}` pairs citing the exact numbers this recommendation is based on — nothing here can be read as an unsupported claim. |
| `bucket` | Additive (not in the work order's minimal field list) — lets Banking/Investments filter the shared list client-side. |
| `category` | Additive — the category/vehicle/merchant this recommendation concerns, when applicable. |
| `incomplete_source` | True when the underlying data is itself incomplete (see completeness-composition policy above). |

## LLM involvement

None, this round. Every field is template-derived Decimal/string
composition. Per the work order's own allowance ("LLM may rewrite a
structured recommendation, but must not invent the math") and the precedent
set by PR10, a template-only v1 is judged sufficient and lower-risk than
adding an LLM restyling pass this round — if one is added later, it must
follow the established hard-fallback-to-template pattern from
`app.services.answer_builder._generate_narrative_from_facts` (precompute the
deterministic template first, LLM only restyles prose, hard fallback on any
failure, and the LLM must never be allowed to touch `estimated_impact`,
`action_type`, `priority`, or `source_facts`).

## API contract

`GET /api/v1/next-month-plan`

Query params (identical to `GET /api/v1/plan-vs-actual`, PR 05's shared
period contract):

- `start_date` + `end_date` (ISO dates, both-or-neither), **or**
- `year` + `month` (a single whole calendar month)
- `account_id` (optional) — narrows every underlying input the same way it
  narrows Plan vs Actual (see `app.services.plan_vs_actual.get_plan_vs_actual`).
  Savings goal progress is NOT account-scoped (goals are household-level by
  design), so `account_id` only narrows the Plan vs Actual / merchant /
  investment inputs.

Response: `NextMonthPlanResult` — `{ period, recommendations: Recommendation[] }`
(0–3 items).

## Frontend

Overview, Banking, and Investments are wired to this endpoint through the
shared `frontend-next/components/overview/NextMonthPlanSection.tsx`
component and `frontend-next/features/overview/api.ts`. The section renders
`title` / `reason` / `estimated_impact` / an icon keyed on `action_type`,
with loading/empty/error states matching the rest of the codebase. Banking,
Investments, and Monthly Close pass `showSourceFacts` so the exact
backend-supplied facts are visible on action/audit surfaces. No financial
computation happens in the component — every number is already-computed
backend output.

The OLD `app.domain.overview_insights.build_next_month_plan` /
`NextMonthPlanItem` (a 4-action-type, single-period-only preview, explicitly
documented in its own docstring as "NOT the full Next Month Planner — see
PR14") is left in place but orphaned: nothing in the backend calls it after
this change (`app.services.overview.get_overview_insights` still calls
`build_overview_insights`, whose `next_month_plan` field is populated but no
longer read by the frontend). It was not deleted, since
`OverviewInsightsResult.next_month_plan` remains part of that endpoint's
response contract and removing it is out of this PR's scope.
