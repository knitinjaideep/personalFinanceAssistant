"use client";

/**
 * <BankingFlowTree /> — the hero of the redesigned Banking page (PR 07,
 * docs/coral-redesign/pr-07-banking-flow.md): "Where did my cash go?"
 *
 *   Income -> Checking -> Needs / Wants / Savings / Unallocated
 *
 * with a category drill-down (Housing/Groceries/... etc.) one level deeper
 * when a master bucket is clicked. Read-only visualization, not a graph
 * editor.
 *
 * All node/link values come from `buildBankingFlowTree()`
 * (lib/bankingFlowTree.ts) — a pure adapter over the already-normalized
 * `PlanVsActualResult` / `CategoryDrift[]` the backend computes (PR 03/04).
 * This component never reclassifies a transaction or computes a bucket
 * total itself (.claude/rules/frontend.md).
 *
 * Layout mirrors docs/design/coral-banking-redesign.png: a Recharts Sankey
 * diagram (colored flow bands, deliberately unlabeled — "avoid excessive
 * labels") on the left/top, paired with labeled detail cards (actual $,
 * actual %, target %, variance) on the right/below — Needs/Wants/Savings are
 * clickable to expand a category breakdown panel underneath. On narrow
 * screens the Sankey diagram (which does not degrade gracefully below ~420px)
 * is replaced by the same detail cards alone, stacked full-width.
 */

import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { HelpCircle, Home, PiggyBank, ShoppingBag } from "lucide-react";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import StatusBadge from "@/components/coral-ds/StatusBadge";
import Surface from "@/components/coral-ds/Surface";
import VarianceBadge from "@/components/coral-ds/VarianceBadge";
import { bankingApi, type CategoryDrift } from "@/features/banking/api";
import type { DashboardPeriodParams, MasterBucket, PlanVsActualResult } from "@/features/overview/api";
import { formatCompactCurrency, formatCurrency } from "@/lib/utils";
import { buildBankingFlowTree, buildFlowAccessibleSummary, type FlowNode } from "@/lib/bankingFlowTree";

interface BankingFlowTreeProps {
  result: PlanVsActualResult | null;
  loading: boolean;
  error: boolean;
  onRetry?: () => void;
  period: DashboardPeriodParams;
}

const BUCKET_ICON: Record<string, React.ReactNode> = {
  needs: <Home size={15} />,
  wants: <ShoppingBag size={15} />,
  savings: <PiggyBank size={15} />,
};

// Consumption buckets (Needs/Wants): overspend is adverse. Savings and this
// tree's synthesized "Unallocated" residual are treated as accumulation-like
// for badge coloring — a shortfall is what should read as adverse, an
// overshoot should not. Mirrors PlanVsActualSection's convention.
const CONSUMPTION_BUCKETS = new Set<MasterBucket>(["needs", "wants"]);

function nodeColor(node: FlowNode): string {
  if (node.kind === "income" || node.kind === "checking") return "var(--accent-strong)";
  if (node.kind === "unallocated") return "var(--status-neutral)";
  const bucket = node.bucket;
  if (bucket === "needs") return "var(--financial-needs)";
  if (bucket === "wants") return "var(--financial-wants)";
  if (bucket === "savings") return "var(--financial-savings)";
  return "var(--status-neutral)";
}

/** The existing `--financial-<bucket>-soft`/`--status-neutral-soft` design
 * tokens (already used by PlanVsActualSection.tsx) — reused here instead of
 * `color-mix()` for the same tinted-background treatment, consistent with
 * the rest of the design system. */
function nodeSoftColor(node: FlowNode): string {
  if (node.kind === "income" || node.kind === "checking") return "var(--status-neutral-soft)";
  const bucket = node.bucket;
  if (bucket === "needs") return "var(--financial-needs-soft)";
  if (bucket === "wants") return "var(--financial-wants-soft)";
  if (bucket === "savings") return "var(--financial-savings-soft)";
  return "var(--status-neutral-soft)";
}

function formatPercent(value: number | null): string {
  if (value === null) return "—";
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function FlowMap({
  tree,
  selectedBucket,
  onSelectBucket,
}: {
  tree: ReturnType<typeof buildBankingFlowTree>;
  selectedBucket: MasterBucket | null;
  onSelectBucket: (bucket: MasterBucket) => void;
}) {
  const bucketNodes = tree.nodes.filter((node) => node.kind === "bucket" || node.kind === "unallocated");
  const positiveNodes = bucketNodes.filter((node) => node.detail.actualAmount > 0);
  const negativeNodes = bucketNodes.filter((node) => node.detail.actualAmount < 0);
  const branchCount = Math.max(positiveNodes.length, 1);
  const maxBranch = Math.max(...positiveNodes.map((node) => node.detail.actualAmount), tree.incomeAmount, 1);
  const pathWidth = (value: number) => Math.max(10, Math.min(64, (value / maxBranch) * 64));

  return (
    <div
      className="relative h-[340px] overflow-hidden rounded-[28px] p-5"
      style={{
        background: "linear-gradient(180deg, rgba(255,255,255,0.18), rgba(255,255,255,0.08))",
        border: "1px solid var(--border-subtle)",
      }}
    >
      <svg viewBox="0 0 760 300" className="h-full w-full" role="img" aria-label="Cash flow from income through checking into plan buckets">
        <defs>
          <filter id="banking-flow-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="10" stdDeviation="12" floodColor="#0b3347" floodOpacity="0.16" />
          </filter>
        </defs>

        <g filter="url(#banking-flow-shadow)">
          <rect x="32" y="72" width="68" height="156" rx="20" fill="rgba(255,255,255,0.72)" />
          <rect x="52" y="92" width="28" height="116" rx="12" fill="var(--accent-strong)" />
          <text x="66" y="52" textAnchor="middle" fontSize="13" fontWeight="800" fill="var(--text-primary)">Income</text>
          <text x="66" y="244" textAnchor="middle" fontSize="12" fontWeight="700" fill="var(--text-secondary)">
            {formatCompactCurrency(tree.incomeAmount)}
          </text>

          <rect x="292" y="72" width="84" height="156" rx="24" fill="rgba(255,255,255,0.78)" />
          <rect x="320" y="92" width="28" height="116" rx="12" fill="var(--accent-strong)" />
          <text x="334" y="52" textAnchor="middle" fontSize="13" fontWeight="800" fill="var(--text-primary)">Checking</text>
          <text x="334" y="244" textAnchor="middle" fontSize="12" fontWeight="700" fill="var(--text-secondary)">
            {formatCompactCurrency(tree.incomeAmount)}
          </text>
        </g>

        <path
          d="M80 150 C160 150 220 150 320 150"
          fill="none"
          stroke="var(--accent-strong)"
          strokeWidth="34"
          strokeLinecap="round"
          strokeOpacity="0.28"
        />

        {positiveNodes.map((node, index) => {
          const y = branchCount === 1 ? 150 : 62 + (index * 176) / Math.max(branchCount - 1, 1);
          const clickable = node.kind === "bucket" && node.bucket !== null;
          const selected = selectedBucket === node.bucket;
          const dimmed = selectedBucket !== null && clickable && !selected;
          return (
            <g
              key={node.id}
              role={clickable ? "button" : undefined}
              tabIndex={clickable ? 0 : undefined}
              aria-label={clickable ? `Show ${node.label} category breakdown` : undefined}
              onClick={clickable ? () => onSelectBucket(node.bucket as MasterBucket) : undefined}
              onKeyDown={clickable ? (event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectBucket(node.bucket as MasterBucket);
                }
              } : undefined}
              style={{ cursor: clickable ? "pointer" : "default", outline: "none" }}
            >
              <path
                d={`M348 150 C460 150 502 ${y} 598 ${y}`}
                fill="none"
                stroke={nodeColor(node)}
                strokeWidth={pathWidth(node.detail.actualAmount)}
                strokeLinecap="round"
                strokeOpacity={dimmed ? 0.16 : selected ? 0.58 : 0.34}
              />
              <rect
                x="598"
                y={y - 26}
                width="132"
                height="52"
                rx="16"
                fill="rgba(255,255,255,0.86)"
                stroke={selected ? nodeColor(node) : "rgba(105,132,155,0.22)"}
              />
              <circle cx="620" cy={y} r="12" fill={nodeSoftColor(node)} />
              <text x="642" y={y - 5} fontSize="12" fontWeight="800" fill="#0a1735">{node.label}</text>
              <text x="642" y={y + 13} fontSize="11" fontWeight="700" fill="#53657f">
                {formatCompactCurrency(node.detail.actualAmount)} · {formatPercent(node.detail.actualPercentage)}
              </text>
            </g>
          );
        })}

        {negativeNodes.map((node, index) => (
          <g key={node.id} opacity="0.95">
            <path
              d={`M348 ${188 + index * 18} C430 ${224 + index * 6} 500 ${236 + index * 6} 590 ${236 + index * 6}`}
              fill="none"
              stroke="var(--status-danger)"
              strokeWidth="3"
              strokeDasharray="7 7"
              strokeLinecap="round"
              strokeOpacity="0.7"
            />
            <rect x="598" y={210 + index * 56} width="132" height="52" rx="16" fill="rgba(255,255,255,0.76)" stroke="rgba(216,75,54,0.42)" />
            <text x="614" y={231 + index * 56} fontSize="12" fontWeight="800" fill="#0a1735">{node.label}</text>
            <text x="614" y={249 + index * 56} fontSize="11" fontWeight="700" fill="var(--status-danger)">
              {formatCompactCurrency(node.detail.actualAmount)} · {formatPercent(node.detail.actualPercentage)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function BucketCard({
  node,
  selected,
  onSelect,
}: {
  node: FlowNode;
  selected: boolean;
  onSelect?: () => void;
}) {
  const d = node.detail;
  const clickable = !!onSelect;
  const icon = node.bucket ? BUCKET_ICON[node.bucket] : <HelpCircle size={15} />;
  const direction = node.bucket && CONSUMPTION_BUCKETS.has(node.bucket) ? "negative-good" : "positive-good";

  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={!clickable}
      aria-pressed={clickable ? selected : undefined}
      className="w-full flex items-center gap-3 px-4 py-3.5 rounded-2xl text-left transition-all"
      style={{
        background: selected ? nodeSoftColor(node) : "var(--card-bg)",
        border: `1px solid ${selected ? nodeColor(node) : "var(--border-subtle)"}`,
        cursor: clickable ? "pointer" : "default",
      }}
    >
      <span
        className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
        style={{ background: nodeSoftColor(node), color: nodeColor(node) }}
      >
        {icon}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="coral-card-title">{node.label}</span>
          {d.varianceAmount !== null && node.kind === "bucket" ? (
            <VarianceBadge value={d.varianceAmount} direction={direction} />
          ) : (
            <StatusBadge status="neutral">
              {formatPercent(d.actualPercentage)}
            </StatusBadge>
          )}
        </div>
        <p className="small-text font-bold tabular mt-0.5" style={{ color: "var(--text-primary)" }}>
          {formatCurrency(d.actualAmount)}
        </p>
        <p className="micro-text mt-0.5" style={{ color: "var(--text-muted)" }}>
          {d.actualPercentage !== null ? `${formatPercent(d.actualPercentage)} of income` : "No income this period"}
          {d.targetPercentage !== null && ` · vs plan ${formatPercent(d.targetPercentage)}`}
        </p>
      </div>
    </button>
  );
}

function CategoryBreakdownPanel({
  bucketLabel,
  loading,
  error,
  rows,
  onRetry,
}: {
  bucketLabel: string;
  loading: boolean;
  error: boolean;
  rows: CategoryDrift[] | null;
  onRetry: () => void;
}) {
  if (loading) return <SkeletonState variant="card" height="140px" />;
  if (error) return <ErrorState compact message={`Couldn't load the ${bucketLabel} breakdown.`} onRetry={onRetry} />;
  if (!rows || rows.length === 0) {
    return (
      <EmptyState
        compact
        title={`No categorized ${bucketLabel.toLowerCase()} activity yet`}
        description="Coral hasn't classified any transactions into this bucket for the selected period."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {rows.map((row) => {
        const actual = Number(row.actual_amount);
        const target = row.target_percentage !== null ? Number(row.target_percentage) : null;
        const variance = row.variance_amount !== null ? Number(row.variance_amount) : null;
        return (
          <div
            key={row.category}
            className="px-4 py-3 rounded-xl"
            style={{ background: "var(--panel-bg, var(--card-bg))", border: "1px solid var(--border-subtle)" }}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>{row.category}</span>
              {variance !== null && <VarianceBadge value={variance} />}
            </div>
            <p className="micro-text mt-1" style={{ color: "var(--text-muted)" }}>
              {formatCurrency(actual)}
              {row.actual_percentage !== null && ` · ${row.actual_percentage}% of income`}
              {target !== null && ` · target ${target}%`}
            </p>
          </div>
        );
      })}
    </div>
  );
}

export default function BankingFlowTree({ result, loading, error, onRetry, period }: BankingFlowTreeProps) {
  const prefersReducedMotion = useReducedMotion();
  const [selectedBucket, setSelectedBucket] = useState<MasterBucket | null>(null);
  const [categoryRows, setCategoryRows] = useState<CategoryDrift[] | null>(null);
  const [categoryLoading, setCategoryLoading] = useState(false);
  const [categoryError, setCategoryError] = useState(false);

  // Reset the drill-down whenever the period changes — a category breakdown
  // fetched for last month must never linger onscreen for this month.
  useEffect(() => {
    setSelectedBucket(null);
    setCategoryRows(null);
    setCategoryError(false);
  }, [period.startDate, period.endDate]);

  const loadCategoryBreakdown = (bucket: MasterBucket) => {
    setCategoryLoading(true);
    setCategoryError(false);
    bankingApi
      .bucketBreakdown(bucket, period)
      .then((rows) => setCategoryRows(rows))
      .catch(() => setCategoryError(true))
      .finally(() => setCategoryLoading(false));
  };

  const handleSelectBucket = (bucket: MasterBucket) => {
    if (selectedBucket === bucket) {
      // Click again to collapse — "clicking master buckets filters detail",
      // not a one-way drill that traps the user.
      setSelectedBucket(null);
      setCategoryRows(null);
      return;
    }
    setSelectedBucket(bucket);
    setCategoryRows(null);
    loadCategoryBreakdown(bucket);
  };

  const tree = useMemo(
    () => buildBankingFlowTree(result, { expandedBucket: selectedBucket, categoryRows }),
    [result, selectedBucket, categoryRows],
  );
  const accessibleSummary = useMemo(() => buildFlowAccessibleSummary(tree), [tree]);

  if (loading) return <SkeletonState variant="card" height="420px" />;
  if (error) return <ErrorState message="Couldn't load your cash-flow breakdown for this period." onRetry={onRetry} />;
  if (!tree.hasIncome) {
    return (
      <EmptyState
        title="No income recorded yet"
        description="Once Coral sees income for this period it can show where that cash went — Needs, Wants, Savings, and anything unallocated."
      />
    );
  }

  const bucketNodes = tree.nodes.filter((n) => n.kind === "bucket" || n.kind === "unallocated");
  const selectedNode = selectedBucket ? tree.nodes.find((n) => n.bucket === selectedBucket) : null;

  return (
    <motion.div
      key={`${period.startDate ?? ""}-${period.endDate ?? ""}`}
      initial={prefersReducedMotion ? undefined : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="space-y-6"
    >
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Sankey diagram — desktop/tablet only; narrow screens fall back to
         * the detail cards alone (below), which is a complete, readable
         * representation of the same data on its own. */}
        <div className="hidden sm:block lg:col-span-3" style={{ minHeight: 340 }}>
          <FlowMap tree={tree} selectedBucket={selectedBucket} onSelectBucket={handleSelectBucket} />
        </div>

        {/* Detail cards — the primary, always-visible representation of
         * every node's actual $ / actual % / target % / variance. */}
        <div className="lg:col-span-2 space-y-2.5">
          {bucketNodes.map((node) => (
            <BucketCard
              key={node.id}
              node={node}
              selected={selectedBucket === node.bucket}
              onSelect={node.kind === "bucket" && node.bucket ? () => handleSelectBucket(node.bucket as MasterBucket) : undefined}
            />
          ))}
        </div>
      </div>

      {selectedBucket && selectedNode && (
        <Surface padding="md">
          <div className="flex items-center justify-between mb-4">
            <p className="coral-card-title">{selectedNode.label} breakdown</p>
            <button
              type="button"
              onClick={() => handleSelectBucket(selectedBucket)}
              className="micro-text font-semibold"
              style={{ color: "var(--text-muted)" }}
            >
              Collapse
            </button>
          </div>
          <CategoryBreakdownPanel
            bucketLabel={selectedNode.label}
            loading={categoryLoading}
            error={categoryError}
            rows={categoryRows}
            onRetry={() => loadCategoryBreakdown(selectedBucket)}
          />
        </Surface>
      )}

      {/* Accessible textual summary — .claude/rules/frontend.md requires an
       * accessible label/summary alongside every chart. */}
      <span className="sr-only">{accessibleSummary}</span>
    </motion.div>
  );
}
