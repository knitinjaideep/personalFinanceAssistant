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
import { ResponsiveContainer, Sankey, Tooltip } from "recharts";
import type { LinkProps, NodeProps } from "recharts/types/chart/Sankey";
import { HelpCircle, Home, PiggyBank, ShoppingBag } from "lucide-react";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import StatusBadge from "@/components/coral-ds/StatusBadge";
import Surface from "@/components/coral-ds/Surface";
import VarianceBadge from "@/components/coral-ds/VarianceBadge";
import { bankingApi, type CategoryDrift } from "@/features/banking/api";
import type { DashboardPeriodParams, MasterBucket, PlanVsActualResult } from "@/features/overview/api";
import { formatCurrency } from "@/lib/utils";
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

function FlowSankeyNode(props: NodeProps & { selectedBucket: MasterBucket | null; onSelectBucket: (b: MasterBucket) => void }) {
  const { x, y, width, height, payload, selectedBucket, onSelectBucket } = props;
  const node = payload as unknown as FlowNode;
  const color = nodeColor(node);
  const clickable = node.kind === "bucket" && node.bucket !== null;
  const dimmed = selectedBucket !== null && node.kind === "bucket" && node.bucket !== selectedBucket;
  const h = Math.max(height, 3);

  return (
    <g
      style={{ cursor: clickable ? "pointer" : "default" }}
      onClick={clickable ? () => onSelectBucket(node.bucket as MasterBucket) : undefined}
      role={clickable ? "button" : undefined}
      aria-label={clickable ? `Show ${node.label} category breakdown` : undefined}
    >
      <rect
        x={x}
        y={y}
        width={width}
        height={h}
        rx={3}
        fill={color}
        fillOpacity={dimmed ? 0.35 : 0.92}
      />
      <text
        x={x + width / 2}
        y={y - 6}
        textAnchor="middle"
        fontSize={11}
        fontWeight={600}
        style={{ fill: dimmed ? "var(--text-dim)" : "var(--text-secondary)" }}
      >
        {node.label}
      </text>
    </g>
  );
}

function FlowSankeyLink(props: LinkProps & { selectedBucket: MasterBucket | null }) {
  const { sourceX, sourceY, sourceControlX, targetX, targetY, targetControlX, linkWidth, payload, selectedBucket } = props;
  const target = payload.target as unknown as FlowNode;
  const color = nodeColor(target);
  const dimmed = selectedBucket !== null && target.kind === "bucket" && target.bucket !== selectedBucket;

  return (
    <path
      d={`M${sourceX},${sourceY} C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`}
      fill="none"
      stroke={color}
      strokeWidth={Math.max(linkWidth, 1)}
      strokeOpacity={dimmed ? 0.12 : 0.32}
    />
  );
}

function FlowTooltipContent({ active, payload }: { active?: boolean; payload?: { payload?: { payload?: FlowNode | { source: FlowNode; target: FlowNode; value: number } } }[] }) {
  if (!active || !payload?.length) return null;
  const raw = payload[0]?.payload?.payload;
  if (!raw) return null;

  // Node hover: raw is a FlowNode. Link hover: raw is {source, target, value}.
  const node: FlowNode | null = "detail" in raw ? (raw as FlowNode) : null;
  const link = "source" in raw && "target" in raw ? (raw as { source: FlowNode; target: FlowNode; value: number }) : null;

  const box = (title: string, body: React.ReactNode) => (
    <div
      className="rounded-xl px-3 py-2.5 small-text"
      style={{ background: "var(--card-bg)", border: "1px solid var(--border-subtle)", color: "var(--text-secondary)" }}
    >
      <p className="font-semibold mb-1" style={{ color: "var(--text-primary)" }}>{title}</p>
      {body}
    </div>
  );

  if (node) {
    const d = node.detail;
    return box(
      node.label,
      <div className="space-y-0.5">
        <p>Actual {formatCurrency(d.actualAmount)}{d.actualPercentage !== null ? ` (${d.actualPercentage}% of income)` : ""}</p>
        {d.targetPercentage !== null && <p>Target {d.targetPercentage}%{d.targetAmount !== null ? ` (${formatCurrency(d.targetAmount)})` : ""}</p>}
        {d.varianceAmount !== null && (
          <p>{d.varianceAmount >= 0 ? "Over" : "Under"} plan by {formatCurrency(Math.abs(d.varianceAmount))}</p>
        )}
      </div>,
    );
  }
  if (link) {
    return box(`${link.source.label} → ${link.target.label}`, <p>{formatCurrency(link.value)}</p>);
  }
  return null;
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
              {d.actualPercentage !== null ? `${d.actualPercentage}%` : "—"}
            </StatusBadge>
          )}
        </div>
        <p className="small-text font-bold tabular mt-0.5" style={{ color: "var(--text-primary)" }}>
          {formatCurrency(d.actualAmount)}
        </p>
        <p className="micro-text mt-0.5" style={{ color: "var(--text-muted)" }}>
          {d.actualPercentage !== null ? `${d.actualPercentage}% of income` : "No income this period"}
          {d.targetPercentage !== null && ` · vs plan ${d.targetPercentage}%`}
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

  const sankeyData = { nodes: tree.nodes, links: tree.links };
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
          <ResponsiveContainer width="100%" height={340}>
            <Sankey
              data={sankeyData}
              nodeWidth={12}
              nodePadding={28}
              linkCurvature={0.55}
              iterations={32}
              margin={{ top: 28, right: 24, bottom: 12, left: 8 }}
              node={(props: NodeProps) => (
                <FlowSankeyNode {...props} selectedBucket={selectedBucket} onSelectBucket={handleSelectBucket} />
              )}
              link={(props: LinkProps) => <FlowSankeyLink {...props} selectedBucket={selectedBucket} />}
            >
              <Tooltip content={<FlowTooltipContent />} />
            </Sankey>
          </ResponsiveContainer>
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
