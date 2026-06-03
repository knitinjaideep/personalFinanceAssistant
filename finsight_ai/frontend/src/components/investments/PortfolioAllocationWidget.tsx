import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { AlertCircle } from "lucide-react";
import type { InvestmentsDashboard } from "../../api/dashboard";

const CHART_COLORS = ["#1F6F8B", "#FF7A5A", "#4CAF93", "#FFD166", "#5FA8D3", "#FFA38F", "#0B3C5D"];

const tooltipStyle = {
  borderRadius: 10,
  fontSize: 12,
  background: "rgba(3,17,31,0.92)",
  border: "1px solid rgba(34,211,238,0.22)",
  boxShadow: "0 4px 16px rgba(3,17,31,0.50)",
  color: "rgba(255,255,255,0.85)",
};

interface Props {
  allocation: InvestmentsDashboard["allocation"];
  loading?: boolean;
}

export function PortfolioAllocationWidget({ allocation, loading }: Props) {
  if (loading) {
    return (
      <div className="rounded-2xl p-5 animate-pulse" style={{ background: "rgba(3,17,31,0.60)", border: "1px solid rgba(34,211,238,0.10)" }}>
        <div className="w-32 h-2.5 rounded mb-4" style={{ background: "rgba(34,211,238,0.10)" }} />
        <div className="w-full h-36 rounded" style={{ background: "rgba(34,211,238,0.07)" }} />
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
        background: "rgba(3,17,31,0.60)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: "1px solid rgba(34,211,238,0.12)",
        boxShadow: "0 8px 32px rgba(3,17,31,0.40)",
      }}
    >
      <p className="text-[13px] font-semibold text-white mb-1">Portfolio Allocation</p>
      <p className="text-[11px] mb-4" style={{ color: "rgba(255,255,255,0.38)" }}>% of total by account</p>

      {slices.length < 2 ? (
        <div className="flex flex-col items-center gap-2 py-6 text-center">
          <AlertCircle size={16} style={{ color: "rgba(255,255,255,0.18)" }} />
          <p className="text-[11px]" style={{ color: "rgba(255,255,255,0.30)" }}>Need 2+ accounts to show allocation</p>
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
              <span key={i} className="flex items-center gap-1.5 text-[10px]" style={{ color: "rgba(255,255,255,0.50)" }}>
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
