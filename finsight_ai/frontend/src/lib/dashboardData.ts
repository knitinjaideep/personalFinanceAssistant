// Shared dashboard data utilities for Coral.
// All functions are defensive: null/undefined safe, never throw, return stable empty structures.

// ── Formatters ────────────────────────────────────────────────────────────────

export function formatCurrency(value: number | null | undefined): string {
  const n = safeNumber(value);
  if (n === 0) return "$0";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}k`;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

export function formatCurrencyFull(value: number | null | undefined): string {
  const n = safeNumber(value);
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

export function formatPercent(value: number | null | undefined, decimals = 1): string {
  const n = safeNumber(value);
  return `${n >= 0 ? "+" : ""}${n.toFixed(decimals)}%`;
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr + "T00:00:00").toLocaleDateString("en-US", {
      month: "short",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

export function formatDateFull(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr + "T00:00:00").toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

export function monthKey(date: string | null | undefined): string | null {
  if (!date) return null;
  return date.slice(0, 7);
}

export function monthLabel(yyyyMM: string): string {
  try {
    const [y, m] = yyyyMM.split("-").map(Number);
    return new Date(y, m - 1, 1).toLocaleString("default", { month: "short", year: "2-digit" });
  } catch {
    return yyyyMM;
  }
}

// ── Safe coercions ────────────────────────────────────────────────────────────

export function safeNumber(value: unknown): number {
  if (typeof value === "number" && isFinite(value)) return value;
  if (typeof value === "string") {
    const n = parseFloat(value.replace(/[$,]/g, ""));
    if (isFinite(n)) return n;
  }
  return 0;
}

export function safeArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

// ── Date utilities ────────────────────────────────────────────────────────────

export function getLatestDate(items: Array<{ date?: string | null } | string | null | undefined>): string | null {
  const dates = items
    .map((item) => (typeof item === "string" ? item : item?.date ?? null))
    .filter(Boolean) as string[];
  if (dates.length === 0) return null;
  return dates.sort((a, b) => b.localeCompare(a))[0];
}

export function lastNMonths(n: number): string[] {
  const result: string[] = [];
  const now = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    result.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return result;
}

// ── Data freshness ────────────────────────────────────────────────────────────

export type FreshnessStatus = "fresh" | "stale" | "missing";

export function getDataFreshnessStatus(latestDate: string | null | undefined): FreshnessStatus {
  if (!latestDate) return "missing";
  try {
    const latest = new Date(latestDate);
    const now = new Date();
    const diffDays = (now.getTime() - latest.getTime()) / (1000 * 60 * 60 * 24);
    if (diffDays <= 45) return "fresh";
    if (diffDays <= 90) return "stale";
    return "missing";
  } catch {
    return "missing";
  }
}

export function getMissingDataMessage(context: string): string {
  return `No ${context} data found. Upload or reprocess statements to populate this section.`;
}

// ── Trend computation ─────────────────────────────────────────────────────────

export interface TrendResult {
  pct: number | null;
  direction: "up" | "down" | "flat" | "unknown";
  label: string;
}

export function computeTrend(current: number, previous: number): TrendResult {
  if (previous === 0) return { pct: null, direction: "unknown", label: "—" };
  const pct = ((current - previous) / Math.abs(previous)) * 100;
  const direction = pct > 1 ? "up" : pct < -1 ? "down" : "flat";
  const sign = pct >= 0 ? "+" : "";
  return { pct, direction, label: `${sign}${pct.toFixed(1)}% vs last month` };
}
