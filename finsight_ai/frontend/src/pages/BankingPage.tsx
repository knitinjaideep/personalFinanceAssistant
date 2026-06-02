import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { CreditCard, AlertCircle } from "lucide-react";
import { dashboardApi } from "../api/dashboard";
import type { BankingDashboard } from "../api/dashboard";
import { staggerContainer, staggerChild, contentPageVariants } from "../design/motion";
import { CoralMascot } from "../components/CoralMascot";
import { CoralEmptyState } from "../components/CoralEmptyState";

const CHART_COLORS = [
  "#FF7A5A", "#1F6F8B", "#4CAF93", "#FFD166",
  "#5FA8D3", "#FFA38F", "#0B3C5D", "#E45757",
];

const CATEGORY_LABELS: Record<string, string> = {
  groceries: "Groceries", restaurants: "Dining", subscriptions: "Subscriptions",
  travel: "Travel", shopping: "Shopping", gas: "Gas", utilities: "Utilities",
  healthcare: "Healthcare", entertainment: "Entertainment",
  atm_cash: "ATM / Cash", fees: "Fees", transfers: "Transfers", other: "Other",
};

// ── Shared ────────────────────────────────────────────────────────────────────

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
      <div className="flex items-center gap-3">
        <CoralMascot variant="banking" size="sm" className="shrink-0" />
        <div>
          <h1 className="text-[18px] font-bold text-ocean-deep tracking-tight">Banking</h1>
          <p className="text-[12px] text-ocean/40 mt-0.5 font-medium">Spending, cash flow & card activity</p>
        </div>
      </div>
    </div>
  );
}

function GlassCard({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-2xl p-5 ${className ?? ""}`}
      style={{
        background: "rgba(255,255,255,0.82)",
        border: "1px solid rgba(205,237,246,0.65)",
        boxShadow: "0 4px 24px rgba(11,60,93,0.07), inset 0 1px 0 rgba(255,255,255,0.90)",
      }}
    >
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

// ── Page ──────────────────────────────────────────────────────────────────────

export function BankingPage() {
  const [loading, setLoading] = useState(true);
  const [data, setData]       = useState<BankingDashboard | null>(null);

  const fetch = useCallback(async () => {
    try { setData(await dashboardApi.banking()); }
    catch { /* backend not ready */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  const hasData = !!data && data.spend_by_month.length > 0;

  const pieData = (data?.spend_by_category ?? []).slice(0, 8).map((c, i) => ({
    name: CATEGORY_LABELS[c.category] ?? c.category,
    value: Math.round(c.total),
    color: CHART_COLORS[i % CHART_COLORS.length],
  }));

  return (
    <div className="flex flex-col h-full">
      <PageHeader />
      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-5"
      >

        {/* Monthly spend trend */}
        <motion.div variants={staggerChild}>
          <GlassCard>
            <ChartTitle sub="Total across all cards & accounts">Monthly Spending Trend</ChartTitle>
            {loading ? <Skeleton h={180} /> : !hasData ? (
              <EmptyBox message="Upload Chase, Amex, or Discover statements to see your spending trend" />
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={data!.spend_by_month} barSize={14}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,60,93,0.07)" vertical={false} />
                  <XAxis dataKey="month" tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }} tickLine={false} axisLine={false}
                    tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} width={36} />
                  <Tooltip formatter={(v: number) => [`$${v.toLocaleString()}`, "Spending"]} contentStyle={tooltipStyle} />
                  <Bar dataKey="total_spend" fill="#FF7A5A" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </GlassCard>
        </motion.div>

        {/* Category pie + top merchants */}
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-1 lg:grid-cols-2 gap-4"
        >
          <motion.div variants={staggerChild}>
            <GlassCard>
              <ChartTitle sub="Where your money goes">Spend by Category</ChartTitle>
              {loading ? <Skeleton h={200} /> : pieData.length === 0 ? (
                <EmptyBox message="No category data yet" />
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={52} outerRadius={78}
                      paddingAngle={2} dataKey="value" strokeWidth={0}>
                      {pieData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                    </Pie>
                    <Tooltip formatter={(v: number) => [`$${v.toLocaleString()}`, ""]} contentStyle={tooltipStyle} />
                  </PieChart>
                </ResponsiveContainer>
              )}
              {pieData.length > 0 && (
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
                  {pieData.map((d, i) => (
                    <span key={i} className="flex items-center gap-1.5 text-[10px] text-ocean/55">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: d.color }} />
                      {d.name}
                    </span>
                  ))}
                </div>
              )}
            </GlassCard>
          </motion.div>

          <motion.div variants={staggerChild}>
            <GlassCard>
              <ChartTitle sub="All time">Top Merchants</ChartTitle>
              {loading ? <Skeleton h={200} /> : !hasData || !data!.top_merchants.length ? (
                <EmptyBox message="No merchant data yet" />
              ) : (
                <div className="space-y-2.5 mt-1">
                  {data!.top_merchants.slice(0, 8).map((m, i) => (
                    <div key={i} className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span className="text-[10px] font-bold text-ocean/22 w-4 shrink-0 text-right">{i + 1}</span>
                        <span className="text-ocean-deep font-medium truncate">{m.merchant}</span>
                      </div>
                      <div className="text-right shrink-0 ml-3">
                        <span className="text-[13px] font-bold text-coral">${m.total_fmt}</span>
                        <span className="text-[10px] text-ocean/30 ml-1">×{m.transaction_count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </GlassCard>
          </motion.div>
        </motion.div>

        {/* Per-card summary */}
        {!loading && hasData && data!.card_summary.length > 0 && (
          <motion.div variants={staggerChild}>
            <GlassCard>
              <ChartTitle>Card Summary</ChartTitle>
              <div className="space-y-2 mt-1">
                {data!.card_summary.map((c, i) => (
                  <div key={i} className="flex items-center justify-between py-2.5 border-b border-ocean-50/50 last:border-0">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="p-1.5 rounded-lg shrink-0"
                        style={{ background: "rgba(31,111,139,0.08)", color: "#1F6F8B" }}>
                        <CreditCard size={13} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-[13px] font-semibold text-ocean-deep truncate">{c.product_label}</p>
                        <p className="text-[10px] text-ocean/38">{c.transaction_count} transactions</p>
                      </div>
                    </div>
                    <div className="text-right shrink-0 ml-3">
                      <p className="text-[13px] font-bold text-coral">${c.total_spend_fmt}</p>
                      {c.latest_statement && (
                        <p className="text-[10px] text-ocean/30">Latest: {c.latest_statement}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </GlassCard>
          </motion.div>
        )}

        {/* Cash flow */}
        {!loading && hasData && data!.cash_flow.length > 1 && (
          <motion.div variants={staggerChild}>
            <GlassCard>
              <ChartTitle sub="Checking & savings accounts">Inflow vs Outflow</ChartTitle>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={data!.cash_flow} barSize={10} barGap={2}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,60,93,0.07)" vertical={false} />
                  <XAxis dataKey="month" tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }} tickLine={false} axisLine={false}
                    tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} width={36} />
                  <Tooltip formatter={(v: number, name: string) => [`$${v.toLocaleString()}`, name]} contentStyle={tooltipStyle} />
                  <Bar dataKey="inflow"  name="Inflow"  fill="#4CAF93" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="outflow" name="Outflow" fill="#FF7A5A" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </GlassCard>
          </motion.div>
        )}

        {!loading && !hasData && (
          <motion.div variants={staggerChild}>
            <div className="rounded-2xl"
              style={{ background: "rgba(255,255,255,0.65)", border: "1px dashed rgba(205,237,246,0.70)" }}>
              <CoralEmptyState
                variant="banking"
                title="No banking data yet"
                description="Upload Chase, Amex, or Discover statements to see spending trends and card activity."
              />
            </div>
          </motion.div>
        )}

        <div className="h-3" />
      </motion.div>
    </div>
  );
}
