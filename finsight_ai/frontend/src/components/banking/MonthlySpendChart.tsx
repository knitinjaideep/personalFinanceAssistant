import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { AlertCircle } from "lucide-react";

interface Props {
  data: Array<{ month: string; spend: number }>;
  height?: number;
  emptyMessage?: string;
}

const tooltipStyle = {
  borderRadius: 10,
  fontSize: 12,
  background: "rgba(255,255,255,0.96)",
  border: "1px solid rgba(205,237,246,0.8)",
  boxShadow: "0 4px 16px rgba(11,60,93,0.10)",
};

export function MonthlySpendChart({ data, height = 160, emptyMessage }: Props) {
  const hasData = data.some((d) => d.spend > 0);

  if (!hasData) {
    return (
      <div
        className="rounded-xl flex flex-col items-center justify-center gap-2 py-8"
        style={{ height, background: "rgba(240,249,252,0.40)", border: "1px dashed rgba(205,237,246,0.70)" }}
      >
        <AlertCircle size={15} className="text-ocean/20" />
        <p className="text-[11px] text-ocean/30 text-center max-w-[200px] leading-relaxed">
          {emptyMessage ?? "No spending data yet. Upload or reprocess statements."}
        </p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} barSize={12} margin={{ left: 0, right: 4, top: 4, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,60,93,0.07)" vertical={false} />
        <XAxis
          dataKey="month"
          tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}`}
          width={36}
        />
        <Tooltip
          formatter={(v: number) => [`$${v.toLocaleString()}`, "Spend"]}
          contentStyle={tooltipStyle}
        />
        <Bar dataKey="spend" fill="#FF7A5A" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
