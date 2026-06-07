import { TrendingUp, Shield, Home, Calendar } from "lucide-react";
import { DashboardMetricCard } from "../dashboard/DashboardMetricCard";
import type { InvestmentMetrics } from "../../lib/investmentsDashboard";

interface Props {
  metrics: InvestmentMetrics;
}

export function InvestmentMetricCards({ metrics }: Props) {
  const {
    totalPortfolioFmt,
    totalPortfolioSubtitle,
    portfolioTrend,
    iraTotalFmt,
    iraTotalSubtitle,
    downPaymentSavingsFmt,
    latestStatementFmt,
    latestStatementSource,
  } = metrics;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <DashboardMetricCard
        title="Total Portfolio"
        value={totalPortfolioFmt}
        subtitle={totalPortfolioSubtitle}
        trend={totalPortfolioFmt !== "Needs data" ? portfolioTrend : null}
        status={totalPortfolioFmt === "Needs data" ? "missing" : "ok"}
        icon={<TrendingUp size={14} />}
        accentColor="#22d3ee"
      />

      <DashboardMetricCard
        title="IRA Total"
        value={iraTotalFmt}
        subtitle={iraTotalSubtitle}
        status={iraTotalFmt === "Needs data" ? "missing" : "ok"}
        icon={<Shield size={14} />}
        accentColor="#4CAF93"
      />

      <DashboardMetricCard
        title="Down Payment Savings"
        value={downPaymentSavingsFmt}
        subtitle="Mapped savings account"
        status={downPaymentSavingsFmt === "Needs data" ? "missing" : "ok"}
        icon={<Home size={14} />}
        accentColor="#a78bfa"
      />

      <DashboardMetricCard
        title="Latest Statement"
        value={latestStatementFmt}
        subtitle={latestStatementSource !== "—" ? latestStatementSource : undefined}
        status={latestStatementFmt === "—" ? "missing" : "ok"}
        icon={<Calendar size={14} />}
        accentColor="#FFD166"
      />
    </div>
  );
}
