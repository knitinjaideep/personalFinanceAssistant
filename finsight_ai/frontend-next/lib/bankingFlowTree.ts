/**
 * Banking Cash-Flow Tree — pure data adapter (PR 07,
 * docs/coral-redesign/pr-07-banking-flow.md).
 *
 * Turns already-normalized, backend-computed `PlanVsActualResult` /
 * `CategoryDrift[]` (backend/app/domain/plan_vs_actual.py, via
 * GET /api/v1/plan-vs-actual and GET /api/v1/plan-vs-actual/buckets/{bucket})
 * into the node/link shape `<BankingFlowTree />` hands to Recharts' `Sankey`.
 *
 * This module is intentionally framework-free (no React import) so it can be
 * unit tested in isolation — see bankingFlowTree.test.ts. It never
 * reclassifies a transaction, recomputes a bucket total, or invents a number:
 * every dollar amount here is either copied directly from the backend result
 * or a single deterministic subtraction/addition of numbers the backend
 * already computed (see `buildUnallocatedDetail` below for the one place
 * that happens, and why).
 *
 * Tree shape (concept, pr-07-banking-flow.md):
 *
 *   Income -> Checking -> Needs
 *                       -> Wants
 *                       -> Savings
 *                       -> Unallocated   (residual — see below)
 *
 * Needs/Wants/Savings each optionally expand one more level (category
 * drill-down, e.g. Needs -> Housing/Groceries/...) when the caller has
 * fetched that bucket's `CategoryDrift[]` (lazy, on click — see
 * `options.expandedBucket`/`options.categoryRows`).
 *
 * Investments is deliberately NOT a branch here — per design-rules.md's page
 * hierarchy, "Am I investing according to plan?" is the Investments page's
 * question (its own Investment Contribution Tree, PR11/12), not Banking's.
 * Any investment-contribution dollars (and any genuinely unclassified
 * dollars) fall out of Needs/Wants/Savings and are surfaced honestly in the
 * "Unallocated" node instead of being silently dropped from the diagram.
 */

import type { BucketDrift, DriftStatus, MasterBucket, PlanVsActualResult } from "@/features/overview/api";
import type { CategoryDrift } from "@/features/banking/api";
import { formatCurrency } from "@/lib/utils";

export type FlowNodeKind = "income" | "checking" | "bucket" | "unallocated" | "category";

/** A node's PLAN -> ACTUAL -> DRIFT figures. `status` is `"neutral"` for
 * nodes the backend does not compute a drift status for (Income, Checking,
 * Unallocated) — never invented client-side. */
export interface FlowNodeDetail {
  actualAmount: number;
  /** Percentage of Plannable Income, e.g. 48 for "48% of income". Null when
   * the backend could not honestly compute it (no income observed). */
  actualPercentage: number | null;
  targetPercentage: number | null;
  targetAmount: number | null;
  varianceAmount: number | null;
  status: DriftStatus | "neutral";
  transactionCount: number | null;
}

export interface FlowNode {
  id: string;
  label: string;
  kind: FlowNodeKind;
  bucket: MasterBucket | null;
  category: string | null;
  detail: FlowNodeDetail;
}

export interface FlowLink {
  source: number;
  target: number;
  /** Non-negative dollar volume — the sole input to Sankey branch thickness. */
  value: number;
}

export interface BankingFlowTreeResult {
  hasIncome: boolean;
  incomeAmount: number;
  nodes: FlowNode[];
  links: FlowLink[];
  /** Primary buckets that have at least one classified transaction this
   * period — i.e. worth letting the user click through to a category
   * drill-down. A bucket absent from this list can still be clicked (it will
   * just show an honest "no activity" detail panel), this is only a UI hint. */
  expandableBuckets: MasterBucket[];
}

export interface BuildFlowTreeOptions {
  /** The bucket the caller has drilled into (via a node click), if any. */
  expandedBucket?: MasterBucket | null;
  /** That bucket's category rows, once fetched. `null`/`undefined` while
   * still loading — the adapter simply omits the category level until it has
   * real data (never fabricates placeholder categories). */
  categoryRows?: CategoryDrift[] | null;
}

const PRIMARY_BUCKETS: readonly MasterBucket[] = ["needs", "wants", "savings"];

const BUCKET_LABEL: Record<string, string> = {
  needs: "Needs",
  wants: "Wants",
  savings: "Savings",
};

function toNumber(v: string | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function emptyResult(): BankingFlowTreeResult {
  return { hasIncome: false, incomeAmount: 0, nodes: [], links: [], expandableBuckets: [] };
}

function passThroughDetail(amount: number): FlowNodeDetail {
  return {
    actualAmount: amount,
    actualPercentage: amount > 0 ? 100 : null,
    targetPercentage: 100,
    targetAmount: amount,
    varianceAmount: 0,
    status: "neutral",
    transactionCount: null,
  };
}

function bucketNodeDetail(row: BucketDrift | undefined): FlowNodeDetail {
  if (!row) {
    return {
      actualAmount: 0,
      actualPercentage: null,
      targetPercentage: null,
      targetAmount: null,
      varianceAmount: null,
      status: "unknown",
      transactionCount: 0,
    };
  }
  return {
    actualAmount: toNumber(row.actual_amount) ?? 0,
    actualPercentage: toNumber(row.actual_percentage),
    targetPercentage: toNumber(row.target_percentage),
    targetAmount: toNumber(row.target_amount),
    varianceAmount: toNumber(row.variance_amount),
    status: row.status,
    transactionCount: row.transaction_count,
  };
}

function categoryNodeDetail(row: CategoryDrift): FlowNodeDetail {
  return {
    actualAmount: toNumber(row.actual_amount) ?? 0,
    actualPercentage: toNumber(row.actual_percentage),
    targetPercentage: toNumber(row.target_percentage),
    targetAmount: toNumber(row.target_amount),
    varianceAmount: toNumber(row.variance_amount),
    status: row.status,
    transactionCount: row.transaction_count,
  };
}

/**
 * "Unallocated" = Plannable Income minus the three consumption/accumulation
 * buckets Banking shows (Needs + Wants + Savings). This is arithmetic over
 * numbers the backend already computed, not a new classification pass — it
 * necessarily also contains any Investments contribution $ (a legitimate use
 * of income that just isn't Banking's story to tell — see module docstring)
 * plus any genuinely unclassified $ (already separately surfaced in
 * `result.completeness.unclassified_amount`).
 *
 * `status` is deliberately always `"neutral"`: the backend's
 * `compute_status()` is defined per-MasterBucket (consumption vs
 * accumulation semantics), and this residual isn't one bucket, so no
 * good/watch/off-track judgement is invented for it here.
 *
 * Target % is the residual of the three buckets' OWN targets (100 - needs% -
 * wants% - savings%) when all three are known — for the plan's default
 * 50/20/15/15 split this equals the Investments target (15%) by
 * construction, without hard-coding that number. If ANY of the three targets
 * is unavailable (no plan in effect), the residual target is honestly null
 * rather than a guess.
 */
function buildUnallocatedDetail(
  plannableIncome: number,
  bucketDetails: Record<string, FlowNodeDetail>,
): FlowNodeDetail {
  const consumed = PRIMARY_BUCKETS.reduce((sum, b) => sum + bucketDetails[b].actualAmount, 0);
  const actualAmount = plannableIncome - consumed;
  const actualPercentage = plannableIncome > 0 ? (actualAmount / plannableIncome) * 100 : null;

  const targets = PRIMARY_BUCKETS.map((b) => bucketDetails[b].targetPercentage);
  const allTargetsKnown = targets.every((t) => t !== null);
  const targetPercentage = allTargetsKnown
    ? 100 - (targets as number[]).reduce((sum, t) => sum + t, 0)
    : null;
  const targetAmount =
    targetPercentage !== null && plannableIncome > 0 ? (plannableIncome * targetPercentage) / 100 : null;
  const varianceAmount = targetAmount !== null ? actualAmount - targetAmount : null;

  return {
    actualAmount,
    actualPercentage,
    targetPercentage,
    targetAmount,
    varianceAmount,
    status: "neutral",
    transactionCount: null,
  };
}

/**
 * Build the flow tree's node/link data from a `PlanVsActualResult` (and,
 * optionally, one bucket's category-level drill-down). Pure and
 * deterministic: same input always produces the same output.
 */
export function buildBankingFlowTree(
  result: PlanVsActualResult | null,
  options: BuildFlowTreeOptions = {},
): BankingFlowTreeResult {
  if (!result) return emptyResult();

  const plannableIncome = toNumber(result.plannable_income) ?? 0;
  const hasIncome = result.completeness.income_observed && plannableIncome > 0;
  if (!hasIncome) return emptyResult();

  const rowByBucket = new Map(result.buckets.map((b) => [b.bucket, b]));
  const bucketDetails: Record<string, FlowNodeDetail> = {};
  for (const bucket of PRIMARY_BUCKETS) {
    bucketDetails[bucket] = bucketNodeDetail(rowByBucket.get(bucket));
  }

  const nodes: FlowNode[] = [];
  const links: FlowLink[] = [];

  const incomeIdx = nodes.length;
  nodes.push({
    id: "income",
    label: "Income",
    kind: "income",
    bucket: null,
    category: null,
    detail: passThroughDetail(plannableIncome),
  });

  const checkingIdx = nodes.length;
  nodes.push({
    id: "checking",
    label: "Checking",
    kind: "checking",
    bucket: null,
    category: null,
    detail: passThroughDetail(plannableIncome),
  });
  links.push({ source: incomeIdx, target: checkingIdx, value: Math.max(0, plannableIncome) });

  const expandableBuckets: MasterBucket[] = [];
  const bucketNodeIndex: Partial<Record<MasterBucket, number>> = {};

  for (const bucket of PRIMARY_BUCKETS) {
    const detail = bucketDetails[bucket];
    const idx = nodes.length;
    bucketNodeIndex[bucket] = idx;
    nodes.push({
      id: bucket,
      label: BUCKET_LABEL[bucket],
      kind: "bucket",
      bucket,
      category: null,
      detail,
    });
    links.push({ source: checkingIdx, target: idx, value: Math.max(0, detail.actualAmount) });
    if ((detail.transactionCount ?? 0) > 0) expandableBuckets.push(bucket);
  }

  const unallocatedDetail = buildUnallocatedDetail(plannableIncome, bucketDetails);
  const unallocatedIdx = nodes.length;
  nodes.push({
    id: "unallocated",
    label: "Unallocated",
    kind: "unallocated",
    bucket: null,
    category: null,
    detail: unallocatedDetail,
  });
  links.push({ source: checkingIdx, target: unallocatedIdx, value: Math.max(0, unallocatedDetail.actualAmount) });

  // Depth-2 category drill-down for exactly the clicked bucket, only once
  // its rows have actually been fetched (categoryRows is null while
  // loading/not-yet-requested — see BuildFlowTreeOptions docstring).
  const { expandedBucket, categoryRows } = options;
  if (expandedBucket && categoryRows && bucketNodeIndex[expandedBucket] !== undefined) {
    const parentIdx = bucketNodeIndex[expandedBucket]!;
    for (const row of categoryRows) {
      const idx = nodes.length;
      nodes.push({
        id: `${expandedBucket}:${row.category}`,
        label: row.category,
        kind: "category",
        bucket: expandedBucket,
        category: row.category,
        detail: categoryNodeDetail(row),
      });
      links.push({ source: parentIdx, target: idx, value: Math.max(0, toNumber(row.actual_amount) ?? 0) });
    }
  }

  return { hasIncome: true, incomeAmount: plannableIncome, nodes, links, expandableBuckets };
}

/**
 * A screen-reader-usable plain-English equivalent of the diagram —
 * .claude/rules/frontend.md requires "accessible textual labels or summaries
 * where practical" for charts.
 */
export function buildFlowAccessibleSummary(tree: BankingFlowTreeResult): string {
  if (!tree.hasIncome) {
    return "No income has been recorded for this period yet, so a cash-flow breakdown is not available.";
  }

  const sentences: string[] = [
    `Income of ${formatCurrency(tree.incomeAmount)} flowed into Checking this period.`,
  ];

  for (const node of tree.nodes) {
    if (node.kind !== "bucket" && node.kind !== "unallocated") continue;
    const d = node.detail;
    const pct = d.actualPercentage !== null ? `${d.actualPercentage}% of income` : "an unknown share of income";
    let sentence = `${node.label}: ${formatCurrency(d.actualAmount)} (${pct})`;
    if (d.targetPercentage !== null) {
      sentence += `, against a target of ${d.targetPercentage}%`;
      if (d.varianceAmount !== null) {
        const overUnder = d.varianceAmount >= 0 ? "over" : "under";
        sentence += ` (${formatCurrency(Math.abs(d.varianceAmount))} ${overUnder} plan)`;
      }
    } else {
      sentence += ", no target set for this period";
    }
    sentence += ".";
    sentences.push(sentence);
  }

  return sentences.join(" ");
}
