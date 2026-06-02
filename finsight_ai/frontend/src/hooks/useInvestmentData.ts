import { useEffect, useState, useCallback } from "react";
import { dashboardApi } from "../api/dashboard";
import type { InvestmentsDashboard, AccountBalance, Holding } from "../api/dashboard";
import { calculateInvestmentTotals, type InvestmentTotals } from "../lib/financeDataAdapters";
import { isIRAAccount } from "../lib/accountMapping";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface DataFreshness {
  institutionKey: string;
  displayName: string;
  latestStatement: string | null;
  isMissing: boolean;
  warningMessage: string | null;
}

export interface InvestmentDataResult {
  loading: boolean;
  error: string | null;
  raw: InvestmentsDashboard | null;
  accounts: AccountBalance[];
  iraAccounts: AccountBalance[];
  holdings: Holding[];
  totals: InvestmentTotals;
  dataFreshness: DataFreshness[];
  hasData: boolean;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

const EMPTY_TOTALS: InvestmentTotals = {
  combined: 0,
  institutions: [],
  iraTotal: 0,
  asOf: null,
};

export function useInvestmentData(): InvestmentDataResult {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [raw, setRaw] = useState<InvestmentsDashboard | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await dashboardApi.investments();
      setRaw(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load investment data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (!raw) {
    return {
      loading,
      error,
      raw: null,
      accounts: [],
      iraAccounts: [],
      holdings: [],
      totals: EMPTY_TOTALS,
      dataFreshness: buildFreshness([]),
      hasData: false,
    };
  }

  const accounts = raw.portfolio_summary.accounts ?? [];
  const iraAccounts = accounts.filter((a) =>
    isIRAAccount(a.account_name, a.account_type),
  );

  const totals = calculateInvestmentTotals(
    accounts.map((a) => ({
      account_name: a.account_name,
      account_type: a.account_type,
      institution_type: a.institution_type,
      total_value: a.total_value,
      total_value_fmt: a.total_value_fmt,
      snapshot_date: a.snapshot_date,
      latest_statement_date: a.latest_statement_date,
    })),
  );

  return {
    loading,
    error,
    raw,
    accounts,
    iraAccounts,
    holdings: raw.top_holdings ?? [],
    totals,
    dataFreshness: buildFreshness(raw.coverage ?? []),
    hasData: accounts.length > 0,
  };
}

function buildFreshness(coverage: InvestmentsDashboard["coverage"]): DataFreshness[] {
  const known = [
    { key: "morgan_stanley", displayName: "Morgan Stanley" },
    { key: "etrade", displayName: "E*TRADE" },
  ];
  return known.map(({ key, displayName }) => {
    const cov = coverage.find(
      (c) => (c.institution_type ?? "").toLowerCase().replace(/[\s*-]/g, "") === key.replace(/_/g, ""),
    );
    const latestStatement = cov?.latest_statement ?? null;
    const isMissing = !latestStatement;
    return {
      institutionKey: key,
      displayName,
      latestStatement,
      isMissing,
      warningMessage: isMissing
        ? `No ${displayName} statements found. Upload statements to see portfolio data.`
        : null,
    };
  });
}
