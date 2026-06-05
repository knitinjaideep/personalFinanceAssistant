import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { AlertCircle } from "lucide-react";
import type { InvestmentsDashboard } from "../../api/dashboard";
import { useAppStore } from "../../store/appStore";

const CHART_COLORS = ["#1F6F8B", "#FF7A5A", "#4CAF93", "#FFD166", "#5FA8D3", "#FFA38F", "#0B3C5D"];

interface Props {
  allocation: InvestmentsDashboard["allocation"];
  loading?: boolean;
}

export function PortfolioAllocationWidget({ allocation, loading }: Props) {
  const isLight = useAppStore((s) => s.theme === "light");
  const tooltipStyle = {
    borderRadius: 10, fontSize: 12,
    background: isLight ? "rgba(255,255,255,0.97)" : "rgba(3,17,31,0.92)",
    border: isLight ? "1px solid rgba(31,111,139,0.20)" : "1px solid rgba(34,211,238,0.22)",
    boxShadow: isLight ? "0 4px 16px rgba(11,60,93,0.15)" : "0 4px 16px rgba(3,17,31,0.50)",
    color: isLight ? "rgba(11,40,65,0.85)" : "rgba(255,255,255,0.85)",
  };

  if (loading) {
    return (
      <div className="rounded-2xl p-5 animate-pulse" style={{ background: "var(--panel-bg-alt)", border: "1px solid var(--panel-border)" }}>
        <div className="w-32 h-2.5 rounded mb-4" style={{ background: "var(--empty-bg)" }} />
        <div className="w-full h-36 rounded" style={{ background: "var(--row-bg)" }} />
      </div>
    );
  }

  const slices = (allocation ?? []).map((a, i) => ({
    name: a.account_name,
    value: Math.round(a.total_value),
    pct: a.pct_of_portfolio,
    color: CHART_COLORS[i % CHART_COLORS.length],
  }));

  return (
    <div
      className="rounded-2xl p-5"
      style={{
        background: "var(--panel-bg-alt)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: "1px solid var(--panel-border-accent)",
        boxShadow: "var(--panel-shadow)",
      }}
    >
      <p className="text-[13px] font-semibold mb-1" style={{ color: "var(--text-primary)" }}>Portfolio Allocation</p>
      <p className="text-[11px] mb-4" style={{ color: "var(--text-muted)" }}>% of total by account</p>

      {slices.length < 2 ? (
        <div className="flex flex-col items-center gap-2 py-6 text-center">
          <AlertCircle size={16} style={{ color: "var(--empty-icon)" }} />
          <p className="text-[11px]" style={{ color: "var(--empty-text)" }}>Need 2+ accounts to show allocation</p>
        </div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie
                data={slices}
                cx="50%"
                cy="50%"
                innerRadius={44}
                outerRadius={68}
                paddingAngle={2}
                dataKey="value"
                strokeWidth={0}
              >
                {slices.map((entry, i) => <Cell key={i} fill={entry.color} />)}
              </Pie>
              <Tooltip
                formatter={(v: number, _: string, props: any) => [
                  `$${v.toLocaleString()} (${props.payload.pct}%)`,
                  props.payload.name,
                ]}
                contentStyle={tooltipStyle}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1">
            {slices.map((d, i) => (
              <span key={i} className="flex items-center gap-1.5 text-[10px]" style={{ color: "var(--text-secondary)" }}>
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: d.color }} />
                {d.name}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
