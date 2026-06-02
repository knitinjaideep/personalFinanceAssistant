import { motion } from "framer-motion";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { AlertCircle, RefreshCw, Calendar, Sparkles } from "lucide-react";
import { staggerContainer, staggerChild, contentPageVariants } from "../design/motion";
import { CoralMascot } from "../components/CoralMascot";
import { CoralEmptyState } from "../components/CoralEmptyState";
import { CoralLoadingState } from "../components/CoralLoadingState";
import { InvestmentSummaryWidget } from "../components/investments/InvestmentSummaryWidget";
import { IRATotalWidget } from "../components/investments/IRATotalWidget";
import { DownPaymentWidget } from "../components/investments/DownPaymentWidget";
import { PortfolioAllocationWidget } from "../components/investments/PortfolioAllocationWidget";
import { useInvestmentData } from "../hooks/useInvestmentData";
import { useAppStore } from "../store/appStore";
import { fmtDate } from "../lib/financeDataAdapters";

const tooltipStyle = {
  borderRadius: 10,
  fontSize: 12,
  background: "rgba(255,255,255,0.96)",
  border: "1px solid rgba(205,237,246,0.8)",
  boxShadow: "0 4px 16px rgba(11,60,93,0.10)",
};

// ── Page header ───────────────────────────────────────────────────────────────

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
        <CoralMascot variant="investments" size="sm" className="shrink-0" />
        <div>
          <h1 className="text-[18px] font-bold text-ocean-deep tracking-tight">Investments</h1>
          <p className="text-[12px] text-ocean/40 mt-0.5 font-medium">
            Portfolio value, retirement, brokerage, and savings
          </p>
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

function Skeleton({ h = 160 }: { h?: number }) {
  return <div className="rounded-xl animate-pulse" style={{ height: h, background: "rgba(205,237,246,0.20)" }} />;
}

function EmptyBox({ message }: { message: string }) {
  return (
    <div
      className="rounded-xl flex flex-col items-center justify-center gap-2 py-8"
      style={{ background: "rgba(240,249,252,0.40)", border: "1px dashed rgba(205,237,246,0.70)" }}
    >
      <AlertCircle size={16} className="text-ocean/20" />
      <p className="text-[11px] text-ocean/30 text-center max-w-[220px] leading-relaxed">{message}</p>
    </div>
  );
}

// ── Account freshness panel ───────────────────────────────────────────────────

function DataFreshnessPanel({
  freshness,
  onReprocess,
}: {
  freshness: ReturnType<typeof useInvestmentData>["dataFreshness"];
  onReprocess: () => void;
}) {
  return (
    <GlassCard>
      <p className="text-[13px] font-semibold text-ocean-deep mb-1">Data Freshness</p>
      <p className="text-[11px] text-ocean/40 mb-4">Latest available statements per institution</p>
      <div className="space-y-2.5">
        {freshness.map((f) => (
          <div key={f.institutionKey} className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div
                className="w-2 h-2 rounded-full shrink-0"
                style={{ background: f.isMissing ? "#E45757" : "#4CAF93" }}
              />
              <span className="text-[13px] font-medium text-ocean-deep">{f.displayName}</span>
            </div>
            <div className="text-right">
              {f.latestStatement ? (
                <div className="flex items-center gap-1 text-[11px] text-ocean/45">
                  <Calendar size={10} />
                  <span>{fmtDate(f.latestStatement)}</span>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={onReprocess}
                  className="flex items-center gap-1 text-[11px] font-semibold"
                  style={{ color: "#E45757" }}
                >
                  <RefreshCw size={10} />
                  Missing — reprocess
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </GlassCard>
  );
}

// ── Coral insight card ────────────────────────────────────────────────────────

function CoralInsightCard({ freshness }: { freshness: ReturnType<typeof useInvestmentData>["dataFreshness"] }) {
  const missing = freshness.filter((f) => f.isMissing);
  const latest = freshness.filter((f) => !f.isMissing).sort((a, b) =>
    (b.latestStatement ?? "").localeCompare(a.latestStatement ?? ""),
  )[0];

  let insight = "Upload your latest Morgan Stanley and E*TRADE statements to get the most accurate portfolio view.";
  if (missing.length > 0) {
    insight = `${missing.map((f) => f.displayName).join(" and ")} statement${missing.length > 1 ? "s are" : " is"} missing. Upload to refresh portfolio values.`;
  } else if (latest?.latestStatement) {
    insight = `Your latest available ${latest.displayName} statement is from ${fmtDate(latest.latestStatement)}. Upload a newer statement to refresh portfolio values.`;
  }

  return (
    <div
      className="flex items-start gap-3 rounded-2xl px-5 py-4"
      style={{
        background: "rgba(95,168,211,0.07)",
        border: "1px solid rgba(95,168,211,0.22)",
      }}
    >
      <Sparkles size={15} style={{ color: "#1F6F8B" }} className="shrink-0 mt-0.5" />
      <div>
        <p className="text-[12px] font-semibold text-ocean-deep">Coral insight</p>
        <p className="text-[11.5px] text-ocean/55 mt-0.5 leading-relaxed">{insight}</p>
      </div>
    </div>
  );
}

// ── Portfolio history chart ───────────────────────────────────────────────────

function PortfolioHistoryChart({
  data,
  loading,
}: {
  data: ReturnType<typeof useInvestmentData>["raw"];
  loading: boolean;
}) {
  const historyByDate: Record<string, number> = {};
  for (const pt of data?.balance_history ?? []) {
    historyByDate[pt.date] = (historyByDate[pt.date] ?? 0) + pt.total_value;
  }
  const historyData = Object.entries(historyByDate)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, value]) => ({ date: date.slice(0, 7), value: Math.round(value) }));

  return (
    <GlassCard>
      <p className="text-[13px] font-semibold text-ocean-deep mb-1">Portfolio History</p>
      <p className="text-[11px] text-ocean/40 mb-4">Total value across all accounts</p>
      {loading ? (
        <Skeleton h={180} />
      ) : historyData.length < 2 ? (
        <EmptyBox message="Need at least 2 months of statements to show portfolio history" />
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={historyData} barSize={14}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,60,93,0.07)" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              width={40}
            />
            <Tooltip formatter={(v: number) => [`$${v.toLocaleString()}`, "Value"]} contentStyle={tooltipStyle} />
            <Bar dataKey="value" fill="#1F6F8B" radius={[5, 5, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </GlassCard>
  );
}

// ── Holdings table ────────────────────────────────────────────────────────────

function HoldingsTable({ holdings, loading }: { holdings: ReturnType<typeof useInvestmentData>["holdings"]; loading: boolean }) {
  if (loading) {
    return (
      <GlassCard>
        <p className="text-[13px] font-semibold text-ocean-deep mb-4">Top Holdings</p>
        <Skeleton h={200} />
      </GlassCard>
    );
  }

  return (
    <GlassCard>
      <p className="text-[13px] font-semibold text-ocean-deep mb-1">Top Holdings</p>
      <p className="text-[11px] text-ocean/40 mb-4">
        {holdings.length > 0 ? `${holdings.length} positions` : "No holdings data"}
      </p>
      {holdings.length === 0 ? (
        <EmptyBox message="No holdings data yet. Reprocess Morgan Stanley or E*TRADE statements." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b" style={{ borderColor: "rgba(205,237,246,0.60)", color: "rgba(11,60,93,0.35)" }}>
                <th className="text-left py-2 pr-3 font-semibold">Symbol / Name</th>
                <th className="text-right py-2 px-2 font-semibold hidden sm:table-cell">Qty</th>
                <th className="text-right py-2 px-2 font-semibold">Value</th>
                <th className="text-right py-2 px-2 font-semibold hidden md:table-cell">G/L</th>
                <th className="text-right py-2 pl-2 font-semibold hidden sm:table-cell">Wt%</th>
              </tr>
            </thead>
            <tbody>
              {holdings.slice(0, 20).map((h, i) => {
                const glPos = h.unrealized_gain_loss >= 0;
                return (
                  <tr
                    key={i}
                    className="border-b last:border-0 hover:bg-ocean-50/20 transition-colors"
                    style={{ borderColor: "rgba(205,237,246,0.40)" }}
                  >
                    <td className="py-2 pr-3">
                      <span className="font-semibold text-ocean-deep">{h.symbol ?? "–"}</span>
                      {h.description && (
                        <span className="block text-[10px] text-ocean/35 truncate max-w-[130px]">
                          {h.description.slice(0, 22)}
                        </span>
                      )}
                    </td>
                    <td className="text-right py-2 px-2 text-ocean/45 tabular hidden sm:table-cell">
                      {h.quantity !== null ? h.quantity.toFixed(2) : "–"}
                    </td>
                    <td className="text-right py-2 px-2 font-semibold text-ocean-deep tabular">
                      ${h.market_value_fmt}
                    </td>
                    <td className={`text-right py-2 px-2 font-semibold tabular hidden md:table-cell ${glPos ? "text-positive" : "text-coral"}`}>
                      {glPos ? "+" : ""}${h.unrealized_gain_loss_fmt}
                    </td>
                    <td className="text-right py-2 pl-2 text-ocean/38 tabular hidden sm:table-cell">
                      {h.portfolio_weight !== null ? `${h.portfolio_weight}%` : "–"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </GlassCard>
  );
}

// ── Account cards grid ────────────────────────────────────────────────────────

function AccountCardsGrid({ accounts, loading }: { accounts: ReturnType<typeof useInvestmentData>["accounts"]; loading: boolean }) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {[0, 1].map((i) => (
          <div key={i} className="rounded-2xl p-4 animate-pulse" style={{ background: "rgba(255,255,255,0.88)", border: "1px solid rgba(205,237,246,0.60)", height: 88 }} />
        ))}
      </div>
    );
  }

  if (accounts.length === 0) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {accounts.map((acct, i) => {
        const glPos = acct.unrealized_gain_loss >= 0;
        return (
          <div
            key={i}
            className="rounded-2xl p-4"
            style={{ background: "rgba(255,255,255,0.88)", border: "1px solid rgba(205,237,246,0.60)" }}
          >
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
          </div>
        );
      })}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function InvestmentsPage() {
  const setActivePage = useAppStore((s) => s.setActivePage);
  const { loading, raw, accounts, iraAccounts, holdings, totals, dataFreshness, hasData } = useInvestmentData();

  if (loading) {
    return (
      <div className="flex flex-col h-full">
        <PageHeader />
        <div className="flex-1 flex items-center justify-center">
          <CoralLoadingState variant="investments" message="Loading portfolio data…" />
        </div>
      </div>
    );
  }

  // Down payment: use savings/Marcus total as proxy (backend doesn't have a dedicated field yet)
  const downPaymentAmount = 0; // Will be non-zero once Marcus savings data is available

  return (
    <div className="flex flex-col h-full">
      <PageHeader />

      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-5"
      >
        {/* ── Top row: 3 summary widgets ─────────────────────────────────── */}
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-1 sm:grid-cols-3 gap-4"
        >
          <motion.div variants={staggerChild}>
            <InvestmentSummaryWidget totals={totals} loading={loading} />
          </motion.div>
          <motion.div variants={staggerChild}>
            <IRATotalWidget iraAccounts={iraAccounts} loading={loading} />
          </motion.div>
          <motion.div variants={staggerChild}>
            <DownPaymentWidget
              savedAmount={downPaymentAmount}
              loading={loading}
              asOf={totals.asOf}
            />
          </motion.div>
        </motion.div>

        {/* ── Account cards ──────────────────────────────────────────────── */}
        {hasData && (
          <motion.div variants={staggerChild}>
            <AccountCardsGrid accounts={accounts} loading={loading} />
          </motion.div>
        )}

        {/* ── Second row: portfolio history + allocation ─────────────────── */}
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-1 lg:grid-cols-2 gap-4"
        >
          <motion.div variants={staggerChild}>
            <PortfolioHistoryChart data={raw} loading={loading} />
          </motion.div>
          <motion.div variants={staggerChild}>
            <PortfolioAllocationWidget allocation={raw?.allocation ?? []} loading={loading} />
          </motion.div>
        </motion.div>

        {/* ── Holdings table ──────────────────────────────────────────────── */}
        <motion.div variants={staggerChild}>
          <HoldingsTable holdings={holdings} loading={loading} />
        </motion.div>

        {/* ── Bottom row: freshness + insight ───────────────────────────── */}
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-1 lg:grid-cols-2 gap-4"
        >
          <motion.div variants={staggerChild}>
            <DataFreshnessPanel
              freshness={dataFreshness}
              onReprocess={() => setActivePage("documents")}
            />
          </motion.div>
          <motion.div variants={staggerChild}>
            <div className="flex flex-col gap-4">
              <CoralInsightCard freshness={dataFreshness} />

              {/* Retirement vs taxable split */}
              {hasData && iraAccounts.length > 0 && (
                <GlassCard>
                  <p className="text-[13px] font-semibold text-ocean-deep mb-1">Retirement vs Taxable</p>
                  <p className="text-[11px] text-ocean/40 mb-3">IRA vs brokerage accounts</p>
                  <div className="space-y-2">
                    {[
                      {
                        label: "IRA / Retirement",
                        value: totals.iraTotal,
                        total: totals.combined,
                        color: "#4CAF93",
                      },
                      {
                        label: "Brokerage / Other",
                        value: Math.max(0, totals.combined - totals.iraTotal),
                        total: totals.combined,
                        color: "#1F6F8B",
                      },
                    ].map(({ label, value, total, color }) => {
                      const pct = total > 0 ? ((value / total) * 100).toFixed(0) : "0";
                      return (
                        <div key={label}>
                          <div className="flex items-center justify-between text-[12px] mb-1">
                            <span className="text-ocean/55 font-medium">{label}</span>
                            <span className="font-semibold tabular" style={{ color }}>
                              {pct}%
                            </span>
                          </div>
                          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(205,237,246,0.50)" }}>
                            <div
                              className="h-full rounded-full"
                              style={{ width: `${pct}%`, background: color }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </GlassCard>
              )}
            </div>
          </motion.div>
        </motion.div>

        {/* ── Empty state ────────────────────────────────────────────────── */}
        {!hasData && (
          <motion.div variants={staggerChild}>
            <div
              className="rounded-2xl"
              style={{ background: "rgba(255,255,255,0.65)", border: "1px dashed rgba(205,237,246,0.70)" }}
            >
              <CoralEmptyState
                variant="investments"
                title="No investment data yet"
                description="Upload Morgan Stanley or E*TRADE statements and Coral will organize your holdings, portfolio value, and gains/losses."
                actionLabel="Upload statements"
                onAction={() => setActivePage("documents")}
              />
            </div>
          </motion.div>
        )}

        <div className="h-3" />
      </motion.div>
    </div>
  );
}
