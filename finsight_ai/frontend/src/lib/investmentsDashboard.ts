// Investments dashboard normalization utilities.
// All functions are null-safe and never throw.

import type { InvestmentsDashboard, Holding, InstitutionCoverage } from "../api/dashboard";
import { isIRAAccount } from "./accountMapping";
import {
  safeArray,
  safeNumber,
  formatCurrency,
  getDataFreshnessStatus,
  computeTrend,
  lastNMonths,
  monthLabel,
  type TrendResult,
} from "./dashboardData";

// ── Metric computations ───────────────────────────────────────────────────────

export interface InvestmentMetrics {
  totalPortfolio: number;
  totalPortfolioFmt: string;
  totalPortfolioSubtitle: string;
  iraTotal: number;
  iraTotalFmt: string;
  iraTotalSubtitle: string;
  downPaymentSavings: number;
  downPaymentSavingsFmt: string;
  latestStatementDate: string | null;
  latestStatementFmt: string;
  latestStatementSource: string;
  portfolioTrend: TrendResult;
  needsAttentionCount: number;
}

export function buildInvestmentMetrics(raw: InvestmentsDashboard | null): InvestmentMetrics {
  if (!raw) {
    return {
      totalPortfolio: 0,
      totalPortfolioFmt: "Needs data",
      totalPortfolioSubtitle: "Upload statements",
      iraTotal: 0,
      iraTotalFmt: "Needs data",
      iraTotalSubtitle: "Traditional + Roth IRA",
      downPaymentSavings: 0,
      downPaymentSavingsFmt: "Needs data",
      latestStatementDate: null,
      latestStatementFmt: "—",
      latestStatementSource: "—",
      portfolioTrend: { pct: null, direction: "unknown", label: "—" },
      needsAttentionCount: 0,
    };
  }

  const accounts = safeArray(raw.portfolio_summary?.accounts);
  const totalPortfolio = safeNumber(raw.portfolio_summary?.total_portfolio_value);

  const iraAccounts = accounts.filter((a) => isIRAAccount(a.account_name, a.account_type));
  const iraTotal = iraAccounts.reduce((s, a) => s + safeNumber(a.total_value), 0);

  const downPaymentAccounts = accounts.filter((a) => {
    const name = (a.account_name ?? "").toLowerCase();
    return name.includes("down") || name.includes("savings") || name.includes("529");
  });
  const downPaymentSavings = downPaymentAccounts.reduce((s, a) => s + safeNumber(a.total_value), 0);

  // Latest statement across all accounts
  let latestStatementDate: string | null = null;
  let latestStatementSource = "—";
  for (const a of accounts) {
    const d = a.latest_statement_date ?? a.snapshot_date;
    if (d && (!latestStatementDate || d > latestStatementDate)) {
      latestStatementDate = d;
      latestStatementSource = a.institution_type ?? a.account_name ?? "—";
    }
  }

  // Portfolio trend from balance history
  const history = safeArray(raw.balance_history);
  const byMonth: Record<string, number> = {};
  for (const pt of history) {
    byMonth[pt.date.slice(0, 7)] = (byMonth[pt.date.slice(0, 7)] ?? 0) + safeNumber(pt.total_value);
  }
  const sortedMonths = Object.keys(byMonth).sort((a, b) => b.localeCompare(a));
  const curMonth = byMonth[sortedMonths[0]] ?? totalPortfolio;
  const prevMonth = byMonth[sortedMonths[1]] ?? 0;
  const portfolioTrend = prevMonth > 0 ? computeTrend(curMonth, prevMonth) : { pct: null, direction: "unknown" as const, label: "—" };

  // Needs attention
  const coverage = safeArray(raw.coverage);
  const needsAttentionCount = coverage.filter((c) => c.missing_recent_data || !c.latest_statement).length;

  // Institution breakdown subtitle
  const byInstitution: Record<string, number> = {};
  for (const a of accounts) {
    const key = a.institution_type ?? "other";
    byInstitution[key] = (byInstitution[key] ?? 0) + safeNumber(a.total_value);
  }
  const topInstitutions = Object.entries(byInstitution)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2)
    .map(([name]) => name);
  const totalPortfolioSubtitle = topInstitutions.length > 0 ? topInstitutions.join(" + ") : "No accounts";

  return {
    totalPortfolio,
    totalPortfolioFmt: totalPortfolio > 0 ? formatCurrency(totalPortfolio) : "Needs data",
    totalPortfolioSubtitle,
    iraTotal,
    iraTotalFmt: iraTotal > 0 ? formatCurrency(iraTotal) : "Needs data",
    iraTotalSubtitle: "Traditional + Roth IRA",
    downPaymentSavings,
    downPaymentSavingsFmt: downPaymentSavings > 0 ? formatCurrency(downPaymentSavings) : "Needs data",
    latestStatementDate,
    latestStatementFmt: latestStatementDate
      ? new Date(latestStatementDate + "T00:00:00").toLocaleDateString("en-US", { month: "long", year: "numeric" })
      : "—",
    latestStatementSource,
    portfolioTrend,
    needsAttentionCount,
  };
}

// ── Investment insights ───────────────────────────────────────────────────────

export interface InvestmentInsight {
  text: string;
  type: "info" | "warn" | "ok";
}

export function buildInvestmentInsights(raw: InvestmentsDashboard | null): InvestmentInsight[] {
  if (!raw) {
    return [{ text: "Upload Morgan Stanley and E*TRADE statements to populate your investment view.", type: "info" }];
  }

  const insights: InvestmentInsight[] = [];
  const coverage = safeArray(raw.coverage);

  for (const cov of coverage) {
    if (!cov.latest_statement) {
      insights.push({ text: `${cov.institution} has no parsed statements. Upload to see portfolio data.`, type: "warn" });
    } else if (cov.missing_recent_data) {
      insights.push({ text: `${cov.institution} may have a missing recent statement.`, type: "warn" });
    } else {
      const date = new Date(cov.latest_statement + "T00:00:00");
      const label = date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
      insights.push({ text: `Your latest ${cov.institution} statement is from ${label}.`, type: "ok" });
    }
  }

  const history = safeArray(raw.balance_history);
  const byMonth: Record<string, number> = {};
  for (const pt of history) {
    byMonth[pt.date.slice(0, 7)] = (byMonth[pt.date.slice(0, 7)] ?? 0) + safeNumber(pt.total_value);
  }
  if (Object.keys(byMonth).length < 2) {
    insights.push({ text: "Coral needs at least two parsed investment statements to show changes over time.", type: "info" });
  }

  if (insights.length === 0) {
    insights.push({ text: "Upload the latest statements to keep your portfolio view fresh.", type: "info" });
  }

  return insights.slice(0, 4);
}

// ── Data freshness ────────────────────────────────────────────────────────────

export interface InvestmentFreshnessItem {
  label: string;
  institutionKey: string;
  latestDate: string | null;
  docCount: number;
  status: "fresh" | "stale" | "missing";
}

const KNOWN_INVESTMENT_INSTITUTIONS = [
  { label: "Morgan Stanley", key: "morgan_stanley" },
  { label: "E*TRADE", key: "etrade" },
];

export function buildInvestmentFreshness(raw: InvestmentsDashboard | null): InvestmentFreshnessItem[] {
  const coverage = safeArray(raw?.coverage);
  return KNOWN_INVESTMENT_INSTITUTIONS.map(({ label, key }) => {
    const cov = coverage.find(
      (c) =>
        (c.institution_type ?? c.institution ?? "")
          .toLowerCase()
          .replace(/[\s*-]/g, "")
          .includes(key.replace(/_/g, "")),
    );
    const latestDate = cov?.latest_statement ?? null;
    return {
      label,
      institutionKey: key,
      latestDate,
      docCount: cov?.doc_count ?? 0,
      status: getDataFreshnessStatus(latestDate),
    };
  });
}

// ── Account cards ─────────────────────────────────────────────────────────────

export interface InvestmentAccountCard {
  accountName: string;
  institutionType: string;
  accountType: string;
  totalValue: number;
  totalValueFmt: string;
  unrealizedGainLoss: number;
  unrealizedGainLossFmt: string;
  gainLossPct: number | null;
  latestStatementDate: string | null;
  isIRA: boolean;
  status: "fresh" | "stale" | "missing";
}

export function buildInvestmentAccountCards(raw: InvestmentsDashboard | null): InvestmentAccountCard[] {
  if (!raw) return [];
  const accounts = safeArray(raw.portfolio_summary?.accounts);
  return accounts.map((a) => {
    const latestDate = a.latest_statement_date ?? a.snapshot_date ?? null;
    return {
      accountName: a.account_name ?? "Unknown Account",
      institutionType: a.institution_type ?? "—",
      accountType: a.account_type ?? "—",
      totalValue: safeNumber(a.total_value),
      totalValueFmt: a.total_value_fmt ?? formatCurrency(safeNumber(a.total_value)),
      unrealizedGainLoss: safeNumber(a.unrealized_gain_loss),
      unrealizedGainLossFmt: a.unrealized_gain_loss_fmt ?? formatCurrency(Math.abs(safeNumber(a.unrealized_gain_loss))),
      gainLossPct: a.gain_loss_pct ?? null,
      latestStatementDate: latestDate,
      isIRA: isIRAAccount(a.account_name, a.account_type),
      status: getDataFreshnessStatus(latestDate),
    };
  });
}

// ── Portfolio allocation chart ────────────────────────────────────────────────

export interface AllocationSlice {
  name: string;
  value: number;
  pct: number;
  color: string;
}

const ALLOCATION_COLORS = ["#22d3ee", "#4CAF93", "#FF7A5A", "#5FA8D3", "#FFD166", "#a78bfa"];

export function buildPortfolioAllocation(raw: InvestmentsDashboard | null): AllocationSlice[] {
  if (!raw) return [];
  const allocation = safeArray(raw.allocation);
  if (allocation.length === 0) return [];

  const total = allocation.reduce((s, a) => s + safeNumber(a.total_value), 0);
  if (total === 0) return [];

  return allocation
    .filter((a) => safeNumber(a.total_value) > 0)
    .map((a, i) => ({
      name: a.account_name ?? a.institution_type ?? "Other",
      value: safeNumber(a.total_value),
      pct: Math.round((safeNumber(a.total_value) / total) * 100),
      color: ALLOCATION_COLORS[i % ALLOCATION_COLORS.length],
    }));
}

// ── Portfolio value trend chart ───────────────────────────────────────────────

export interface PortfolioTrendPoint {
  month: string;
  label: string;
  value: number;
}

export function buildPortfolioTrend(raw: InvestmentsDashboard | null, n = 12): PortfolioTrendPoint[] {
  const months = lastNMonths(n);
  const byMonth: Record<string, number> = {};
  for (const pt of safeArray(raw?.balance_history)) {
    const ym = pt.date.slice(0, 7);
    byMonth[ym] = (byMonth[ym] ?? 0) + safeNumber(pt.total_value);
  }
  return months
    .map((m) => ({ month: m, label: monthLabel(m), value: byMonth[m] ?? 0 }))
    .filter((p) => p.value > 0);
}

// ── Holdings table ────────────────────────────────────────────────────────────

export function buildTopHoldings(raw: InvestmentsDashboard | null, limit = 20): Holding[] {
  return safeArray(raw?.top_holdings).slice(0, limit);
}

// ── Activity ──────────────────────────────────────────────────────────────────

export interface InvestmentActivityItem {
  type: string;
  description: string;
  amount: number;
  amountFmt: string;
  date: string | null;
  account: string;
  isPositive: boolean;
}

export function buildInvestmentActivity(raw: InvestmentsDashboard | null): InvestmentActivityItem[] {
  // Top gainers and losers as "activity" proxy when no explicit activity endpoint exists
  if (!raw) return [];
  const gainers = safeArray(raw.top_gainers).map((h): InvestmentActivityItem => ({
    type: "gain",
    description: h.symbol ?? h.description ?? "—",
    amount: safeNumber(h.unrealized_gain_loss),
    amountFmt: h.unrealized_gain_loss_fmt ?? formatCurrency(safeNumber(h.unrealized_gain_loss)),
    date: null,
    account: h.account_name ?? "—",
    isPositive: true,
  }));
  const losers = safeArray(raw.top_losers).map((h): InvestmentActivityItem => ({
    type: "loss",
    description: h.symbol ?? h.description ?? "—",
    amount: safeNumber(h.unrealized_gain_loss),
    amountFmt: h.unrealized_gain_loss_fmt ?? formatCurrency(Math.abs(safeNumber(h.unrealized_gain_loss))),
    date: null,
    account: h.account_name ?? "—",
    isPositive: false,
  }));
  return [...gainers, ...losers];
}

// ── Statement coverage grid ───────────────────────────────────────────────────

export interface InvestmentCoverageRow {
  accountKey: string;
  accountName: string;
  institutionKey: string;
  coverage: InstitutionCoverage | null;
  latestStatement: string | null;
  docCount: number;
  status: "fresh" | "stale" | "missing";
}

const KNOWN_INVESTMENT_ACCOUNTS = [
  { key: "morgan_stanley", label: "Morgan Stanley", institution: "morgan_stanley" },
  { key: "etrade", label: "E*TRADE", institution: "etrade" },
  { key: "traditional_ira", label: "Traditional IRA", institution: "morgan_stanley" },
  { key: "roth_ira", label: "Roth IRA", institution: "morgan_stanley" },
  { key: "down_payment", label: "Down Payment Savings", institution: "etrade" },
];

export function buildInvestmentCoverageRows(raw: InvestmentsDashboard | null): InvestmentCoverageRow[] {
  const coverage = safeArray(raw?.coverage);
  return KNOWN_INVESTMENT_ACCOUNTS.map(({ key, label, institution }) => {
    const cov =
      coverage.find((c) =>
        (c.institution_type ?? c.institution ?? "").toLowerCase().replace(/[\s*-]/g, "").includes(institution.replace(/_/g, "")),
      ) ?? null;
    const latestStatement = cov?.latest_statement ?? null;
    const status = getDataFreshnessStatus(latestStatement);
    return {
      accountKey: key,
      accountName: label,
      institutionKey: institution,
      coverage: cov,
      latestStatement,
      docCount: cov?.doc_count ?? 0,
      status,
    };
  });
}
