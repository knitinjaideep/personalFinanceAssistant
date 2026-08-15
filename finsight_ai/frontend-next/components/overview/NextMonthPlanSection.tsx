"use client";

/**
 * Section 6 (pr-06-overview.md): Next Month Plan — driven by the PR 14 Next
 * Month Planner (backend/app/domain/next_month_planner.py via
 * GET /api/v1/next-month-plan), superseding the old lightweight preview from
 * `overview_insights.build_next_month_plan` that module's own docstring
 * documents as a stand-in for this. Up to 3 ranked, deterministic
 * recommendations for this period's own drift — never a projection, never
 * user-editable/persisted here. See docs/NEXT_MONTH_PLANNER.md.
 */

import { CheckCircle2, PiggyBank, Search, Settings2, Target, TrendingUp } from "lucide-react";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import Surface from "@/components/coral-ds/Surface";
import { formatCurrency } from "@/lib/utils";
import type { Recommendation, RecommendationActionType } from "@/features/overview/api";

interface NextMonthPlanSectionProps {
  recommendations: Recommendation[] | null;
  loading: boolean;
  error: boolean;
  onRetry?: () => void;
  showSourceFacts?: boolean;
}

const ACTION_ICON: Record<RecommendationActionType, React.ReactNode> = {
  reduce_category: <Target size={15} />,
  increase_savings_goal: <PiggyBank size={15} />,
  increase_investment_contribution: <TrendingUp size={15} />,
  maintain_contribution: <CheckCircle2 size={15} />,
  review_merchant: <Search size={15} />,
  // Declared for forward-compatibility but never emitted by the backend this
  // round (see docs/NEXT_MONTH_PLANNER.md) — icon included so this map stays
  // exhaustive over RecommendationActionType.
  review_subscription: <Search size={15} />,
  adjust_plan: <Settings2 size={15} />,
};

export default function NextMonthPlanSection({
  recommendations,
  loading,
  error,
  onRetry,
  showSourceFacts = false,
}: NextMonthPlanSectionProps) {
  if (loading) return <SkeletonState variant="card" height="220px" />;
  if (error) {
    return <ErrorState compact message="Couldn't load next period's plan." onRetry={onRetry} />;
  }
  if (!recommendations || recommendations.length === 0) {
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
      {recommendations.map((rec) => (
        <Surface
          key={`${rec.priority}-${rec.action_type}-${rec.category ?? rec.bucket ?? "plan"}`}
          padding="sm"
          className="flex items-start gap-3"
        >
          <span
            className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: "var(--status-neutral-soft)", color: "var(--text-secondary)" }}
          >
            {ACTION_ICON[rec.action_type] ?? <Target size={15} />}
          </span>
          <div className="flex-1 min-w-0">
            <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>
              {rec.title}
            </p>
            <p className="micro-text mt-0.5" style={{ color: "var(--text-muted)" }}>
              {rec.reason}
            </p>
            {rec.incomplete_source && (
              <p className="micro-text mt-0.5" style={{ color: "var(--status-warning)" }}>
                Based on incomplete data - see details.
              </p>
            )}
            {showSourceFacts && rec.source_facts.length > 0 && (
              <dl
                className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1"
                style={{ color: "var(--text-muted)" }}
              >
                {rec.source_facts.map((fact) => (
                  <div key={`${fact.label}-${fact.value}`} className="min-w-0">
                    <dt className="micro-text font-semibold" style={{ color: "var(--text-secondary)" }}>
                      {fact.label}
                    </dt>
                    <dd className="micro-text truncate">{fact.value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
          <span
            className="micro-text font-semibold tabular-nums shrink-0"
            style={{ color: "var(--text-secondary)" }}
          >
            {formatCurrency(Number(rec.estimated_impact))}
          </span>
        </Surface>
      ))}
    </div>
  );
}
