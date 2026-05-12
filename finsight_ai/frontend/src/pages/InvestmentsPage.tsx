import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { AlertCircle } from "lucide-react";
import { dashboardApi } from "../api/dashboard";
import type { InvestmentsDashboard } from "../api/dashboard";
import { staggerContainer, staggerChild, contentPageVariants } from "../design/motion";

const CHART_COLORS = [
  "#1F6F8B", "#FF7A5A", "#4CAF93", "#FFD166",
  "#5FA8D3", "#FFA38F", "#0B3C5D", "#E45757",
];

function PageHeader() {
  return (
    <div
      className="shrink-0 px-7 py-5"
      style={{
        borderBottom: "1px solid rgba(205,237,246,0.50)",
        background: "rgba(255,255,255,0.55)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      <h1 className="text-[18px] font-bold text-ocean-deep tracking-tight">Investments</h1>
      <p className="text-[12px] text-ocean/40 mt-0.5 font-medium">Portfolio, holdings & performance</p>
    </div>
  );
}

function GlassCard({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl p-5 ${className ?? ""}`}
      style={{
        background: "rgba(255,255,255,0.82)",
        border: "1px solid rgba(205,237,246,0.65)",
        boxShadow: "0 4px 24px rgba(11,60,93,0.07), inset 0 1px 0 rgba(255,255,255,0.90)",
      }}>
      {children}
    </div>
  );
}

function ChartTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div className="mb-4">
      <p className="text-[13px] font-semibold text-ocean-deep">{children}</p>
      {sub && <p className="text-[11px] text-ocean/40 mt-0.5">{sub}</p>}
    </div>
  );
}

function EmptyBox({ message }: { message: string }) {
  return (
    <div className="rounded-xl flex flex-col items-center justify-center gap-2 py-8"
      style={{ background: "rgba(240,249,252,0.40)", border: "1px dashed rgba(205,237,246,0.70)" }}>
      <AlertCircle size={16} className="text-ocean/20" />
      <p className="text-[11px] text-ocean/30 text-center max-w-[200px] leading-relaxed">{message}</p>
    </div>
  );
}

function Skeleton({ h = 160 }: { h?: number }) {
  return <div className="rounded-xl animate-pulse" style={{ height: h, background: "rgba(205,237,246,0.20)" }} />;
}

const tooltipStyle = {
  borderRadius: 10, fontSize: 12,
  background: "rgba(255,255,255,0.96)",
  border: "1px solid rgba(205,237,246,0.8)",
  boxShadow: "0 4px 16px rgba(11,60,93,0.10)",
};

export function InvestmentsPage() {
  const [loading, setLoading] = useState(true);
  const [data, setData]       = useState<InvestmentsDashboard | null>(null);

  const fetch = useCallback(async () => {
    try { setData(await dashboardApi.investments()); }
    catch { /* backend not ready */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  const hasData = !!data && data.portfolio_summary.accounts.length > 0;
  const ps = data?.portfolio_summary;

  const allocationPie = (data?.allocation ?? []).map((a, i) => ({
    name: a.account_name,
    value: a.total_value,
    pct: a.pct_of_portfolio,
    color: CHART_COLORS[i % CHART_COLORS.length],
  }));

  const historyByDate: Record<string, number> = {};
  for (const pt of data?.balance_history ?? []) {
    historyByDate[pt.date] = (historyByDate[pt.date] ?? 0) + pt.total_value;
  }
  const historyData = Object.entries(historyByDate)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, value]) => ({ date: date.slice(0, 7), value: Math.round(value) }));

  const glPositive = (ps?.total_unrealized_gain_loss ?? 0) >= 0;

  return (
    <div className="flex flex-col h-full">
      <PageHeader />
      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-5"
      >

        {/* Summary strip */}
        {!loading && hasData && ps && (
          <motion.div variants={staggerChild}>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                {
                  label: "Portfolio Value",
                  value: `$${ps.total_portfolio_value_fmt}`,
                  color: "#0B3C5D",
                },
                {
                  label: "Unrealized G/L",
                  value: `${glPositive ? "+" : ""}$${ps.total_unrealized_gain_loss_fmt}`,
                  color: glPositive ? "#4CAF93" : "#E45757",
                },
                {
                  label: "Accounts",
                  value: String(ps.accounts.length),
                  color: "#1F6F8B",
                },
                {
                  label: "Top Holdings",
                  value: String(data!.top_holdings.length),
                  color: "#c89a00",
                },
              ].map(({ label, value, color }) => (
                <div key={label} className="rounded-2xl p-4 text-center"
                  style={{ background: "rgba(255,255,255,0.88)", border: "1px solid rgba(205,237,246,0.65)" }}>
                  <p className="text-[10px] font-semibold text-ocean/38 uppercase tracking-widest mb-1.5">{label}</p>
                  <p className="text-[18px] font-bold tracking-tight tabular" style={{ color }}>{value}</p>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Account cards */}
        {!loading && hasData && (
          <motion.div variants={staggerContainer} initial="hidden" animate="visible"
            className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {ps!.accounts.map((acct, i) => {
              const glPos = acct.unrealized_gain_loss >= 0;
              return (
                <motion.div key={i} variants={staggerChild}
                  className="rounded-2xl p-4"
                  style={{ background: "rgba(255,255,255,0.88)", border: "1px solid rgba(205,237,246,0.60)" }}>
                  <div className="flex items-start justify-between mb-2">
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold text-ocean-deep truncate">{acct.account_name}</p>
                      <p className="text-[10px] text-ocean/40 capitalize">{acct.institution_type}</p>
                    </div>
                    <p className="text-[15px] font-bold text-ocean-deep shrink-0 ml-2">${acct.total_value_fmt}</p>
                  </div>
                  <div className="flex items-center justify-between text-[11px]">
                    <span className={`font-semibold ${glPos ? "text-positive" : "text-coral"}`}>
                      {glPos ? "+" : ""}${acct.unrealized_gain_loss_fmt} G/L
                      {acct.gain_loss_pct !== null && (
                        <span className="ml-1 opacity-65">({acct.gain_loss_pct > 0 ? "+" : ""}{acct.gain_loss_pct}%)</span>
                      )}
                    </span>
                    {acct.latest_statement_date && (
                      <span className="text-ocean/30">as of {acct.latest_statement_date}</span>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </motion.div>
        )}

        {/* Portfolio history + allocation side by side */}
        <motion.div variants={staggerContainer} initial="hidden" animate="visible"
          className="grid grid-cols-1 lg:grid-cols-2 gap-4">

          <motion.div variants={staggerChild}>
            <GlassCard>
              <ChartTitle sub="Total value across all accounts">Portfolio History</ChartTitle>
              {loading ? <Skeleton h={180} /> : historyData.length < 2 ? (
                <EmptyBox message="Need at least 2 months of statements to show history" />
              ) : (
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={historyData} barSize={14}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,60,93,0.07)" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }} tickLine={false} axisLine={false}
                      tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} width={40} />
                    <Tooltip formatter={(v: number) => [`$${v.toLocaleString()}`, "Value"]} contentStyle={tooltipStyle} />
                    <Bar dataKey="value" fill="#1F6F8B" radius={[5, 5, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </GlassCard>
          </motion.div>

          <motion.div variants={staggerChild}>
            <GlassCard>
              <ChartTitle sub="% of total portfolio">Allocation by Account</ChartTitle>
              {loading ? <Skeleton h={180} /> : allocationPie.length < 2 ? (
                <EmptyBox message="Need multiple accounts to show allocation breakdown" />
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={160}>
                    <PieChart>
                      <Pie data={allocationPie} cx="50%" cy="50%" innerRadius={44} outerRadius={68}
                        paddingAngle={2} dataKey="value" strokeWidth={0}>
                        {allocationPie.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                      </Pie>
                      <Tooltip
                        formatter={(v: number, _: string, props: any) => [
                          `$${v.toLocaleString()} (${props.payload.pct}%)`, props.payload.name
                        ]}
                        contentStyle={tooltipStyle}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                    {allocationPie.map((d, i) => (
                      <span key={i} className="flex items-center gap-1.5 text-[10px] text-ocean/55">
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: d.color }} />
                        {d.name}
                      </span>
                    ))}
                  </div>
                </>
              )}
            </GlassCard>
          </motion.div>
        </motion.div>

        {/* Top holdings table */}
        {!loading && hasData && data!.top_holdings.length > 0 && (
          <motion.div variants={staggerChild}>
            <GlassCard>
              <ChartTitle sub={`${data!.top_holdings.length} positions`}>Holdings</ChartTitle>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-ocean-50/60" style={{ color: "rgba(11,60,93,0.35)" }}>
                      <th className="text-left py-2 pr-3 font-semibold">Symbol</th>
                      <th className="text-right py-2 px-2 font-semibold">Qty</th>
                      <th className="text-right py-2 px-2 font-semibold">Value</th>
                      <th className="text-right py-2 px-2 font-semibold">G/L</th>
                      <th className="text-right py-2 pl-2 font-semibold">Wt%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data!.top_holdings.slice(0, 20).map((h, i) => {
                      const glPos = h.unrealized_gain_loss >= 0;
                      return (
                        <tr key={i} className="border-b border-ocean-50/40 last:border-0 hover:bg-ocean-50/20 transition-colors">
                          <td className="py-2 pr-3">
                            <span className="font-semibold text-ocean-deep">{h.symbol ?? "–"}</span>
                            {h.symbol && (
                              <span className="block text-[10px] text-ocean/35 truncate max-w-[130px]">
                                {h.description.slice(0, 22)}
                              </span>
                            )}
                          </td>
                          <td className="text-right py-2 px-2 text-ocean/45 tabular">
                            {h.quantity !== null ? h.quantity.toFixed(2) : "–"}
                          </td>
                          <td className="text-right py-2 px-2 font-semibold text-ocean-deep tabular">
                            ${h.market_value_fmt}
                          </td>
                          <td className={`text-right py-2 px-2 font-semibold tabular ${glPos ? "text-positive" : "text-coral"}`}>
                            {glPos ? "+" : ""}${h.unrealized_gain_loss_fmt}
                          </td>
                          <td className="text-right py-2 pl-2 text-ocean/38 tabular">
                            {h.portfolio_weight !== null ? `${h.portfolio_weight}%` : "–"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          </motion.div>
        )}

        {!loading && !hasData && (
          <motion.div variants={staggerChild}>
            <div className="rounded-2xl px-6 py-12 text-center"
              style={{ background: "rgba(255,255,255,0.65)", border: "1px dashed rgba(205,237,246,0.70)" }}>
              <div className="text-3xl mb-3">📈</div>
              <p className="text-[14px] font-semibold text-ocean-deep mb-1.5">No investment data yet</p>
              <p className="text-[12px] text-ocean/40 max-w-xs mx-auto leading-relaxed">
                Upload Morgan Stanley or E*TRADE statements to see your portfolio, holdings, and performance.
              </p>
            </div>
          </motion.div>
        )}

        <div className="h-3" />
      </motion.div>
    </div>
  );
}
