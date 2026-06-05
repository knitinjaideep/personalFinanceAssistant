import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import { AlertCircle } from "lucide-react";
import { useAppStore } from "../../store/appStore";

interface Props {
  data: Array<{ month: string; inflow: number; outflow: number; net?: number }>;
  height?: number;
  emptyMessage?: string;
}

export function CashFlowChart({ data, height = 160, emptyMessage }: Props) {
  const isLight = useAppStore((s) => s.theme === "light");
  const axisColor = isLight ? "rgba(11,40,65,0.45)" : "rgba(255,255,255,0.38)";
  const gridColor = isLight ? "rgba(31,111,139,0.10)" : "rgba(34,211,238,0.07)";
  const legendColor = isLight ? "rgba(11,40,65,0.50)" : "rgba(255,255,255,0.45)";
  const tooltipStyle = {
    borderRadius: 10,
    fontSize: 12,
    background: isLight ? "rgba(255,255,255,0.97)" : "rgba(3,17,31,0.92)",
    border: isLight ? "1px solid rgba(31,111,139,0.20)" : "1px solid rgba(34,211,238,0.22)",
    boxShadow: isLight ? "0 4px 16px rgba(11,60,93,0.15)" : "0 4px 16px rgba(3,17,31,0.50)",
    color: isLight ? "rgba(11,40,65,0.85)" : "rgba(255,255,255,0.85)",
  };

  const hasData = data.some((d) => d.inflow > 0 || d.outflow > 0);

  if (!hasData) {
    return (
      <div
        className="rounded-xl flex flex-col items-center justify-center gap-2 py-8"
        style={{ height, background: "var(--empty-bg)", border: "1px dashed var(--empty-border)" }}
      >
        <AlertCircle size={15} style={{ color: "var(--empty-icon)" }} />
        <p className="text-[11px] text-center max-w-[200px] leading-relaxed" style={{ color: "var(--empty-text)" }}>
          {emptyMessage ?? "No cash flow data yet. Upload checking or savings statements."}
        </p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} barSize={10} barGap={2} margin={{ left: 0, right: 4, top: 4, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
        <XAxis
          dataKey="month"
          tick={{ fontSize: 10, fill: axisColor }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 10, fill: axisColor }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}`}
          width={36}
        />
        <Tooltip
          formatter={(v: number, name: string) => [`$${v.toLocaleString()}`, name]}
          contentStyle={tooltipStyle}
        />
        <Legend
          iconSize={8}
          iconType="circle"
          wrapperStyle={{ fontSize: 10, color: legendColor, paddingTop: 4 }}
        />
        <Bar dataKey="inflow"  name="Inflow"  fill="#4CAF93" radius={[4, 4, 0, 0]} />
        <Bar dataKey="outflow" name="Outflow" fill="#FF7A5A" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
