"use client";

/**
 * Section 6 (pr-06-overview.md): Next Month Plan — small, focused preview
 * driven entirely by the deterministic engine output
 * (backend/app/domain/overview_insights.py::build_next_month_plan). This is
 * explicitly NOT the full Next Month Planner (PR 14 / Milestone M6) — no
 * projections, no editing, just a read-only preview of up to 3 deterministic
 * recommendations for this period's own variance.
 */

import { CheckCircle2, PiggyBank, Target, TrendingUp } from "lucide-react";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import Surface from "@/components/coral-ds/Surface";
import { formatCurrency } from "@/lib/utils";
import type { NextMonthActionType, NextMonthPlanItem } from "@/features/overview/api";

interface NextMonthPlanSectionProps {
  items: NextMonthPlanItem[] | null;
  loading: boolean;
  error: boolean;
  onRetry?: () => void;
}

const ACTION_ICON: Record<NextMonthActionType, React.ReactNode> = {
  reduce_category: <Target size={15} />,
  increase_savings_goal: <PiggyBank size={15} />,
  increase_investment_contribution: <TrendingUp size={15} />,
  maintain_contribution: <CheckCircle2 size={15} />,
};

export default function NextMonthPlanSection({ items, loading, error, onRetry }: NextMonthPlanSectionProps) {
  if (loading) return <SkeletonState variant="card" height="220px" />;
  if (error) {
    return <ErrorState compact message="Couldn't load next period's plan." onRetry={onRetry} />;
  }
  if (!items || items.length === 0) {
    return (
      <EmptyState
        compact
        icon={<Target size={22} />}
        title="Nothing to adjust yet"
        description="Coral will suggest adjustments here once it has enough data for this period."
      />
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <Surface key={`${item.bucket}-${item.category ?? item.action_type}`} padding="sm" className="flex items-start gap-3">
          <span
            className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: "var(--status-neutral-soft)", color: "var(--text-secondary)" }}
          >
            {ACTION_ICON[item.action_type] ?? <Target size={15} />}
          </span>
          <div className="flex-1 min-w-0">
            <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>{item.title}</p>
            <p className="micro-text mt-0.5" style={{ color: "var(--text-muted)" }}>{item.description}</p>
          </div>
          <span
            className="micro-text font-semibold tabular-nums shrink-0"
            style={{ color: "var(--text-secondary)" }}
          >
            {formatCurrency(Number(item.estimated_impact))}
          </span>
        </Surface>
      ))}
    </div>
  );
}
