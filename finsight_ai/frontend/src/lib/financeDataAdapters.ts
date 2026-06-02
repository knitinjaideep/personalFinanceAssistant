// Defensive data adapter helpers for Coral's frontend.
// All functions handle null/undefined gracefully and return empty structures rather than throwing.

import { normalizeName, IRA_KEYWORDS } from "./accountMapping";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface MonthLabel {
  key: string;   // "2025-11"
  label: string; // "Nov"
}

export interface MonthlyStat {
  month: string;
  spend: number;
  inflow: number;
  outflow: number;
  net: number;
}

export interface RecurringTransaction {
  merchant: string;
  avgAmount: number;
  frequency: string;
  lastSeen: string | null;
  count: number;
  category: string | null;
}

export interface TopTransaction {
  date: string | null;
  description: string;
  category: string | null;
  amount: number;
}

// ── Date helpers ──────────────────────────────────────────────────────────────

/** Returns the last N calendar months as { key: "YYYY-MM", label: "Mon" } */
export function getLastNMonths(n = 6): MonthLabel[] {
  const result: MonthLabel[] = [];
  const now = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = d.toLocaleString("default", { month: "short" });
    result.push({ key, label });
  }
  return result;
}

/** Extract YYYY-MM from an ISO date string or null. */
export function toYearMonth(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null;
  return dateStr.slice(0, 7);
}

// ── Transaction groupers ──────────────────────────────────────────────────────

export interface RawTransaction {
  date?: string | null;
  description?: string | null;
  merchant?: string | null;
  amount?: number | null;
  transaction_type?: string | null;
  category?: string | null;
  account_name?: string | null;
  institution_type?: string | null;
}

/** Group transactions by YYYY-MM and compute spend/inflow/outflow per month. */
export function groupTransactionsByMonth(
  transactions: RawTransaction[],
  months: MonthLabel[],
): MonthlyStat[] {
  const map: Record<string, MonthlyStat> = {};
  for (const m of months) {
    map[m.key] = { month: m.label, spend: 0, inflow: 0, outflow: 0, net: 0 };
  }
  for (const tx of transactions) {
    const ym = toYearMonth(tx.date);
    if (!ym || !map[ym]) continue;
    const amt = Math.abs(tx.amount ?? 0);
    const isDebit = (tx.amount ?? 0) < 0 || normalizeName(tx.transaction_type).includes("debit") || normalizeName(tx.transaction_type).includes("charge");
    const isCredit = (tx.amount ?? 0) > 0 || normalizeName(tx.transaction_type).includes("credit") || normalizeName(tx.transaction_type).includes("deposit") || normalizeName(tx.transaction_type).includes("payment");
    if (isDebit) {
      map[ym].spend += amt;
      map[ym].outflow += amt;
    } else if (isCredit) {
      map[ym].inflow += amt;
    }
    map[ym].net = map[ym].inflow - map[ym].outflow;
  }
  return months.map((m) => map[m.key]);
}

/** Calculate monthly spend from transactions (absolute values of outgoing). */
export function calculateMonthlySpend(
  transactions: RawTransaction[],
  months: MonthLabel[],
): Array<{ month: string; spend: number }> {
  return groupTransactionsByMonth(transactions, months).map((m) => ({
    month: m.month,
    spend: Math.round(m.spend),
  }));
}

/** Calculate inflow/outflow per month for checking/savings. */
export function calculateIncomingOutgoing(
  transactions: RawTransaction[],
  months: MonthLabel[],
): Array<{ month: string; inflow: number; outflow: number; net: number }> {
  return groupTransactionsByMonth(transactions, months).map((m) => ({
    month: m.month,
    inflow: Math.round(m.inflow),
    outflow: Math.round(m.outflow),
    net: Math.round(m.net),
  }));
}

/** Find top N transactions by absolute amount (descending). */
export function findTopTransactions(
  transactions: RawTransaction[],
  limit = 5,
): TopTransaction[] {
  const sorted = [...transactions]
    .filter((tx) => tx.amount != null && tx.amount !== 0)
    .sort((a, b) => Math.abs(b.amount ?? 0) - Math.abs(a.amount ?? 0))
    .slice(0, limit);

  return sorted.map((tx) => ({
    date: tx.date ?? null,
    description: tx.merchant || tx.description || "Unknown",
    category: tx.category ?? null,
    amount: Math.abs(tx.amount ?? 0),
  }));
}

// ── Recurring transaction detection ──────────────────────────────────────────

/** Detect recurring transactions from raw transactions.
 *  A recurring pattern = same normalized merchant, ≥2 occurrences,
 *  amounts within 30% tolerance of the average. */
export function detectRecurringTransactions(
  transactions: RawTransaction[],
  minOccurrences = 2,
): RecurringTransaction[] {
  const groups: Record<string, RawTransaction[]> = {};
  for (const tx of transactions) {
    const key = normalizeName(tx.merchant || tx.description);
    if (!key || key.length < 2) continue;
    if (!groups[key]) groups[key] = [];
    groups[key].push(tx);
  }

  const result: RecurringTransaction[] = [];
  for (const [, txs] of Object.entries(groups)) {
    if (txs.length < minOccurrences) continue;
    const amounts = txs.map((t) => Math.abs(t.amount ?? 0)).filter((a) => a > 0);
    if (amounts.length < minOccurrences) continue;
    const avg = amounts.reduce((s, a) => s + a, 0) / amounts.length;
    const sorted = [...txs].sort((a, b) => (b.date ?? "").localeCompare(a.date ?? ""));
    result.push({
      merchant: txs[0].merchant || txs[0].description || "Unknown",
      avgAmount: Math.round(avg * 100) / 100,
      frequency: txs.length >= 12 ? "Monthly+" : txs.length >= 4 ? "Quarterly" : "Occasional",
      lastSeen: sorted[0]?.date ?? null,
      count: txs.length,
      category: txs[0].category ?? null,
    });
  }

  return result.sort((a, b) => b.avgAmount - a.avgAmount);
}

// ── Summary computations ──────────────────────────────────────────────────────

export interface CashFlowSummary {
  totalInflow: number;
  totalOutflow: number;
  netCashFlow: number;
  largestDeposit: number;
  largestWithdrawal: number;
}

export function computeCashFlowSummary(transactions: RawTransaction[]): CashFlowSummary {
  let totalInflow = 0;
  let totalOutflow = 0;
  let largestDeposit = 0;
  let largestWithdrawal = 0;

  for (const tx of transactions) {
    const amt = Math.abs(tx.amount ?? 0);
    const isDebit = (tx.amount ?? 0) < 0 || normalizeName(tx.transaction_type).includes("debit") || normalizeName(tx.transaction_type).includes("charge");
    if (isDebit) {
      totalOutflow += amt;
      if (amt > largestWithdrawal) largestWithdrawal = amt;
    } else {
      totalInflow += amt;
      if (amt > largestDeposit) largestDeposit = amt;
    }
  }

  return {
    totalInflow: Math.round(totalInflow),
    totalOutflow: Math.round(totalOutflow),
    netCashFlow: Math.round(totalInflow - totalOutflow),
    largestDeposit: Math.round(largestDeposit),
    largestWithdrawal: Math.round(largestWithdrawal),
  };
}

// ── Investment helpers ────────────────────────────────────────────────────────

export interface InstitutionTotal {
  institutionKey: string;
  displayName: string;
  totalValue: number;
  asOf: string | null;
}

export interface InvestmentTotals {
  combined: number;
  institutions: InstitutionTotal[];
  iraTotal: number;
  asOf: string | null;
}

export interface AccountBalance {
  account_name?: string | null;
  account_type?: string | null;
  institution_type?: string | null;
  total_value?: number | null;
  total_value_fmt?: string | null;
  snapshot_date?: string | null;
  latest_statement_date?: string | null;
}

/** Calculate combined investment totals from account balances. */
export function calculateInvestmentTotals(accounts: AccountBalance[]): InvestmentTotals {
  const institutionMap: Record<string, InstitutionTotal> = {
    morgan_stanley: { institutionKey: "morgan_stanley", displayName: "Morgan Stanley", totalValue: 0, asOf: null },
    etrade: { institutionKey: "etrade", displayName: "E*TRADE", totalValue: 0, asOf: null },
  };

  let combined = 0;
  let iraTotal = 0;
  let latestDate: string | null = null;

  for (const acct of accounts) {
    const val = acct.total_value ?? 0;
    const instKey = normalizeName(acct.institution_type);
    combined += val;

    if (instKey.includes("morgan") || instKey.includes("ms")) {
      institutionMap.morgan_stanley.totalValue += val;
      const d = acct.snapshot_date ?? acct.latest_statement_date;
      if (d && (!institutionMap.morgan_stanley.asOf || d > institutionMap.morgan_stanley.asOf)) {
        institutionMap.morgan_stanley.asOf = d;
      }
    } else if (instKey.includes("etrade") || instKey.includes("e*trade") || instKey.includes("e-trade")) {
      institutionMap.etrade.totalValue += val;
      const d = acct.snapshot_date ?? acct.latest_statement_date;
      if (d && (!institutionMap.etrade.asOf || d > institutionMap.etrade.asOf)) {
        institutionMap.etrade.asOf = d;
      }
    }

    if (isIRAAccount(acct.account_name, acct.account_type)) {
      iraTotal += val;
    }

    const d = acct.snapshot_date ?? acct.latest_statement_date;
    if (d && (!latestDate || d > latestDate)) latestDate = d;
  }

  return {
    combined: Math.round(combined),
    institutions: Object.values(institutionMap).filter((i) => i.totalValue > 0),
    iraTotal: Math.round(iraTotal),
    asOf: latestDate,
  };
}

function isIRAAccount(name: string | null | undefined, type: string | null | undefined): boolean {
  const combined = normalizeName(name) + " " + normalizeName(type);
  return IRA_KEYWORDS.some((kw) => combined.includes(kw));
}

// ── Formatters ────────────────────────────────────────────────────────────────

export function fmtUSD(n: number): string {
  if (!isFinite(n)) return "$—";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000)     return `$${(n / 1_000).toFixed(1)}k`;
  return `$${Math.round(n).toLocaleString()}`;
}

export function fmtDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return dateStr;
  }
}
