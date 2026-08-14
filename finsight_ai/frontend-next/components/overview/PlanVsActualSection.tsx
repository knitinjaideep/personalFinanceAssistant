"use client";

/**
 * Section 4 (pr-06-overview.md): Plan vs Actual — Needs/Wants/Savings/
 * Investments, each with target %, actual %, target $, actual $, variance $.
 * Dollar drift is the visually prominent element (VarianceBadge), per
 * .claude/skills/coral-redesign "Dollar-first communication" and
 * .claude/rules/frontend.md's PLAN -> ACTUAL -> DRIFT -> ACTION ordering.
 *
 * Pure presentation over already-computed backend numbers
 * (GET /api/v1/plan-vs-actual, PR 04) — no financial math happens here.
 */

import { Home, PiggyBank, ShoppingBag, TrendingUp } from "lucide-react";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import StatusBadge from "@/components/coral-ds/StatusBadge";
import TargetProgressBar, { type FinancialBucket } from "@/components/coral-ds/TargetProgressBar";
import VarianceBadge from "@/components/coral-ds/VarianceBadge";
import { formatCurrency } from "@/lib/utils";
import type { BucketDrift, MasterBucket, PlanVsActualResult } from "@/features/overview/api";

interface PlanVsActualSectionProps {
  result: PlanVsActualResult | null;
  loading: boolean;
  error: boolean;
  onRetry?: () => void;
}

const BUCKET_ORDER: MasterBucket[] = ["needs", "wants", "savings", "investments"];

const BUCKET_META: Record<string, { label: string; icon: React.ReactNode }> = {
  needs: { label: "Needs", icon: <Home size={16} /> },
  wants: { label: "Wants", icon: <ShoppingBag size={16} /> },
  savings: { label: "Savings", icon: <PiggyBank size={16} /> },
  investments: { label: "Investments", icon: <TrendingUp size={16} /> },
};

// Consumption buckets: overspend (positive variance) is adverse, so a
// positive variance is NOT good. Accumulation buckets: shortfall (negative
// variance) is adverse, so a positive variance IS good. Mirrors
// app.domain.plan_vs_actual.compute_status's sign convention exactly.
const CONSUMPTION_BUCKETS = new Set<MasterBucket>(["needs", "wants"]);

function PlanVsActualRow({ bucket }: { bucket: BucketDrift }) {
  const meta = BUCKET_META[bucket.bucket];
  if (!meta) return null;

  const targetPct = bucket.target_percentage !== null ? Number(bucket.target_percentage) : 0;
  const actualPct = bucket.actual_percentage !== null ? Number(bucket.actual_percentage) : 0;
  const hasVariance = bucket.variance_amount !== null;
  const financialBucket = bucket.bucket as FinancialBucket;

  return (
    <div
      className="flex flex-col sm:flex-row sm:items-center gap-4 py-4"
      style={{ borderBottom: "1px solid var(--border-subtle)" }}
    >
      <span
        className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
        style={{
          background: `var(--financial-${bucket.bucket}-soft)`,
          color: `var(--financial-${bucket.bucket})`,
        }}
      >
        {meta.icon}
      </span>

      <div className="flex-1 min-w-0">
        <TargetProgressBar label={meta.label} actual={actualPct} target={targetPct} bucket={financialBucket} />
        {/* Dollars lead; the actual % is supporting information alongside the
         * target % shown by TargetProgressBar — pr-06-overview.md requires
         * target %, actual %, target $ and actual $ on every row, and the
         * skill's "Dollar-first communication" sets the emphasis order. */}
        <p className="micro-text mt-1.5" style={{ color: "var(--text-muted)" }}>
          {bucket.target_amount !== null
            ? `Target ${formatCurrency(Number(bucket.target_amount))}`
            : "No target this period"}
          {" · "}
          Actual {formatCurrency(Number(bucket.actual_amount))}
          {bucket.actual_percentage !== null && ` (${Number(bucket.actual_percentage)}% of income)`}
        </p>
      </div>

      <div className="text-right shrink-0 sm:pl-2">
        {hasVariance ? (
          <VarianceBadge
            value={Number(bucket.variance_amount)}
            direction={CONSUMPTION_BUCKETS.has(bucket.bucket) ? "negative-good" : "positive-good"}
          />
        ) : (
          <StatusBadge status="neutral">No data</StatusBadge>
        )}
      </div>
    </div>
  );
}

export default function PlanVsActualSection({ result, loading, error, onRetry }: PlanVsActualSectionProps) {
  if (loading) return <SkeletonState variant="card" height="320px" />;
  if (error) {
    return <ErrorState compact message="Couldn't load Plan vs Actual for this period." onRetry={onRetry} />;
  }
  if (!result) return null;

  if (!result.completeness.income_observed) {
    return (
      <EmptyState
        compact
        title="No income recorded yet"
        description="Once Coral sees income for this period it can compare your spending and saving against your plan."
      />
    );
  }

  const ordered = BUCKET_ORDER
    .map((bucket) => result.buckets.find((row) => row.bucket === bucket))
    .filter((row): row is BucketDrift => Boolean(row));

  if (ordered.length === 0) {
    return (
      <EmptyState compact title="No plan data yet" description="Coral doesn't have a financial plan in effect for this period." />
    );
  }

  return (
    <div>
      {ordered.map((row) => (
        <PlanVsActualRow key={row.bucket} bucket={row} />
      ))}
      {result.completeness.notes.length > 0 && (
        <p className="micro-text mt-4" style={{ color: "var(--text-muted)" }}>
          {result.completeness.notes[0]}
        </p>
      )}
    </div>
  );
}
