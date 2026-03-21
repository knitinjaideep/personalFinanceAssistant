import { useState, useEffect, useCallback } from "react";
import {
  FileText, BarChart3, Building2, DollarSign,
  TrendingUp, TrendingDown, ChevronDown, Calendar,
  FolderOpen, RefreshCw, Loader2, Download, Landmark,
  CreditCard, Package, Plus,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from "recharts";
import toast from "react-hot-toast";
import { dashboardApi } from "../api/dashboard";
import { scanApi } from "../api/scan";
import type { DashboardSummary, InvestmentsDashboard, BankingDashboard } from "../api/dashboard";
import type { ScanStatusResponse, SourceSummary } from "../api/scan";
import { MetricCard } from "../components/ui/MetricCard";
import { Card } from "../components/ui/Card";
import { SectionHeader } from "../components/ui/SectionHeader";
import { EmptyState } from "../components/ui/EmptyState";
import { BucketToggle } from "../components/ui/BucketToggle";
import { UploadModal } from "../components/upload/UploadModal";
import { INSTITUTION_COLORS } from "../design/tokens";
import {
  contentPageVariants, staggerContainer, staggerChild, fadeVariants,
} from "../design/motion";

type Bucket = "investments" | "banking";

// ── Colour palette for Recharts ───────────────────────────────────────────────

const CHART_COLORS = [
  "#1F6F8B", "#FF7A5A", "#4CAF93", "#FFD166",
  "#5FA8D3", "#FFA38F", "#CDEDF6", "#0B3C5D",
  "#E45757", "#B5EAD7",
];

// ── Skeleton ──────────────────────────────────────────────────────────────────

function MetricSkeleton() {
  return (
    <div
      className="rounded-3xl p-5 flex flex-col gap-4"
      style={{
        background: "rgba(255,255,255,0.72)",
        border: "1px solid rgba(205,237,246,0.6)",
      }}
    >
      <div className="flex items-start justify-between">
        <div className="skeleton w-20 h-3" />
        <div className="skeleton w-9 h-9 rounded-xl" />
      </div>
      <div className="skeleton w-16 h-8" />
    </div>
  );
}

function ChartSkeleton({ height = 200 }: { height?: number }) {
  return (
    <div
      className="rounded-2xl animate-pulse"
      style={{ height, background: "rgba(205,237,246,0.25)" }}
    />
  );
}

// ── Section card wrapper ──────────────────────────────────────────────────────

function SectionCard({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-3xl p-5 ${className ?? ""}`}
      style={{
        background: "rgba(255,255,255,0.80)",
        border: "1px solid rgba(205,237,246,0.60)",
        boxShadow: "0 4px 24px rgba(11,60,93,0.07), inset 0 1px 0 rgba(255,255,255,0.9)",
      }}
    >
      {children}
    </div>
  );
}

// ── Source card (per-folder pill) ─────────────────────────────────────────────

function SourceCard({ source }: { source: SourceSummary }) {
  const colorCls =
    INSTITUTION_COLORS[source.institution_type] ?? "bg-ocean-50 text-ocean border-ocean-100";

  const pendingCount = source.pending + source.failed;

  return (
    <motion.div
      variants={staggerChild}
      whileHover={{ y: -2, transition: { type: "spring", stiffness: 350, damping: 25 } }}
      className="flex items-center justify-between p-4 rounded-2xl cursor-default"
      style={{
        background: "rgba(255,255,255,0.88)",
        border: "1px solid rgba(205,237,246,0.55)",
        boxShadow: "0 2px 12px rgba(11,60,93,0.06)",
      }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className={`p-2 rounded-xl border shrink-0 ${colorCls}`}>
          <FolderOpen size={14} />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ocean-deep leading-tight truncate">
            {source.account_product}
          </p>
          {source.latest_file_date && (
            <p className="text-xs text-ocean/40 mt-0.5 flex items-center gap-1">
              <Calendar size={9} />
              Latest: {source.latest_file_date}
            </p>
          )}
        </div>
      </div>

      <div className="text-right shrink-0 ml-3">
        <p className="text-lg font-bold text-ocean-deep tabular">
          {source.total_files}
        </p>
        <p className="text-[10px] text-ocean/35 uppercase tracking-wide">
          {source.ingested}/{source.total_files} ingested
        </p>
        {pendingCount > 0 && (
          <span className="inline-block mt-0.5 text-[9px] font-semibold px-1.5 py-0.5 rounded-full bg-highlight/20 text-yellow-700">
            {pendingCount} pending
          </span>
        )}
      </div>
    </motion.div>
  );
}

// ── Recent files section ──────────────────────────────────────────────────────

function RecentFilesSection({ sources }: { sources: SourceSummary[] }) {
  const [expanded, setExpanded] = useState(false);

  // Flatten and sort recent files from scan sources (we only have top-level counts here)
  // Show the top-10 sources with the latest file dates
  const recentSources = [...sources]
    .filter(s => s.total_files > 0 && s.latest_file_date)
    .sort((a, b) => (b.latest_file_date ?? "").localeCompare(a.latest_file_date ?? ""))
    .slice(0, 10);

  if (recentSources.length === 0) return null;

  return (
    <motion.div variants={staggerChild}>
      <Card padding="none">
        <button
          className="w-full px-5 py-4 flex items-center justify-between text-left"
          onClick={() => setExpanded(!expanded)}
        >
          <SectionHeader
            title="Recent Activity"
            subtitle={`${recentSources.length} active sources`}
          />
          <motion.span
            animate={{ rotate: expanded ? 180 : 0 }}
            transition={{ duration: 0.25 }}
            className="text-ocean/30"
          >
            <ChevronDown size={14} />
          </motion.span>
        </button>

        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
              className="overflow-hidden"
            >
              <div className="divide-y divide-ocean-50/70 border-t border-ocean-100/60">
                {recentSources.map((s, i) => (
                  <motion.div
                    key={s.source_id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04 }}
                    className="px-5 py-3 flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <FileText size={13} className="text-ocean/30 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-ocean-deep truncate">
                          {s.account_product}
                        </p>
                        <p className="text-[10px] text-ocean/35">
                          {s.total_files} files · {s.ingested} ingested
                        </p>
                      </div>
                    </div>
                    <div className="text-[10px] text-ocean/30 shrink-0 ml-3">
                      {s.latest_file_date}
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </motion.div>
  );
}

// ── Investments dashboard ─────────────────────────────────────────────────────

function InvestmentsDashboard({ data }: { data: InvestmentsDashboard | null }) {
  if (!data || data.portfolio_summary.accounts.length === 0) {
    return (
      <EmptyState
        title="No investment data yet"
        description="Click 'Scan & Ingest' to load statements from your Morgan Stanley and E*TRADE folders."
        showMascot
      />
    );
  }

  const { portfolio_summary, top_holdings, fees, balance_history } = data;
  const gl = portfolio_summary.total_unrealized_gain_loss;
  const glPositive = gl >= 0;

  // Prepare balance history chart data — aggregate per date across accounts
  const historyByDate: Record<string, number> = {};
  for (const point of balance_history) {
    historyByDate[point.date] = (historyByDate[point.date] ?? 0) + point.total_value;
  }
  const historyData = Object.entries(historyByDate)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, value]) => ({ date: date.slice(0, 7), value: Math.round(value) }));

  return (
    <div className="space-y-5">
      {/* Summary metrics */}
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
        className="grid grid-cols-2 md:grid-cols-4 gap-3"
      >
        <MetricCard
          label="Portfolio Value"
          value={`$${portfolio_summary.total_portfolio_value_fmt}`}
          icon={<TrendingUp size={15} />}
          accent="ocean"
        />
        <MetricCard
          label="Unrealized G/L"
          value={`${glPositive ? "+" : ""}$${portfolio_summary.total_unrealized_gain_loss_fmt}`}
          icon={glPositive ? <TrendingUp size={15} /> : <TrendingDown size={15} />}
          accent={glPositive ? "positive" : "coral"}
        />
        <MetricCard
          label="Holdings"
          value={top_holdings.length}
          icon={<Package size={15} />}
          accent="highlight"
        />
        <MetricCard
          label="Total Fees"
          value={`$${fees.total_fees_fmt}`}
          icon={<DollarSign size={15} />}
          accent="coral"
        />
      </motion.div>

      {/* Balance history chart */}
      {historyData.length > 1 && (
        <SectionCard>
          <SectionHeader title="Portfolio Value Over Time" />
          <div className="mt-4">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={historyData} barSize={16}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,60,93,0.08)" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: "rgba(11,60,93,0.4)" }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: "rgba(11,60,93,0.4)" }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  formatter={(v: number) => [`$${v.toLocaleString()}`, "Portfolio Value"]}
                  contentStyle={{ borderRadius: 12, fontSize: 12 }}
                />
                <Bar dataKey="value" fill="#1F6F8B" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      )}

      {/* Top holdings table */}
      {top_holdings.length > 0 && (
        <SectionCard>
          <SectionHeader title="Top Holdings by Value" />
          <div className="mt-3 space-y-2">
            {top_holdings.slice(0, 8).map((h, i) => {
              const glPos = h.unrealized_gain_loss >= 0;
              return (
                <div
                  key={i}
                  className="flex items-center justify-between py-2 border-b border-ocean-50/60 last:border-0"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-[10px] font-bold text-ocean/30 w-5 shrink-0">{i + 1}</span>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-ocean-deep truncate">
                        {h.symbol ?? h.description.slice(0, 30)}
                      </p>
                      {h.symbol && (
                        <p className="text-[10px] text-ocean/35 truncate">{h.description.slice(0, 35)}</p>
                      )}
                    </div>
                  </div>
                  <div className="text-right shrink-0 ml-3">
                    <p className="text-xs font-bold text-ocean-deep">${h.market_value_fmt}</p>
                    <p className={`text-[10px] font-semibold ${glPos ? "text-positive" : "text-coral"}`}>
                      {glPos ? "+" : ""}${h.unrealized_gain_loss_fmt}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>
      )}

      {/* Fee breakdown */}
      {fees.by_category.length > 0 && (
        <SectionCard>
          <SectionHeader title="Investment Fees" subtitle={`Total: $${fees.total_fees_fmt}`} />
          <div className="mt-3 space-y-2">
            {fees.by_category.map((f, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="capitalize text-ocean/60">{f.category}</span>
                <span className="font-semibold text-ocean-deep">${f.total_fmt}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  );
}

// ── Banking dashboard ─────────────────────────────────────────────────────────

const CATEGORY_LABELS: Record<string, string> = {
  groceries: "Groceries", restaurants: "Restaurants", subscriptions: "Subscriptions",
  travel: "Travel", shopping: "Shopping", gas: "Gas", utilities: "Utilities",
  healthcare: "Healthcare", entertainment: "Entertainment", education: "Education",
  insurance: "Insurance", transfers: "Transfers", fees: "Fees",
  atm_cash: "ATM / Cash", other: "Other",
};

function BankingDashboard({ data }: { data: BankingDashboard | null }) {
  if (!data || data.spend_by_month.length === 0) {
    return (
      <EmptyState
        title="No banking data yet"
        description="Click 'Scan & Ingest' to load statements from your Chase, Amex, and Discover folders."
        showMascot
      />
    );
  }

  const { spend_by_month, spend_by_category, top_merchants, card_summary, cash_flow, subscriptions } = data;

  // Total spend across all time
  const totalSpend = spend_by_month.reduce((s, m) => s + m.total_spend, 0);
  const currentMonth = spend_by_month[spend_by_month.length - 1];

  // Category data for pie chart
  const pieData = spend_by_category.slice(0, 8).map((c, i) => ({
    name: CATEGORY_LABELS[c.category] ?? c.category,
    value: c.total,
    color: CHART_COLORS[i % CHART_COLORS.length],
  }));

  return (
    <div className="space-y-5">
      {/* Summary row */}
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
        className="grid grid-cols-2 md:grid-cols-4 gap-3"
      >
        <MetricCard
          label="Total Spend"
          value={`$${Math.round(totalSpend).toLocaleString()}`}
          icon={<CreditCard size={15} />}
          accent="coral"
        />
        <MetricCard
          label="This Month"
          value={currentMonth ? `$${Math.round(currentMonth.total_spend).toLocaleString()}` : "–"}
          icon={<BarChart3 size={15} />}
          accent="ocean"
        />
        <MetricCard
          label="Transactions"
          value={spend_by_month.reduce((s, m) => s + m.transaction_count, 0)}
          icon={<DollarSign size={15} />}
          accent="highlight"
        />
        <MetricCard
          label="Subscriptions"
          value={subscriptions.length}
          icon={<Package size={15} />}
          accent="positive"
        />
      </motion.div>

      {/* Monthly spend trend */}
      {spend_by_month.length > 1 && (
        <SectionCard>
          <SectionHeader title="Monthly Spend Trend" />
          <div className="mt-4">
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={spend_by_month} barSize={14}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,60,93,0.08)" />
                <XAxis
                  dataKey="month"
                  tick={{ fontSize: 10, fill: "rgba(11,60,93,0.4)" }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: "rgba(11,60,93,0.4)" }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  formatter={(v: number) => [`$${v.toLocaleString()}`, "Spend"]}
                  contentStyle={{ borderRadius: 12, fontSize: 12 }}
                />
                <Bar dataKey="total_spend" fill="#FF7A5A" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      )}

      {/* Spend by category + top merchants side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {pieData.length > 0 && (
          <SectionCard>
            <SectionHeader title="Spend by Category" />
            <div className="mt-3">
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={75}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {pieData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v: number) => [`$${v.toLocaleString()}`, ""]}
                    contentStyle={{ borderRadius: 12, fontSize: 12 }}
                  />
                  <Legend
                    iconSize={8}
                    iconType="circle"
                    wrapperStyle={{ fontSize: 10 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>
        )}

        {top_merchants.length > 0 && (
          <SectionCard>
            <SectionHeader title="Top Merchants" />
            <div className="mt-3 space-y-2">
              {top_merchants.slice(0, 8).map((m, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[10px] font-bold text-ocean/25 w-4 shrink-0">{i + 1}</span>
                    <span className="text-ocean-deep font-medium truncate">{m.merchant}</span>
                  </div>
                  <div className="text-right shrink-0 ml-2">
                    <span className="font-semibold text-coral">${m.total_fmt}</span>
                    <span className="text-ocean/30 ml-1">({m.transaction_count}x)</span>
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>
        )}
      </div>

      {/* Per-card spend summary */}
      {card_summary.length > 0 && (
        <SectionCard>
          <SectionHeader title="Per-Card Spend" />
          <div className="mt-3 space-y-2">
            {card_summary.map((c, i) => (
              <div key={i} className="flex items-center justify-between py-2 border-b border-ocean-50/60 last:border-0">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="p-1.5 rounded-lg bg-ocean-50 text-ocean border border-ocean-100 shrink-0">
                    <CreditCard size={12} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-ocean-deep truncate">{c.product_label}</p>
                    <p className="text-[10px] text-ocean/35">{c.transaction_count} transactions</p>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-xs font-bold text-coral">${c.total_spend_fmt}</p>
                  {c.latest_statement && (
                    <p className="text-[10px] text-ocean/30">Latest: {c.latest_statement}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {/* Cash flow (checking/savings) */}
      {cash_flow.length > 1 && (
        <SectionCard>
          <SectionHeader title="Inflow vs Outflow" subtitle="Checking & savings accounts" />
          <div className="mt-4">
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={cash_flow} barSize={10} barGap={2}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,60,93,0.08)" />
                <XAxis
                  dataKey="month"
                  tick={{ fontSize: 9, fill: "rgba(11,60,93,0.4)" }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tick={{ fontSize: 9, fill: "rgba(11,60,93,0.4)" }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  formatter={(v: number, name: string) => [`$${v.toLocaleString()}`, name]}
                  contentStyle={{ borderRadius: 12, fontSize: 12 }}
                />
                <Bar dataKey="inflow"  name="Inflow"  fill="#4CAF93" radius={[3, 3, 0, 0]} />
                <Bar dataKey="outflow" name="Outflow" fill="#FF7A5A" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      )}

      {/* Subscriptions */}
      {subscriptions.length > 0 && (
        <SectionCard>
          <SectionHeader title="Recurring / Subscriptions" />
          <div className="mt-3 space-y-2">
            {subscriptions.slice(0, 8).map((s, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="text-ocean-deep font-medium">{s.merchant}</span>
                <div className="text-right">
                  <span className="font-semibold text-ocean">${s.avg_monthly_amount_fmt}/mo</span>
                  <span className="text-ocean/30 ml-1.5 text-[10px]">×{s.occurrences}</span>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  );
}

// ── Top bar ───────────────────────────────────────────────────────────────────

function TopBar({
  bucket,
  onBucketChange,
  onRefresh,
  onIngest,
  onUpload,
  ingesting,
  pendingCount,
}: {
  bucket: Bucket;
  onBucketChange: (b: Bucket) => void;
  onRefresh: () => void;
  onIngest: () => void;
  onUpload: () => void;
  ingesting: boolean;
  pendingCount: number;
}) {
  return (
    <div
      className="shrink-0 px-7 py-4 flex items-center justify-between"
      style={{
        borderBottom: "1px solid rgba(205,237,246,0.55)",
        background: "rgba(255,255,255,0.60)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      <div>
        <h1 className="text-[17px] font-bold text-ocean-deep leading-tight tracking-tight">
          Dashboard
        </h1>
        <p className="text-[12px] text-ocean/45 mt-0.5 font-medium">
          Your financial statements, analyzed locally
        </p>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={onRefresh}
          className="flex items-center gap-1.5 text-xs text-ocean/40 hover:text-ocean font-medium transition-colors"
        >
          <RefreshCw size={11} />
          Refresh
        </button>

        {/* Manual upload → opens destination modal */}
        <button
          onClick={onUpload}
          className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-xl transition-all"
          style={{
            background: "rgba(205,237,246,0.6)",
            color: "rgba(11,60,93,0.6)",
          }}
        >
          <Plus size={11} />
          Add File
        </button>

        <button
          onClick={onIngest}
          disabled={ingesting}
          className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-xl transition-all"
          style={{
            background: ingesting
              ? "rgba(205,237,246,0.5)"
              : pendingCount > 0
                ? "linear-gradient(135deg, #FF7A5A, #FFA38F)"
                : "rgba(205,237,246,0.6)",
            color: ingesting
              ? "rgba(11,60,93,0.4)"
              : pendingCount > 0
                ? "white"
                : "rgba(11,60,93,0.5)",
          }}
        >
          {ingesting ? (
            <><Loader2 size={11} className="animate-spin" /> Ingesting…</>
          ) : (
            <><Download size={11} /> Scan & Ingest{pendingCount > 0 ? ` (${pendingCount})` : ""}</>
          )}
        </button>

        <BucketToggle value={bucket} onChange={onBucketChange} />
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function HomePage() {
  const [bucket, setBucket]           = useState<Bucket>("investments");
  const [loading, setLoading]         = useState(true);
  const [ingesting, setIngesting]     = useState(false);
  const [uploadOpen, setUploadOpen]   = useState(false);

  const [summary, setSummary]         = useState<DashboardSummary | null>(null);
  const [investments, setInvestments] = useState<InvestmentsDashboard | null>(null);
  const [banking, setBanking]         = useState<BankingDashboard | null>(null);
  const [scanStatus, setScanStatus]   = useState<ScanStatusResponse | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [sumResult, scanResult] = await Promise.all([
        dashboardApi.summary(),
        scanApi.status(),
      ]);
      setSummary(sumResult);
      setScanStatus(scanResult);

      // Fetch bucket-specific data in parallel
      const [invResult, bankResult] = await Promise.all([
        dashboardApi.investments(),
        dashboardApi.banking(),
      ]);
      setInvestments(invResult);
      setBanking(bankResult);
    } catch {
      // backend may not be ready yet
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleIngest = useCallback(async () => {
    setIngesting(true);
    try {
      const result = await scanApi.ingest();
      if (result.ingested > 0) {
        toast.success(`Ingested ${result.ingested} new statement${result.ingested !== 1 ? "s" : ""}`);
      } else if ((scanStatus?.total_pending ?? 0) === 0) {
        toast.success("All statements are already ingested");
      }
      if (result.failed > 0) {
        toast.error(`${result.failed} file${result.failed !== 1 ? "s" : ""} failed to ingest`);
      }
      await fetchData();
    } catch {
      toast.error("Scan & ingest failed — is the backend running?");
    } finally {
      setIngesting(false);
    }
  }, [fetchData, scanStatus]);

  const visibleSources = scanStatus?.sources.filter((s) => s.bucket === bucket) ?? [];
  const pendingCount   = scanStatus?.total_pending ?? 0;

  return (
    <div className="flex flex-col h-full">
      {/* Upload destination modal — opens when user clicks "Add File" */}
      <UploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={() => { setUploadOpen(false); fetchData(); }}
      />

      <TopBar
        bucket={bucket}
        onBucketChange={setBucket}
        onRefresh={fetchData}
        onIngest={handleIngest}
        onUpload={() => setUploadOpen(true)}
        ingesting={ingesting}
        pendingCount={pendingCount}
      />

      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-5"
      >
        {/* KPI row */}
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-2 md:grid-cols-4 gap-4"
        >
          {loading ? (
            <><MetricSkeleton /><MetricSkeleton /><MetricSkeleton /><MetricSkeleton /></>
          ) : (
            <>
              <MetricCard
                label="Total Files"
                value={scanStatus?.total_discovered ?? 0}
                icon={<FileText size={16} />}
                accent="ocean"
              />
              <MetricCard
                label="Ingested"
                value={scanStatus?.total_ingested ?? 0}
                icon={<Download size={16} />}
                accent="positive"
              />
              <MetricCard
                label="Institutions"
                value={summary?.total_institutions ?? 0}
                icon={<Building2 size={16} />}
                accent="highlight"
              />
              <MetricCard
                label="Accounts"
                value={summary?.total_accounts ?? 0}
                icon={<Landmark size={16} />}
                accent="coral"
              />
            </>
          )}
        </motion.div>

        {/* Source / folder cards */}
        <motion.div variants={staggerChild}>
          <SectionCard>
            <div className="flex items-center justify-between mb-5">
              <SectionHeader
                title={bucket === "investments" ? "Investment Accounts" : "Banking Accounts"}
                subtitle={`${visibleSources.reduce((s, f) => s + f.total_files, 0)} files across ${visibleSources.length} sources`}
              />
            </div>

            {loading ? (
              <div className="py-8 text-center">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                  className="inline-block mb-2"
                >
                  <RefreshCw size={18} className="text-ocean/25" />
                </motion.div>
                <p className="text-sm text-ocean/35">Scanning folders…</p>
              </div>
            ) : visibleSources.length === 0 ? (
              <p className="text-sm text-ocean/35 py-2">No sources configured for this bucket.</p>
            ) : (
              <motion.div
                variants={staggerContainer}
                initial="hidden"
                animate="visible"
                className="grid grid-cols-1 sm:grid-cols-2 gap-3"
              >
                {visibleSources.map((s) => (
                  <SourceCard key={s.source_id} source={s} />
                ))}
              </motion.div>
            )}
          </SectionCard>
        </motion.div>

        {/* Bucket dashboard */}
        <motion.div variants={staggerChild}>
          <SectionCard>
            <div className="mb-5">
              <SectionHeader
                title={bucket === "investments" ? "Investments Overview" : "Banking Overview"}
              />
            </div>
            <AnimatePresence mode="wait">
              <motion.div
                key={bucket}
                variants={fadeVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                {loading ? (
                  <div className="space-y-3">
                    <ChartSkeleton height={120} />
                    <ChartSkeleton height={80} />
                  </div>
                ) : bucket === "investments" ? (
                  <InvestmentsDashboard data={investments} />
                ) : (
                  <BankingDashboard data={banking} />
                )}
              </motion.div>
            </AnimatePresence>
          </SectionCard>
        </motion.div>

        {/* Recent activity */}
        {scanStatus && <RecentFilesSection sources={scanStatus.sources} />}

        <div className="h-4" />
      </motion.div>
    </div>
  );
}
