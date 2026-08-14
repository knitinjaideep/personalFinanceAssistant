"use client";

/**
 * Section 5 (pr-06-overview.md): Coral Insights — maximum 3, ranked,
 * deterministic (backend/app/domain/overview_insights.py::build_insights).
 * This component only renders what the backend already ranked and capped;
 * it never re-sorts, re-filters, or invents additional insights.
 */

import { CheckCircle2, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import InsightCard from "@/components/coral-ds/InsightCard";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import type { CoralInsight } from "@/features/overview/api";

interface CoralInsightsSectionProps {
  insights: CoralInsight[] | null;
  loading: boolean;
  error: boolean;
  onRetry?: () => void;
}

function iconFor(insight: CoralInsight) {
  if (insight.tone === "danger") return <TrendingUp size={16} />;
  if (insight.tone === "warning") return <TrendingDown size={16} />;
  if (insight.tone === "good") return <CheckCircle2 size={16} />;
  return <Sparkles size={16} />;
}

export default function CoralInsightsSection({ insights, loading, error, onRetry }: CoralInsightsSectionProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        <SkeletonState variant="card" height="150px" count={3} />
      </div>
    );
  }
  if (error) {
    return <ErrorState compact message="Couldn't load Coral Insights for this period." onRetry={onRetry} />;
  }
  if (!insights || insights.length === 0) {
    return (
      <EmptyState
        compact
        icon={<Sparkles size={22} />}
        title="No insights yet"
        description="Once Coral has enough classified activity for this period, ranked insights will appear here."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
      {insights.map((insight, i) => (
        <InsightCard
          key={`${insight.bucket ?? "summary"}-${insight.category ?? i}`}
          icon={iconFor(insight)}
          title={insight.title}
          description={insight.description}
          tone={insight.tone}
        />
      ))}
    </div>
  );
}
