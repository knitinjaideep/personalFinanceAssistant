"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Sparkles,
  Upload,
  TrendingUp,
} from "lucide-react";
import {
  AccountValueLegend,
  AccountValueSummaryCard,
  AccountValueTable,
  AccountValueTrendChart,
  AccountValueViewToggle,
  ExpandedAccountDetail,
  colorFor,
  type AccountValueViewMode,
} from "@/components/account-value/AccountValueExperience";
import CoralMascot from "@/components/coral/CoralMascot";
import EmptyState from "@/components/coral/EmptyState";
import ErrorState from "@/components/coral/ErrorState";
import GlassCard from "@/components/coral/GlassCard";
import SectionHeader from "@/components/coral/SectionHeader";
import FinancialPeriodSelector from "@/components/coral-ds/FinancialPeriodSelector";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import Surface from "@/components/coral-ds/Surface";
import {
  investmentsApi,
  type Holding,
  type InvestmentsDashboard,
} from "@/features/investments/api";
import { useFinancialPeriod } from "@/hooks/useFinancialPeriod";
import { buildAccountValueDataset, type AccountValueSnapshot } from "@/lib/accountValue";
import { formatCurrency } from "@/lib/utils";
import { useAppStore } from "@/store/appStore";

const INSIGHT_PROMPTS = [
  "Which account moved my portfolio most?",
  "Where is my portfolio concentrated?",
  "Review my portfolio concentration.",
  "Compare my IRA balances over time.",
];

function investmentAccountSnapshots(data: InvestmentsDashboard | null): AccountValueSnapshot[] {
  if (!data) return [];
  const accountByName = new Map(data.portfolio_summary.accounts.map((account) => [
    account.account_name,
    account,
  ]));
  return data.balance_history.map((point) => {
    const account = accountByName.get(point.account_name);
    return {
      account_id: `${point.institution_type}:${point.account_name}`,
      account_name: point.account_name,
      institution: point.institution_type.replace(/_/g, " "),
      institution_type: point.institution_type,
      account_type: account?.account_type ?? "investment",
      domain: "investments",
      snapshot_date: point.date,
      value: point.total_value,
      currency: "USD",
      source_type: "balance_snapshot",
      latest_statement_month: account?.latest_statement_date?.slice(0, 7) ?? point.date.slice(0, 7),
      status: "complete",
    };
  });
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

function PortfolioIntelligence({
  data,
  dataset,
}: {
  data: InvestmentsDashboard | null;
  dataset: ReturnType<typeof buildAccountValueDataset>;
}) {
  if (!data || dataset.accounts.length === 0) return null;

  const totalValue = dataset.totalLatestValue;
  const largestAccount = [...(data.allocation ?? [])].sort((a, b) => (
    b.pct_of_portfolio - a.pct_of_portfolio
  ))[0] ?? null;
  const largestHolding = data.top_holdings.find((holding) => (
    holding.portfolio_weight !== null && holding.portfolio_weight !== undefined
  )) ?? null;
  const cashTotal = data.portfolio_summary.accounts.reduce((sum, account) => (
    sum + (account.cash_value ?? 0)
  ), 0);
  const cashPct = totalValue > 0 ? (cashTotal / totalValue) * 100 : null;
  const biggestMover = [...dataset.accounts]
    .filter((account) => account.change !== null)
    .sort((a, b) => Math.abs(b.change ?? 0) - Math.abs(a.change ?? 0))[0] ?? null;
  const healthRows = buildHealthRows(data);

  const facts = [
    largestAccount ? {
      label: "Largest account",
      value: largestAccount.account_name,
      detail: `${largestAccount.pct_of_portfolio.toFixed(1)}% of imported portfolio`,
      tone: largestAccount.pct_of_portfolio >= 70 ? "warning" as const : "good" as const,
    } : null,
    largestHolding ? {
      label: "Largest holding",
      value: largestHolding.symbol || largestHolding.description,
      detail: `${largestHolding.portfolio_weight?.toFixed(1)}% of imported holdings`,
      tone: (largestHolding.portfolio_weight ?? 0) >= 25 ? "warning" as const : "good" as const,
    } : null,
    {
      label: "Cash position",
      value: formatCurrency(cashTotal),
      detail: cashPct === null ? "Cash share unavailable" : `${cashPct.toFixed(1)}% of portfolio is cash`,
      tone: cashTotal > 0 ? "neutral" as const : "good" as const,
    },
    biggestMover ? {
      label: "Biggest monthly move",
      value: biggestMover.accountName,
      detail: `${biggestMover.change! >= 0 ? "+" : "-"}${formatCurrency(Math.abs(biggestMover.change!))} vs prior snapshot`,
      tone: biggestMover.change! >= 0 ? "good" as const : "warning" as const,
    } : null,
  ].filter((fact): fact is NonNullable<typeof fact> => fact !== null);

  return (
    <section>
      <SectionHeader
        eyebrow="Portfolio intelligence"
        title="What Coral Can Trust From Your Statements"
        description="Insights below use imported portfolio balances, allocation, cash, and holdings only."
        size="sm"
        className="mb-5"
      />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        <Surface padding="lg" className="relative overflow-hidden">
          <div
            className="absolute -right-16 -top-20 h-52 w-52 rounded-full opacity-30 blur-3xl"
            style={{ background: "var(--financial-investments-soft)" }}
          />
          <div className="relative">
            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="micro-text font-bold uppercase tracking-[0.18em] text-financial-investments">
                  Statement-backed
                </p>
                <h2 className="mt-2 text-3xl font-black tracking-normal" style={{ color: "var(--text-primary)" }}>
                  Portfolio Snapshot
                </h2>
                <p className="mt-2 max-w-xl small-text" style={{ color: "var(--text-muted)" }}>
                  No contribution targets, no uncategorized-transfer math. Just the reliable investment facts Coral imported.
                </p>
              </div>
              <div className="rounded-3xl bg-white/70 px-5 py-4 text-right ring-1 ring-slate-200/80">
                <p className="micro-text font-bold uppercase tracking-[0.16em]" style={{ color: "var(--text-muted)" }}>
                  Imported value
                </p>
                <p className="mt-1 text-3xl font-black tabular-nums" style={{ color: "var(--text-primary)" }}>
                  {formatCurrency(totalValue)}
                </p>
                {dataset.totalChange !== null && (
                  <p
                    className="mt-1 small-text font-bold tabular-nums"
                    style={{ color: dataset.totalChange >= 0 ? "var(--status-good)" : "var(--status-danger)" }}
                  >
                    {dataset.totalChange >= 0 ? "+" : "-"}
                    {formatCurrency(Math.abs(dataset.totalChange))} vs prior snapshot
                  </p>
                )}
              </div>
            </div>

            <div className="mt-7 grid gap-3 md:grid-cols-2">
              {facts.map((fact) => (
                <div
                  key={fact.label}
                  className="rounded-3xl bg-white/72 p-4 ring-1 ring-slate-200/80"
                >
                  <div className="flex items-start gap-3">
                    <span
                      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl"
                      style={{
                        background: fact.tone === "warning" ? "var(--status-warning-soft)" : fact.tone === "good" ? "var(--status-good-soft)" : "var(--financial-investments-soft)",
                        color: fact.tone === "warning" ? "var(--status-warning)" : fact.tone === "good" ? "var(--status-good)" : "var(--financial-investments)",
                      }}
                    >
                      {fact.tone === "warning" ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
                    </span>
                    <div className="min-w-0">
                      <p className="micro-text font-bold uppercase tracking-[0.14em]" style={{ color: "var(--text-muted)" }}>
                        {fact.label}
                      </p>
                      <p className="mt-1 truncate text-lg font-black" style={{ color: "var(--text-primary)" }}>
                        {fact.value}
                      </p>
                      <p className="mt-1 micro-text" style={{ color: "var(--text-muted)" }}>
                        {fact.detail}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Surface>

        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-1">
          <PortfolioHealth data={data} />
          <AccountAllocation data={data} />
        </div>
      </div>
      {healthRows.length === 0 && (
        <p className="mt-3 micro-text" style={{ color: "var(--text-dim)" }}>
          Add holdings or allocation pages to unlock deeper concentration and cash-position insights.
        </p>
      )}
    </section>
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
  const [accountViewMode, setAccountViewMode] = useState<AccountValueViewMode>("line");
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
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

  useEffect(() => { loadDashboard(data !== null); }, [loadDashboard]);

  const retryAll = () => {
    loadDashboard(false);
  };

  const hasAnyData = !!data && (
    data.portfolio_summary.accounts.length > 0 || data.top_holdings.length > 0
  );
  const accountDataset = useMemo(
    () => buildAccountValueDataset(investmentAccountSnapshots(data)),
    [data],
  );
  const selectedAccount = accountDataset.accounts.find((account) => (
    account.accountId === selectedAccountId
  )) ?? null;
  const allocationByName = useMemo(() => new Map((data?.allocation ?? []).map((account) => [
    account.account_name,
    account.pct_of_portfolio,
  ])), [data?.allocation]);
  const holdingsByAccount = useMemo(() => {
    const counts = new Map<string, number>();
    for (const holding of data?.top_holdings ?? []) {
      counts.set(holding.account_name, (counts.get(holding.account_name) ?? 0) + 1);
    }
    return counts;
  }, [data?.top_holdings]);

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

  return (
    <div className="space-y-8">
      <section className="space-y-6">
        <div className="grid items-center gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.28em] text-blue-600">
              Portfolio
            </p>
            <h1 className="mt-3 text-5xl font-black tracking-normal text-slate-950 md:text-6xl">
              Investments
            </h1>
            <p className="mt-3 max-w-xl text-lg text-slate-600">
              See how your investment accounts change month by month.
            </p>
            <div className="mt-5">
              <FinancialPeriodSelector
                selection={selection}
                resolved={resolved}
                onChange={setSelection}
                onPrevMonth={goToPreviousMonth}
                onNextMonth={goToNextMonth}
                loading={refreshing}
              />
            </div>
          </div>

          <CoralMascot
            variant="investments"
            size="xl"
            priority
            speech="Portfolio detail lives here."
            className="mx-auto"
          />
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
                classification: selectedAccount.accountType.replace(/_/g, " "),
                shareOfTotal: allocationByName.get(selectedAccount.accountName) ?? null,
                holdingsSummary: holdingsByAccount.get(selectedAccount.accountName)
                  ? `${holdingsByAccount.get(selectedAccount.accountName)} top holdings imported`
                  : null,
              } : null}
            />
          </>
        ) : null}
      </section>

      <section
        className="rounded-[30px] bg-white/90 p-5 shadow-[0_20px_60px_rgba(30,70,110,0.10)] ring-1 ring-slate-200/80 md:p-6"
      >
        <div className="mb-5 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-black text-slate-950">Portfolio Account Value Trends</h2>
              <Info size={15} className="text-slate-400" />
            </div>
            <p className="mt-1 text-sm text-slate-600">Monthly account snapshots from imported statements</p>
          </div>
          <AccountValueViewToggle value={accountViewMode} onChange={setAccountViewMode} />
        </div>
        <div className="mb-4">
          <AccountValueLegend dataset={accountDataset} />
        </div>
        {accountViewMode === "line" ? (
          <AccountValueTrendChart
            dataset={accountDataset}
            height={430}
            selectedAccountId={selectedAccountId}
          />
        ) : (
          <AccountValueTable dataset={accountDataset} />
        )}
      </section>

      <PortfolioIntelligence data={data} dataset={accountDataset} />

      {loading && !data && (
        <SkeletonState variant="card" height="260px" />
      )}

      {error && !data && (
        <ErrorState
          message={error}
          onRetry={retryAll}
        />
      )}

      {!hasAnyData && (
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
              Deep-dive into portfolio movement, imported holdings, and account allocation.
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
