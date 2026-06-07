// Banking dashboard normalization utilities.
// Computes UI-ready structures from raw BankingDashboard API data.
// All functions are null-safe and never throw.

import type {
  BankingDashboard,
  CardSpend,
  CashFlowMonth,
  Subscription,
  InstitutionCoverage,
} from "../api/dashboard";
import {
  CREDIT_CARD_ACCOUNTS,
  CHECKING_ACCOUNTS,
  SAVINGS_ACCOUNTS,
  matchAccount,
  type AccountConfig,
} from "./accountMapping";
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

// ── Summary metrics ───────────────────────────────────────────────────────────

export interface BankingMetrics {
  monthlySpend: number;
  monthlySpendFmt: string;
  monthlySpendTrend: TrendResult;
  cashFlowNet: number;
  cashFlowFmt: string;
  cashFlowDirection: "positive" | "negative" | "neutral";
  upcomingPaymentsCount: number;
  needsAttentionCount: number;
  needsAttentionItems: string[];
  latestMonth: string | null;
}

export function buildBankingMetrics(raw: BankingDashboard | null): BankingMetrics {
  if (!raw) {
    return {
      monthlySpend: 0,
      monthlySpendFmt: "Needs data",
      monthlySpendTrend: { pct: null, direction: "unknown", label: "—" },
      cashFlowNet: 0,
      cashFlowFmt: "Needs data",
      cashFlowDirection: "neutral",
      upcomingPaymentsCount: 0,
      needsAttentionCount: 0,
      needsAttentionItems: ["No banking data loaded. Upload statements."],
      latestMonth: null,
    };
  }

  // Monthly spend: sum of latest month's card spend
  const spendByMonth = safeArray(raw.spend_by_month);
  const sortedSpend = [...spendByMonth].sort((a, b) => b.month.localeCompare(a.month));
  const latestSpend = sortedSpend[0];
  const prevSpend = sortedSpend[1];
  const monthlySpend = safeNumber(latestSpend?.total_spend);
  const prevMonthlySpend = safeNumber(prevSpend?.total_spend);

  // Cash flow: latest month net from cash_flow
  const cashFlow = safeArray(raw.cash_flow);
  const sortedCF = [...cashFlow].sort((a, b) => b.month.localeCompare(a.month));
  const latestCF = sortedCF[0];
  const cashFlowNet = safeNumber(latestCF?.net);

  // Needs attention: accounts with no data + coverage issues
  const coverage = safeArray(raw.coverage);
  const needsAttentionItems: string[] = [];

  const allExpected = [...CREDIT_CARD_ACCOUNTS, ...CHECKING_ACCOUNTS, ...SAVINGS_ACCOUNTS];
  const cardSummaryNames = safeArray(raw.card_summary).map((c) =>
    (c.product_label ?? c.account_name ?? "").toLowerCase(),
  );

  for (const account of allExpected) {
    const matched = safeArray(raw.card_summary).find((cs) => {
      const m = matchAccount(cs.product_label ?? cs.account_name, [account]);
      return m?.key === account.key;
    });
    if (!matched) {
      needsAttentionItems.push(`${account.displayName} — no data found`);
    }
  }

  for (const cov of coverage) {
    if (cov.missing_recent_data) {
      needsAttentionItems.push(`${cov.institution} — missing recent statement`);
    }
  }

  void cardSummaryNames;

  const upcomingPaymentsCount = safeArray(raw.card_summary).filter(
    (c) => c.account_type === "credit_card" && c.latest_statement != null,
  ).length;

  return {
    monthlySpend,
    monthlySpendFmt: monthlySpend > 0 ? formatCurrency(monthlySpend) : "Needs data",
    monthlySpendTrend: computeTrend(monthlySpend, prevMonthlySpend),
    cashFlowNet,
    cashFlowFmt: cashFlowNet !== 0 ? (cashFlowNet > 0 ? `+${formatCurrency(cashFlowNet)}` : formatCurrency(cashFlowNet)) : "Needs data",
    cashFlowDirection: cashFlowNet > 0 ? "positive" : cashFlowNet < 0 ? "negative" : "neutral",
    upcomingPaymentsCount,
    needsAttentionCount: needsAttentionItems.length,
    needsAttentionItems,
    latestMonth: latestSpend?.month ?? null,
  };
}

// ── Banking insights ──────────────────────────────────────────────────────────

export interface BankingInsight {
  text: string;
  type: "info" | "warn" | "ok";
}

export function buildBankingInsights(raw: BankingDashboard | null): BankingInsight[] {
  if (!raw) return [{ text: "Upload banking statements to see insights.", type: "info" }];

  const insights: BankingInsight[] = [];
  const spendByMonth = safeArray(raw.spend_by_month);
  const sortedSpend = [...spendByMonth].sort((a, b) => b.month.localeCompare(a.month));

  if (sortedSpend.length >= 2) {
    const cur = safeNumber(sortedSpend[0]?.total_spend);
    const prev = safeNumber(sortedSpend[1]?.total_spend);
    if (prev > 0) {
      const pct = ((cur - prev) / prev) * 100;
      if (pct > 10) {
        insights.push({ text: `Spending is up ${pct.toFixed(0)}% vs last month.`, type: "warn" });
      } else if (pct < -10) {
        insights.push({ text: `Spending is down ${Math.abs(pct).toFixed(0)}% vs last month.`, type: "ok" });
      } else {
        insights.push({ text: "Spending is in line with last month.", type: "info" });
      }
    }
  }

  const cashFlow = safeArray(raw.cash_flow);
  const sortedCF = [...cashFlow].sort((a, b) => b.month.localeCompare(a.month));
  const latestCF = sortedCF[0];
  if (latestCF) {
    const net = safeNumber(latestCF.net);
    if (net > 500) {
      insights.push({ text: `Cash flow is positive — income exceeded spending by ${formatCurrency(net)}.`, type: "ok" });
    } else if (net < -200) {
      insights.push({ text: `Cash flow is negative — spending exceeded income by ${formatCurrency(Math.abs(net))}.`, type: "warn" });
    }
  }

  const subs = safeArray(raw.subscriptions);
  if (subs.length > 0) {
    const total = subs.reduce((s, sub) => s + safeNumber(sub.avg_monthly_amount), 0);
    insights.push({ text: `${subs.length} recurring charges detected, averaging ${formatCurrency(total)}/month.`, type: "info" });
  }

  const coverage = safeArray(raw.coverage);
  const missingCoverage = coverage.filter((c) => c.missing_recent_data);
  for (const c of missingCoverage.slice(0, 2)) {
    insights.push({ text: `${c.institution} is missing a recent statement.`, type: "warn" });
  }

  if (insights.length === 0) {
    insights.push({ text: "Coral needs more parsed statements to compare changes.", type: "info" });
  }

  return insights.slice(0, 5);
}

// ── Account group builders ────────────────────────────────────────────────────

export interface BankingAccountRow {
  config: AccountConfig;
  cardSummary: CardSpend | null;
  cashFlow: CashFlowMonth[];
  coverage: InstitutionCoverage | null;
  latestStatement: string | null;
  latestSpend: number;
  latestSpendFmt: string;
  status: "ok" | "warn" | "missing";
  statusLabel: string;
}

function buildAccountRow(
  config: AccountConfig,
  raw: BankingDashboard,
  pool: AccountConfig[],
): BankingAccountRow {
  const cardSummary =
    safeArray(raw.card_summary).find((cs) => {
      const m = matchAccount(cs.product_label ?? cs.account_name, pool);
      return m?.key === config.key;
    }) ?? null;

  const coverage =
    safeArray(raw.coverage).find(
      (c) => (c.institution_type ?? "").toLowerCase().replace(/[\s*-]/g, "").includes(config.institutionKey.replace(/_/g, "")),
    ) ?? null;

  const latestStatement = cardSummary?.latest_statement ?? coverage?.latest_statement ?? null;
  const freshnessStatus = getDataFreshnessStatus(latestStatement);

  let status: "ok" | "warn" | "missing" = "ok";
  let statusLabel = latestStatement ? `Latest: ${latestStatement}` : "No data";

  if (!cardSummary && !coverage) {
    status = "missing";
    statusLabel = "No data found";
  } else if (freshnessStatus === "stale") {
    status = "warn";
    statusLabel = `Stale — ${latestStatement}`;
  } else if (freshnessStatus === "missing") {
    status = "missing";
    statusLabel = "No recent statement";
  }

  return {
    config,
    cardSummary,
    cashFlow: safeArray(raw.cash_flow),
    coverage,
    latestStatement,
    latestSpend: safeNumber(cardSummary?.total_spend),
    latestSpendFmt: cardSummary?.total_spend_fmt ?? "—",
    status,
    statusLabel,
  };
}

export function buildCreditCardRows(raw: BankingDashboard | null): BankingAccountRow[] {
  if (!raw) {
    return CREDIT_CARD_ACCOUNTS.map((config) => ({
      config,
      cardSummary: null,
      cashFlow: [],
      coverage: null,
      latestStatement: null,
      latestSpend: 0,
      latestSpendFmt: "—",
      status: "missing",
      statusLabel: "No data",
    }));
  }
  return CREDIT_CARD_ACCOUNTS.map((c) => buildAccountRow(c, raw, CREDIT_CARD_ACCOUNTS));
}

export function buildCheckingRows(raw: BankingDashboard | null): BankingAccountRow[] {
  if (!raw) {
    return CHECKING_ACCOUNTS.map((config) => ({
      config,
      cardSummary: null,
      cashFlow: [],
      coverage: null,
      latestStatement: null,
      latestSpend: 0,
      latestSpendFmt: "—",
      status: "missing",
      statusLabel: "No data",
    }));
  }
  return CHECKING_ACCOUNTS.map((c) => buildAccountRow(c, raw, CHECKING_ACCOUNTS));
}

export function buildSavingsRows(raw: BankingDashboard | null): BankingAccountRow[] {
  if (!raw) {
    return SAVINGS_ACCOUNTS.map((config) => ({
      config,
      cardSummary: null,
      cashFlow: [],
      coverage: null,
      latestStatement: null,
      latestSpend: 0,
      latestSpendFmt: "—",
      status: "missing",
      statusLabel: "No data",
    }));
  }
  return SAVINGS_ACCOUNTS.map((c) => buildAccountRow(c, raw, SAVINGS_ACCOUNTS));
}

// ── Data freshness for Banking ────────────────────────────────────────────────

export interface BankingFreshnessItem {
  label: string;
  institutionKey: string;
  latestDate: string | null;
  docCount: number;
  status: "fresh" | "stale" | "missing";
}

export function buildBankingFreshness(raw: BankingDashboard | null): BankingFreshnessItem[] {
  const known = [
    { label: "Chase", key: "chase" },
    { label: "American Express", key: "amex" },
    { label: "Macy's", key: "macys" },
    { label: "Bank of America", key: "bank_of_america" },
    { label: "Marcus", key: "marcus" },
  ];

  const coverage = safeArray(raw?.coverage);

  return known.map(({ label, key }) => {
    const cov = coverage.find((c) =>
      (c.institution_type ?? c.institution ?? "").toLowerCase().replace(/[\s*-]/g, "").includes(key.replace(/_/g, "")),
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

// ── Spend by month chart data ─────────────────────────────────────────────────

export interface MonthlySpendPoint {
  month: string;
  label: string;
  spend: number;
}

export function buildMonthlySpendChart(raw: BankingDashboard | null, n = 6): MonthlySpendPoint[] {
  const months = lastNMonths(n);
  const spendMap: Record<string, number> = {};
  for (const item of safeArray(raw?.spend_by_month)) {
    spendMap[item.month] = safeNumber(item.total_spend);
  }
  return months.map((m) => ({
    month: m,
    label: monthLabel(m),
    spend: spendMap[m] ?? 0,
  }));
}

// ── Cash flow chart data ──────────────────────────────────────────────────────

export interface CashFlowPoint {
  month: string;
  label: string;
  inflow: number;
  outflow: number;
  net: number;
}

export function buildCashFlowChart(raw: BankingDashboard | null, n = 6): CashFlowPoint[] {
  const months = lastNMonths(n);
  const cfMap: Record<string, CashFlowMonth> = {};
  for (const item of safeArray(raw?.cash_flow)) {
    cfMap[item.month] = item;
  }
  return months.map((m) => ({
    month: m,
    label: monthLabel(m),
    inflow: safeNumber(cfMap[m]?.inflow),
    outflow: safeNumber(cfMap[m]?.outflow),
    net: safeNumber(cfMap[m]?.net),
  }));
}

// ── Statements coverage grid ──────────────────────────────────────────────────

export interface StatementCoverageRow {
  accountKey: string;
  accountName: string;
  institution: string;
  months: Record<string, "parsed" | "missing">;
}

export function buildStatementCoverageGrid(
  raw: BankingDashboard | null,
  n = 12,
): { months: string[]; rows: StatementCoverageRow[] } {
  const months = lastNMonths(n);
  const allAccounts = [...CREDIT_CARD_ACCOUNTS, ...CHECKING_ACCOUNTS, ...SAVINGS_ACCOUNTS];

  const rows: StatementCoverageRow[] = allAccounts.map((config) => {
    const cardSummary =
      safeArray(raw?.card_summary).find((cs) => {
        const m = matchAccount(cs.product_label ?? cs.account_name, [config]);
        return m?.key === config.key;
      }) ?? null;

    const parsedMonths: Record<string, "parsed" | "missing"> = {};
    for (const m of months) {
      parsedMonths[m] = "missing";
    }

    if (cardSummary?.latest_statement) {
      const ym = cardSummary.latest_statement.slice(0, 7);
      if (parsedMonths[ym] !== undefined) {
        parsedMonths[ym] = "parsed";
      }
    }

    return {
      accountKey: config.key,
      accountName: config.displayName,
      institution: config.institution,
      months: parsedMonths,
    };
  });

  return { months, rows };
}

// ── Top transactions helper ───────────────────────────────────────────────────

export function getTopMerchants(raw: BankingDashboard | null, limit = 5) {
  return safeArray(raw?.top_merchants).slice(0, limit);
}

export function getSubscriptions(raw: BankingDashboard | null): Subscription[] {
  return safeArray(raw?.subscriptions);
}
