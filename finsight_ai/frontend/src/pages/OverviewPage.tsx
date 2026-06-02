import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  LineChart, Line, PieChart, Pie, Cell, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  CreditCard, TrendingUp, RefreshCw, Receipt,
  FileText, AlertCircle, MessageSquare, Upload, BarChart3,
} from "lucide-react";
import { dashboardApi } from "../api/dashboard";
import type { DashboardSummary, BankingDashboard, InvestmentsDashboard } from "../api/dashboard";
import { staggerContainer, staggerChild, contentPageVariants } from "../design/motion";
import { CoralMascot } from "../components/CoralMascot";
import { CoralEmptyState } from "../components/CoralEmptyState";
import { CoralBubbleMascot } from "../components/CoralBubbleMascot";
import { CoralCategoryBubble } from "../components/CoralCategoryBubble";
import { useAppStore } from "../store/appStore";

// ── Colours ───────────────────────────────────────────────────────────────────

const CHART_COLORS = [
  "#FF7A5A", "#1F6F8B", "#4CAF93", "#FFD166",
  "#5FA8D3", "#FFA38F", "#0B3C5D", "#E45757",
];

const CATEGORY_LABELS: Record<string, string> = {
  groceries: "Groceries", restaurants: "Dining", subscriptions: "Subscriptions",
  travel: "Travel", shopping: "Shopping", gas: "Gas", utilities: "Utilities",
  healthcare: "Healthcare", entertainment: "Entertainment", other: "Other",
};

// ── Shared UI primitives ──────────────────────────────────────────────────────

function PageHeader() {
  return (
    <div
      className="shrink-0 px-7 py-5 flex items-center justify-between"
      style={{
        borderBottom: "1px solid rgba(205,237,246,0.50)",
        background: "rgba(255,255,255,0.55)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      <div className="flex items-center gap-3">
        <CoralMascot variant="analytics" size="sm" className="shrink-0" />
        <div>
          <h1 className="text-[18px] font-bold text-ocean-deep tracking-tight leading-none">
            Overview
          </h1>
          <p className="text-[12px] text-ocean/40 mt-1 font-medium">
            Your financial picture at a glance
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

function ChartTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div className="mb-4">
      <p className="text-[13px] font-semibold text-ocean-deep">{children}</p>
      {sub && <p className="text-[11px] text-ocean/40 mt-0.5">{sub}</p>}
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function MetricSkeleton() {
  return (
    <div
      className="rounded-2xl p-5"
      style={{ background: "rgba(255,255,255,0.65)", border: "1px solid rgba(205,237,246,0.50)" }}
    >
      <div className="skeleton w-20 h-2.5 rounded mb-4" />
      <div className="skeleton w-14 h-7 rounded" />
    </div>
  );
}

function ChartSkeleton({ height = 180 }: { height?: number }) {
  return (
    <div
      className="rounded-xl animate-pulse"
      style={{ height, background: "rgba(205,237,246,0.20)" }}
    />
  );
}

// ── Metric card ───────────────────────────────────────────────────────────────

interface MetricProps {
  label: string;
  value: string;
  sub?: string;
  icon: React.ReactNode;
  accent: "coral" | "ocean" | "positive" | "highlight";
}

const accentStyles = {
  coral:     { icon: "rgba(255,122,90,0.12)", iconColor: "#FF7A5A", value: "#CC5A40" },
  ocean:     { icon: "rgba(31,111,139,0.10)", iconColor: "#1F6F8B", value: "#0B3C5D" },
  positive:  { icon: "rgba(76,175,147,0.12)", iconColor: "#4CAF93", value: "#3a9c7a" },
  highlight: { icon: "rgba(255,209,102,0.18)", iconColor: "#c89a00", value: "#a07800" },
};

function MetricCard({ label, value, sub, icon, accent }: MetricProps) {
  const s = accentStyles[accent];
  return (
    <motion.div
      variants={staggerChild}
      whileHover={{ y: -2, transition: { type: "spring", stiffness: 350, damping: 26 } }}
      className="rounded-2xl p-5 cursor-default"
      style={{
        background: "rgba(255,255,255,0.88)",
        border: "1px solid rgba(205,237,246,0.65)",
        boxShadow: "0 2px 16px rgba(11,60,93,0.06), inset 0 1px 0 rgba(255,255,255,0.95)",
      }}
    >
      <div className="flex items-start justify-between mb-3">
        <span className="text-[10px] font-semibold text-ocean/38 uppercase tracking-widest leading-tight">
          {label}
        </span>
        <div
          className="p-2 rounded-xl"
          style={{ background: s.icon, color: s.iconColor }}
        >
          {icon}
        </div>
      </div>
      <p className="text-[22px] font-bold tracking-tight tabular" style={{ color: s.value }}>
        {value}
      </p>
      {sub && (
        <p className="text-[10px] text-ocean/35 mt-1">{sub}</p>
      )}
    </motion.div>
  );
}

// ── Empty chart placeholder ───────────────────────────────────────────────────

function EmptyChart({ message }: { message: string }) {
  return (
    <div
      className="rounded-xl flex flex-col items-center justify-center gap-2 py-10"
      style={{ background: "rgba(240,249,252,0.40)", border: "1px dashed rgba(205,237,246,0.70)" }}
    >
      <AlertCircle size={18} className="text-ocean/20" />
      <p className="text-[11px] text-ocean/30 text-center max-w-[180px] leading-relaxed">{message}</p>
    </div>
  );
}

// ── Hero / mascot card ────────────────────────────────────────────────────────

function HeroCard() {
  const setActivePage = useAppStore((s) => s.setActivePage);

  const ctaBase =
    "flex items-center gap-2 px-4 py-2.5 rounded-xl text-[13px] font-semibold transition-all";

  return (
    <motion.div variants={staggerChild}>
      <div
        className="relative overflow-hidden rounded-3xl"
        style={{
          background:
            "linear-gradient(135deg, rgba(7,24,38,0.97) 0%, rgba(11,45,70,0.96) 55%, rgba(15,61,85,0.95) 100%)",
          border: "1px solid rgba(95,168,211,0.18)",
          boxShadow:
            "0 18px 60px rgba(4,14,26,0.45), inset 0 1px 0 rgba(255,255,255,0.06)",
        }}
      >
        {/* Ambient glow accents */}
        <div
          aria-hidden
          className="pointer-events-none absolute -top-24 -right-16 w-72 h-72 rounded-full"
          style={{
            background:
              "radial-gradient(circle, rgba(95,168,211,0.28) 0%, transparent 70%)",
            filter: "blur(8px)",
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-20 right-32 w-56 h-56 rounded-full"
          style={{
            background:
              "radial-gradient(circle, rgba(255,122,90,0.22) 0%, transparent 70%)",
            filter: "blur(8px)",
          }}
        />
        <div className="relative flex flex-col md:flex-row items-center gap-6 px-7 py-8 md:py-9">
          {/* Left — copy + CTAs */}
          <div className="flex-1 text-center md:text-left order-2 md:order-1">
            <h2 className="text-[26px] font-extrabold tracking-tight leading-none">
              <span className="text-gradient-coral">Coral</span>
            </h2>
            <p className="text-[13px] font-semibold text-ocean-aqua/80 mt-1.5">
              Local financial intelligence
            </p>
            <p className="text-[13px] text-white/55 mt-3 max-w-md leading-relaxed mx-auto md:mx-0">
              Your local AI analyst for statements, spending, fees, and
              investments. Ask me about your spending, statements, fees, and
              investments.
            </p>

            <div className="flex flex-wrap items-center justify-center md:justify-start gap-2.5 mt-5">
              <button
                onClick={() => setActivePage("chat")}
                className={ctaBase + " text-white"}
                style={{
                  background: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
                  boxShadow: "0 6px 20px rgba(255,122,90,0.38)",
                }}
              >
                <MessageSquare size={14} />
                Ask Coral
              </button>
              <button
                onClick={() => setActivePage("documents")}
                className={ctaBase + " text-white/85"}
                style={{
                  background: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.16)",
                }}
              >
                <Upload size={14} />
                Upload Documents
              </button>
              <button
                onClick={() => setActivePage("banking")}
                className={ctaBase + " text-white/85"}
                style={{
                  background: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.16)",
                }}
              >
                <BarChart3 size={14} />
                View Insights
              </button>
            </div>
          </div>

          {/* Right — mascot inside water-droplet bubble */}
          <div className="order-1 md:order-2 shrink-0 pt-2">
            <CoralBubbleMascot
              variant="main"
              size="hero"
              glow
              animated
              priority
              speech="Ask me about your spending, statements, fees, and investments."
            />
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// ── Category bubbles (large, floating, mascot-led navigation) ────────────────

function FeatureCards() {
  const setActivePage = useAppStore((s) => s.setActivePage);

  const CATEGORIES = [
    {
      variant: "banking"     as const,
      title: "Banking",
      description: "Spending, cash flow, and card activity.",
      actionLabel: "View banking",
      onAction: () => setActivePage("banking"),
      floatDelay: "0ms",
    },
    {
      variant: "investments" as const,
      title: "Investments",
      description: "Portfolio value, holdings, and performance.",
      actionLabel: "View portfolio",
      onAction: () => setActivePage("investments"),
      floatDelay: "260ms",
    },
    {
      variant: "documents"   as const,
      title: "Documents",
      description: "Upload statements and track parsing.",
      actionLabel: "Manage documents",
      onAction: () => setActivePage("documents"),
      floatDelay: "520ms",
    },
    {
      variant: "analytics"   as const,
      title: "Insights",
      description: "Trends, categories, and spending analysis.",
      actionLabel: "Explore insights",
      onAction: () => setActivePage("overview"),
      floatDelay: "780ms",
    },
  ] as const;

  return (
    <motion.div
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
      className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5"
    >
      {CATEGORIES.map((cat) => (
        <motion.div key={cat.variant} variants={staggerChild} className="flex">
          <CoralCategoryBubble
            variant={cat.variant}
            title={cat.title}
            description={cat.description}
            actionLabel={cat.actionLabel}
            onAction={cat.onAction}
            floatDelay={cat.floatDelay}
            animated
            className="flex-1"
          />
        </motion.div>
      ))}
    </motion.div>
  );
}

// ── Charts ────────────────────────────────────────────────────────────────────

function SpendingLineChart({ data }: { data: { month: string; total_spend: number }[] }) {
  if (data.length < 2) {
    return <EmptyChart message="Upload more monthly statements to see your spending trend" />;
  }

  const formatted = data.map(d => ({
    month: d.month.slice(0, 7),
    spend: Math.round(d.total_spend),
  }));

  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={formatted} margin={{ left: 4, right: 8, top: 4, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(11,60,93,0.07)" vertical={false} />
        <XAxis
          dataKey="month"
          tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
          width={36}
        />
        <Tooltip
          formatter={(v: number) => [`$${v.toLocaleString()}`, "Spending"]}
          contentStyle={{
            borderRadius: 10, fontSize: 12,
            background: "rgba(255,255,255,0.96)",
            border: "1px solid rgba(205,237,246,0.8)",
            boxShadow: "0 4px 16px rgba(11,60,93,0.10)",
          }}
          cursor={{ stroke: "rgba(255,122,90,0.20)", strokeWidth: 1 }}
        />
        <Line
          type="monotone"
          dataKey="spend"
          stroke="#FF7A5A"
          strokeWidth={2.5}
          dot={{ r: 3, fill: "#FF7A5A", strokeWidth: 0 }}
          activeDot={{ r: 5, fill: "#FF7A5A", strokeWidth: 0 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function CategoryPieChart({ data }: { data: { category: string; total: number }[] }) {
  if (data.length === 0) {
    return <EmptyChart message="No spending categories found — upload bank or credit card statements" />;
  }

  const slices = data.slice(0, 7).map((d, i) => ({
    name: CATEGORY_LABELS[d.category] ?? d.category,
    value: Math.round(d.total),
    color: CHART_COLORS[i % CHART_COLORS.length],
  }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie
          data={slices}
          cx="40%"
          cy="50%"
          innerRadius={52}
          outerRadius={78}
          paddingAngle={2}
          dataKey="value"
          strokeWidth={0}
        >
          {slices.map((entry, i) => (
            <Cell key={i} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip
          formatter={(v: number) => [`$${v.toLocaleString()}`, ""]}
          contentStyle={{
            borderRadius: 10, fontSize: 12,
            background: "rgba(255,255,255,0.96)",
            border: "1px solid rgba(205,237,246,0.8)",
          }}
        />
        {/* Legend positioned to the right of pie */}
        <g>
          {slices.map((entry, i) => (
            <text key={i} x="82%" y={`${18 + i * 13}%`} fill={entry.color} fontSize={10} dominantBaseline="middle">
              ● {entry.name}
            </text>
          ))}
        </g>
      </PieChart>
    </ResponsiveContainer>
  );
}

function InvestmentBarChart({ data }: { data: { account_name: string; total_value: number; pct_of_portfolio: number }[] }) {
  if (data.length === 0) {
    return <EmptyChart message="No investment account data — upload Morgan Stanley or E*TRADE statements" />;
  }

  const bars = data.map(d => ({
    account: d.account_name.length > 18 ? d.account_name.slice(0, 18) + "…" : d.account_name,
    value: Math.round(d.total_value),
    pct: d.pct_of_portfolio,
  }));

  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={bars} layout="vertical" margin={{ left: 0, right: 24, top: 0, bottom: 0 }}>
        <XAxis
          type="number"
          tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
        />
        <YAxis
          type="category"
          dataKey="account"
          tick={{ fontSize: 10, fill: "rgba(11,60,93,0.55)" }}
          tickLine={false}
          axisLine={false}
          width={110}
        />
        <Tooltip
          formatter={(v: number, _: string, props: any) => [
            `$${v.toLocaleString()} (${props.payload.pct}%)`, "Value"
          ]}
          contentStyle={{
            borderRadius: 10, fontSize: 12,
            background: "rgba(255,255,255,0.96)",
            border: "1px solid rgba(205,237,246,0.8)",
          }}
        />
        <Bar dataKey="value" radius={[0, 5, 5, 0]}>
          {bars.map((_, i) => (
            <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

function fmtUSD(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000)     return `$${(n / 1_000).toFixed(1)}k`;
  return `$${Math.round(n).toLocaleString()}`;
}

export function OverviewPage() {
  const setActivePage = useAppStore((s) => s.setActivePage);
  const [loading, setLoading]       = useState(true);
  const [summary, setSummary]       = useState<DashboardSummary | null>(null);
  const [banking, setBanking]       = useState<BankingDashboard | null>(null);
  const [investments, setInvestments] = useState<InvestmentsDashboard | null>(null);

  const fetch = useCallback(async () => {
    try {
      const [s, b, inv] = await Promise.all([
        dashboardApi.summary(),
        dashboardApi.banking(),
        dashboardApi.investments(),
      ]);
      setSummary(s);
      setBanking(b);
      setInvestments(inv);
    } catch {
      // backend not ready
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  // Derived values
  const spendByMonth  = banking?.spend_by_month ?? [];
  const currentMonthSpend = spendByMonth.length > 0 ? spendByMonth[spendByMonth.length - 1].total_spend : 0;
  const totalInvested = investments?.portfolio_summary.total_portfolio_value ?? 0;
  const subsTotal = banking?.subscriptions?.reduce((s, x) => s + x.avg_monthly_amount, 0) ?? 0;
  const feesTotal = investments?.fees?.total_fees ?? 0;
  const docsProcessed = summary?.total_documents ?? 0;
  const spendByCat    = banking?.spend_by_category ?? [];
  const allocation    = investments?.allocation ?? [];

  return (
    <div className="flex flex-col h-full">
      <PageHeader />

      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-5"
      >

        {/* ── Hero / mascot card ───────────────────────────────────────────── */}
        <HeroCard />

        {/* ── Feature cards ────────────────────────────────────────────────── */}
        <FeatureCards />

        {/* ── Metric cards ─────────────────────────────────────────────────── */}
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-2 lg:grid-cols-5 gap-3"
        >
          {loading ? (
            Array.from({ length: 5 }).map((_, i) => <MetricSkeleton key={i} />)
          ) : (
            <>
              <MetricCard
                label="Monthly Spending"
                value={fmtUSD(currentMonthSpend)}
                sub={spendByMonth.length > 0 ? spendByMonth[spendByMonth.length - 1].month : undefined}
                icon={<CreditCard size={14} />}
                accent="coral"
              />
              <MetricCard
                label="Total Invested"
                value={fmtUSD(totalInvested)}
                sub={investments?.portfolio_summary.last_updated ?? undefined}
                icon={<TrendingUp size={14} />}
                accent="ocean"
              />
              <MetricCard
                label="Subscriptions"
                value={subsTotal > 0 ? fmtUSD(subsTotal) + "/mo" : "—"}
                sub={`${banking?.subscriptions?.length ?? 0} detected`}
                icon={<RefreshCw size={14} />}
                accent="positive"
              />
              <MetricCard
                label="Fees This Month"
                value={feesTotal > 0 ? fmtUSD(feesTotal) : "—"}
                sub={investments?.fees?.by_category?.length
                  ? `${investments.fees.by_category.length} categories`
                  : undefined}
                icon={<Receipt size={14} />}
                accent="highlight"
              />
              <MetricCard
                label="Docs Processed"
                value={String(docsProcessed)}
                sub={summary?.total_institutions
                  ? `${summary.total_institutions} institution${summary.total_institutions !== 1 ? "s" : ""}`
                  : undefined}
                icon={<FileText size={14} />}
                accent="ocean"
              />
            </>
          )}
        </motion.div>

        {/* ── Charts row ───────────────────────────────────────────────────── */}
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-1 lg:grid-cols-3 gap-4"
        >
          {/* Spending line chart — spans 2 cols on large screens */}
          <motion.div variants={staggerChild} className="lg:col-span-2">
            <GlassCard>
              <ChartTitle sub="All accounts · last 12 months">
                Monthly Spending
              </ChartTitle>
              {loading
                ? <ChartSkeleton height={180} />
                : <SpendingLineChart data={spendByMonth} />}
            </GlassCard>
          </motion.div>

          {/* Category pie chart */}
          <motion.div variants={staggerChild}>
            <GlassCard>
              <ChartTitle sub="By transaction category">
                Spend Breakdown
              </ChartTitle>
              {loading
                ? <ChartSkeleton height={200} />
                : <CategoryPieChart data={spendByCat} />}
            </GlassCard>
          </motion.div>
        </motion.div>

        {/* ── Investment breakdown ─────────────────────────────────────────── */}
        <motion.div variants={staggerChild}>
          <GlassCard>
            <ChartTitle sub="Portfolio value by account">
              Investment Accounts
            </ChartTitle>
            {loading
              ? <ChartSkeleton height={180} />
              : <InvestmentBarChart data={allocation} />}
          </GlassCard>
        </motion.div>

        {/* ── Quick stats strip ────────────────────────────────────────────── */}
        {!loading && summary && (
          <motion.div variants={staggerChild}>
            <div
              className="rounded-2xl px-5 py-3 grid grid-cols-2 sm:grid-cols-4 gap-4"
              style={{
                background: "rgba(255,255,255,0.60)",
                border: "1px solid rgba(205,237,246,0.55)",
              }}
            >
              {[
                { label: "Statements", value: summary.total_statements },
                { label: "Transactions", value: summary.total_transactions.toLocaleString() },
                { label: "Holdings", value: summary.total_holdings },
                { label: "Accounts", value: summary.total_accounts },
              ].map(({ label, value }) => (
                <div key={label} className="text-center py-1">
                  <p className="text-[18px] font-bold text-ocean-deep tabular">{value}</p>
                  <p className="text-[10px] text-ocean/38 font-medium mt-0.5 uppercase tracking-wide">{label}</p>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {/* ── Empty state when no data at all ─────────────────────────────── */}
        {!loading && docsProcessed === 0 && (
          <motion.div variants={staggerChild}>
            <div
              className="rounded-2xl"
              style={{
                background: "rgba(255,255,255,0.65)",
                border: "1px dashed rgba(205,237,246,0.70)",
              }}
            >
              <CoralEmptyState
                variant="documents"
                title="No statements uploaded yet"
                description="Drop your PDFs here and Coral will turn them into searchable financial data."
                actionLabel="Upload a statement"
                onAction={() => setActivePage("documents")}
              />
            </div>
          </motion.div>
        )}

        {/* ── Security / privacy callout ───────────────────────────────────── */}
        <motion.div variants={staggerChild}>
          <div
            className="flex items-center gap-4 rounded-2xl px-5 py-4"
            style={{
              background: "rgba(76,175,147,0.07)",
              border: "1px solid rgba(76,175,147,0.22)",
            }}
          >
            <CoralMascot variant="security" size="sm" className="shrink-0" />
            <div>
              <p className="text-[13px] font-semibold text-ocean-deep">
                Your financial data stays local.
              </p>
              <p className="text-[11.5px] text-ocean/45 mt-0.5">
                Coral parses and stores everything on your device — no cloud, no external APIs.
              </p>
            </div>
          </div>
        </motion.div>

        <div className="h-3" />
      </motion.div>
    </div>
  );
}
