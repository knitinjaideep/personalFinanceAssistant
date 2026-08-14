import { describe, expect, it } from "vitest";
import { buildBankingFlowTree, buildFlowAccessibleSummary } from "./bankingFlowTree";
import type { BucketDrift, CompletenessMetadata, MasterBucket, PlanVsActualResult } from "@/features/overview/api";
import type { CategoryDrift } from "@/features/banking/api";

// ── Fixtures ─────────────────────────────────────────────────────────────
// Mirror backend/app/domain/plan_vs_actual.py shapes exactly (decimal
// amounts as strings, exactly as the real API returns them) so the adapter
// under test sees the same input shape it does in production.

function completeness(overrides: Partial<CompletenessMetadata> = {}): CompletenessMetadata {
  return {
    plan_available: true,
    plan_version_changed_mid_period: false,
    income_observed: true,
    unclassified_transaction_count: 0,
    unclassified_amount: "0.00",
    needs_review_count: 0,
    origin_only_transfer_legs_count: 0,
    origin_only_transfer_legs_amount: "0.00",
    payroll_deduction_signal_detected: false,
    notes: [],
    ...overrides,
  };
}

function bucketRow(bucket: MasterBucket, overrides: Partial<BucketDrift> = {}): BucketDrift {
  return {
    bucket,
    target_percentage: "50",
    actual_percentage: "50",
    target_amount: "3000.00",
    actual_amount: "3000.00",
    variance_amount: "0.00",
    variance_percentage_points: "0",
    status: "on_track",
    transaction_count: 10,
    ...overrides,
  };
}

function planResult(overrides: Partial<PlanVsActualResult> = {}): PlanVsActualResult {
  return {
    period: { start: "2026-08-01", end: "2026-08-31", label: "2026-08" },
    plan_version_id: "plan-1",
    plan_version_number: 1,
    plan_effective_from: "2026-01-01",
    plannable_income: "6000.00",
    buckets: [
      bucketRow("needs", {
        target_percentage: "50", actual_percentage: "50",
        target_amount: "3000.00", actual_amount: "3000.00",
        variance_amount: "0.00", variance_percentage_points: "0",
      }),
      bucketRow("wants", {
        target_percentage: "20", actual_percentage: "25",
        target_amount: "1200.00", actual_amount: "1500.00",
        variance_amount: "300.00", variance_percentage_points: "5",
        status: "watch",
      }),
      bucketRow("savings", {
        target_percentage: "15", actual_percentage: "10",
        target_amount: "900.00", actual_amount: "600.00",
        variance_amount: "-300.00", variance_percentage_points: "-5",
        status: "watch",
      }),
      bucketRow("investments", {
        target_percentage: "15", actual_percentage: "0",
        target_amount: "900.00", actual_amount: "0.00",
        variance_amount: "-900.00", variance_percentage_points: "-15",
        status: "off_track", transaction_count: 0,
      }),
    ],
    completeness: completeness(),
    ...overrides,
  };
}

function categoryRow(category: string, overrides: Partial<CategoryDrift> = {}): CategoryDrift {
  return {
    bucket: "needs",
    category,
    target_percentage: null,
    actual_percentage: "20",
    target_amount: null,
    actual_amount: "1200.00",
    variance_amount: null,
    variance_percentage_points: null,
    status: "unknown",
    transaction_count: 4,
    ...overrides,
  };
}

// ── buildBankingFlowTree ─────────────────────────────────────────────────

describe("buildBankingFlowTree", () => {
  it("returns an empty tree for null input", () => {
    const tree = buildBankingFlowTree(null);
    expect(tree).toEqual({ hasIncome: false, incomeAmount: 0, nodes: [], links: [], expandableBuckets: [] });
  });

  it("returns an empty tree when income was not observed", () => {
    const tree = buildBankingFlowTree(
      planResult({ completeness: completeness({ income_observed: false }), plannable_income: "0.00" }),
    );
    expect(tree.hasIncome).toBe(false);
    expect(tree.nodes).toHaveLength(0);
    expect(tree.links).toHaveLength(0);
  });

  it("returns an empty tree when plannable income is zero even if flagged observed", () => {
    const tree = buildBankingFlowTree(planResult({ plannable_income: "0.00" }));
    expect(tree.hasIncome).toBe(false);
  });

  it("builds Income -> Checking -> {Needs, Wants, Savings, Unallocated} with correct node count and order", () => {
    const tree = buildBankingFlowTree(planResult());
    expect(tree.hasIncome).toBe(true);
    expect(tree.incomeAmount).toBe(6000);
    expect(tree.nodes.map((n) => n.id)).toEqual(["income", "checking", "needs", "wants", "savings", "unallocated"]);
    expect(tree.nodes.map((n) => n.kind)).toEqual([
      "income", "checking", "bucket", "bucket", "bucket", "unallocated",
    ]);
  });

  it("wires Income->Checking and Checking->{bucket} links by node index, with dollar-volume link values", () => {
    const tree = buildBankingFlowTree(planResult());
    // income(0) -> checking(1)
    expect(tree.links[0]).toEqual({ source: 0, target: 1, value: 6000 });
    // checking(1) -> needs(2), wants(3), savings(4), unallocated(5)
    expect(tree.links[1]).toEqual({ source: 1, target: 2, value: 3000 });
    expect(tree.links[2]).toEqual({ source: 1, target: 3, value: 1500 });
    expect(tree.links[3]).toEqual({ source: 1, target: 4, value: 600 });
    // unallocated = income - (needs + wants + savings) = 6000 - (3000+1500+600) = 900
    expect(tree.links[4]).toEqual({ source: 1, target: 5, value: 900 });
  });

  it("carries actual $, actual %, target %, and variance on every primary bucket node", () => {
    const tree = buildBankingFlowTree(planResult());
    const wants = tree.nodes.find((n) => n.id === "wants")!;
    expect(wants.detail).toEqual({
      actualAmount: 1500,
      actualPercentage: 25,
      targetPercentage: 20,
      targetAmount: 1200,
      varianceAmount: 300,
      status: "watch",
      transactionCount: 10,
    });
  });

  it("never includes Investments as its own branch (that's the Investments page's tree, not Banking's)", () => {
    const tree = buildBankingFlowTree(planResult());
    expect(tree.nodes.find((n) => n.bucket === "investments")).toBeUndefined();
  });

  it("computes Unallocated's target % as the residual of the three shown buckets' targets (never hard-coded)", () => {
    const tree = buildBankingFlowTree(planResult());
    const unallocated = tree.nodes.find((n) => n.id === "unallocated")!;
    // 100 - 50 - 20 - 15 = 15, matching the plan's own Investments target by
    // construction for this fixture, without the adapter ever reading or
    // hard-coding "15".
    expect(unallocated.detail.targetPercentage).toBe(15);
    expect(unallocated.detail.targetAmount).toBe(900); // 6000 * 15%
    expect(unallocated.detail.actualAmount).toBe(900);
    expect(unallocated.detail.varianceAmount).toBe(0);
    expect(unallocated.detail.status).toBe("neutral");
  });

  it("leaves Unallocated's target % honestly null when any of the three underlying targets is unknown", () => {
    const tree = buildBankingFlowTree(
      planResult({
        buckets: [
          bucketRow("needs", { target_percentage: null, target_amount: null, variance_amount: null, variance_percentage_points: null }),
          bucketRow("wants", { target_percentage: "20" }),
          bucketRow("savings", { target_percentage: "15" }),
          bucketRow("investments", { target_percentage: "15" }),
        ],
      }),
    );
    const unallocated = tree.nodes.find((n) => n.id === "unallocated")!;
    expect(unallocated.detail.targetPercentage).toBeNull();
    expect(unallocated.detail.targetAmount).toBeNull();
    expect(unallocated.detail.varianceAmount).toBeNull();
  });

  it("clamps a negative Unallocated residual (buckets overspend beyond income) to a zero-value link, while the node keeps the true negative amount", () => {
    const tree = buildBankingFlowTree(
      planResult({
        plannable_income: "1000.00",
        buckets: [
          bucketRow("needs", { actual_amount: "800.00" }),
          bucketRow("wants", { actual_amount: "400.00" }),
          bucketRow("savings", { actual_amount: "0.00" }),
          bucketRow("investments", { actual_amount: "0.00" }),
        ],
      }),
    );
    const unallocated = tree.nodes.find((n) => n.id === "unallocated")!;
    expect(unallocated.detail.actualAmount).toBe(-200); // 1000 - (800+400+0)
    const link = tree.links.find((l) => l.target === tree.nodes.indexOf(unallocated))!;
    expect(link.value).toBe(0);
  });

  it("defensively fills a missing bucket row with an honest zero/unknown node rather than throwing", () => {
    const tree = buildBankingFlowTree(planResult({ buckets: [bucketRow("wants"), bucketRow("investments")] }));
    const needs = tree.nodes.find((n) => n.id === "needs")!;
    expect(needs.detail).toEqual({
      actualAmount: 0,
      actualPercentage: null,
      targetPercentage: null,
      targetAmount: null,
      varianceAmount: null,
      status: "unknown",
      transactionCount: 0,
    });
  });

  it("lists a bucket in expandableBuckets only when it has at least one classified transaction", () => {
    const tree = buildBankingFlowTree(
      planResult({
        buckets: [
          bucketRow("needs", { transaction_count: 12 }),
          bucketRow("wants", { transaction_count: 0, actual_amount: "0.00" }),
          bucketRow("savings", { transaction_count: 3 }),
          bucketRow("investments", { transaction_count: 0 }),
        ],
      }),
    );
    expect(tree.expandableBuckets).toEqual(["needs", "savings"]);
  });

  it("adds a category drill-down level only for the expanded bucket, once rows are provided", () => {
    const rows: CategoryDrift[] = [
      categoryRow("Housing", { actual_amount: "1800.00", actual_percentage: "30", transaction_count: 1 }),
      categoryRow("Groceries", { actual_amount: "800.00", actual_percentage: "13.33", transaction_count: 9 }),
    ];
    const tree = buildBankingFlowTree(planResult(), { expandedBucket: "needs", categoryRows: rows });

    expect(tree.nodes).toHaveLength(8); // 6 base + 2 categories
    const housing = tree.nodes.find((n) => n.id === "needs:Housing")!;
    expect(housing.kind).toBe("category");
    expect(housing.bucket).toBe("needs");
    expect(housing.category).toBe("Housing");
    expect(housing.detail.actualAmount).toBe(1800);

    const needsIdx = tree.nodes.findIndex((n) => n.id === "needs");
    const housingIdx = tree.nodes.findIndex((n) => n.id === "needs:Housing");
    const groceriesIdx = tree.nodes.findIndex((n) => n.id === "needs:Groceries");
    expect(tree.links).toContainEqual({ source: needsIdx, target: housingIdx, value: 1800 });
    expect(tree.links).toContainEqual({ source: needsIdx, target: groceriesIdx, value: 800 });
  });

  it("does not add a category level while categoryRows has not been fetched yet (still loading)", () => {
    const tree = buildBankingFlowTree(planResult(), { expandedBucket: "needs", categoryRows: null });
    expect(tree.nodes).toHaveLength(6);
  });

  it("ignores an expandedBucket that isn't one of Banking's three shown buckets (e.g. investments)", () => {
    const tree = buildBankingFlowTree(planResult(), {
      expandedBucket: "investments",
      categoryRows: [categoryRow("401(k)", { bucket: "investments" })],
    });
    expect(tree.nodes).toHaveLength(6);
  });

  it("clamps a category row's negative actual amount (refund-heavy category) to a zero-value link but keeps the true amount in the node", () => {
    const rows: CategoryDrift[] = [categoryRow("Shopping", { actual_amount: "-50.00" })];
    const tree = buildBankingFlowTree(planResult(), { expandedBucket: "needs", categoryRows: rows });
    const shopping = tree.nodes.find((n) => n.id === "needs:Shopping")!;
    expect(shopping.detail.actualAmount).toBe(-50);
    const link = tree.links.find((l) => l.target === tree.nodes.indexOf(shopping))!;
    expect(link.value).toBe(0);
  });
});

// ── buildFlowAccessibleSummary ───────────────────────────────────────────

describe("buildFlowAccessibleSummary", () => {
  it("explains the absence of income honestly rather than describing an empty diagram", () => {
    const tree = buildBankingFlowTree(null);
    expect(buildFlowAccessibleSummary(tree)).toBe(
      "No income has been recorded for this period yet, so a cash-flow breakdown is not available.",
    );
  });

  it("produces a dollar-first sentence per primary node, in tree order", () => {
    const tree = buildBankingFlowTree(planResult());
    const summary = buildFlowAccessibleSummary(tree);
    expect(summary).toContain("Income of $6,000 flowed into Checking this period.");
    expect(summary).toContain("Needs: $3,000 (50% of income), against a target of 50% ($0 over plan).");
    expect(summary).toContain("Wants: $1,500 (25% of income), against a target of 20% ($300 over plan).");
    expect(summary).toContain("Savings: $600 (10% of income), against a target of 15% ($300 under plan).");
    expect(summary).toContain("Unallocated: $900 (15% of income), against a target of 15% ($0 over plan).");
  });

  it("states 'no target set' rather than fabricating one when a bucket has none", () => {
    const tree = buildBankingFlowTree(
      planResult({
        buckets: [
          bucketRow("needs", { target_percentage: null, target_amount: null, variance_amount: null }),
          bucketRow("wants"),
          bucketRow("savings"),
          bucketRow("investments"),
        ],
      }),
    );
    const summary = buildFlowAccessibleSummary(tree);
    expect(summary).toContain("Needs: $3,000 (50% of income), no target set for this period.");
  });
});
