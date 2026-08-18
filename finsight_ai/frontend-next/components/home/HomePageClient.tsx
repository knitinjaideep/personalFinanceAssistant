"use client";

/**
 * Overview page (PR 06 — docs/coral-redesign/pr-06-overview.md). Answers
 * "How am I doing financially?" in ~10 seconds:
 *
 *   1. Financial status header (CoralAdvisorCard, restrained mascot)
 *   2. Shared FinancialPeriodSelector (PR 05, reused as-is)
 *   3. Income vs Spent vs Saved/Invested grouped bar chart
 *   4. Plan vs Actual (Needs/Wants/Savings/Investments)
 *   5. Coral Insights (<=3, ranked, deterministic)
 *   6. Next Month Plan (small, deterministic preview)
 *
 * Document processing/upload status is intentionally demoted to a single
 * low-key strip at the bottom (DocumentsStrip) rather than the dominant
 * content it used to be — see pr-06-overview.md's "Demote/remove from Home
 * as dominant content" list. Upload functionality itself is preserved.
 *
 * All financial values are already-computed backend output
 * (GET /api/v1/plan-vs-actual, GET /api/v1/overview/insights,
 * GET /api/v1/overview/monthly-flow, GET /api/v1/next-month-plan) — no
 * financial math happens in this component tree (.claude/rules/frontend.md).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, FileCheck2, Landmark, Sparkles, TrendingUp, Upload } from "lucide-react";
import CoralMascot from "@/components/coral/CoralMascot";
import CoralAdvisorCard from "@/components/coral-ds/CoralAdvisorCard";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import FinancialPeriodSelector from "@/components/coral-ds/FinancialPeriodSelector";
import PageHeader from "@/components/coral-ds/PageHeader";
import SectionHeader from "@/components/coral-ds/SectionHeader";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import Surface from "@/components/coral-ds/Surface";
import CoralInsightsSection from "@/components/overview/CoralInsightsSection";
import DocumentsStrip from "@/components/overview/DocumentsStrip";
import IncomeSpentSavedChart from "@/components/overview/IncomeSpentSavedChart";
import NextMonthPlanSection from "@/components/overview/NextMonthPlanSection";
import PlanVsActualSection from "@/components/overview/PlanVsActualSection";
import { bankingApi, type BankingDashboard } from "@/features/banking/api";
import { documentsApi } from "@/features/documents/api";
import { investmentsApi, type InvestmentsDashboard } from "@/features/investments/api";
import {
  overviewApi,
  type MonthlyFlowSummary,
  type NextMonthPlanResult,
  type OverviewInsightsResult,
  type PlanVsActualResult,
} from "@/features/overview/api";
import { useAppStore } from "@/store/appStore";
import { useFinancialPeriod } from "@/hooks/useFinancialPeriod";
import { buildAccountValueDataset } from "@/lib/accountValue";
import { formatCurrency } from "@/lib/utils";
import type { DocumentStats } from "@/types/index";

interface LoadState<T> {
  data: T | null;
  loading: boolean;
  error: boolean;
}

const INITIAL_LOAD_STATE = { data: null, loading: true, error: false };
const BUDGET_PLAN_STORAGE_KEY = "coral:overview:budgetPlan";
const DEFAULT_MONTHLY_SALARY = "12000";
const DEFAULT_MONTHLY_TARGETS = {
  needs: "6400",
  wants: "1100",
  savings: "2100",
  investments: "2400",
} as const;
const PLAN_BUCKET_LABELS = {
  needs: "Needs",
  wants: "Wants",
  savings: "Savings",
  investments: "Investments",
} as const;

type BudgetPlanBucket = keyof typeof DEFAULT_MONTHLY_TARGETS;
type BudgetPlanTargets = Record<BudgetPlanBucket, string>;

interface StoredBudgetPlan {
  salary: string;
  targets: BudgetPlanTargets;
}

function parseSalaryInput(value: string): number | null {
  const normalized = value.replace(/[$,\s]/g, "");
  if (normalized.length === 0) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function parseMoneyInput(value: string): number | null {
  const normalized = value.replace(/[$,\s]/g, "");
  if (normalized.length === 0) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function displayNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/\.?0+$/, "");
}

function percentagesFromTargets(targets: BudgetPlanTargets, salary: number): BudgetPlanTargets {
  return Object.fromEntries(
    (Object.keys(targets) as BudgetPlanBucket[]).map((bucket) => {
      const amount = parseMoneyInput(targets[bucket]) ?? 0;
      return [bucket, salary > 0 ? displayNumber(amount / salary * 100) : ""];
    }),
  ) as BudgetPlanTargets;
}

function periodMonthCount(startDate: string, endDate: string): number {
  const start = new Date(`${startDate}T00:00:00`);
  const end = new Date(`${endDate}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) return 1;
  const days = Math.max(1, (end.getTime() - start.getTime()) / 86_400_000 + 1);
  return Math.max(1, Math.round(days / 30.4375));
}

function readStoredBudgetPlan(): StoredBudgetPlan | null {
  try {
    const raw = window.localStorage.getItem(BUDGET_PLAN_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredBudgetPlan>;
    if (!parsed.salary || !parsed.targets) return null;
    return {
      salary: parsed.salary,
      targets: {
        needs: parsed.targets.needs ?? DEFAULT_MONTHLY_TARGETS.needs,
        wants: parsed.targets.wants ?? DEFAULT_MONTHLY_TARGETS.wants,
        savings: parsed.targets.savings ?? DEFAULT_MONTHLY_TARGETS.savings,
        investments: parsed.targets.investments ?? DEFAULT_MONTHLY_TARGETS.investments,
      },
    };
  } catch {
    return null;
  }
}

export default function HomePageClient() {
  const openUploadModal = useAppStore((s) => s.openUploadModal);
  const { selection, resolved, setSelection, goToPreviousMonth, goToNextMonth } = useFinancialPeriod();

  const [planVsActual, setPlanVsActual] = useState<LoadState<PlanVsActualResult>>(INITIAL_LOAD_STATE);
  const [insights, setInsights] = useState<LoadState<OverviewInsightsResult>>(INITIAL_LOAD_STATE);
  const [monthlyFlow, setMonthlyFlow] = useState<LoadState<MonthlyFlowSummary[]>>(INITIAL_LOAD_STATE);
  const [nextMonthPlan, setNextMonthPlan] = useState<LoadState<NextMonthPlanResult>>(INITIAL_LOAD_STATE);
  const [bankingSnapshot, setBankingSnapshot] = useState<LoadState<BankingDashboard>>(INITIAL_LOAD_STATE);
  const [investmentSnapshot, setInvestmentSnapshot] = useState<LoadState<InvestmentsDashboard>>(INITIAL_LOAD_STATE);
  const [salaryInput, setSalaryInput] = useState(DEFAULT_MONTHLY_SALARY);
  const [targetInputs, setTargetInputs] = useState<BudgetPlanTargets>({ ...DEFAULT_MONTHLY_TARGETS });
  const [targetPercentInputs, setTargetPercentInputs] = useState<BudgetPlanTargets>(
    percentagesFromTargets({ ...DEFAULT_MONTHLY_TARGETS }, Number(DEFAULT_MONTHLY_SALARY)),
  );
  const [budgetPlanDirty, setBudgetPlanDirty] = useState(false);
  const [budgetPlanSaved, setBudgetPlanSaved] = useState(false);

  const [docStats, setDocStats] = useState<DocumentStats | null>(null);
  const [docsLoading, setDocsLoading] = useState(true);
  const [docsError, setDocsError] = useState(false);

  const { startDate, endDate } = resolved;

  useEffect(() => {
    const saved = readStoredBudgetPlan();
    if (!saved) return;
    setSalaryInput(saved.salary);
    setTargetInputs(saved.targets);
    setTargetPercentInputs(percentagesFromTargets(saved.targets, parseSalaryInput(saved.salary) ?? 0));
  }, []);

  const salaryOverride = useMemo(() => parseSalaryInput(salaryInput), [salaryInput]);
  const periodMonths = useMemo(
    () => periodMonthCount(resolved.startDate, resolved.endDate),
    [resolved.startDate, resolved.endDate],
  );
  const monthlyTargetNumbers = useMemo(() => Object.fromEntries(
    (Object.keys(targetInputs) as BudgetPlanBucket[]).map((bucket) => [
      bucket,
      parseMoneyInput(targetInputs[bucket]) ?? 0,
    ]),
  ) as Record<BudgetPlanBucket, number>, [targetInputs]);

  const markBudgetPlanDirty = () => {
    setBudgetPlanDirty(true);
    setBudgetPlanSaved(false);
  };

  const onSalaryInputChange = (value: string) => {
    setSalaryInput(value);
    const nextSalary = parseSalaryInput(value);
    if (nextSalary) {
      setTargetInputs((current) => Object.fromEntries(
        (Object.keys(current) as BudgetPlanBucket[]).map((bucket) => {
          const pct = parseMoneyInput(targetPercentInputs[bucket]) ?? 0;
          return [bucket, displayNumber(nextSalary * pct / 100)];
        }),
      ) as BudgetPlanTargets);
    }
    markBudgetPlanDirty();
  };

  const updateTargetAmount = (bucket: BudgetPlanBucket, value: string) => {
    setTargetInputs((current) => ({ ...current, [bucket]: value }));
    const amount = parseMoneyInput(value);
    if (amount !== null && salaryOverride) {
      setTargetPercentInputs((current) => ({
        ...current,
        [bucket]: displayNumber(amount / salaryOverride * 100),
      }));
    }
    markBudgetPlanDirty();
  };

  const updateTargetPercentage = (bucket: BudgetPlanBucket, value: string) => {
    setTargetPercentInputs((current) => ({ ...current, [bucket]: value }));
    const pct = parseMoneyInput(value);
    setTargetInputs((current) => ({
      ...current,
      [bucket]: pct !== null && salaryOverride ? displayNumber(salaryOverride * pct / 100) : current[bucket],
    }));
    markBudgetPlanDirty();
  };

  const resetTargetsToPercentages = () => {
    const salary = salaryOverride ?? Number(DEFAULT_MONTHLY_SALARY);
    setSalaryInput((current) => current || DEFAULT_MONTHLY_SALARY);
    setTargetInputs({
      needs: displayNumber(salary * 0.5),
      wants: displayNumber(salary * 0.2),
      savings: displayNumber(salary * 0.15),
      investments: displayNumber(salary * 0.15),
    });
    setTargetPercentInputs({
      needs: "50",
      wants: "20",
      savings: "15",
      investments: "15",
    });
    markBudgetPlanDirty();
  };

  const saveBudgetPlan = () => {
    window.localStorage.setItem(BUDGET_PLAN_STORAGE_KEY, JSON.stringify({
      salary: salaryInput,
      targets: targetInputs,
    }));
    setBudgetPlanDirty(false);
    setBudgetPlanSaved(true);
  };

  const load = useCallback(() => {
    const periodParams = { startDate, endDate };

    setPlanVsActual((s) => ({ ...s, loading: true, error: false }));
    overviewApi
      .planVsActual(periodParams)
      .then((data) => setPlanVsActual({ data, loading: false, error: false }))
      .catch(() => setPlanVsActual({ data: null, loading: false, error: true }));

    setInsights((s) => ({ ...s, loading: true, error: false }));
    overviewApi
      .insights(periodParams)
      .then((data) => setInsights({ data, loading: false, error: false }))
      .catch(() => setInsights({ data: null, loading: false, error: true }));

    setMonthlyFlow((s) => ({ ...s, loading: true, error: false }));
    overviewApi
      .monthlyFlow(periodParams)
      .then((data) => setMonthlyFlow({ data, loading: false, error: false }))
      .catch(() => setMonthlyFlow({ data: null, loading: false, error: true }));

    setNextMonthPlan((s) => ({ ...s, loading: true, error: false }));
    overviewApi
      .nextMonthPlan(periodParams)
      .then((data) => setNextMonthPlan({ data, loading: false, error: false }))
      .catch(() => setNextMonthPlan({ data: null, loading: false, error: true }));

    setBankingSnapshot((s) => ({ ...s, loading: true, error: false }));
    bankingApi
      .banking(12, periodParams)
      .then((data) => setBankingSnapshot({ data, loading: false, error: false }))
      .catch(() => setBankingSnapshot({ data: null, loading: false, error: true }));

    setInvestmentSnapshot((s) => ({ ...s, loading: true, error: false }));
    investmentsApi
      .investments(periodParams)
      .then((data) => setInvestmentSnapshot({ data, loading: false, error: false }))
      .catch(() => setInvestmentSnapshot({ data: null, loading: false, error: true }));
  }, [startDate, endDate]);

  useEffect(() => {
    load();
  }, [load]);

  const loadDocStats = useCallback(() => {
    setDocsLoading(true);
    setDocsError(false);
    documentsApi
      .stats()
      .then((data) => {
        setDocStats(data);
        setDocsError(false);
      })
      .catch(() => {
        setDocStats(null);
        setDocsError(true);
      })
      .finally(() => setDocsLoading(false));
  }, []);

  useEffect(() => {
    loadDocStats();
  }, [loadDocStats]);

  const anyLoading =
    planVsActual.loading || insights.loading || monthlyFlow.loading || nextMonthPlan.loading ||
    bankingSnapshot.loading || investmentSnapshot.loading;

  // A total backend outage (every request failed) gets one clear full-page
  // error rather than a dashboard shell full of individually-broken
  // sections — .claude/rules/frontend.md requires a real error state, and
  // stacking small inline ones would bury the actual problem.
  const isTotalOutage =
    !anyLoading &&
    !docsLoading &&
    planVsActual.error &&
    insights.error &&
    monthlyFlow.error &&
    nextMonthPlan.error &&
    bankingSnapshot.error &&
    investmentSnapshot.error &&
    docsError;

  const bankingAccountDataset = useMemo(
    () => buildAccountValueDataset(bankingSnapshot.data?.account_value_history ?? []),
    [bankingSnapshot.data?.account_value_history],
  );
  const investmentAccountDataset = useMemo(
    () => buildAccountValueDataset((investmentSnapshot.data?.balance_history ?? []).map((point) => ({
      account_id: `${point.institution_type}:${point.account_name}`,
      account_name: point.account_name,
      institution: point.institution_type.replace(/_/g, " "),
      institution_type: point.institution_type,
      account_type: "investment",
      domain: "investments" as const,
      snapshot_date: point.date,
      value: point.total_value,
      currency: "USD",
      source_type: "balance_snapshot",
      latest_statement_month: point.date.slice(0, 7),
      status: "complete",
    }))),
    [investmentSnapshot.data?.balance_history],
  );

  if (isTotalOutage) {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow="Overview" title="How am I doing?" />
        <ErrorState
          message="Coral couldn't reach the backend to load your financial overview. Make sure the Coral backend is running, then try again."
          onRetry={() => {
            load();
            loadDocStats();
          }}
        />
      </div>
    );
  }

  // First-time state: zero documents ever uploaded, CONFIRMED by a
  // successful fetch (distinct from "the documents request failed" above,
  // and distinct from "zero activity in the selected period" — see this
  // PR's final report for the product ambiguity noted around that second
  // distinction). A brand-new install gets one focused welcome message
  // instead of four separate empty sections all saying "no data". Never
  // triggered by a failed request — `docsError` must be false and
  // `docStats` must be a real, successfully-fetched zero.
  const isFirstTime = !docsLoading && !docsError && docStats !== null && docStats.total === 0;

  if (isFirstTime) {
    return (
      <div className="space-y-8">
        <PageHeader
          eyebrow="Overview"
          title="Welcome to Coral"
          subtitle="Upload your first statement and Coral will show you exactly how this period is going against your plan — income vs. spending, plan vs. actual, and a few ranked insights."
        />
        <EmptyState
          icon={<Sparkles size={28} />}
          title="No statements yet"
          description="Once you upload a bank or investment statement, Coral will show Income vs Spent vs Saved, Plan vs Actual, and personalized insights right here."
          action={
            <button
              type="button"
              onClick={openUploadModal}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-2xl text-white font-semibold btn-coral transition-all"
            >
              <Upload size={16} /> Upload your first statement
            </button>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <PageHeader
        eyebrow="Overview"
        title="How am I doing?"
        subtitle="A quick, honest read on this period's income, spending, and progress toward your plan."
        action={
          <FinancialPeriodSelector
            selection={selection}
            resolved={resolved}
            onChange={setSelection}
            onPrevMonth={goToPreviousMonth}
            onNextMonth={goToNextMonth}
            loading={anyLoading}
          />
        }
      />

      <section className="grid items-center gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="grid gap-4 md:grid-cols-2">
          <Surface padding="md" className="bg-white/88">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="micro-text font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>
                  Banking overview
                </p>
                <h2 className="mt-2 card-title-lg" style={{ color: "var(--text-primary)" }}>Cash accounts</h2>
                <p className="mt-2 text-3xl font-black tabular-nums" style={{ color: "var(--text-primary)" }}>
                  {bankingSnapshot.loading ? "Loading" : formatCurrency(bankingAccountDataset.totalLatestValue)}
                </p>
                {bankingAccountDataset.totalChange !== null && (
                  <p
                    className="mt-1 small-text font-bold tabular-nums"
                    style={{ color: bankingAccountDataset.totalChange >= 0 ? "var(--status-good)" : "var(--status-danger)" }}
                  >
                    {bankingAccountDataset.totalChange >= 0 ? "+" : "-"}
                    {formatCurrency(Math.abs(bankingAccountDataset.totalChange))} vs prior snapshot
                  </p>
                )}
              </div>
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
                <Landmark size={20} />
              </span>
            </div>
            <Link href="/banking" className="mt-5 inline-flex items-center gap-2 small-text font-bold text-blue-600">
              Open banking details <ArrowRight size={14} />
            </Link>
          </Surface>

          <Surface padding="md" className="bg-white/88">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="micro-text font-bold uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>
                  Investments overview
                </p>
                <h2 className="mt-2 card-title-lg" style={{ color: "var(--text-primary)" }}>Portfolio snapshot</h2>
                <p className="mt-2 text-3xl font-black tabular-nums" style={{ color: "var(--text-primary)" }}>
                  {investmentSnapshot.loading ? "Loading" : formatCurrency(investmentAccountDataset.totalLatestValue)}
                </p>
                {investmentAccountDataset.totalChange !== null && (
                  <p
                    className="mt-1 small-text font-bold tabular-nums"
                    style={{ color: investmentAccountDataset.totalChange >= 0 ? "var(--status-good)" : "var(--status-danger)" }}
                  >
                    {investmentAccountDataset.totalChange >= 0 ? "+" : "-"}
                    {formatCurrency(Math.abs(investmentAccountDataset.totalChange))} vs prior snapshot
                  </p>
                )}
              </div>
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-violet-50 text-violet-600">
                <TrendingUp size={20} />
              </span>
            </div>
            <Link href="/investments" className="mt-5 inline-flex items-center gap-2 small-text font-bold text-violet-600">
              Open investment details <ArrowRight size={14} />
            </Link>
          </Surface>
        </div>

        <div className="hidden justify-center lg:flex">
          <CoralMascot
            variant="main"
            size="xl"
            priority
            speech="I’ll keep the high-level picture here."
            className="drop-shadow-[0_24px_50px_rgba(17,80,120,0.20)]"
          />
        </div>
      </section>

      {/* 1. Financial status header */}
      {insights.loading ? (
        <SkeletonState variant="card" height="112px" />
      ) : insights.error ? (
        <ErrorState compact message="Couldn't load your financial status for this period." onRetry={load} />
      ) : insights.data ? (
        <CoralAdvisorCard
          headline={insights.data.status.headline}
          body={insights.data.status.body}
          tone={insights.data.status.tone}
        />
      ) : null}

      {/* 3. Income vs Spent vs Saved/Invested */}
      <section>
        <SectionHeader eyebrow="This period" title="Income vs Spent vs Saved/Invested" size="sm" className="mb-5" />
        <Surface padding="md">
          <IncomeSpentSavedChart
            rows={monthlyFlow.data}
            loading={monthlyFlow.loading}
            error={monthlyFlow.error}
            onRetry={load}
          />
        </Surface>
      </section>

      {/* 4. Plan vs Actual */}
      <section>
        <SectionHeader
          eyebrow="Drift"
          title="Plan vs Actual"
          description="Set monthly take-home pay and bucket targets. Coral multiplies them by the selected period before comparing against actual transactions."
          size="sm"
          className="mb-5"
          action={
            <div className="flex flex-wrap items-end gap-3">
              <label className="block min-w-[230px]">
                <span className="micro-text font-bold uppercase tracking-[0.14em]" style={{ color: "var(--text-muted)" }}>
                  Monthly salary
                </span>
                <div className="mt-1 flex items-center rounded-2xl bg-white/90 px-3 py-2 ring-1 ring-slate-200/90 focus-within:ring-2 focus-within:ring-coral-orange/45">
                  <span className="small-text font-bold" style={{ color: "var(--text-muted)" }}>$</span>
                  <input
                    aria-label="Expected monthly take-home salary"
                    inputMode="decimal"
                    value={salaryInput}
                    onChange={(event) => onSalaryInputChange(event.target.value)}
                    placeholder="12,000"
                    className="min-w-0 flex-1 bg-transparent px-2 text-sm font-bold tabular-nums outline-none"
                    style={{ color: "var(--text-primary)" }}
                  />
                </div>
              </label>
              <button
                type="button"
                onClick={saveBudgetPlan}
                className="rounded-2xl px-4 py-2.5 text-sm font-black text-white shadow-[0_10px_24px_rgba(255,122,90,0.24)] transition-transform active:scale-[0.98]"
                style={{ background: "var(--coral-primary)" }}
              >
                Save targets
              </button>
            </div>
          }
        />
        <Surface padding="md">
          <div className="mb-5 rounded-2xl bg-slate-50/80 p-4 ring-1 ring-slate-200/80">
            <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="text-sm font-black" style={{ color: "var(--text-primary)" }}>
                  Monthly target plan
                </p>
                <p className="mt-1 micro-text" style={{ color: "var(--text-muted)" }}>
                  {periodMonths} month{periodMonths === 1 ? "" : "s"} selected. Target amounts below are monthly; period targets are calculated automatically.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={resetTargetsToPercentages}
                  className="rounded-xl bg-white px-3 py-2 text-xs font-black ring-1 ring-slate-200 transition-transform active:scale-[0.98]"
                  style={{ color: "var(--text-secondary)" }}
                >
                  Reset 50/20/15/15
                </button>
                <span
                  className="rounded-full px-3 py-1 text-xs font-black"
                  style={{
                    background: budgetPlanSaved
                      ? "var(--status-good-soft)"
                      : budgetPlanDirty
                        ? "var(--status-warning-soft)"
                        : "var(--border-subtle)",
                    color: budgetPlanSaved
                      ? "var(--status-good)"
                      : budgetPlanDirty
                        ? "var(--status-warning)"
                        : "var(--text-muted)",
                  }}
                >
                  {budgetPlanSaved ? "Saved locally" : budgetPlanDirty ? "Unsaved changes" : "Using saved/default targets"}
                </span>
              </div>
            </div>
            <div className="grid gap-3 lg:grid-cols-4">
              {(Object.keys(targetInputs) as BudgetPlanBucket[]).map((bucket) => {
                const amount = monthlyTargetNumbers[bucket];
                return (
                  <div key={bucket} className="rounded-2xl bg-white/86 p-3 ring-1 ring-slate-200/80">
                    <p className="text-sm font-black" style={{ color: `var(--financial-${bucket})` }}>
                      {PLAN_BUCKET_LABELS[bucket]}
                    </p>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <label>
                        <span className="micro-text" style={{ color: "var(--text-muted)" }}>%</span>
                        <input
                          aria-label={`${PLAN_BUCKET_LABELS[bucket]} target percentage`}
                          inputMode="decimal"
                          value={targetPercentInputs[bucket]}
                          onChange={(event) => updateTargetPercentage(bucket, event.target.value)}
                          className="mt-1 w-full rounded-xl bg-slate-50 px-3 py-2 text-sm font-bold tabular-nums outline-none ring-1 ring-slate-200 focus:ring-2 focus:ring-coral-orange/45"
                          style={{ color: "var(--text-primary)" }}
                        />
                      </label>
                      <label>
                        <span className="micro-text" style={{ color: "var(--text-muted)" }}>Monthly $</span>
                        <input
                          aria-label={`${PLAN_BUCKET_LABELS[bucket]} monthly target amount`}
                          inputMode="decimal"
                          value={targetInputs[bucket]}
                          onChange={(event) => updateTargetAmount(bucket, event.target.value)}
                          className="mt-1 w-full rounded-xl bg-slate-50 px-3 py-2 text-sm font-bold tabular-nums outline-none ring-1 ring-slate-200 focus:ring-2 focus:ring-coral-orange/45"
                          style={{ color: "var(--text-primary)" }}
                        />
                      </label>
                    </div>
                    <p className="mt-2 micro-text tabular-nums" style={{ color: "var(--text-dim)" }}>
                      Period target {formatCurrency(amount * periodMonths)}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
          <PlanVsActualSection
            result={planVsActual.data}
            loading={planVsActual.loading}
            error={planVsActual.error}
            onRetry={load}
            monthlyIncome={salaryOverride}
            monthlyTargets={monthlyTargetNumbers}
            periodMonths={periodMonths}
          />
        </Surface>
      </section>

      {/* 5 + 6: Coral Insights and Next Month Plan */}
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-8">
        <section className="xl:col-span-3">
          <SectionHeader eyebrow="Ranked by impact" title="Coral Insights" size="sm" className="mb-5" />
          <CoralInsightsSection
            insights={insights.data?.insights ?? null}
            loading={insights.loading}
            error={insights.error}
            onRetry={load}
          />
        </section>
        <section className="xl:col-span-2">
          <SectionHeader eyebrow="Ranked by impact" title="Next Month Plan" size="sm" className="mb-5" />
          <NextMonthPlanSection
            recommendations={nextMonthPlan.data?.recommendations ?? null}
            loading={nextMonthPlan.loading}
            error={nextMonthPlan.error}
            onRetry={load}
            showSourceFacts
          />
        </section>
      </div>

      <Surface padding="md" as="section" className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span
            className="w-10 h-10 rounded-2xl flex items-center justify-center shrink-0"
            style={{ background: "var(--coral-primary-soft)", color: "var(--coral-primary)" }}
          >
            <FileCheck2 size={17} />
          </span>
          <div>
            <h2 className="coral-card-title">Monthly Financial Close</h2>
            <p className="small-text mt-1" style={{ color: "var(--text-secondary)" }}>
              Review a completed month across income, plan drift, drivers, goals, and next actions.
            </p>
          </div>
        </div>
        <Link
          href={`/monthly-close?period=custom&start=${startDate}&end=${endDate}`}
          className="btn-coral inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl small-text font-semibold text-white"
        >
          Open close
        </Link>
      </Surface>

      {/* Demoted document/upload strip — see DocumentsStrip docstring. */}
      <DocumentsStrip stats={docStats} loading={docsLoading} error={docsError} onRetry={loadDocStats} />
    </div>
  );
}
