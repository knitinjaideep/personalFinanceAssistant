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

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { FileCheck2, Sparkles, Upload } from "lucide-react";
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
import { documentsApi } from "@/features/documents/api";
import {
  overviewApi,
  type MonthlyFlowSummary,
  type NextMonthPlanResult,
  type OverviewInsightsResult,
  type PlanVsActualResult,
} from "@/features/overview/api";
import { useAppStore } from "@/store/appStore";
import { useFinancialPeriod } from "@/hooks/useFinancialPeriod";
import type { DocumentStats } from "@/types/index";

interface LoadState<T> {
  data: T | null;
  loading: boolean;
  error: boolean;
}

const INITIAL_LOAD_STATE = { data: null, loading: true, error: false };

export default function HomePageClient() {
  const openUploadModal = useAppStore((s) => s.openUploadModal);
  const { selection, resolved, setSelection, goToPreviousMonth, goToNextMonth } = useFinancialPeriod();

  const [planVsActual, setPlanVsActual] = useState<LoadState<PlanVsActualResult>>(INITIAL_LOAD_STATE);
  const [insights, setInsights] = useState<LoadState<OverviewInsightsResult>>(INITIAL_LOAD_STATE);
  const [monthlyFlow, setMonthlyFlow] = useState<LoadState<MonthlyFlowSummary[]>>(INITIAL_LOAD_STATE);
  const [nextMonthPlan, setNextMonthPlan] = useState<LoadState<NextMonthPlanResult>>(INITIAL_LOAD_STATE);

  const [docStats, setDocStats] = useState<DocumentStats | null>(null);
  const [docsLoading, setDocsLoading] = useState(true);
  const [docsError, setDocsError] = useState(false);

  const { startDate, endDate } = resolved;

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
    planVsActual.loading || insights.loading || monthlyFlow.loading || nextMonthPlan.loading;

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
    docsError;

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
        <SectionHeader eyebrow="Drift" title="Plan vs Actual" size="sm" className="mb-5" />
        <Surface padding="md">
          <PlanVsActualSection
            result={planVsActual.data}
            loading={planVsActual.loading}
            error={planVsActual.error}
            onRetry={load}
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
