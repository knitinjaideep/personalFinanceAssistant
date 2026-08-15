"use client";

/**
 * Banking Insights (PR 10): render backend-ranked deterministic insights.
 * This component does not calculate, rank, or filter financial facts.
 */

import { AlertTriangle, CheckCircle2, SearchCheck, Sparkles, TrendingUp } from "lucide-react";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import InsightCard from "@/components/coral-ds/InsightCard";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import type { BankingInsight } from "@/features/banking/api";

interface BankingInsightsSectionProps {
  insights: BankingInsight[] | null;
  loading: boolean;
  error: boolean;
  onRetry?: () => void;
}

function iconFor(insight: BankingInsight) {
  if (insight.type === "classification_uncertainty") return <SearchCheck size={16} />;
  if (insight.tone === "danger") return <TrendingUp size={16} />;
  if (insight.tone === "warning") return <AlertTriangle size={16} />;
  if (insight.tone === "good") return <CheckCircle2 size={16} />;
  return <Sparkles size={16} />;
}

export default function BankingInsightsSection({
  insights,
  loading,
  error,
  onRetry,
}: BankingInsightsSectionProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SkeletonState variant="card" height="156px" count={3} />
      </div>
    );
  }
  if (error) {
    return <ErrorState compact message="Couldn't load Banking Insights for this period." onRetry={onRetry} />;
  }
  if (!insights || insights.length === 0) {
    return (
      <EmptyState
        compact
        icon={<Sparkles size={22} />}
        title="No banking insights yet"
        description="Once Coral has enough classified banking activity, the top three actions will appear here."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {insights.map((insight, index) => (
        <InsightCard
          key={`${insight.type}-${index}`}
          icon={iconFor(insight)}
          title={insight.title}
          description={insight.summary}
          tone={insight.tone}
          action={
            <p className="micro-text font-semibold" style={{ color: "var(--text-muted)" }}>
              {insight.action}
            </p>
          }
        />
      ))}
    </div>
  );
}
