import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell,
} from "recharts";
import { InvestmentMetricCards } from "./InvestmentMetricCards";
import { InvestmentInsights } from "./InvestmentInsights";
import { InvestmentAccountCardItem } from "./InvestmentAccountCard";
import { InvestmentAccountDetailDrawer } from "./InvestmentAccountDetailDrawer";
import { SectionCard } from "../dashboard/SectionCard";
import { DashboardEmptyState } from "../dashboard/DashboardEmptyState";
import type { InvestmentMetrics, InvestmentInsight, InvestmentAccountCard, AllocationSlice, PortfolioTrendPoint } from "../../lib/investmentsDashboard";
import type { Holding } from "../../api/dashboard";
import { formatCurrency } from "../../lib/dashboardData";
import { useAppStore } from "../../store/appStore";

interface Props {
  metrics: InvestmentMetrics;
  insights: InvestmentInsight[];
  accountCards: InvestmentAccountCard[];
  allocation: AllocationSlice[];
  trendData: PortfolioTrendPoint[];
  holdings: Holding[];
  onDocuments: () => void;
  onAskCoral: () => void;
}

export function InvestmentsOverviewTab({
  metrics,
  insights,
  accountCards,
  allocation,
  trendData,
  holdings,
  onDocuments,
  onAskCoral,
}: Props) {
  const isLight = useAppStore((s) => s.theme === "light");
  const [selectedCard, setSelectedCard] = useState<InvestmentAccountCard | null>(null);

  const axisColor = isLight ? "rgba(7,31,51,0.55)" : "rgba(220,242,250,0.45)";
  const gridColor = isLight ? "rgba(31,111,139,0.12)" : "rgba(34,211,238,0.07)";
  const tooltipStyle = {
    borderRadius: 10,
    fontSize: 11,
    background: isLight ? "rgba(255,255,255,0.97)" : "rgba(5,20,36,0.94)",
    border: isLight ? "1px solid rgba(31,111,139,0.22)" : "1px solid rgba(34,211,238,0.22)",
    color: isLight ? "rgba(7,31,51,0.88)" : "rgba(220,242,250,0.88)",
    boxShadow: "0 4px 16px rgba(3,17,31,0.4)",
  };

  return (
    <div className="space-y-4">
      {/* Metric cards */}
      <InvestmentMetricCards metrics={metrics} />

      {/* Insights + Trend row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <InvestmentInsights insights={insights} />

        {/* Portfolio trend */}
        <SectionCard title="Portfolio History" subtitle="Total value across all accounts">
          {trendData.length < 2 ? (
            <DashboardEmptyState
              compact
              title="Need more data"
              description="Upload at least two months of investment statements to show the trend."
              primaryAction={{ label: "Upload", onClick: onDocuments }}
            />
          ) : (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={trendData} barSize={14}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 10, fill: axisColor }} tickLine={false} axisLine={false} />
                <YAxis
                  tick={{ fontSize: 10, fill: axisColor }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                  width={40}
                />
                <Tooltip
                  formatter={(v: number) => [`$${v.toLocaleString()}`, "Value"]}
                  contentStyle={tooltipStyle}
                />
                <Bar dataKey="value" fill="#22d3ee" radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </SectionCard>
      </div>

      {/* Allocation chart + accounts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Allocation */}
        <SectionCard title="Portfolio Allocation" subtitle="By account">
          {allocation.length === 0 ? (
            <DashboardEmptyState
              compact
              title="No allocation data"
              description="Allocation will appear once investment statements are parsed."
              primaryAction={{ label: "Upload", onClick: onDocuments }}
            />
          ) : (
            <div className="flex items-center gap-6">
              <ResponsiveContainer width={140} height={140}>
                <PieChart>
                  <Pie
                    data={allocation}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={65}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {allocation.map((slice, i) => (
                      <Cell key={i} fill={slice.color} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>

              <div className="flex-1 space-y-2 min-w-0">
                {allocation.map((slice, i) => (
                  <div key={i} className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: slice.color }} />
                      <span className="text-[11px] truncate" style={{ color: "var(--text-secondary)" }}>
                        {slice.name.slice(0, 20)}
                      </span>
                    </div>
                    <div className="text-right shrink-0">
                      <span className="text-[11px] font-semibold" style={{ color: "var(--text-primary)" }}>
                        {slice.pct}%
                      </span>
                      <span className="block text-[10px]" style={{ color: "var(--text-dim)" }}>
                        {formatCurrency(slice.value)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </SectionCard>

        {/* IRA vs brokerage bar */}
        <SectionCard title="IRA vs Brokerage">
          {metrics.totalPortfolio === 0 ? (
            <DashboardEmptyState
              compact
              title="No portfolio data"
              description="Upload Morgan Stanley or E*TRADE statements."
              primaryAction={{ label: "Upload", onClick: onDocuments }}
            />
          ) : (
            <div className="space-y-3 pt-1">
              {[
                { label: "IRA / Retirement", value: metrics.iraTotal, color: "#4CAF93" },
                { label: "Brokerage / Other", value: Math.max(0, metrics.totalPortfolio - metrics.iraTotal), color: "#22d3ee" },
              ].map(({ label, value, color }) => {
                const pct = metrics.totalPortfolio > 0 ? Math.round((value / metrics.totalPortfolio) * 100) : 0;
                return (
                  <div key={label}>
                    <div className="flex items-center justify-between text-[12px] mb-1.5">
                      <span className="font-medium" style={{ color: "var(--text-secondary)" }}>{label}</span>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold tabular" style={{ color }}>
                          {formatCurrency(value)}
                        </span>
                        <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                          {pct}%
                        </span>
                      </div>
                    </div>
                    <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--insight-bg)" }}>
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </SectionCard>
      </div>

      {/* Account cards */}
      {accountCards.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {accountCards.map((card, i) => (
              <InvestmentAccountCardItem
                key={i}
                card={card}
                onClick={() => setSelectedCard(card)}
              />
            ))}
          </div>

          <InvestmentAccountDetailDrawer
            card={selectedCard}
            holdings={holdings}
            open={!!selectedCard}
            onClose={() => setSelectedCard(null)}
            onAskCoral={onAskCoral}
            onViewDocuments={onDocuments}
          />
        </>
      )}
    </div>
  );
}
