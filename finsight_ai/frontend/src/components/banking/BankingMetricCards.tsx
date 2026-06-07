import { CreditCard, TrendingUp, Calendar, AlertCircle } from "lucide-react";
import { DashboardMetricCard } from "../dashboard/DashboardMetricCard";
import type { BankingMetrics } from "../../lib/bankingDashboard";

interface Props {
  metrics: BankingMetrics;
  onNeedsAttentionClick?: () => void;
}

export function BankingMetricCards({ metrics, onNeedsAttentionClick }: Props) {
  const {
    monthlySpendFmt,
    monthlySpendTrend,
    cashFlowFmt,
    cashFlowDirection,
    upcomingPaymentsCount,
    needsAttentionCount,
    needsAttentionItems,
  } = metrics;

  const cashFlowStatus =
    cashFlowDirection === "positive" ? "ok" : cashFlowDirection === "negative" ? "warn" : "missing";

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <DashboardMetricCard
        title="Monthly Spend"
        value={monthlySpendFmt}
        subtitle={monthlySpendFmt === "Needs data" ? undefined : "Latest available month"}
        trend={monthlySpendFmt !== "Needs data" ? monthlySpendTrend : null}
        status={monthlySpendFmt === "Needs data" ? "missing" : "ok"}
        icon={<CreditCard size={14} />}
        accentColor="#FF7A5A"
      />

      <DashboardMetricCard
        title="Cash Flow"
        value={cashFlowFmt}
        subtitle={
          cashFlowFmt === "Needs data"
            ? undefined
            : cashFlowDirection === "positive"
              ? "Income exceeded spending"
              : cashFlowDirection === "negative"
                ? "Spending exceeded income"
                : "Checking accounts"
        }
        status={cashFlowFmt === "Needs data" ? "missing" : cashFlowStatus}
        icon={<TrendingUp size={14} />}
        accentColor={cashFlowDirection === "positive" ? "#4CAF93" : cashFlowDirection === "negative" ? "#E45757" : "#22d3ee"}
      />

      <DashboardMetricCard
        title="Upcoming Payments"
        value={upcomingPaymentsCount > 0 ? `${upcomingPaymentsCount} due` : "—"}
        subtitle={upcomingPaymentsCount > 0 ? "Credit card statements" : "No data available"}
        status={upcomingPaymentsCount > 0 ? "warn" : "missing"}
        icon={<Calendar size={14} />}
        accentColor="#FFD166"
      />

      <DashboardMetricCard
        title="Needs Attention"
        value={needsAttentionCount > 0 ? `${needsAttentionCount} item${needsAttentionCount > 1 ? "s" : ""}` : "All good"}
        subtitle={
          needsAttentionCount > 0
            ? needsAttentionItems[0]?.slice(0, 36) + (needsAttentionItems[0]?.length > 36 ? "…" : "")
            : "Banking data looks complete"
        }
        status={needsAttentionCount > 0 ? "warn" : "ok"}
        icon={<AlertCircle size={14} />}
        accentColor={needsAttentionCount > 0 ? "#E45757" : "#4CAF93"}
        onClick={needsAttentionCount > 0 ? onNeedsAttentionClick : undefined}
      />
    </div>
  );
}
