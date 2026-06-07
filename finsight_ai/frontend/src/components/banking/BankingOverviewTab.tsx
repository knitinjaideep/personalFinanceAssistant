import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  LineChart, Line,
} from "recharts";
import { CreditCard, Landmark, PiggyBank } from "lucide-react";
import { SectionCard } from "../dashboard/SectionCard";
import { DashboardEmptyState } from "../dashboard/DashboardEmptyState";
import { BankingInsights } from "./BankingInsights";
import { BankingMetricCards } from "./BankingMetricCards";
import type { BankingMetrics, BankingInsight, BankingAccountRow, MonthlySpendPoint, CashFlowPoint } from "../../lib/bankingDashboard";
import { formatCurrency } from "../../lib/dashboardData";
import { useAppStore } from "../../store/appStore";

interface SummaryGroupProps {
  title: string;
  icon: React.ReactNode;
  accentColor: string;
  rows: BankingAccountRow[];
  onSeeAll: () => void;
}

function AccountGroupSummary({ title, icon, accentColor, rows, onSeeAll }: SummaryGroupProps) {
  const withData = rows.filter((r) => r.status !== "missing");
  const totalSpend = withData.reduce((s, r) => s + r.latestSpend, 0);

  return (
    <div
      className="rounded-[20px] p-4"
      style={{
        background: "var(--panel-bg)",
        backdropFilter: "blur(16px)",
        border: `1px solid ${accentColor}20`,
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div
            className="w-6 h-6 rounded-lg flex items-center justify-center"
            style={{ background: `${accentColor}18`, color: accentColor }}
          >
            {icon}
          </div>
          <span className="text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>{title}</span>
        </div>
        <button
          type="button"
          onClick={onSeeAll}
          className="text-[11px] font-medium transition-colors hover:text-white"
          style={{ color: "#22d3ee" }}
        >
          See all →
        </button>
      </div>

      {withData.length === 0 ? (
        <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          No {title.toLowerCase()} data found. Upload statements.
        </p>
      ) : (
        <div className="space-y-1.5">
          {withData.slice(0, 3).map((row) => (
            <div key={row.config.key} className="flex items-center justify-between">
              <span className="text-[12px]" style={{ color: "var(--text-secondary)" }}>{row.config.displayName}</span>
              <span className="text-[12px] font-semibold tabular" style={{ color: "var(--text-primary)" }}>
                {row.latestSpend > 0 ? formatCurrency(row.latestSpend) : "—"}
              </span>
            </div>
          ))}
          {totalSpend > 0 && (
            <div
              className="flex items-center justify-between pt-2 mt-2"
              style={{ borderTop: "1px solid var(--panel-border)" }}
            >
              <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Total</span>
              <span className="text-[13px] font-bold" style={{ color: "var(--text-primary)" }}>
                {formatCurrency(totalSpend)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface Props {
  metrics: BankingMetrics;
  insights: BankingInsight[];
  spendChart: MonthlySpendPoint[];
  cashFlowChart: CashFlowPoint[];
  creditCardRows: BankingAccountRow[];
  checkingRows: BankingAccountRow[];
  savingsRows: BankingAccountRow[];
  onTabChange: (tab: string) => void;
  onDocuments: () => void;
}

export function BankingOverviewTab({
  metrics,
  insights,
  spendChart,
  cashFlowChart,
  creditCardRows,
  checkingRows,
  savingsRows,
  onTabChange,
  onDocuments,
}: Props) {
  const isLight = useAppStore((s) => s.theme === "light");
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

  const hasSpendData = spendChart.some((p) => p.spend > 0);
  const hasCFData = cashFlowChart.some((p) => p.inflow > 0 || p.outflow > 0);

  return (
    <div className="space-y-4">
      {/* Metric cards */}
      <BankingMetricCards metrics={metrics} onNeedsAttentionClick={() => onTabChange("statements")} />

      {/* Insights + Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* What changed */}
        <BankingInsights insights={insights} />

        {/* Monthly spend chart */}
        <SectionCard title="Monthly Spend" subtitle="Across all credit cards">
          {hasSpendData ? (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={spendChart} barSize={16}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 10, fill: axisColor }} tickLine={false} axisLine={false} />
                <YAxis
                  tick={{ fontSize: 10, fill: axisColor }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                  width={36}
                />
                <Tooltip
                  formatter={(v: number) => [`$${v.toLocaleString()}`, "Spend"]}
                  contentStyle={tooltipStyle}
                />
                <Bar dataKey="spend" fill="#FF7A5A" radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <DashboardEmptyState
              compact
              title="No spend data"
              description="Upload credit card statements to see monthly spend."
              primaryAction={{ label: "Upload", onClick: onDocuments }}
            />
          )}
        </SectionCard>
      </div>

      {/* Cash flow chart */}
      <SectionCard title="Cash Flow" subtitle="Checking account inflow vs outflow">
        {hasCFData ? (
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={cashFlowChart}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: axisColor }} tickLine={false} axisLine={false} />
              <YAxis
                tick={{ fontSize: 10, fill: axisColor }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                width={36}
              />
              <Tooltip
                formatter={(v: number, name: string) => [`$${v.toLocaleString()}`, name]}
                contentStyle={tooltipStyle}
              />
              <Line type="monotone" dataKey="inflow" stroke="#4CAF93" strokeWidth={2} dot={false} name="Inflow" />
              <Line type="monotone" dataKey="outflow" stroke="#E45757" strokeWidth={2} dot={false} name="Outflow" />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <DashboardEmptyState
            compact
            title="No cash flow data"
            description="Upload checking account statements to see cash flow."
            primaryAction={{ label: "Upload", onClick: onDocuments }}
          />
        )}
      </SectionCard>

      {/* Account group summaries */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <AccountGroupSummary
          title="Credit Cards"
          icon={<CreditCard size={13} />}
          accentColor="#FF7A5A"
          rows={creditCardRows}
          onSeeAll={() => onTabChange("accounts")}
        />
        <AccountGroupSummary
          title="Checking"
          icon={<Landmark size={13} />}
          accentColor="#22d3ee"
          rows={checkingRows}
          onSeeAll={() => onTabChange("accounts")}
        />
        <AccountGroupSummary
          title="Savings"
          icon={<PiggyBank size={13} />}
          accentColor="#4CAF93"
          rows={savingsRows}
          onSeeAll={() => onTabChange("accounts")}
        />
      </div>
    </div>
  );
}
