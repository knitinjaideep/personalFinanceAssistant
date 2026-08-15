/**
 * Banking Drift & Top Drivers — pure data adapter (PR 08,
 * docs/coral-redesign/pr-08-banking-drift.md).
 *
 * Turns already-normalized, backend-computed `CategoryDrift[]` (from
 * GET /api/v1/plan-vs-actual/buckets/{bucket}), `BucketDrift[]` (from
 * GET /api/v1/plan-vs-actual — the same `PlanVsActualResult.buckets` rows
 * BankingFlowTree.tsx already fetches/renders) and `MerchantDriver[]` (from
 * GET /api/v1/plan-vs-actual/merchants) into the row/group shapes
 * `<BudgetDriftTable />` and `<TopDrivers />` render.
 *
 * Intentionally framework-free (no React import) so it can be unit tested in
 * isolation — see bankingDrift.test.ts, matching bankingFlowTree.ts's
 * rigor/style. Never reclassifies a transaction or recomputes a bucket/
 * category total: every dollar here is either copied directly from the
 * backend or a single documented subtraction over numbers the backend
 * already computed (see `buildTopDriverGroup`'s `other` residual below, the
 * only place that happens — same discipline as bankingFlowTree.ts's
 * `buildUnallocatedDetail`).
 *
 * Investments is deliberately excluded — same as PR07's flow tree, Banking's
 * page question is "where did my cash go?", not "am I investing according to
 * plan?" (design-rules.md).
 *
 * ── Two different anchors, on purpose (see docs/coral-redesign/BLOCKED.md,
 * Decision 2, RESOLVED — Option B) ──────────────────────────────────────
 *
 * `_DEFAULT_ALLOCATIONS` (backend/app/services/financial_plan.py) only
 * defines percentage sub-targets for Savings/Investments — Needs and Wants
 * have no per-category targets today, so `compute_category_breakdown`
 * honestly returns `target=null` for every Needs/Wants category. That is
 * real (not a bug), so:
 *
 *   - `buildBudgetDriftRows` (below) stays CATEGORY-anchored — it is "Where
 *     You're Off Plan", a table that must honestly show "No target" for
 *     Needs/Wants categories rather than fabricate one.
 *   - `buildTopDriverCandidates` / `buildTopDriverGroup` are BUCKET-anchored
 *     — Needs/Wants master buckets DO have real plan targets (50%/20% of
 *     income), so Top Drivers is keyed off bucket-level drift and ranks
 *     categories/merchants within an off-plan bucket as *contributors* to
 *     that bucket's drift, never as if they had a target of their own.
 */

import type { CategoryDrift, MerchantDriver } from "@/features/banking/api";
import type { BucketDrift, DriftStatus, MasterBucket } from "@/features/overview/api";

// Consumption buckets (Needs/Wants): overspend is adverse. Accumulation
// (Savings): shortfall is adverse. Mirrors
// backend/app/domain/plan_vs_actual.py::compute_status's own adverse-
// direction convention exactly (and PlanVsActualSection.tsx / BankingFlowTree
// .tsx's identical CONSUMPTION_BUCKETS convention for VarianceBadge
// `direction`) — never a new judgment call, just applying the same polarity
// as a presentation-only sort key over already-backend-computed variance $.
const CONSUMPTION_BUCKETS = new Set<MasterBucket>(["needs", "wants"]);

export type DriftBucket = "needs" | "wants" | "savings";

export interface DriftRow {
  bucket: DriftBucket;
  category: string;
  targetAmount: number | null;
  actualAmount: number;
  targetPercentage: number | null;
  actualPercentage: number | null;
  varianceAmount: number | null;
  status: DriftStatus;
  transactionCount: number;
  /**
   * Presentation-only sort key — NOT a new financial calculation, just a
   * sign convention applied to the backend's own `varianceAmount`:
   *   - Needs/Wants (consumption): adverseAmount = varianceAmount
   *     (positive = overspend = adverse)
   *   - Savings (accumulation): adverseAmount = -varianceAmount
   *     (negative variance = shortfall = adverse, so negate to make
   *     "more adverse" read as "more positive")
   * `null` when the backend reports no target this period (varianceAmount is
   * null) — honestly nothing to call "off plan" rather than fabricating a
   * sort position.
   */
  adverseAmount: number | null;
}

function toNumber(v: string | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function toDriftRow(bucket: DriftBucket, row: CategoryDrift): DriftRow {
  const varianceAmount = toNumber(row.variance_amount);
  const adverseAmount =
    varianceAmount === null ? null : CONSUMPTION_BUCKETS.has(bucket) ? varianceAmount : -varianceAmount;
  return {
    bucket,
    category: row.category,
    targetAmount: toNumber(row.target_amount),
    actualAmount: toNumber(row.actual_amount) ?? 0,
    targetPercentage: toNumber(row.target_percentage),
    actualPercentage: toNumber(row.actual_percentage),
    varianceAmount,
    status: row.status,
    transactionCount: row.transaction_count,
    adverseAmount,
  };
}

/**
 * Merge the three already-fetched per-bucket category breakdowns
 * (Needs/Wants/Savings — Investments intentionally excluded, see module
 * docstring) into one row list, sorted with the largest adverse/most-off-plan
 * category first.
 *
 * Sort semantics (documented explicitly — pr-08-banking-drift.md's "largest
 * negative financial drift first" is ambiguous about literal sign vs.
 * semantic-adverse direction): rows sort by `adverseAmount` DESCENDING —
 * i.e. semantically most off-plan first, not most-negative-`varianceAmount`
 * first. Semantic-adverse is correct per the skill's "avoid treating every
 * over-target Need as inherently bad" instruction — an over-target Need with
 * a small positive `varianceAmount` is genuinely adverse (spent more than
 * planned), while a Savings category with a large positive `varianceAmount`
 * (overshot the goal) is NOT adverse and must not out-rank it just because
 * its raw signed number is bigger. This also guarantees sort order and the
 * backend's own `status` field (on_track/watch/off_track use the identical
 * adverse-direction polarity, see compute_status) never disagree — a
 * `status: off_track` row is never sorted below an `on_track` row in the
 * same bucket type.
 *
 * Rows with `adverseAmount === null` (no target this period) sort last, in
 * their original per-bucket order — never given a fabricated position.
 */
export function buildBudgetDriftRows(
  needsRows: CategoryDrift[] | null,
  wantsRows: CategoryDrift[] | null,
  savingsRows: CategoryDrift[] | null,
): DriftRow[] {
  const rows: DriftRow[] = [
    ...(needsRows ?? []).map((r) => toDriftRow("needs", r)),
    ...(wantsRows ?? []).map((r) => toDriftRow("wants", r)),
    ...(savingsRows ?? []).map((r) => toDriftRow("savings", r)),
  ];

  const withAdverse = rows
    .map((row, index) => ({ row, index }))
    .filter((x) => x.row.adverseAmount !== null);
  const withoutAdverse = rows
    .map((row, index) => ({ row, index }))
    .filter((x) => x.row.adverseAmount === null);

  withAdverse.sort((a, b) => {
    const diff = (b.row.adverseAmount as number) - (a.row.adverseAmount as number);
    if (diff !== 0) return diff;
    return a.index - b.index; // stable tie-break: original merge order
  });
  withoutAdverse.sort((a, b) => a.index - b.index);

  return [...withAdverse.map((x) => x.row), ...withoutAdverse.map((x) => x.row)];
}

// ── Top Drivers (bucket-anchored — Decision 2 / Option B) ──────────────────

/** Needs/Wants only — the only master buckets Top Drivers ever surfaces.
 * Savings/Investments are accumulation buckets (a shortfall, not a
 * merchant, "drives" them), and Banking's own question is "where did my
 * cash go", not "am I on track for savings/investing" — same convention as
 * `CONSUMPTION_BUCKETS` above and BankingFlowTree.tsx / PlanVsActualSection
 * .tsx's identical exclusion. */
export type ConsumptionBucket = "needs" | "wants";

export interface TopDriverCandidate {
  bucket: ConsumptionBucket;
  targetAmount: number | null;
  targetPercentage: number | null;
  actualAmount: number;
  actualPercentage: number | null;
  /** The bucket's own adverse drift $ vs. its plan target — copied directly
   * from `BucketDrift.variance_amount`. Unlike category-level drift for
   * Needs/Wants (always `null`, see module docstring), this is a real,
   * target-backed number: the master buckets have plan-defined targets
   * (50%/20% of income) even though their categories don't. Always strictly
   * positive here (see `buildTopDriverCandidates`'s filter) — Needs/Wants
   * are consumption buckets, so "adverse" and "positive variance" are the
   * same thing, no sign flip needed. */
  driftAmount: number;
  status: DriftStatus;
}

/**
 * Select up to `limit` Needs/Wants buckets that are genuinely off plan this
 * period (`variance_amount > 0`, i.e. actual spend above the bucket's own
 * target), ranked by largest drift $ first. Savings/Investments rows are
 * never candidates, and a bucket with no target this period
 * (`variance_amount === null`, e.g. no income observed) is honestly
 * excluded rather than guessed at — never a fabricated candidate.
 *
 * `buckets` is the exact `PlanVsActualResult.buckets` array
 * (`GET /api/v1/plan-vs-actual`) BankingFlowTree.tsx already fetches for the
 * same period — no new backend call, no reclassification, just a filter +
 * sort over numbers the backend already computed.
 */
export function buildTopDriverCandidates(buckets: BucketDrift[] | null, limit = 3): TopDriverCandidate[] {
  const candidates: TopDriverCandidate[] = [];
  for (const b of buckets ?? []) {
    if (b.bucket !== "needs" && b.bucket !== "wants") continue;
    const driftAmount = toNumber(b.variance_amount);
    if (driftAmount === null || driftAmount <= 0) continue;
    candidates.push({
      bucket: b.bucket,
      targetAmount: toNumber(b.target_amount),
      targetPercentage: toNumber(b.target_percentage),
      actualAmount: toNumber(b.actual_amount) ?? 0,
      actualPercentage: toNumber(b.actual_percentage),
      driftAmount,
      status: b.status,
    });
  }
  candidates.sort((a, b) => b.driftAmount - a.driftAmount);
  return candidates.slice(0, limit);
}

export interface TopDriverMerchant {
  merchant: string;
  /** The backend groups merchant drivers by `(driver_key, bucket, category)`
   * (see `compute_merchant_drivers`), so a whole-bucket fetch (category=null,
   * which is what Top Drivers uses) can legitimately return the SAME merchant
   * name twice — e.g. Amazon under both Wants/Shopping and Wants/Groceries.
   * The category is carried through verbatim so those rows stay distinct and
   * individually labelled, rather than being merged (which would be a
   * frontend re-aggregation) or colliding on a shared render key. */
  category: string | null;
  amount: number;
}

export interface TopDriverGroup {
  bucket: ConsumptionBucket;
  status: DriftStatus;
  /** The bucket's own adverse drift $ vs. plan — the card's headline. This
   * number is shared across EVERY merchant listed below (it is the whole
   * bucket's drift, not any one merchant's); it is not, and must not be
   * presented as, a sum of per-merchant targets — Coral has none. */
  driftAmount: number;
  /** The bucket's total actual $ this period, copied verbatim from the
   * backend row. This — NOT `driftAmount` — is what `merchants` + `other`
   * decompose: Coral has no per-merchant target, so attributing the bucket's
   * drift across individual merchants would be a fabricated allocation. The
   * two figures must therefore be labelled distinctly wherever they are
   * rendered together (see TopDrivers.tsx's DriverCard). */
  actualAmount: number;
  merchants: TopDriverMerchant[];
  /** Residual = bucket actual $ minus the sum of the fetched top merchant $
   * — i.e. exactly the net total of the merchants NOT shown. Usually
   * positive, but genuinely negative when the un-shown tail is refund-heavy
   * (invariant #6), so the sign is preserved rather than clamped away: a
   * dropped negative residual would make the decomposition silently fail to
   * reconcile to `actualAmount`. `null` only when it is too small to render
   * at the displayed precision. */
  other: number | null;
}

// Below the whole-dollar precision `formatCurrency` renders at, so a sub-
// dollar residual would display as "$0" — suppressed rather than shown.
const OTHER_EPSILON = 0.5;

/**
 * Build one Top Drivers card for an already-selected off-plan bucket
 * candidate (see `buildTopDriverCandidates`) plus that bucket's fetched
 * merchant drivers — `compute_merchant_drivers(bucket=…)` with NO category
 * filter (whole-bucket), i.e. `bankingApi.merchantDrivers(bucket, null,
 * period, limit)`. The backend aggregation already excludes internal
 * transfers/card payments; nothing is re-filtered here.
 *
 * `other` is a single documented subtraction over backend-computed numbers
 * (candidate.actualAmount minus the sum of the fetched merchants' amounts)
 * — not a new classification or aggregation pass. Because the backend derives
 * both figures from the identical `_counts_toward_bucket` eligibility gate
 * over the same period, the residual is exactly the net total of the
 * merchants that were not fetched, so `merchants` + `other` always reconciles
 * to `actualAmount` — deliberately NOT to `driftAmount` (the bucket's drift
 * and its actual $ are different numbers; only actual $ decomposes by
 * merchant). Only a residual too small to render at whole-dollar precision
 * is suppressed (to `null`) — never a real one, in either direction,
 * matching bankingFlowTree.ts's "never invent/fabricate and never silently
 * drop a number" discipline.
 */
export function buildTopDriverGroup(candidate: TopDriverCandidate, merchantRows: MerchantDriver[]): TopDriverGroup {
  const merchants = merchantRows.map((m) => ({
    merchant: m.merchant,
    category: m.category,
    amount: Number(m.amount),
  }));
  const merchantTotal = merchants.reduce((sum, m) => sum + m.amount, 0);
  const residual = candidate.actualAmount - merchantTotal;
  const other = Math.abs(residual) >= OTHER_EPSILON ? residual : null;

  return {
    bucket: candidate.bucket,
    status: candidate.status,
    driftAmount: candidate.driftAmount,
    actualAmount: candidate.actualAmount,
    merchants,
    other,
  };
}
