export interface AccountValueSnapshot {
  account_id: string;
  account_name: string;
  institution: string;
  institution_type: string;
  account_type: string;
  domain: "banking" | "investments";
  snapshot_date: string;
  value: number;
  currency?: string;
  source_statement_id?: string | null;
  source_type?: string | null;
  latest_statement_month?: string | null;
  status?: string | null;
}

export interface AccountValuePoint {
  month: string;
  monthLabel: string;
  date: string;
  value: number;
}

export interface AccountValueSeries {
  accountId: string;
  accountName: string;
  institution: string;
  institutionType: string;
  accountType: string;
  domain: "banking" | "investments";
  currency: string;
  points: AccountValuePoint[];
  latest: AccountValuePoint | null;
  previous: AccountValuePoint | null;
  change: number | null;
  changePct: number | null;
  latestStatementMonth: string | null;
  status: string | null;
}

export interface AccountValueDataset {
  accounts: AccountValueSeries[];
  months: string[];
  totalLatestValue: number;
  totalPreviousValue: number | null;
  totalChange: number | null;
  totalChangePct: number | null;
}

function monthKey(date: string) {
  return date.slice(0, 7);
}

export function formatMonthLabel(month: string) {
  const [year, monthNumber] = month.split("-").map(Number);
  return new Date(year, monthNumber - 1, 1).toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
  });
}

export function formatShortMonthLabel(month: string) {
  const [year, monthNumber] = month.split("-").map(Number);
  return new Date(year, monthNumber - 1, 1).toLocaleDateString("en-US", {
    month: "short",
    year: "2-digit",
  });
}

function accountKey(snapshot: AccountValueSnapshot) {
  return snapshot.account_id || [
    snapshot.domain,
    snapshot.institution_type,
    snapshot.account_name,
    snapshot.account_type,
  ].join(":");
}

export function buildAccountValueDataset(
  snapshots: AccountValueSnapshot[],
): AccountValueDataset {
  const byAccount = new Map<string, AccountValueSnapshot[]>();

  for (const snapshot of snapshots) {
    if (!Number.isFinite(snapshot.value)) continue;
    const key = accountKey(snapshot);
    byAccount.set(key, [...(byAccount.get(key) ?? []), snapshot]);
  }

  const accounts = Array.from(byAccount.entries()).map(([key, rows]) => {
    const byMonth = new Map<string, AccountValueSnapshot>();
    for (const row of rows) {
      const month = monthKey(row.snapshot_date);
      const existing = byMonth.get(month);
      if (!existing || row.snapshot_date > existing.snapshot_date) {
        byMonth.set(month, row);
      }
    }

    const points = Array.from(byMonth.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([month, row]) => ({
        month,
        monthLabel: formatShortMonthLabel(month),
        date: row.snapshot_date,
        value: row.value,
      }));

    const first = rows[0];
    const latest = points.at(-1) ?? null;
    const previous = points.length >= 2 ? points[points.length - 2] : null;
    const change = latest && previous ? latest.value - previous.value : null;
    const changePct = latest && previous && previous.value !== 0
      ? (change! / previous.value) * 100
      : null;
    const latestSource = latest
      ? rows.find((row) => row.snapshot_date === latest.date)
      : null;

    return {
      accountId: key,
      accountName: first.account_name,
      institution: first.institution,
      institutionType: first.institution_type,
      accountType: first.account_type,
      domain: first.domain,
      currency: first.currency ?? "USD",
      points,
      latest,
      previous,
      change,
      changePct,
      latestStatementMonth: latestSource?.latest_statement_month ?? latest?.month ?? null,
      status: latestSource?.status ?? null,
    } satisfies AccountValueSeries;
  }).sort((a, b) => {
    const bValue = b.latest?.value ?? 0;
    const aValue = a.latest?.value ?? 0;
    return bValue - aValue || a.accountName.localeCompare(b.accountName);
  });

  const months = Array.from(new Set(accounts.flatMap((account) => (
    account.points.map((point) => point.month)
  )))).sort();

  const totalLatestValue = accounts.reduce((sum, account) => sum + (account.latest?.value ?? 0), 0);
  const accountsWithPrevious = accounts.filter((account) => account.latest && account.previous);
  const totalPreviousValue = accountsWithPrevious.length === accounts.length && accounts.length > 0
    ? accounts.reduce((sum, account) => sum + (account.previous?.value ?? 0), 0)
    : null;
  const totalChange = totalPreviousValue === null ? null : totalLatestValue - totalPreviousValue;
  const totalChangePct = totalPreviousValue && totalPreviousValue !== 0
    ? (totalChange! / totalPreviousValue) * 100
    : null;

  return {
    accounts,
    months,
    totalLatestValue,
    totalPreviousValue,
    totalChange,
    totalChangePct,
  };
}

