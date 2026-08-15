"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  AlertTriangle,
  ArrowRight,
  BarChart2,
  CheckCircle2,
  CircleDollarSign,
  Info,
  Landmark,
  PieChart,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Upload,
} from "lucide-react";
import { motion } from "framer-motion";
import EmptyState from "@/components/coral/EmptyState";
import ErrorState from "@/components/coral/ErrorState";
import GlassCard from "@/components/coral/GlassCard";
import SectionHeader from "@/components/coral/SectionHeader";
import FinancialPeriodSelector from "@/components/coral-ds/FinancialPeriodSelector";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import StatusBadge, { type StatusTone } from "@/components/coral-ds/StatusBadge";
import Surface from "@/components/coral-ds/Surface";
import TargetProgressBar from "@/components/coral-ds/TargetProgressBar";
import NextMonthPlanSection from "@/components/overview/NextMonthPlanSection";
import {
  investmentsApi,
  type AccountBalance,
  type Holding,
  type InvestmentContributionPlanResult,
  type InvestmentContributionVehicle,
  type InvestmentsDashboard,
} from "@/features/investments/api";
import { overviewApi, type NextMonthPlanResult } from "@/features/overview/api";
import { useFinancialPeriod } from "@/hooks/useFinancialPeriod";
import { formatCompactCurrency, formatCurrency } from "@/lib/utils";
import { useAppStore } from "@/store/appStore";

const INSIGHT_PROMPTS = [
  "Am I investing according to plan?",
  "Which contribution should I adjust next month?",
  "Review my portfolio concentration.",
  "Compare my IRA balances over time.",
];

interface LoadState<T> {
  data: T | null;
  loading: boolean;
  error: boolean;
}

const INITIAL_LOAD_STATE = { data: null, loading: true, error: false };

function num(value: string | null | undefined): number {
  return value === null || value === undefined ? 0 : Number(value);
}

function statusTone(status: InvestmentContributionVehicle["status"]): StatusTone {
  if (status === "on_track") return "good";
  if (status === "watch") return "warning";
  if (status === "off_track") return "danger";
  return "neutral";
}

function statusLabel(status: InvestmentContributionVehicle["status"]) {
  if (status === "on_track") return "On track";
  if (status === "watch") return "Watch";
  if (status === "off_track") return "Behind";
  return "No data";
}

function vehicleLabel(vehicle: string) {
  return vehicle === "Taxable Brokerage" ? "Brokerage" : vehicle;
}

function gapLabel(vehicle: InvestmentContributionVehicle) {
  if (vehicle.variance_amount === null) return "Gap unavailable";
  const variance = Number(vehicle.variance_amount);
  if (variance < 0) return `Behind by ${formatCurrency(Math.abs(variance))}`;
  if (variance > 0) return `Ahead by ${formatCurrency(variance)}`;
  return "No gap";
}

function pctLabel(value: string | null | undefined) {
  return value === null || value === undefined
    ? "-"
    : `${Number(value).toFixed(1).replace(".0", "")}%`;
}

function ContributionHero({
  plan,
  loading,
  error,
  onRetry,
}: {
  plan: InvestmentContributionPlanResult | null;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}) {
  if (loading) return <SkeletonState variant="card" height="360px" />;
  if (error) {
    return (
      <ErrorState
        message="Couldn't load investment contribution plan for this period."
        onRetry={onRetry}
      />
    );
  }
  if (!plan) return null;

  const targetPct = plan.total_target_pct ?? "15";
  const actualPct = plan.total_actual_pct;
  const hasContributionRate = actualPct !== null;
  const totalGap = plan.vehicles.reduce((sum, vehicle) => {
    const variance = vehicle.variance_amount === null ? 0 : Number(vehicle.variance_amount);
    return variance < 0 ? sum + Math.abs(variance) : sum;
  }, 0);
  const headline = !hasContributionRate
    ? "Contribution rate unavailable"
    : totalGap > 0
      ? "You're behind plan this period"
      : "You're investing according to plan";
  const summaryStatus = !hasContributionRate
    ? "Data unavailable"
    : totalGap > 0
      ? `Behind by ${formatCurrency(totalGap)}`
      : "On track";
  const summaryColor = !hasContributionRate
    ? "var(--status-neutral)"
    : totalGap > 0
      ? "var(--status-danger)"
      : "var(--status-good)";

  return (
    <section className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_380px] gap-6 items-stretch">
      <Surface padding="lg" className="relative overflow-hidden min-h-[360px]">
        <Image
          src="/mascots/coral-investments.png"
          alt=""
          width={112}
          height={112}
          className="absolute right-5 top-5 z-0 h-28 w-28 object-contain opacity-10 pointer-events-none"
        />
        <div className="relative z-10">
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
            <div>
              <p className="micro-text font-bold uppercase tracking-[0.18em] text-financial-investments">
                Investments
              </p>
              <h1
                className="mt-2 text-4xl md:text-5xl font-bold"
                style={{ color: "var(--heading-primary)" }}
              >
                Investments
              </h1>
              <p className="mt-3 max-w-xl text-base" style={{ color: "var(--text-secondary)" }}>
                Track your contributions and stay on plan for your long-term goals.
              </p>
            </div>

            <div
              className="rounded-2xl px-6 py-4 min-w-[220px]"
              style={{
                background: "var(--financial-investments-soft)",
                border: "1px solid rgba(156,141,255,0.28)",
              }}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>
                  Investments
                </span>
                <span className="micro-text" style={{ color: "var(--text-muted)" }}>
                  Target {pctLabel(targetPct)}
                </span>
              </div>
              <p className="mt-2 text-3xl font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>
                {pctLabel(actualPct)}
              </p>
              <p
                className="micro-text mt-1 font-semibold"
                style={{ color: summaryColor }}
              >
                {summaryStatus}
              </p>
            </div>
          </div>

          <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            {plan.vehicles.slice(0, 4).map((vehicle) => (
              <Surface key={vehicle.vehicle} padding="sm" className="relative">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="small-text font-bold" style={{ color: "var(--text-primary)" }}>
                      {vehicleLabel(vehicle.vehicle)}
                    </p>
                    <p className="micro-text mt-0.5" style={{ color: "var(--text-muted)" }}>
                      Target {pctLabel(vehicle.target_pct)}
                    </p>
                  </div>
                  <StatusBadge status={statusTone(vehicle.status)}>
                    {statusLabel(vehicle.status)}
                  </StatusBadge>
                </div>
                <p className="mt-4 text-2xl font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>
                  {pctLabel(vehicle.actual_pct)}
                </p>
                <p className="micro-text mt-1" style={{ color: "var(--text-muted)" }}>
                  {gapLabel(vehicle)}
                </p>
              </Surface>
            ))}
          </div>
        </div>
      </Surface>

      <Surface padding="lg" className="flex flex-col justify-center">
        <span
          className="w-12 h-12 rounded-2xl flex items-center justify-center"
          style={{ background: "var(--financial-investments-soft)", color: "var(--financial-investments)" }}
        >
          {!hasContributionRate
            ? <Info size={20} />
            : totalGap > 0
              ? <AlertTriangle size={20} />
              : <CheckCircle2 size={20} />}
        </span>
        <h2 className="mt-5 card-title-lg" style={{ color: "var(--text-primary)" }}>
          {headline}
        </h2>
        <p className="mt-3 small-text" style={{ color: "var(--text-muted)" }}>
          {!hasContributionRate
            ? "Coral needs observed income before it can calculate contribution percentages."
            : totalGap > 0
              ? `You need ${formatCurrency(totalGap)} more to match this period's vehicle targets.`
              : "Your current contribution mix meets the target allocation for this period."}
        </p>
        {plan.completeness.notes.length > 0 && (
          <p className="mt-4 micro-text" style={{ color: "var(--text-dim)" }}>
            {plan.completeness.notes[0]}
          </p>
        )}
        <Link
          href="/chat"
          className="mt-6 inline-flex items-center gap-2 small-text font-semibold"
          style={{ color: "var(--financial-investments)" }}
        >
          See recommended next steps <ArrowRight size={14} />
        </Link>
      </Surface>
    </section>
  );
}

function ContributionBars({
  plan,
  loading,
  error,
}: {
  plan: InvestmentContributionPlanResult | null;
  loading: boolean;
  error: boolean;
}) {
  if (loading) return <SkeletonState variant="card" height="280px" />;
  if (error) return <ErrorState compact message="Couldn't load contribution bars." />;
  if (!plan) return null;

  return (
    <Surface padding="md" as="section">
      <div className="flex items-center gap-2 mb-5">
        <h2 className="card-title-lg" style={{ color: "var(--text-primary)" }}>
          Plan vs Actual Contributions
        </h2>
        <Info size={14} style={{ color: "var(--text-muted)" }} />
      </div>
      <div className="space-y-5">
        {plan.vehicles.map((vehicle) => (
          <div
            key={vehicle.vehicle}
            className="grid grid-cols-[120px_minmax(0,1fr)_76px] gap-4 items-center"
          >
            <div>
              <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>
                {vehicleLabel(vehicle.vehicle)}
              </p>
              <p className="micro-text" style={{ color: "var(--text-muted)" }}>
                {formatCurrency(Number(vehicle.actual_amount))}
              </p>
            </div>
            <TargetProgressBar
              label=""
              actual={num(vehicle.actual_pct)}
              target={num(vehicle.target_pct)}
              bucket="investments"
            />
            <div className="text-right">
              <p className="small-text font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>
                {pctLabel(vehicle.actual_pct)}
              </p>
              <p className="micro-text tabular-nums" style={{ color: "var(--text-muted)" }}>
                {pctLabel(vehicle.target_pct)}
              </p>
            </div>
          </div>
        ))}
        <div
          className="pt-4 flex items-center justify-between"
          style={{ borderTop: "1px solid var(--border-subtle)" }}
        >
          <span className="small-text font-bold" style={{ color: "var(--financial-investments)" }}>
            Total Investments
          </span>
          <span className="small-text font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>
            {pctLabel(plan.total_actual_pct)} / {pctLabel(plan.total_target_pct)}
          </span>
        </div>
      </div>
    </Surface>
  );
}

function NextMonthContributionPlan({
  plan,
  loading,
  error,
}: {
  plan: InvestmentContributionPlanResult | null;
  loading: boolean;
  error: boolean;
}) {
  if (loading) return <SkeletonState variant="card" height="280px" />;
  if (error) return <ErrorState compact message="Couldn't load contribution recommendations." />;
  if (!plan) return null;

  return (
    <Surface padding="md" as="section">
      <div className="flex items-center gap-2 mb-5">
        <h2 className="card-title-lg" style={{ color: "var(--text-primary)" }}>
          Next Month Contribution Plan
        </h2>
        <Info size={14} style={{ color: "var(--text-muted)" }} />
      </div>
      <div className="space-y-2">
        {plan.vehicles.map((vehicle) => {
          const hasRecommendation = vehicle.recommended_next_month_delta !== null;
          const delta = hasRecommendation ? Number(vehicle.recommended_next_month_delta) : 0;
          const needsIncrease = hasRecommendation && delta > 0;
          return (
            <div
              key={vehicle.vehicle}
              className="flex items-center gap-3 py-3"
              style={{ borderBottom: "1px solid var(--border-subtle)" }}
            >
              <span
                className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
                style={{ background: "var(--financial-investments-soft)", color: "var(--financial-investments)" }}
              >
                <CircleDollarSign size={15} />
              </span>
              <div className="flex-1 min-w-0">
                <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>
                  {vehicleLabel(vehicle.vehicle)}
                </p>
                <p className="micro-text" style={{ color: "var(--text-muted)" }}>
                  {!hasRecommendation
                    ? "Contribution data unavailable"
                    : needsIncrease
                    ? `To reach ${pctLabel(vehicle.target_pct)} of gross pay`
                    : "You're on track"}
                </p>
              </div>
              <div className="text-right shrink-0">
                <p className="small-text font-bold" style={{ color: "var(--text-primary)" }}>
                  {!hasRecommendation
                    ? "Data unavailable"
                    : needsIncrease
                    ? `Add ${formatCurrency(delta)} more`
                    : `Keep at ${pctLabel(vehicle.target_pct)}`}
                </p>
                <StatusBadge status={!hasRecommendation ? "neutral" : needsIncrease ? "danger" : statusTone(vehicle.status)}>
                  {!hasRecommendation ? "No data" : needsIncrease ? "Increase" : statusLabel(vehicle.status)}
                </StatusBadge>
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-5 flex flex-wrap gap-3">
        <Link
          href="/chat"
          className="btn-coral inline-flex items-center gap-2 px-4 py-2 rounded-xl small-text font-semibold text-white"
        >
          View plan <ArrowRight size={14} />
        </Link>
        <Link
          href="/chat"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl small-text font-semibold"
          style={{
            background: "var(--glass-light-bg)",
            border: "1px solid var(--border-subtle)",
            color: "var(--text-secondary)",
          }}
        >
          Adjust target
        </Link>
      </div>
    </Surface>
  );
}

function InvestmentInsights({
  plan,
  loading,
  error,
}: {
  plan: InvestmentContributionPlanResult | null;
  loading: boolean;
  error: boolean;
}) {
  if (loading) return <SkeletonState variant="card" height="190px" />;
  if (error) return <ErrorState compact message="Couldn't load investment insights." />;
  if (!plan) return null;

  const insights = plan.vehicles
    .filter((vehicle) => vehicle.variance_amount !== null)
    .sort((a, b) => Number(a.variance_amount) - Number(b.variance_amount))
    .slice(0, 3);

  if (insights.length === 0) {
    return (
      <EmptyState
        compact
        icon={<Sparkles size={22} />}
        title="No investment insights yet"
        description="Once Coral has observed income and contribution data, investment insights will appear here."
      />
    );
  }

  return (
    <section>
      <SectionHeader eyebrow="Insights" title="Coral Investment Insights" size="sm" className="mb-5" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {insights.map((vehicle) => {
          const variance = Number(vehicle.variance_amount);
          const behind = variance < 0;
          return (
            <Surface key={vehicle.vehicle} padding="md">
              <span
                className="w-10 h-10 rounded-2xl flex items-center justify-center"
                style={{
                  background: behind ? "var(--status-danger-soft)" : "var(--status-good-soft)",
                  color: behind ? "var(--status-danger)" : "var(--status-good)",
                }}
              >
                {behind ? <TrendingDown size={16} /> : <CheckCircle2 size={16} />}
              </span>
              <h3 className="mt-4 small-text font-bold" style={{ color: "var(--text-primary)" }}>
                {behind
                  ? `${vehicleLabel(vehicle.vehicle)} behind target`
                  : `${vehicleLabel(vehicle.vehicle)} on track`}
              </h3>
              <p className="mt-2 micro-text" style={{ color: "var(--text-muted)" }}>
                {behind
                  ? `You're contributing ${pctLabel(vehicle.actual_pct)} against a ${pctLabel(vehicle.target_pct)} target.`
                  : `You're meeting the ${pctLabel(vehicle.target_pct)} contribution target.`}
              </p>
              <Link
                href="/chat"
                className="mt-5 inline-flex items-center gap-2 micro-text font-semibold"
                style={{ color: behind ? "var(--status-danger)" : "var(--status-good)" }}
              >
                {behind ? "Review contribution" : "Review election"} <ArrowRight size={12} />
              </Link>
            </Surface>
          );
        })}
      </div>
    </section>
  );
}

function buildHealthRows(data: InvestmentsDashboard | null) {
  if (!data) return [];
  const allocation = data.allocation ?? [];
  const topHolding = data.top_holdings.find((holding) => holding.portfolio_weight !== null);
  const cashTotal = data.portfolio_summary.accounts.reduce((sum, account) => (
    sum + (account.cash_value ?? 0)
  ), 0);
  const rows = [];

  if (allocation.length > 0) {
    rows.push({
      title: allocation.length >= 3 ? "Good diversification" : "Account concentration",
      body: allocation.length >= 3
        ? "Your imported accounts are spread across several investment accounts."
        : "Most imported investment value is concentrated in a small number of accounts.",
      tone: allocation.length >= 3 ? "good" as const : "warning" as const,
    });
  }

  if (topHolding?.portfolio_weight !== null && topHolding?.portfolio_weight !== undefined) {
    const high = topHolding.portfolio_weight >= 25;
    rows.push({
      title: high ? "Asset concentration" : "Largest holding within range",
      body: `${topHolding.symbol || topHolding.description} is ${topHolding.portfolio_weight.toFixed(1)}% of imported holdings.`,
      tone: high ? "warning" as const : "good" as const,
    });
  }

  if (cashTotal > 0) {
    rows.push({
      title: "Cash waiting to invest",
      body: `${formatCurrency(cashTotal)} is currently reported as cash across investment accounts.`,
      tone: "neutral" as const,
    });
  }

  return rows.slice(0, 3);
}

function PortfolioHealth({ data }: { data: InvestmentsDashboard | null }) {
  const rows = buildHealthRows(data);
  if (rows.length === 0) return null;

  return (
    <Surface padding="md" as="section">
      <div className="flex items-center gap-2 mb-5">
        <h2 className="card-title-lg" style={{ color: "var(--text-primary)" }}>Portfolio Health</h2>
        <Info size={14} style={{ color: "var(--text-muted)" }} />
      </div>
      <div className="space-y-3">
        {rows.map((row) => (
          <div
            key={row.title}
            className="flex items-start gap-3 rounded-2xl p-4"
            style={{ background: `var(--status-${row.tone}-soft)` }}
          >
            <span
              className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
              style={{ background: "var(--card-bg)", color: `var(--status-${row.tone})` }}
            >
              {row.tone === "good" ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
            </span>
            <div className="min-w-0">
              <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>{row.title}</p>
              <p className="micro-text mt-1" style={{ color: "var(--text-muted)" }}>{row.body}</p>
            </div>
          </div>
        ))}
      </div>
    </Surface>
  );
}

function AccountAllocation({ data }: { data: InvestmentsDashboard | null }) {
  if (!data || data.allocation.length === 0) return null;
  const colors = ["#9C8DFF", "#5B9CFF", "#4FC79A", "#FFB85C", "#FF8266"];

  return (
    <Surface padding="md" as="section">
      <div className="flex items-center gap-2 mb-5">
        <h2 className="card-title-lg" style={{ color: "var(--text-primary)" }}>Account Allocation</h2>
        <Info size={14} style={{ color: "var(--text-muted)" }} />
      </div>
      <div className="space-y-4">
        {data.allocation.slice(0, 6).map((account, index) => (
          <div key={`${account.account_name}-${index}`}>
            <div className="flex items-center justify-between mb-1.5 gap-4">
              <p className="small-text font-semibold truncate" style={{ color: "var(--text-primary)" }}>
                {account.account_name}
              </p>
              <p className="small-text font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>
                {account.pct_of_portfolio.toFixed(1)}%
              </p>
            </div>
            <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--border-subtle)" }}>
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.max(0, Math.min(account.pct_of_portfolio, 100))}%`,
                  background: colors[index % colors.length],
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </Surface>
  );
}

function AccountCard({
  label,
  icon,
  data,
}: {
  label: string;
  icon: string;
  data?: AccountBalance | null;
}) {
  const hasData = !!data && !!data.total_value_fmt;
  const gainPositive = (data?.unrealized_gain_loss ?? 0) >= 0;

  return (
    <div
      className="flex items-center justify-between px-5 py-4 rounded-2xl transition-colors hover:bg-white/[0.02]"
      style={{ background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div
          className="w-10 h-10 rounded-2xl flex items-center justify-center shrink-0"
          style={{
            background: "var(--financial-investments-soft)",
            border: "1px solid rgba(156,141,255,0.20)",
            color: "var(--financial-investments)",
            fontSize: "0.65rem",
            fontWeight: 700,
          }}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <p className="small-text font-semibold truncate" style={{ color: "var(--text-primary)" }}>
            {label}
          </p>
          {data?.latest_statement_date && (
            <p className="micro-text mt-0.5" style={{ color: "var(--text-muted)" }}>
              {new Date(data.latest_statement_date).toLocaleDateString()}
            </p>
          )}
          {!hasData && (
            <p className="micro-text mt-0.5" style={{ color: "var(--text-dim)" }}>Waiting for data</p>
          )}
        </div>
      </div>

      {hasData ? (
        <div className="text-right shrink-0">
          <p className="small-text font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>
            {data!.total_value_fmt}
          </p>
          {data?.unrealized_gain_loss_fmt && (
            <p
              className="micro-text tabular-nums"
              style={{ color: gainPositive ? "#4CAF93" : "#E45757" }}
            >
              {gainPositive ? "↑" : "↓"} {data.unrealized_gain_loss_fmt}
            </p>
          )}
        </div>
      ) : (
        <span
          className="px-2.5 py-1 rounded-lg text-xs font-medium shrink-0"
          style={{ background: "var(--empty-bg)", color: "var(--text-dim)", border: "1px solid var(--empty-border)" }}
        >
          No data
        </span>
      )}
    </div>
  );
}

function HoldingRow({ holding, index, total }: { holding: Holding; index: number; total: number }) {
  return (
    <div
      className="flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-white/[0.02]"
      style={{ borderBottom: index < total - 1 ? "1px solid var(--border-subtle)" : "none" }}
    >
      <span className="w-6 text-center micro-text font-bold" style={{ color: "var(--text-dim)" }}>
        {index + 1}
      </span>
      <div className="flex-1 min-w-0">
        <p className="small-text font-semibold truncate" style={{ color: "var(--text-primary)" }}>
          {holding.symbol || holding.description.slice(0, 35)}
        </p>
        <p className="micro-text truncate" style={{ color: "var(--text-muted)" }}>{holding.account_name}</p>
      </div>
      <div className="text-right shrink-0">
        <p className="small-text font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>
          {holding.market_value_fmt}
        </p>
        <p
          className="micro-text tabular-nums"
          style={{ color: holding.unrealized_gain_loss >= 0 ? "#4CAF93" : "#E45757" }}
        >
          {holding.unrealized_gain_loss >= 0 ? "↑" : "↓"} {holding.unrealized_gain_loss_fmt}
        </p>
      </div>
    </div>
  );
}

export default function InvestmentsPageClient() {
  const [data, setData] = useState<InvestmentsDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contributionPlan, setContributionPlan] =
    useState<LoadState<InvestmentContributionPlanResult>>(INITIAL_LOAD_STATE);
  const [nextMonthPlan, setNextMonthPlan] = useState<LoadState<NextMonthPlanResult>>(INITIAL_LOAD_STATE);
  const openUploadModal = useAppStore((s) => s.openUploadModal);
  const { selection, resolved, setSelection, goToPreviousMonth, goToNextMonth } = useFinancialPeriod();

  const { startDate, endDate } = resolved;

  const loadDashboard = useCallback((isPeriodChange: boolean) => {
    if (isPeriodChange) setRefreshing(true); else setLoading(true);
    setError(null);
    investmentsApi
      .investments({ startDate, endDate })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => { setLoading(false); setRefreshing(false); });
  }, [startDate, endDate]);

  const loadContributionPlan = useCallback(() => {
    setContributionPlan((state) => ({ ...state, loading: true, error: false }));
    investmentsApi
      .contributionPlan({ startDate, endDate })
      .then((plan) => setContributionPlan({ data: plan, loading: false, error: false }))
      .catch(() => setContributionPlan({ data: null, loading: false, error: true }));
  }, [startDate, endDate]);

  const loadNextMonthPlan = useCallback(() => {
    setNextMonthPlan((state) => ({ ...state, loading: true, error: false }));
    overviewApi
      .nextMonthPlan({ startDate, endDate })
      .then((plan) => setNextMonthPlan({ data: plan, loading: false, error: false }))
      .catch(() => setNextMonthPlan({ data: null, loading: false, error: true }));
  }, [startDate, endDate]);

  useEffect(() => { loadDashboard(data !== null); }, [loadDashboard]);
  useEffect(() => { loadContributionPlan(); }, [loadContributionPlan]);
  useEffect(() => { loadNextMonthPlan(); }, [loadNextMonthPlan]);

  const retryAll = () => {
    loadDashboard(false);
    loadContributionPlan();
    loadNextMonthPlan();
  };

  const findAccount = useCallback((searchKeys: string[]) =>
    data?.portfolio_summary.accounts.find((account) => {
      const name = (account.account_name ?? "").toLowerCase();
      return searchKeys.some((key) => name.includes(key));
    }) ?? null, [data]);

  const hasAnyData = !!data && (
    data.portfolio_summary.accounts.length > 0 || data.top_holdings.length > 0
  );
  const portfolioRows = useMemo(() => buildHealthRows(data), [data]);
  const investmentPlanRecommendations = nextMonthPlan.data?.recommendations.filter((rec) => (
    rec.bucket === "investments" ||
    rec.action_type === "increase_investment_contribution" ||
    rec.action_type === "maintain_contribution"
  )) ?? null;

  return (
    <div className="space-y-8">
      <SectionHeader
        eyebrow="Investments"
        title="Am I investing according to plan?"
        description="Track contributions against your long-term investment targets."
        size="lg"
        action={
          <FinancialPeriodSelector
            selection={selection}
            resolved={resolved}
            onChange={setSelection}
            onPrevMonth={goToPreviousMonth}
            onNextMonth={goToNextMonth}
            loading={refreshing || contributionPlan.loading}
          />
        }
      />

      <ContributionHero
        plan={contributionPlan.data}
        loading={contributionPlan.loading}
        error={contributionPlan.error}
        onRetry={loadContributionPlan}
      />

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] gap-6">
        <ContributionBars
          plan={contributionPlan.data}
          loading={contributionPlan.loading}
          error={contributionPlan.error}
        />
        <NextMonthContributionPlan
          plan={contributionPlan.data}
          loading={contributionPlan.loading}
          error={contributionPlan.error}
        />
      </div>

      <section>
        <SectionHeader eyebrow="Shared planner" title="Investment Next Month Plan" size="sm" className="mb-5" />
        <NextMonthPlanSection
          recommendations={investmentPlanRecommendations}
          loading={nextMonthPlan.loading}
          error={nextMonthPlan.error}
          onRetry={loadNextMonthPlan}
          showSourceFacts
        />
      </section>

      <InvestmentInsights
        plan={contributionPlan.data}
        loading={contributionPlan.loading}
        error={contributionPlan.error}
      />

      {(portfolioRows.length > 0 || (data?.allocation.length ?? 0) > 0) && (
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] gap-6">
          <PortfolioHealth data={data} />
          <AccountAllocation data={data} />
        </div>
      )}

      {loading && !data && (
        <SkeletonState variant="card" height="260px" />
      )}

      {error && !data && (
        <ErrorState
          message={error}
          onRetry={retryAll}
        />
      )}

      {data && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="grid grid-cols-2 md:grid-cols-4 gap-4"
        >
          <Surface padding="md">
            <BarChart2 size={16} style={{ color: "var(--financial-investments)" }} />
            <p className="micro-text mt-3" style={{ color: "var(--text-muted)" }}>Total Portfolio</p>
            <p className="card-title-lg mt-1" style={{ color: "var(--text-primary)" }}>
              {data.portfolio_summary.total_portfolio_value > 0
                ? formatCompactCurrency(data.portfolio_summary.total_portfolio_value)
                : "-"}
            </p>
          </Surface>
          <Surface padding="md">
            <TrendingUp size={16} style={{ color: "#4CAF93" }} />
            <p className="micro-text mt-3" style={{ color: "var(--text-muted)" }}>Unrealized G/L</p>
            <p className="card-title-lg mt-1" style={{ color: "var(--text-primary)" }}>
              {data.portfolio_summary.total_unrealized_gain_loss_fmt}
            </p>
          </Surface>
          <Surface padding="md">
            <Landmark size={16} style={{ color: "var(--text-muted)" }} />
            <p className="micro-text mt-3" style={{ color: "var(--text-muted)" }}>Accounts Tracked</p>
            <p className="card-title-lg mt-1" style={{ color: "var(--text-primary)" }}>
              {data.portfolio_summary.accounts.length || "-"}
            </p>
          </Surface>
          <Surface padding="md">
            <PieChart size={16} style={{ color: "var(--text-muted)" }} />
            <p className="micro-text mt-3" style={{ color: "var(--text-muted)" }}>Last Updated</p>
            <p className="card-title-lg mt-1" style={{ color: "var(--text-primary)" }}>
              {data.portfolio_summary.last_updated
                ? new Date(data.portfolio_summary.last_updated).toLocaleDateString()
                : "-"}
            </p>
          </Surface>
        </motion.div>
      )}

      {hasAnyData ? (
        <section>
          <SectionHeader eyebrow="Accounts" title="Investment Accounts" size="sm" className="mb-5" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[
              { label: "Morgan Stanley Joint", icon: "MS", keys: ["joint", "morgan"] },
              { label: "Traditional IRA", icon: "IRA", keys: ["traditional", "trad ira"] },
              { label: "Roth IRA", icon: "Roth", keys: ["roth"] },
              { label: "E*TRADE", icon: "ET", keys: ["etrade", "e*trade"] },
              { label: "Empower / 401k", icon: "401k", keys: ["empower", "401k"] },
              { label: "Down-Payment Savings", icon: "$", keys: ["down", "savings", "529"] },
            ].map((account) => (
              <AccountCard
                key={account.label}
                label={account.label}
                icon={account.icon}
                data={findAccount(account.keys)}
              />
            ))}
          </div>
        </section>
      ) : (
        <EmptyState
          icon={<TrendingUp size={28} />}
          title={data?.period ? "No investment data in this period" : "No investment data yet"}
          description={
            data?.period
              ? `No statement or balance snapshot had been recorded on or before ${data.period.end_date}. Try a later period, or upload the statements covering it.`
              : "Upload statements from Morgan Stanley, E*TRADE, or other investment accounts to see your portfolio."
          }
          action={
            <button
              type="button"
              onClick={openUploadModal}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-2xl text-white font-semibold btn-coral"
            >
              <Upload size={15} /> Upload statements
            </button>
          }
        />
      )}

      {data?.top_holdings.length ? (
        <section>
          <SectionHeader eyebrow="Holdings" title="Top Holdings" size="sm" className="mb-5" />
          <GlassCard variant="default" className="!p-0 overflow-hidden">
            {data.top_holdings.slice(0, 10).map((holding, index) => (
              <HoldingRow
                key={`${holding.account_name}-${holding.symbol ?? holding.description}-${index}`}
                holding={holding}
                index={index}
                total={Math.min(data.top_holdings.length, 10)}
              />
            ))}
          </GlassCard>
        </section>
      ) : null}

      {data && (data.top_gainers.length > 0 || data.top_losers.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {data.top_gainers.length > 0 && (
            <section>
              <SectionHeader eyebrow="Performance" title="Top Gainers" size="sm" className="mb-4" />
              <div className="space-y-2">
                {data.top_gainers.slice(0, 5).map((holding, index) => (
                  <Surface
                    key={`${holding.description}-${index}`}
                    padding="sm"
                    className="flex items-center justify-between gap-4"
                  >
                    <p className="small-text font-medium truncate" style={{ color: "var(--text-primary)" }}>
                      {holding.symbol || holding.description.slice(0, 25)}
                    </p>
                    <p className="small-text font-bold tabular-nums" style={{ color: "#4CAF93" }}>
                      ↑ {holding.unrealized_gain_loss_fmt}
                    </p>
                  </Surface>
                ))}
              </div>
            </section>
          )}
          {data.top_losers.length > 0 && (
            <section>
              <SectionHeader eyebrow="Performance" title="Needs Attention" size="sm" className="mb-4" />
              <div className="space-y-2">
                {data.top_losers.slice(0, 5).map((holding, index) => (
                  <Surface
                    key={`${holding.description}-${index}`}
                    padding="sm"
                    className="flex items-center justify-between gap-4"
                  >
                    <p className="small-text font-medium truncate" style={{ color: "var(--text-primary)" }}>
                      {holding.symbol || holding.description.slice(0, 25)}
                    </p>
                    <p className="small-text font-bold tabular-nums" style={{ color: "#E45757" }}>
                      ↓ {holding.unrealized_gain_loss_fmt}
                    </p>
                  </Surface>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      <GlassCard variant="subtle" className="space-y-4">
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-2xl flex items-center justify-center"
            style={{ background: "rgba(255,122,90,0.15)", border: "1px solid rgba(255,122,90,0.25)" }}
          >
            <Sparkles size={15} style={{ color: "#FF7A5A" }} />
          </div>
          <div>
            <p className="card-title-lg">Ask Coral about your investments</p>
            <p className="small-text mt-0.5" style={{ color: "var(--text-muted)" }}>
              Deep-dive into your contribution plan and imported holdings.
            </p>
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
