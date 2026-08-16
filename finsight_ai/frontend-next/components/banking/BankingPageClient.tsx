"use client";

import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  Landmark, TrendingDown, CreditCard, ArrowDownLeft, ArrowUpRight,
  RefreshCw, ChevronDown, MessageSquare, Sparkles, Info,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { bankingApi, type BankingDashboard, type BankingInsightsResult, type CategoryDrift } from "@/features/banking/api";
import { useAppStore } from "@/store/appStore";
import { useFinancialPeriod } from "@/hooks/useFinancialPeriod";
import { formatCompactCurrency, formatCurrency } from "@/lib/utils";
import { buildBudgetDriftRows, type DriftRow } from "@/lib/bankingDrift";
import MetricCard from "@/components/coral/MetricCard";
import GlassCard from "@/components/coral/GlassCard";
import SectionHeader from "@/components/coral/SectionHeader";
import EmptyState from "@/components/coral/EmptyState";
import LoadingState from "@/components/coral/LoadingState";
import ErrorState from "@/components/coral/ErrorState";
import BankingFlowTree from "@/components/banking/BankingFlowTree";
import BudgetDriftTable from "@/components/banking/BudgetDriftTable";
import TopDrivers from "@/components/banking/TopDrivers";
import ClassificationReviewSection from "@/components/banking/ClassificationReviewSection";
import BankingInsightsSection from "@/components/banking/BankingInsightsSection";
import {
  AccountValueLegend,
  AccountValueSummaryCard,
  AccountValueTable,
  AccountValueTrendChart,
  AccountValueViewToggle,
  CurrentSnapshotPanel,
  ExpandedAccountDetail,
  colorFor,
  type AccountValueViewMode,
} from "@/components/account-value/AccountValueExperience";
import CoralAdvisorCard from "@/components/coral-ds/CoralAdvisorCard";
import DsErrorState from "@/components/coral-ds/ErrorState";
import DsSectionHeader from "@/components/coral-ds/SectionHeader";
import FinancialPeriodSelector from "@/components/coral-ds/FinancialPeriodSelector";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import NextMonthPlanSection from "@/components/overview/NextMonthPlanSection";
import {
  overviewApi,
  type NextMonthPlanResult,
  type OverviewInsightsResult,
  type PlanVsActualResult,
} from "@/features/overview/api";
import { buildAccountValueDataset } from "@/lib/accountValue";

const INSIGHT_PROMPTS = [
  "What were my largest expenses in the last 6 months?",
  "Which recurring charges increased?",
  "Compare my Chase and BOFA cash flow.",
  "What subscriptions should I review?",
];

const KNOWN_ACCOUNTS = {
  checking: [
    { label: "Chase Checking",   key: "chase_checking" },
    { label: "BOFA Checking",    key: "bofa_checking" },
  ],
  savings: [
    { label: "Marcus HYSA",           key: "marcus_hysa" },
    { label: "Marcus Savings (Arjun)", key: "marcus_arjun" },
  ],
  creditCards: [
    { label: "Chase Freedom",            key: "chase_freedom" },
    { label: "Chase Prime",              key: "chase_prime" },
    { label: "Chase Sapphire Preferred", key: "chase_sapphire" },
    { label: "Amex Blue Cash",           key: "amex_blue" },
    { label: "Amex Gold",                key: "amex_gold" },
    { label: "Macy's",                   key: "macys" },
  ],
};

function CollapsibleSection({
  title,
  icon,
  children,
  defaultOpen = true,
  count,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
  count?: number;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div
      className="rounded-3xl overflow-hidden"
      style={{ background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-6 py-5 transition-colors hover:bg-white/[0.02]"
      >
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-2xl flex items-center justify-center"
            style={{ background: "var(--glass-light-bg)", border: "1px solid var(--border-subtle)" }}
          >
            {icon}
          </div>
          <span className="section-title" style={{ fontSize: "var(--font-card-title)" }}>{title}</span>
          {count !== undefined && (
            <span
              className="px-2.5 py-0.5 rounded-full text-xs font-semibold"
              style={{ background: "var(--glass-light-bg)", color: "var(--text-muted)", border: "1px solid var(--border-subtle)" }}
            >
              {count}
            </span>
          )}
        </div>
        <ChevronDown
          size={18}
          className="transition-transform duration-300"
          style={{ color: "var(--text-muted)", transform: open ? "rotate(180deg)" : "rotate(0deg)" }}
        />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.30, ease: [0.4, 0, 0.2, 1] }}
            style={{ overflow: "hidden" }}
          >
            <div
              className="px-6 pb-6 space-y-3"
              style={{ borderTop: "1px solid var(--border-subtle)" }}
            >
              <div className="pt-4">{children}</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AccountRow({
  label,
  data,
  type = "card",
}: {
  label: string;
  data?: { total_spend_fmt?: string; latest_statement?: string | null; transaction_count?: number } | null;
  type?: "card" | "checking" | "savings";
}) {
  const hasData = !!data;

  return (
    <div
      className="flex items-center justify-between px-4 py-3.5 rounded-2xl"
      style={{ background: "var(--row-bg)", border: "1px solid var(--row-border)" }}
    >
      <div className="flex items-center gap-3">
        <div
          className="w-8 h-8 rounded-xl flex items-center justify-center"
          style={{ background: "var(--glass-light-bg)", border: "1px solid var(--border-subtle)" }}
        >
          {type === "card"
            ? <CreditCard size={13} style={{ color: "var(--text-muted)" }} />
            : type === "savings"
              ? <ArrowUpRight size={13} style={{ color: "#4CAF93" }} />
              : <Landmark size={13} style={{ color: "rgba(95,168,211,0.75)" }} />
          }
        </div>
        <div>
          <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>{label}</p>
          {data?.latest_statement && (
            <p className="micro-text mt-0.5" style={{ color: "var(--text-muted)" }}>
              Latest: {new Date(data.latest_statement).toLocaleDateString()}
            </p>
          )}
          {!hasData && (
            <p className="micro-text mt-0.5" style={{ color: "var(--text-dim)" }}>Waiting for data</p>
          )}
        </div>
      </div>
      <div className="text-right">
        {hasData && data?.total_spend_fmt ? (
          <>
            <p className="small-text font-bold" style={{ color: "var(--text-primary)" }}>{data.total_spend_fmt}</p>
            {data.transaction_count !== undefined && (
              <p className="micro-text" style={{ color: "var(--text-muted)" }}>{data.transaction_count} txns</p>
            )}
          </>
        ) : (
          <span
            className="px-2.5 py-1 rounded-lg text-xs font-medium"
            style={{ background: "var(--empty-bg)", color: "var(--text-dim)", border: "1px solid var(--empty-border)" }}
          >
            No data
          </span>
        )}
      </div>
    </div>
  );
}

interface LoadState<T> {
  data: T | null;
  loading: boolean;
  error: boolean;
}

const INITIAL_LOAD_STATE = { data: null, loading: true, error: false };

function accountInsightText(dataset: ReturnType<typeof buildAccountValueDataset>) {
  if (dataset.accounts.length === 0) {
    return {
      title: "Upload cash account statements to unlock account trends.",
      body: "Coral only shows account-value history when real balance snapshots are available.",
    };
  }
  if (dataset.totalChange === null) {
    return {
      title: "Your latest cash snapshot is available.",
      body: "Add another month of statements to compare month-over-month movement.",
    };
  }
  const topMover = [...dataset.accounts]
    .filter((account) => account.change !== null)
    .sort((a, b) => Math.abs(b.change ?? 0) - Math.abs(a.change ?? 0))[0];
  return {
    title: dataset.totalChange >= 0
      ? "Your cash accounts increased this period."
      : "Your cash accounts declined this period.",
    body: topMover
      ? `${topMover.accountName} moved the most, changing by ${formatCurrency(Math.abs(topMover.change ?? 0))}.`
      : "Coral is using the latest available monthly balance snapshots.",
  };
}

export default function BankingPageClient() {
  const [data, setData]     = useState<BankingDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  // Separate from `loading`: true only while refetching for a period change,
  // so the page keeps showing the previous data (dimmed) instead of
  // flashing back to a full-page skeleton every time the filter changes.
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError]   = useState<string | null>(null);
  const openUploadModal     = useAppStore((s) => s.openUploadModal);
  const { selection, resolved, setSelection, goToPreviousMonth, goToNextMonth } = useFinancialPeriod();

  // Plan vs Actual (drives the flow tree, PR 07) and the advisor summary
  // headline — both reuse the exact same already-computed backend surfaces
  // Overview uses (GET /api/v1/plan-vs-actual, GET /api/v1/overview/insights),
  // scoped to Banking's own period selection. No parallel classification or
  // aggregation is introduced here; see BankingFlowTree/lib/bankingFlowTree.ts.
  const [planVsActual, setPlanVsActual] = useState<LoadState<PlanVsActualResult>>(INITIAL_LOAD_STATE);
  const [insights, setInsights] = useState<LoadState<OverviewInsightsResult>>(INITIAL_LOAD_STATE);

  // Needs/Wants/Savings category breakdowns for "Where You're Off Plan"
  // (PR 08) — reuse the exact same GET /plan-vs-actual/buckets/{bucket}
  // endpoint BankingFlowTree's category drill-down already uses
  // (bankingApi.bucketBreakdown), just fetched eagerly for all three
  // consumption/accumulation buckets Banking shows rather than lazily on
  // click. Investments is intentionally excluded (see lib/bankingDrift.ts).
  //
  // "Top Drivers" is anchored differently (Decision 2, RESOLVED — Option B,
  // docs/coral-redesign/BLOCKED.md): Needs/Wants categories have no
  // plan-defined target, so it reads `planVsActual.data.buckets` instead —
  // the exact same bucket-level PlanVsActualResult BankingFlowTree already
  // fetches above, not this category breakdown. See lib/bankingDrift.ts's
  // `buildTopDriverCandidates`.
  const [needsBreakdown, setNeedsBreakdown] = useState<LoadState<CategoryDrift[]>>(INITIAL_LOAD_STATE);
  const [wantsBreakdown, setWantsBreakdown] = useState<LoadState<CategoryDrift[]>>(INITIAL_LOAD_STATE);
  const [savingsBreakdown, setSavingsBreakdown] = useState<LoadState<CategoryDrift[]>>(INITIAL_LOAD_STATE);
  const [bankingInsights, setBankingInsights] = useState<LoadState<BankingInsightsResult>>(INITIAL_LOAD_STATE);
  const [nextMonthPlan, setNextMonthPlan] = useState<LoadState<NextMonthPlanResult>>(INITIAL_LOAD_STATE);
  const [accountViewMode, setAccountViewMode] = useState<AccountValueViewMode>("line");
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);

  const { startDate, endDate } = resolved;

  const loadFlow = useCallback(() => {
    const periodParams = { startDate, endDate };

    setPlanVsActual((s) => ({ ...s, loading: true, error: false }));
    overviewApi
      .planVsActual(periodParams)
      .then((d) => setPlanVsActual({ data: d, loading: false, error: false }))
      .catch(() => setPlanVsActual({ data: null, loading: false, error: true }));

    setInsights((s) => ({ ...s, loading: true, error: false }));
    overviewApi
      .insights(periodParams)
      .then((d) => setInsights({ data: d, loading: false, error: false }))
      .catch(() => setInsights({ data: null, loading: false, error: true }));
  }, [startDate, endDate]);

  useEffect(() => { loadFlow(); }, [loadFlow]);

  const loadDrift = useCallback(() => {
    const periodParams = { startDate, endDate };
    const fetchBucket = (
      bucket: "needs" | "wants" | "savings",
      set: Dispatch<SetStateAction<LoadState<CategoryDrift[]>>>,
    ) => {
      set((s) => ({ ...s, loading: true, error: false }));
      bankingApi
        .bucketBreakdown(bucket, periodParams)
        .then((d) => set({ data: d, loading: false, error: false }))
        .catch(() => set({ data: null, loading: false, error: true }));
    };
    fetchBucket("needs", setNeedsBreakdown);
    fetchBucket("wants", setWantsBreakdown);
    fetchBucket("savings", setSavingsBreakdown);
  }, [startDate, endDate]);

  useEffect(() => { loadDrift(); }, [loadDrift]);

  const loadBankingInsights = useCallback(() => {
    const periodParams = { startDate, endDate };
    setBankingInsights((s) => ({ ...s, loading: true, error: false }));
    bankingApi
      .insights(periodParams)
      .then((d) => setBankingInsights({ data: d, loading: false, error: false }))
      .catch(() => setBankingInsights({ data: null, loading: false, error: true }));
  }, [startDate, endDate]);

  useEffect(() => { loadBankingInsights(); }, [loadBankingInsights]);

  const loadNextMonthPlan = useCallback(() => {
    const periodParams = { startDate, endDate };
    setNextMonthPlan((s) => ({ ...s, loading: true, error: false }));
    overviewApi
      .nextMonthPlan(periodParams)
      .then((d) => setNextMonthPlan({ data: d, loading: false, error: false }))
      .catch(() => setNextMonthPlan({ data: null, loading: false, error: true }));
  }, [startDate, endDate]);

  useEffect(() => { loadNextMonthPlan(); }, [loadNextMonthPlan]);

  const accountDataset = useMemo(
    () => buildAccountValueDataset(data?.account_value_history ?? []),
    [data?.account_value_history],
  );
  const selectedAccount = accountDataset.accounts.find((account) => (
    account.accountId === selectedAccountId
  )) ?? null;
  const accountInsight = useMemo(() => accountInsightText(accountDataset), [accountDataset]);

  useEffect(() => {
    if (accountDataset.accounts.length === 0) {
      if (selectedAccountId !== null) setSelectedAccountId(null);
      return;
    }
    if (!selectedAccountId || !accountDataset.accounts.some((account) => (
      account.accountId === selectedAccountId
    ))) {
      setSelectedAccountId(accountDataset.accounts[0].accountId);
    }
  }, [accountDataset.accounts, selectedAccountId]);

  const driftLoading = needsBreakdown.loading || wantsBreakdown.loading || savingsBreakdown.loading;
  const driftError = needsBreakdown.error || wantsBreakdown.error || savingsBreakdown.error;
  const driftRows: DriftRow[] | null = driftLoading
    ? null
    : buildBudgetDriftRows(needsBreakdown.data, wantsBreakdown.data, savingsBreakdown.data);
  // Retry refetches all three buckets through the same code path as the
  // initial load, so the skeleton (not a stale error card) is shown while the
  // retry is in flight.
  const retryDrift = loadDrift;

  const load = (isPeriodChange: boolean) => {
    if (isPeriodChange) setRefreshing(true); else setLoading(true);
    setError(null);
    bankingApi.banking(12, { startDate: resolved.startDate, endDate: resolved.endDate })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => { setLoading(false); setRefreshing(false); });
  };

  // Initial load, then refetch (server-side, not client-side filtering)
  // whenever the resolved date range changes.
  useEffect(() => { load(data !== null); }, [resolved.startDate, resolved.endDate]);

  if (loading) return <LoadingState columns={4} rows={3} message="Loading your banking data…" />;
  if (error)   return <ErrorState message={error} onRetry={() => load(false)} />;

  const totalSpend  = data?.spend_by_month.reduce((s, m) => s + m.total_spend, 0) ?? 0;
  // Only a real average once the selected period actually covers 2+ months.
  // With a single (often partial) month selected, `totalSpend / 1` is just the
  // period total wearing an "Avg Monthly" label — a misleading restatement of
  // the tile next to it rather than an average.
  const monthsCovered = data?.spend_by_month.length ?? 0;
  const avgMonthly  = monthsCovered >= 2 ? totalSpend / monthsCovered : null;
  const totalInflow = data?.cash_flow.reduce((s, m) => s + m.inflow, 0) ?? 0;
  const totalOutflow= data?.cash_flow.reduce((s, m) => s + m.outflow, 0) ?? 0;
  const netFlow     = totalInflow - totalOutflow;
  const fmt = (n: number) => formatCompactCurrency(n);
  const fullFmt = (n: number) => formatCurrency(n);

  // data is guaranteed non-null here (guarded above by early returns)

  const hasAnyData = (data?.card_summary?.length ?? 0) > 0 || (data?.spend_by_month?.length ?? 0) > 0;

  const anyFlowLoading = planVsActual.loading || insights.loading || nextMonthPlan.loading;
  const bankingPlanRecommendations = nextMonthPlan.data?.recommendations.filter((rec) => (
    rec.bucket === "needs" ||
    rec.bucket === "wants" ||
    rec.bucket === "savings" ||
    rec.action_type === "review_merchant" ||
    rec.action_type === "review_subscription" ||
    rec.action_type === "reduce_category" ||
    rec.action_type === "increase_savings_goal"
  )) ?? null;

  return (
    <div className="space-y-10">

      {/* ── Account-value hero — approved Banking mockup direction ───── */}
      <section className="space-y-6">
        <div className="grid items-center gap-6 lg:grid-cols-[minmax(0,1fr)_560px]">
          <div>
            <h1 className="text-5xl font-black tracking-normal text-slate-950 md:text-6xl">
              Banking
            </h1>
            <p className="mt-3 max-w-xl text-lg text-slate-600">
              Track how your cash accounts are growing month by month.
            </p>
            <div className="mt-5">
              <FinancialPeriodSelector
                selection={selection}
                resolved={resolved}
                onChange={setSelection}
                onPrevMonth={goToPreviousMonth}
                onNextMonth={goToNextMonth}
                loading={refreshing || anyFlowLoading}
              />
            </div>
          </div>

          <div className="grid items-center gap-5 sm:grid-cols-[210px_minmax(0,1fr)]">
            <Image
              src="/mascots/coral-banking.png"
              alt=""
              width={240}
              height={160}
              priority
              className="mx-auto h-36 w-auto object-contain"
            />
            <div
              className="rounded-[28px] bg-white/86 p-6 shadow-[0_18px_48px_rgba(30,70,110,0.08)] ring-1 ring-slate-200/80"
            >
              <div className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-orange-50 text-coral-orange">
                  <Sparkles size={16} />
                </span>
                <div>
                  <p className="text-sm font-black text-slate-950">Here's the story of your cash</p>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{accountInsight.body}</p>
                </div>
              </div>
              <Link
                href="/chat"
                className="mt-4 inline-flex items-center gap-2 text-sm font-bold text-coral-orange"
              >
                View key takeaways <ArrowUpRight size={14} />
              </Link>
            </div>
          </div>
        </div>

        {accountDataset.accounts.length > 0 ? (
          <>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {accountDataset.accounts.map((account, index) => (
                <AccountValueSummaryCard
                  key={account.accountId}
                  account={account}
                  color={colorFor(index)}
                  selected={selectedAccountId === account.accountId}
                  onSelect={() => setSelectedAccountId((current) => (
                    current === account.accountId ? null : account.accountId
                  ))}
                />
              ))}
            </div>

            <ExpandedAccountDetail
              account={selectedAccount}
              color={colorFor(Math.max(0, accountDataset.accounts.findIndex((account) => (
                account.accountId === selectedAccount?.accountId
              ))))}
              meta={selectedAccount ? {
                accountId: selectedAccount.accountId,
                classification: selectedAccount.accountType === "checking"
                  ? "Joint cash account"
                  : "Cash reserve",
                purpose: selectedAccount.institutionType === "bofa"
                  ? "Fun spending and larger wants"
                  : selectedAccount.accountType === "checking"
                    ? "Salary, rent, utilities, cars, groceries, dining, and recurring transfers"
                    : null,
              } : null}
            />
          </>
        ) : (
          <div className="rounded-[28px] bg-white/88 p-8 text-center shadow-[0_18px_50px_rgba(30,70,110,0.08)] ring-1 ring-slate-200/80">
            <h2 className="text-xl font-black text-slate-950">No cash account value snapshots yet</h2>
            <p className="mx-auto mt-2 max-w-2xl text-sm text-slate-600">
              Coral found banking activity, but no checking or savings balance snapshots in this period.
              Upload cash account statements with ending balances to enable account trends.
            </p>
          </div>
        )}
      </section>

      <section
        className="rounded-[30px] bg-white/90 p-5 shadow-[0_20px_60px_rgba(30,70,110,0.10)] ring-1 ring-slate-200/80 md:p-6"
      >
        <div className="mb-5 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-black text-slate-950">Account Value Trends</h2>
              <Info size={15} className="text-slate-400" />
            </div>
            <p className="mt-1 text-sm text-slate-600">Your banking accounts over time</p>
          </div>
          <AccountValueViewToggle value={accountViewMode} onChange={setAccountViewMode} />
        </div>
        <div className="mb-4">
          <AccountValueLegend dataset={accountDataset} />
        </div>
        {accountViewMode === "line" ? (
          <AccountValueTrendChart
            dataset={accountDataset}
            height={390}
            selectedAccountId={selectedAccountId}
          />
        ) : (
          <AccountValueTable dataset={accountDataset} />
        )}
      </section>

      {accountDataset.accounts.length > 0 && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
          <CurrentSnapshotPanel dataset={accountDataset} />
          <div
            className="rounded-[28px] bg-gradient-to-br from-sky-50 to-white p-6 shadow-[0_18px_50px_rgba(30,70,110,0.08)] ring-1 ring-sky-100"
          >
            <div className="flex items-start gap-4">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
                <Sparkles size={20} />
              </span>
              <div>
                <h3 className="text-lg font-black text-slate-950">Coral Insight</h3>
                <p className="mt-5 text-lg font-black text-slate-950">{accountInsight.title}</p>
                <p className="mt-3 text-sm leading-6 text-slate-600">{accountInsight.body}</p>
                <Link
                  href="/chat"
                  className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-coral-orange"
                >
                  See all insights <ArrowUpRight size={14} />
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}

      {insights.loading ? (
        <SkeletonState variant="card" height="96px" />
      ) : insights.error ? (
        <DsErrorState compact message="Couldn't load your banking summary for this period." onRetry={loadFlow} />
      ) : insights.data ? (
        <CoralAdvisorCard
          headline={insights.data.status.headline}
          body={insights.data.status.body}
          tone={insights.data.status.tone}
        />
      ) : null}

      {/* ── Banking Flow Tree — preserved below account-value experience ─ */}
      <section>
        <DsSectionHeader eyebrow="This period" title="Your Cash Flow" size="sm" className="mb-5" />
        <BankingFlowTree
          result={planVsActual.data}
          loading={planVsActual.loading}
          error={planVsActual.error}
          onRetry={loadFlow}
          period={{ startDate, endDate }}
        />
      </section>

      {/* ── Where You're Off Plan (PR 08) ───────────────────────────── */}
      <section>
        <DsSectionHeader eyebrow="This period" title="Where You're Off Plan" size="sm" className="mb-5" />
        <BudgetDriftTable
          rows={driftRows}
          loading={driftLoading}
          error={driftError}
          onRetry={retryDrift}
          period={{ startDate, endDate }}
        />
      </section>

      {/* ── Top Drivers (PR 08) — bucket-anchored, see BankingPageClient's
       * planVsActual state + lib/bankingDrift.ts's module docstring for why
       * this reads `planVsActual.data.buckets` rather than `driftRows`. ── */}
      <section>
        <DsSectionHeader eyebrow="This period" title="Top Drivers" size="sm" className="mb-5" />
        <TopDrivers
          buckets={planVsActual.data?.buckets ?? null}
          loading={planVsActual.loading}
          error={planVsActual.error}
          onRetry={loadFlow}
          period={{ startDate, endDate }}
        />
      </section>

      {/* ── Transactions to Review (PR 09) — the ACTION step after Plan →
       * Actual → Drift above: uncertain classifications the user can confirm
       * or correct. Scoped to the same globally-selected period as every
       * section above (pr-05-period-filter.md), so a correction here always
       * moves numbers the user can currently see. `onChanged` refetches the
       * flow tree/drift/top-drivers data above so that happens without a
       * full page reload — Plan vs Actual is naturally live server-side, so
       * a plain refetch through the same loadFlow/loadDrift callbacks used
       * for period changes is enough. ── */}
      <section>
        <DsSectionHeader eyebrow="This period" title="Transactions to Review" size="sm" className="mb-5" />
        <ClassificationReviewSection
          period={{ startDate, endDate }}
          onChanged={() => {
            loadFlow();
            loadDrift();
            loadBankingInsights();
          }}
        />
      </section>

      {/* ── Banking Insights (PR 10) — deterministic top three actions,
       * backed by the backend's ranked Banking insight facts. ───────── */}
      <section>
        <DsSectionHeader eyebrow="This period" title="Banking Insights" size="sm" className="mb-5" />
        <BankingInsightsSection
          insights={bankingInsights.data?.insights ?? null}
          loading={bankingInsights.loading}
          error={bankingInsights.error}
          onRetry={loadBankingInsights}
        />
      </section>

      {/* ── Next Month Plan (PR 14) — banking-relevant actions from the
       * shared deterministic planner. Source facts are visible here because
       * Banking is the correction/action surface for cash-flow drift. ── */}
      <section>
        <DsSectionHeader eyebrow="Next period" title="Banking Next Month Plan" size="sm" className="mb-5" />
        <NextMonthPlanSection
          recommendations={bankingPlanRecommendations}
          loading={nextMonthPlan.loading}
          error={nextMonthPlan.error}
          onRetry={loadNextMonthPlan}
          showSourceFacts
        />
      </section>

      {/* ── Summary metrics — demoted from dominant position; the flow tree
       * above is the hero (pr-07-banking-flow.md: "Remove generic KPI row
       * from dominant position"). Kept as supporting detail, not removed. ── */}
      <div>
        <SectionHeader eyebrow="At a glance" title="Card & Cash Summary" size="sm" className="mb-5" />
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.40, delay: 0.05 }}
          className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4"
        >
        {[
          {
            title: "Credit Card Spend",
            value: totalSpend > 0 ? fmt(totalSpend) : null,
            fullValue: fullFmt(totalSpend),
            icon: <CreditCard size={16} style={{ color: "#E45757" }} />,
            accent: "rgba(228,87,87,0.14)",
            status: "negative" as const,
            emptyText: "Upload card statements",
          },
          {
            title: "Avg Monthly",
            value: avgMonthly !== null ? fmt(avgMonthly) : null,
            fullValue: avgMonthly !== null ? fullFmt(avgMonthly) : undefined,
            icon: <TrendingDown size={16} style={{ color: "rgba(255,209,102,0.80)" }} />,
            accent: "rgba(255,209,102,0.14)",
            emptyText: monthsCovered === 1 ? "Select a longer period" : "Upload card statements",
          },
          {
            title: "Cash In",
            value: totalInflow > 0 ? fmt(totalInflow) : null,
            fullValue: fullFmt(totalInflow),
            icon: <ArrowDownLeft size={16} style={{ color: "#4CAF93" }} />,
            accent: "rgba(76,175,147,0.14)",
            status: "positive" as const,
            emptyText: "Upload checking statements",
          },
          {
            title: "Cash Out",
            value: totalOutflow > 0 ? fmt(totalOutflow) : null,
            fullValue: fullFmt(totalOutflow),
            icon: <ArrowUpRight size={16} style={{ color: "#E45757" }} />,
            accent: "rgba(228,87,87,0.14)",
            status: "negative" as const,
            emptyText: "Upload checking statements",
          },
          {
            title: "Net Flow",
            value: (totalInflow > 0 || totalOutflow > 0) ? fmt(netFlow) : null,
            fullValue: fullFmt(netFlow),
            icon: <RefreshCw size={16} style={{ color: "var(--accent-strong)" }} />,
            accent: "rgba(34,211,238,0.14)",
            status: netFlow >= 0 ? "positive" as const : "negative" as const,
            emptyText: "Needs checking data",
          },
          {
            title: "Active Accounts",
            value: (data?.card_summary.length ?? 0) > 0 ? String(data!.card_summary.length) : null,
            icon: <Landmark size={16} style={{ color: "rgba(95,168,211,0.80)" }} />,
            accent: "rgba(95,168,211,0.14)",
            emptyText: "Upload statements",
          },
        ].map((m) => (
          <MetricCard key={m.title} {...m} size="sm" />
        ))}
        </motion.div>
      </div>

      {/* ── Account groups ──────────────────────────────────────────── */}
      {hasAnyData ? (
        <div className="space-y-4">
          <SectionHeader eyebrow="Accounts" title="Account Groups" size="sm" className="mb-2" />

          {/* Checking */}
          <CollapsibleSection
            title="Checking"
            icon={<Landmark size={15} style={{ color: "rgba(95,168,211,0.80)" }} />}
            count={KNOWN_ACCOUNTS.checking.length}
          >
            {KNOWN_ACCOUNTS.checking.map((acct) => {
              const match = data?.card_summary.find((c) =>
                (c.account_name ?? c.product_label ?? "").toLowerCase().includes(acct.label.toLowerCase().split(" ")[0].toLowerCase())
              );
              return <AccountRow key={acct.key} label={acct.label} data={match} type="checking" />;
            })}
          </CollapsibleSection>

          {/* Savings */}
          <CollapsibleSection
            title="Savings"
            icon={<ArrowUpRight size={15} style={{ color: "#4CAF93" }} />}
            count={KNOWN_ACCOUNTS.savings.length}
            defaultOpen={false}
          >
            {KNOWN_ACCOUNTS.savings.map((acct) => {
              const match = data?.card_summary.find((c) =>
                (c.account_name ?? c.product_label ?? "").toLowerCase().includes("marcus")
              );
              return <AccountRow key={acct.key} label={acct.label} data={match} type="savings" />;
            })}
          </CollapsibleSection>

          {/* Credit Cards */}
          <CollapsibleSection
            title="Credit Cards"
            icon={<CreditCard size={15} style={{ color: "#E45757" }} />}
            count={KNOWN_ACCOUNTS.creditCards.length}
          >
            {KNOWN_ACCOUNTS.creditCards.map((acct) => {
              const match = data?.card_summary.find((c) => {
                const name = (c.account_name ?? c.product_label ?? "").toLowerCase();
                const labelParts = acct.label.toLowerCase().split(" ");
                return labelParts.some((p) => p.length > 3 && name.includes(p));
              });
              return <AccountRow key={acct.key} label={acct.label} data={match} type="card" />;
            })}
          </CollapsibleSection>
        </div>
      ) : (
        <EmptyState
          icon={<Landmark size={28} />}
          title="No banking data yet"
          description="Upload your bank and credit card statements to see spending analysis, account summaries, and cash flow."
          action={
            <button type="button" onClick={openUploadModal} className="inline-flex items-center gap-2 px-6 py-3 rounded-2xl text-white font-semibold btn-coral">
              <RefreshCw size={15} /> Upload statements
            </button>
          }
        />
      )}

      {/* ── Top merchants ───────────────────────────────────────────── */}
      {(data?.top_merchants?.length ?? 0) > 0 && (
        <section>
          <SectionHeader eyebrow="Spending" title="Top Merchants" size="sm" className="mb-5" />
          <GlassCard variant="default" className="!p-0 overflow-hidden">
            {data!.top_merchants.slice(0, 10).map((merchant, i) => (
              <div
                key={i}
                className="flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-white/[0.02]"
                style={{ borderBottom: i < Math.min(data!.top_merchants.length, 10) - 1 ? "1px solid var(--border-subtle)" : "none" }}
              >
                <span className="w-7 text-center micro-text font-bold" style={{ color: "var(--text-dim)" }}>{i + 1}</span>
                <span className="flex-1 small-text" style={{ color: "var(--text-secondary)" }}>{merchant.merchant}</span>
                <span className="small-text font-bold tabular" style={{ color: "var(--text-primary)" }}>{merchant.total_fmt}</span>
                <span className="micro-text" style={{ color: "var(--text-dim)" }}>{merchant.transaction_count} txns</span>
              </div>
            ))}
          </GlassCard>
        </section>
      )}

      {/* ── Spend by category ───────────────────────────────────────── */}
      {(data?.spend_by_category?.length ?? 0) > 0 && (
        <section>
          <SectionHeader eyebrow="Breakdown" title="Spend by Category" size="sm" className="mb-5" />
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
            {data!.spend_by_category.slice(0, 8).map((cat, i) => (
              <div
                key={i}
                className="flex items-center justify-between px-4 py-3.5 rounded-2xl"
                style={{ background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" }}
              >
                <div className="flex items-center gap-2.5">
                  <TrendingDown size={14} style={{ color: "rgba(34,211,238,0.60)" }} />
                  <span className="small-text" style={{ color: "var(--text-secondary)" }}>{cat.category}</span>
                </div>
                <span className="small-text font-bold tabular" style={{ color: "var(--text-primary)" }}>{cat.total_fmt}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Subscriptions ───────────────────────────────────────────── */}
      {(data?.subscriptions?.length ?? 0) > 0 && (
        <section>
          <SectionHeader eyebrow="Recurring" title="Subscriptions" size="sm" className="mb-5" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {data!.subscriptions.slice(0, 8).map((sub, i) => (
              <div
                key={i}
                className="flex items-center justify-between px-5 py-4 rounded-2xl"
                style={{ background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" }}
              >
                <div>
                  <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>{sub.merchant}</p>
                  <p className="micro-text mt-0.5" style={{ color: "var(--text-muted)" }}>
                    {sub.occurrences}× seen {sub.last_seen ? `· Last: ${new Date(sub.last_seen).toLocaleDateString()}` : ""}
                  </p>
                </div>
                <div className="text-right">
                  <p className="small-text font-bold tabular" style={{ color: "var(--text-primary)" }}>{sub.avg_monthly_amount_fmt}</p>
                  <p className="micro-text" style={{ color: "var(--text-muted)" }}>/mo avg</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Coral insight strip ─────────────────────────────────────── */}
      <GlassCard variant="subtle" className="space-y-4">
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-2xl flex items-center justify-center"
            style={{ background: "rgba(255,122,90,0.15)", border: "1px solid rgba(255,122,90,0.25)" }}
          >
            <MessageSquare size={15} style={{ color: "#FF7A5A" }} />
          </div>
          <div>
            <p className="card-title-lg">Ask Coral about your banking</p>
            <p className="small-text mt-0.5" style={{ color: "var(--text-muted)" }}>Click a prompt or go to chat</p>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {INSIGHT_PROMPTS.map((prompt) => (
            <Link
              key={prompt}
              href="/chat"
              className="flex items-center gap-2 px-4 py-3 rounded-2xl small-text font-medium transition-all hover:-translate-y-0.5"
              style={{
                background: "var(--insight-bg)",
                border: "1px solid var(--insight-border)",
                color: "var(--text-secondary)",
              }}
            >
              <Sparkles size={12} style={{ color: "rgba(255,122,90,0.70)" }} />
              {prompt}
            </Link>
          ))}
        </div>
      </GlassCard>

    </div>
  );
}
