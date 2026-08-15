import { describe, expect, it } from "vitest";
import {
  buildBudgetDriftRows,
  buildTopDriverCandidates,
  buildTopDriverGroup,
  type TopDriverCandidate,
} from "./bankingDrift";
import type { CategoryDrift, MerchantDriver } from "@/features/banking/api";
import type { BucketDrift } from "@/features/overview/api";

// ── Fixtures ─────────────────────────────────────────────────────────────
// Mirror backend/app/domain/plan_vs_actual.py shapes exactly (decimal
// amounts as strings) so the adapter under test sees the same input shape it
// does in production.

function categoryRow(category: string, overrides: Partial<CategoryDrift> = {}): CategoryDrift {
  return {
    bucket: "needs",
    category,
    target_percentage: "10",
    actual_percentage: "10",
    target_amount: "500.00",
    actual_amount: "500.00",
    variance_amount: "0.00",
    variance_percentage_points: "0.00",
    status: "on_track",
    transaction_count: 4,
    ...overrides,
  };
}

function merchant(name: string, amount: string, overrides: Partial<MerchantDriver> = {}): MerchantDriver {
  return {
    merchant: name,
    bucket: "wants",
    category: "Shopping",
    amount,
    transaction_count: 1,
    ...overrides,
  };
}

function bucketDrift(bucket: BucketDrift["bucket"], overrides: Partial<BucketDrift> = {}): BucketDrift {
  return {
    bucket,
    target_percentage: "20",
    actual_percentage: "20",
    target_amount: "1000.00",
    actual_amount: "1000.00",
    variance_amount: "0.00",
    variance_percentage_points: "0.00",
    status: "on_track",
    transaction_count: 10,
    ...overrides,
  };
}

// ── buildBudgetDriftRows ─────────────────────────────────────────────────

describe("buildBudgetDriftRows", () => {
  it("returns an empty list for all-null inputs", () => {
    expect(buildBudgetDriftRows(null, null, null)).toEqual([]);
  });

  it("merges needs/wants/savings rows, tagging each with its bucket", () => {
    const rows = buildBudgetDriftRows(
      [categoryRow("Housing", { bucket: "needs" })],
      [categoryRow("Dining", { bucket: "wants" })],
      [categoryRow("Emergency Fund", { bucket: "savings" })],
    );
    expect(rows.map((r) => r.bucket)).toEqual(["Housing", "Dining", "Emergency Fund"].map((_, i) => ["needs", "wants", "savings"][i]));
  });

  it("copies target/actual $ and % straight from the backend row, never recomputing", () => {
    const rows = buildBudgetDriftRows(
      [categoryRow("Housing", { target_amount: "1500.00", actual_amount: "1800.00", target_percentage: "25", actual_percentage: "30", variance_amount: "300.00" })],
      null,
      null,
    );
    expect(rows[0]).toMatchObject({
      targetAmount: 1500,
      actualAmount: 1800,
      targetPercentage: 25,
      actualPercentage: 30,
      varianceAmount: 300,
    });
  });

  it("computes adverseAmount = varianceAmount for a Needs category (consumption, overspend is adverse)", () => {
    const rows = buildBudgetDriftRows(
      [categoryRow("Housing", { variance_amount: "150.00" })],
      null,
      null,
    );
    expect(rows[0].adverseAmount).toBe(150);
  });

  it("computes adverseAmount = varianceAmount for a Wants category (consumption)", () => {
    const rows = buildBudgetDriftRows(
      null,
      [categoryRow("Dining", { bucket: "wants", variance_amount: "-40.00" })],
      null,
    );
    // Under-target Wants is not adverse -> negative adverseAmount, sorts low.
    expect(rows[0].adverseAmount).toBe(-40);
  });

  it("flips the sign for Savings (accumulation): a shortfall (negative variance) is adverse", () => {
    const rows = buildBudgetDriftRows(
      null,
      null,
      [categoryRow("Emergency Fund", { bucket: "savings", variance_amount: "-200.00" })],
    );
    expect(rows[0].adverseAmount).toBe(200);
  });

  it("flips the sign for Savings so an overshoot (positive variance) is NOT adverse", () => {
    const rows = buildBudgetDriftRows(
      null,
      null,
      [categoryRow("Emergency Fund", { bucket: "savings", variance_amount: "500.00" })],
    );
    expect(rows[0].adverseAmount).toBe(-500);
  });

  it("sets adverseAmount null when variance is null (no target this period) — never fabricated", () => {
    const rows = buildBudgetDriftRows(
      [categoryRow("Uncategorized", { target_amount: null, target_percentage: null, variance_amount: null, status: "unknown" })],
      null,
      null,
    );
    expect(rows[0].adverseAmount).toBeNull();
  });

  it("sorts by adverseAmount descending — most off-plan first, across mixed buckets", () => {
    const rows = buildBudgetDriftRows(
      [categoryRow("Housing", { variance_amount: "50.00" })], // adverse +50
      [categoryRow("Dining", { bucket: "wants", variance_amount: "400.00" })], // adverse +400
      [categoryRow("Emergency Fund", { bucket: "savings", variance_amount: "-100.00" })], // adverse +100
    );
    expect(rows.map((r) => r.category)).toEqual(["Dining", "Emergency Fund", "Housing"]);
  });

  it("never lets a large-but-not-adverse variance outrank a smaller genuinely-adverse one (Savings overshoot vs Needs overspend)", () => {
    const rows = buildBudgetDriftRows(
      [categoryRow("Housing", { variance_amount: "50.00" })], // adverse +50
      null,
      [categoryRow("Emergency Fund", { bucket: "savings", variance_amount: "900.00" })], // adverse -900 (overshoot, good)
    );
    // Housing (genuinely $50 over plan) outranks Emergency Fund's $900
    // overshoot, even though 900 > 50 in raw magnitude.
    expect(rows.map((r) => r.category)).toEqual(["Housing", "Emergency Fund"]);
  });

  it("sorts adverseAmount:null rows last, preserving original per-bucket merge order", () => {
    const rows = buildBudgetDriftRows(
      [
        categoryRow("Housing", { variance_amount: "50.00" }),
        categoryRow("NoTargetNeed", { variance_amount: null, target_amount: null, status: "unknown" }),
      ],
      [categoryRow("AnotherNoTarget", { bucket: "wants", variance_amount: null, target_amount: null, status: "unknown" })],
      null,
    );
    expect(rows.map((r) => r.category)).toEqual(["Housing", "NoTargetNeed", "AnotherNoTarget"]);
  });

  it("tie-breaks equal adverseAmount by original merge order (stable sort)", () => {
    const rows = buildBudgetDriftRows(
      [categoryRow("Housing", { variance_amount: "100.00" })],
      [categoryRow("Dining", { bucket: "wants", variance_amount: "100.00" })],
      null,
    );
    expect(rows.map((r) => r.category)).toEqual(["Housing", "Dining"]);
  });

  it("status is copied verbatim from the backend row, never recomputed here", () => {
    const rows = buildBudgetDriftRows(
      [categoryRow("Housing", { status: "off_track" })],
      null,
      null,
    );
    expect(rows[0].status).toBe("off_track");
  });
});

// ── buildTopDriverCandidates ─────────────────────────────────────────────
// Decision 2 (RESOLVED — Option B): Top Drivers is anchored on BUCKET-level
// drift, not category-level (which is always null for Needs/Wants — see
// bankingDrift.ts's module docstring).

describe("buildTopDriverCandidates", () => {
  it("returns an empty list for null/empty input", () => {
    expect(buildTopDriverCandidates(null)).toEqual([]);
    expect(buildTopDriverCandidates([])).toEqual([]);
  });

  it("surfaces an off-plan Wants bucket (actual > target, positive variance) as a candidate", () => {
    const candidates = buildTopDriverCandidates([
      bucketDrift("wants", { target_amount: "1000.00", actual_amount: "1400.00", variance_amount: "400.00", status: "off_track" }),
    ]);
    expect(candidates).toEqual([
      {
        bucket: "wants",
        targetAmount: 1000,
        targetPercentage: 20,
        actualAmount: 1400,
        actualPercentage: 20,
        driftAmount: 400,
        status: "off_track",
      },
    ]);
  });

  it("does NOT surface an on-plan bucket (variance <= 0) as a candidate", () => {
    const onTarget = buildTopDriverCandidates([bucketDrift("wants", { variance_amount: "0.00" })]);
    const underTarget = buildTopDriverCandidates([bucketDrift("needs", { variance_amount: "-120.00" })]);
    expect(onTarget).toEqual([]);
    expect(underTarget).toEqual([]);
  });

  it("excludes Savings and Investments buckets entirely, even when adverse — Banking answers 'where did my cash go', not 'am I saving/investing on plan'", () => {
    const candidates = buildTopDriverCandidates([
      bucketDrift("savings", { variance_amount: "-500.00" }), // shortfall would be "adverse" for savings, but must never appear
      bucketDrift("investments", { variance_amount: "300.00" }),
      bucketDrift("wants", { variance_amount: "150.00" }),
    ]);
    expect(candidates.map((c) => c.bucket)).toEqual(["wants"]);
  });

  it("excludes a bucket with no target this period (variance null) rather than fabricating a candidate", () => {
    const candidates = buildTopDriverCandidates([
      bucketDrift("needs", { variance_amount: null, target_amount: null, status: "unknown" }),
    ]);
    expect(candidates).toEqual([]);
  });

  it("ignores an 'unclassified' bucket row even if one is ever emitted — only real plan-targeted consumption buckets qualify", () => {
    const candidates = buildTopDriverCandidates([
      bucketDrift("unclassified", { variance_amount: "900.00" }),
      bucketDrift("needs", { variance_amount: "100.00" }),
    ]);
    expect(candidates.map((c) => c.bucket)).toEqual(["needs"]);
  });

  it("sorts candidates by largest drift $ first", () => {
    const candidates = buildTopDriverCandidates([
      bucketDrift("needs", { variance_amount: "100.00" }),
      bucketDrift("wants", { variance_amount: "400.00" }),
    ]);
    expect(candidates.map((c) => c.bucket)).toEqual(["wants", "needs"]);
  });

  it("respects the limit parameter", () => {
    const candidates = buildTopDriverCandidates(
      [bucketDrift("needs", { variance_amount: "100.00" }), bucketDrift("wants", { variance_amount: "400.00" })],
      1,
    );
    expect(candidates).toHaveLength(1);
    expect(candidates[0].bucket).toBe("wants");
  });
});

// ── buildTopDriverGroup ──────────────────────────────────────────────────

function candidate(overrides: Partial<TopDriverCandidate> = {}): TopDriverCandidate {
  return {
    bucket: "wants",
    targetAmount: 1000,
    targetPercentage: 20,
    actualAmount: 1400,
    actualPercentage: 28,
    driftAmount: 400,
    status: "off_track",
    ...overrides,
  };
}

describe("buildTopDriverGroup", () => {
  it("builds the example shape: Wants +$400, Amazon $250, Target $100, Other $50", () => {
    const c = candidate({ actualAmount: 400, driftAmount: 400 });
    const merchants = [merchant("Amazon", "250.00"), merchant("Target", "100.00")];
    const group = buildTopDriverGroup(c, merchants);
    expect(group.bucket).toBe("wants");
    expect(group.driftAmount).toBe(400);
    expect(group.merchants).toEqual([
      { merchant: "Amazon", category: "Shopping", amount: 250 },
      { merchant: "Target", category: "Shopping", amount: 100 },
    ]);
    expect(group.other).toBe(50);
  });

  it("exposes the bucket's actual $ separately from its drift $ — the merchant rows decompose actual, never drift", () => {
    // target 1000 / actual 1400 => drift +400. The merchant rows must
    // reconcile to 1400 (actual), NOT to 400 (drift) — there is no
    // per-merchant target, so drift cannot be attributed to individual
    // merchants. This is the "no false reconciliation" invariant: the
    // merchant list sums independently of, not equal to, the bucket's drift.
    const c = candidate({ targetAmount: 1000, actualAmount: 1400, driftAmount: 400 });
    const merchants = [merchant("Amazon", "900.00"), merchant("Target", "300.00")];
    const group = buildTopDriverGroup(c, merchants);
    expect(group.driftAmount).toBe(400);
    expect(group.actualAmount).toBe(1400);
    const merchantSum = group.merchants.reduce((s, m) => s + m.amount, 0);
    expect(merchantSum).not.toBe(group.driftAmount);
    const decomposed = merchantSum + (group.other ?? 0);
    expect(decomposed).toBe(1400);
  });

  it("omits Other (null) when merchants already cover the full bucket amount", () => {
    const c = candidate({ actualAmount: 350 });
    const merchants = [merchant("Amazon", "250.00"), merchant("Target", "100.00")];
    const group = buildTopDriverGroup(c, merchants);
    expect(group.other).toBeNull();
  });

  it("suppresses a sub-dollar residual (below display precision) rather than rendering 'Other $0'", () => {
    const c = candidate({ actualAmount: 350.4 });
    const merchants = [merchant("Amazon", "250.00"), merchant("Target", "100.00")];
    const group = buildTopDriverGroup(c, merchants);
    expect(group.other).toBeNull();
  });

  it("preserves a genuinely negative residual (refund-heavy un-shown tail) so the decomposition still reconciles", () => {
    // The un-shown merchants net to -$50 (refunds exceeded purchases there).
    // Dropping it would make 250 + 100 read as the whole $300 bucket actual.
    const c = candidate({ actualAmount: 300 });
    const merchants = [merchant("Amazon", "250.00"), merchant("Target", "100.00")];
    const group = buildTopDriverGroup(c, merchants);
    expect(group.other).toBe(-50);
    const decomposed = group.merchants.reduce((s, m) => s + m.amount, 0) + (group.other ?? 0);
    expect(decomposed).toBe(300);
  });

  it("suppresses a sub-dollar NEGATIVE residual too (rounding artifact, not real money)", () => {
    const c = candidate({ actualAmount: 349.7 });
    const merchants = [merchant("Amazon", "250.00"), merchant("Target", "100.00")];
    const group = buildTopDriverGroup(c, merchants);
    expect(group.other).toBeNull();
  });

  it("copies status straight from the candidate, never recomputed here", () => {
    const c = candidate({ status: "watch" });
    const group = buildTopDriverGroup(c, []);
    expect(group.status).toBe("watch");
  });

  it("keeps the same merchant name appearing under two categories as two distinct rows (whole-bucket fetch), without merging their $", () => {
    // `bankingApi.merchantDrivers(bucket, null, …)` groups by
    // (merchant, bucket, category), so one bucket can legitimately return
    // Amazon twice. Merging them would re-aggregate backend-authoritative
    // totals in the frontend; dropping one would lose money from the
    // decomposition. Both rows survive, each carrying its own category.
    const c = candidate({ actualAmount: 400 });
    const group = buildTopDriverGroup(c, [
      merchant("Amazon", "250.00", { category: "Shopping" }),
      merchant("Amazon", "100.00", { category: "Groceries" }),
    ]);
    expect(group.merchants).toEqual([
      { merchant: "Amazon", category: "Shopping", amount: 250 },
      { merchant: "Amazon", category: "Groceries", amount: 100 },
    ]);
    // Still reconciles to the bucket's actual $, duplicates included.
    expect(group.merchants.reduce((s, m) => s + m.amount, 0) + (group.other ?? 0)).toBe(400);
    // ...and the two rows are distinguishable by a stable composite key.
    const keys = group.merchants.map((m) => `${m.merchant} ${m.category ?? ""}`);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("tolerates a null category on a merchant row (uncategorized driver)", () => {
    const c = candidate({ actualAmount: 250 });
    const group = buildTopDriverGroup(c, [merchant("Amazon", "250.00", { category: null })]);
    expect(group.merchants).toEqual([{ merchant: "Amazon", category: null, amount: 250 }]);
    expect(group.other).toBeNull();
  });

  it("handles an empty merchant list — the full bucket amount becomes Other", () => {
    const c = candidate({ actualAmount: 400 });
    const group = buildTopDriverGroup(c, []);
    expect(group.merchants).toEqual([]);
    expect(group.other).toBe(400);
  });
});
