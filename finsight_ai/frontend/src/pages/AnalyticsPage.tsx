/**
 * AnalyticsPage — Phase 5 bucket-aware analytics dashboard.
 *
 * Layout:
 *   BucketSwitcher (INVESTMENTS | BANKING)
 *     ↓
 *   InvestmentsView  or  BankingView
 *
 * Investments view:
 *   - Portfolio value card + period changes
 *   - Account allocation list (with % bars)
 *   - Holdings table
 *   - Fee trend bar chart (simple bars)
 *
 * Banking view:
 *   - Total spend card
 *   - Spend by category (horizontal bars)
 *   - Top merchants table
 *   - Subscription list
 *   - Credit card balances
 *   - Checking in/out summary
 *
 * Partial data → yellow "Partial data" banner with warnings.
 * Empty data   → empty state with descriptive message.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart2,
  CreditCard,
  DollarSign,
  Loader2,
  RefreshCw,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { clsx } from "clsx";
import { investmentsApi, bankingApi } from "../api/analytics";
import type {
  AccountSummary,
  AnalyticsEnvelope,
  BankingOverview,
  BucketKind,
  CardBalance,
  HoldingRow,
  InvestmentsOverview,
  MerchantSpend,
  PeriodChange,
  Subscription,
} from "../types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(value: string | null | undefined, prefix = "$"): string {
  if (!value) return "—";
  const n = parseFloat(value);
  if (isNaN(n)) return value;
  return `${prefix}${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(value: string | null | undefined): string {
  if (!value) return "—";
  return `${parseFloat(value).toFixed(1)}%`;
}

function monthName(month: number): string {
  return new Date(2000, month - 1, 1).toLocaleString("en-US", { month: "short" });
}

// ---------------------------------------------------------------------------
// Shared components
// ---------------------------------------------------------------------------

function MetricCard({
  label,
  value,
  sub,
  icon: Icon,
  accent = "blue",
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ElementType;
  accent?: "blue" | "green" | "amber" | "purple";
}) {
  const colors: Record<string, string> = {
    blue: "bg-blue-50 text-blue-600",
    green: "bg-green-50 text-green-600",
    amber: "bg-amber-50 text-amber-600",
    purple: "bg-purple-50 text-purple-600",
  };
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
          <p className="text-2xl font-bold text-gray-900 tabular-nums mt-1">{value}</p>
          {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
        </div>
        <div className={clsx("p-2 rounded-lg", colors[accent])}>
          <Icon size={18} />
        </div>
      </div>
    </div>
  );
}

function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <h2 className="text-sm font-semibold text-gray-800">{title}</h2>
      {count != null && (
        <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
          {count}
        </span>
      )}
    </div>
  );
}

function PartialBanner({ warnings }: { warnings: string[] }) {
  if (!warnings.length) return null;
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 mb-4">
      <div className="flex items-start gap-2">
        <AlertTriangle size={15} className="text-amber-600 shrink-0 mt-0.5" />
        <div>
          <p className="text-xs font-semibold text-amber-800">Partial data</p>
          <ul className="mt-1 space-y-0.5">
            {warnings.map((w, i) => (
              <li key={i} className="text-xs text-amber-700">{w}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
      <BarChart2 size={36} className="text-gray-300" />
      <p className="text-sm text-gray-500">{message}</p>
      <p className="text-xs text-gray-400">Upload statements to see analytics here.</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center py-16">
      <Loader2 size={24} className="animate-spin text-blue-500" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Investments sub-components
// ---------------------------------------------------------------------------

function AccountAllocationList({ accounts }: { accounts: AccountSummary[] }) {
  if (!accounts.length) return <p className="text-xs text-gray-400">No accounts found.</p>;
  const max = Math.max(...accounts.map((a) => parseFloat(a.portfolio_pct) || 0), 1);
  return (
    <div className="space-y-3">
      {accounts.map((acc) => {
        const pct = parseFloat(acc.portfolio_pct) || 0;
        const barWidth = Math.round((pct / max) * 100);
        return (
          <div key={acc.account_id}>
            <div className="flex items-center justify-between mb-1">
              <div>
                <span className="text-xs font-medium text-gray-700">{acc.account_name}</span>
                <span className="text-xs text-gray-400 ml-1.5">{acc.institution}</span>
              </div>
              <span className="text-xs tabular-nums font-semibold text-gray-800">
                {fmt(acc.current_value)}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1 bg-gray-100 rounded-full h-1.5 overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full"
                  style={{ width: `${barWidth}%` }}
                />
              </div>
              <span className="text-xs text-gray-400 w-10 text-right">{fmtPct(acc.portfolio_pct)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PeriodChangeCards({ changes }: { changes: PeriodChange[] }) {
  if (!changes.length) return null;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {changes.map((c) => {
        const isUp = c.change_amount && parseFloat(c.change_amount) >= 0;
        return (
          <div
            key={c.account_id}
            className="bg-white border border-gray-200 rounded-xl p-3"
          >
            <p className="text-xs text-gray-500">{c.account_name}</p>
            <p className="text-xs text-gray-400 mb-1">{c.institution}</p>
            <div className="flex items-end gap-2">
              <span className="text-lg font-bold tabular-nums text-gray-900">
                {fmt(c.current_value)}
              </span>
              {c.change_pct && (
                <span
                  className={clsx(
                    "flex items-center gap-0.5 text-xs font-semibold mb-0.5",
                    isUp ? "text-green-600" : "text-red-500"
                  )}
                >
                  {isUp ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                  {fmtPct(c.change_pct)}
                </span>
              )}
            </div>
            {c.period_end && (
              <p className="text-xs text-gray-400 mt-0.5">as of {c.period_end}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function HoldingsTable({ holdings }: { holdings: HoldingRow[] }) {
  if (!holdings.length)
    return <p className="text-xs text-gray-400 py-4 text-center">No holdings found.</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-gray-50">
            {["Symbol", "Description", "Market Value", "Unrealized G/L", "Asset Class", "Account"].map(
              (col) => (
                <th key={col} className="px-3 py-2 text-left font-medium text-gray-500 whitespace-nowrap">
                  {col}
                </th>
              )
            )}
          </tr>
        </thead>
        <tbody>
          {holdings.slice(0, 25).map((h, i) => (
            <tr key={i} className={clsx("border-t border-gray-50", i % 2 === 0 ? "bg-white" : "bg-gray-50/40")}>
              <td className="px-3 py-2 font-mono font-semibold text-gray-800">
                {h.symbol ?? "—"}
              </td>
              <td className="px-3 py-2 text-gray-700 max-w-[200px] truncate">{h.description}</td>
              <td className="px-3 py-2 tabular-nums font-medium text-gray-900">
                {fmt(h.market_value)}
              </td>
              <td className="px-3 py-2 tabular-nums">
                {h.unrealized_gain_loss ? (
                  <span
                    className={clsx(
                      "font-medium",
                      parseFloat(h.unrealized_gain_loss) >= 0 ? "text-green-600" : "text-red-500"
                    )}
                  >
                    {fmt(h.unrealized_gain_loss)}
                    {h.unrealized_pct && ` (${fmtPct(h.unrealized_pct)})`}
                  </span>
                ) : (
                  "—"
                )}
              </td>
              <td className="px-3 py-2 text-gray-500">{h.asset_class ?? "—"}</td>
              <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{h.account_name}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {holdings.length > 25 && (
        <p className="text-xs text-gray-400 text-center py-2">
          Showing 25 of {holdings.length} holdings
        </p>
      )}
    </div>
  );
}

function FeeTrendChart({ feeTrend }: { feeTrend: InvestmentsOverview["fee_trend"] }) {
  if (!feeTrend.length) return <p className="text-xs text-gray-400">No fee data.</p>;
  const maxFee = Math.max(...feeTrend.map((f) => parseFloat(f.total_fees) || 0), 1);
  return (
    <div className="flex items-end gap-1.5 h-20">
      {feeTrend.map((f) => {
        const height = Math.round(((parseFloat(f.total_fees) || 0) / maxFee) * 100);
        return (
          <div key={`${f.year}-${f.month}`} className="flex flex-col items-center flex-1 gap-1">
            <div className="w-full bg-gray-100 rounded-sm relative" style={{ height: "56px" }}>
              <div
                className="absolute bottom-0 left-0 right-0 bg-amber-400 rounded-sm"
                style={{ height: `${height}%` }}
                title={fmt(f.total_fees)}
              />
            </div>
            <span className="text-[10px] text-gray-400">{monthName(f.month)}</span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Investments view
// ---------------------------------------------------------------------------

function InvestmentsView({ overview }: { overview: InvestmentsOverview }) {
  const totalVal = fmt(overview.total_portfolio_value);

  return (
    <div className="space-y-6">
      {/* Top metric */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard
          label="Total Portfolio Value"
          value={totalVal}
          icon={TrendingUp}
          accent="blue"
        />
        <MetricCard
          label="Accounts"
          value={String(overview.accounts.length)}
          sub="investment accounts"
          icon={Wallet}
          accent="purple"
        />
        <MetricCard
          label="Holdings"
          value={String(overview.holdings_breakdown.length)}
          sub="positions tracked"
          icon={BarChart2}
          accent="green"
        />
      </div>

      {/* Period changes */}
      {overview.period_changes.length > 0 && (
        <section>
          <SectionHeader title="What changed this statement" count={overview.period_changes.length} />
          <PeriodChangeCards changes={overview.period_changes} />
        </section>
      )}

      {/* Account allocation */}
      <section>
        <SectionHeader title="Account allocation" count={overview.accounts.length} />
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <AccountAllocationList accounts={overview.accounts} />
        </div>
      </section>

      {/* Holdings table */}
      {overview.holdings_breakdown.length > 0 && (
        <section>
          <SectionHeader title="Holdings breakdown" count={overview.holdings_breakdown.length} />
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <HoldingsTable holdings={overview.holdings_breakdown} />
          </div>
        </section>
      )}

      {/* Fee trend */}
      {overview.fee_trend.length > 0 && (
        <section>
          <SectionHeader title="Fee trend" />
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <FeeTrendChart feeTrend={overview.fee_trend} />
          </div>
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Banking sub-components
// ---------------------------------------------------------------------------

function CategoryBars({ categories }: { categories: Record<string, string> }) {
  const entries = Object.entries(categories).slice(0, 10);
  if (!entries.length) return <p className="text-xs text-gray-400">No spending data.</p>;
  const max = Math.max(...entries.map(([, v]) => parseFloat(v) || 0), 1);
  return (
    <div className="space-y-2">
      {entries.map(([cat, val]) => {
        const pct = Math.round(((parseFloat(val) || 0) / max) * 100);
        return (
          <div key={cat} className="flex items-center gap-3">
            <span className="text-xs text-gray-600 w-28 shrink-0 capitalize">
              {cat.replace(/_/g, " ").toLowerCase()}
            </span>
            <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs tabular-nums font-semibold text-gray-800 w-20 text-right">
              {fmt(val)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function MerchantTable({ merchants }: { merchants: MerchantSpend[] }) {
  if (!merchants.length) return <p className="text-xs text-gray-400 py-4 text-center">No merchant data.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-gray-50">
            {["Merchant", "Category", "Total Spend", "# Transactions"].map((col) => (
              <th key={col} className="px-3 py-2 text-left font-medium text-gray-500">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {merchants.slice(0, 20).map((m, i) => (
            <tr key={i} className={clsx("border-t border-gray-50", i % 2 === 0 ? "bg-white" : "bg-gray-50/40")}>
              <td className="px-3 py-2 font-medium text-gray-800">{m.merchant_name}</td>
              <td className="px-3 py-2 text-gray-500 capitalize">
                {m.category?.replace(/_/g, " ").toLowerCase() ?? "—"}
              </td>
              <td className="px-3 py-2 tabular-nums font-semibold text-gray-900">{fmt(m.total_amount)}</td>
              <td className="px-3 py-2 text-gray-500">{m.transaction_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SubscriptionList({ subscriptions }: { subscriptions: Subscription[] }) {
  if (!subscriptions.length)
    return <p className="text-xs text-gray-400 py-2">No recurring subscriptions detected.</p>;
  return (
    <div className="space-y-2">
      {subscriptions.map((s, i) => (
        <div
          key={i}
          className="flex items-center justify-between px-3 py-2 bg-white rounded-lg border border-gray-100"
        >
          <div>
            <p className="text-xs font-medium text-gray-800">{s.merchant_name}</p>
            <p className="text-xs text-gray-400">
              Every ~{s.frequency_days}d · Last {s.last_charged}
              {s.category && ` · ${s.category.replace(/_/g, " ").toLowerCase()}`}
            </p>
          </div>
          <span className="text-xs font-bold tabular-nums text-gray-900">{fmt(s.typical_amount)}</span>
        </div>
      ))}
    </div>
  );
}

function CardBalanceList({ balances }: { balances: CardBalance[] }) {
  if (!balances.length)
    return <p className="text-xs text-gray-400">No credit card balances found.</p>;
  return (
    <div className="space-y-2">
      {balances.map((cb, i) => (
        <div key={i} className="flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-gray-700">{cb.account_name}</p>
            <p className="text-xs text-gray-400">{cb.institution}</p>
          </div>
          <span className="text-sm font-bold tabular-nums text-gray-900">
            {fmt(cb.current_balance)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Banking view
// ---------------------------------------------------------------------------

function BankingView({ overview }: { overview: BankingOverview }) {
  const cs = overview.checking_summary;
  const net = parseFloat(cs.net);
  const netPositive = net >= 0;

  return (
    <div className="space-y-6">
      {/* Top metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard
          label="Total Spend This Month"
          value={fmt(overview.total_spend_this_month)}
          icon={DollarSign}
          accent="amber"
        />
        <MetricCard
          label="Credit Card Balances"
          value={
            overview.credit_card_balances.length > 0
              ? fmt(
                  String(
                    overview.credit_card_balances.reduce(
                      (acc, cb) => acc + parseFloat(cb.current_balance || "0"),
                      0
                    )
                  )
                )
              : "—"
          }
          sub={`${overview.credit_card_balances.length} card(s)`}
          icon={CreditCard}
          accent="purple"
        />
        <MetricCard
          label="Checking Net"
          value={fmt(cs.net)}
          sub={netPositive ? "Net inflow" : "Net outflow"}
          icon={netPositive ? ArrowUpRight : ArrowDownRight}
          accent={netPositive ? "green" : "amber"}
        />
      </div>

      {/* Spend by category */}
      <section>
        <SectionHeader
          title="Spend by category"
          count={Object.keys(overview.spend_by_category).length}
        />
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <CategoryBars categories={overview.spend_by_category} />
        </div>
      </section>

      {/* Top merchants */}
      {overview.spend_by_merchant.length > 0 && (
        <section>
          <SectionHeader title="Top merchants" count={overview.spend_by_merchant.length} />
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <MerchantTable merchants={overview.spend_by_merchant} />
          </div>
        </section>
      )}

      {/* Subscriptions */}
      <section>
        <SectionHeader title="Recurring subscriptions" count={overview.subscriptions.length} />
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <SubscriptionList subscriptions={overview.subscriptions} />
        </div>
      </section>

      {/* Credit card balances */}
      {overview.credit_card_balances.length > 0 && (
        <section>
          <SectionHeader title="Credit card balances" count={overview.credit_card_balances.length} />
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <CardBalanceList balances={overview.credit_card_balances} />
          </div>
        </section>
      )}

      {/* Checking in/out */}
      <section>
        <SectionHeader title="Checking cash flow" />
        <div className="bg-white border border-gray-200 rounded-xl p-4 grid grid-cols-3 gap-4 text-center">
          {[
            { label: "Inflows", value: cs.total_inflows, color: "text-green-600" },
            { label: "Outflows", value: cs.total_outflows, color: "text-red-500" },
            { label: "Net", value: cs.net, color: netPositive ? "text-green-600" : "text-red-500" },
          ].map(({ label, value, color }) => (
            <div key={label}>
              <p className="text-xs text-gray-500 mb-1">{label}</p>
              <p className={clsx("text-base font-bold tabular-nums", color)}>{fmt(value)}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Unusual transactions */}
      {overview.unusual_transactions.length > 0 && (
        <section>
          <SectionHeader
            title="Unusual transactions (>2σ)"
            count={overview.unusual_transactions.length}
          />
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50">
                  {["Date", "Merchant", "Category", "Amount"].map((col) => (
                    <th key={col} className="px-3 py-2 text-left font-medium text-gray-500">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {overview.unusual_transactions.map((tx, i) => (
                  <tr key={i} className={clsx("border-t border-gray-50", i % 2 === 0 ? "bg-white" : "bg-gray-50/40")}>
                    <td className="px-3 py-2 text-gray-500">{String(tx.transaction_date)}</td>
                    <td className="px-3 py-2 font-medium text-gray-800">{tx.merchant_name || tx.description}</td>
                    <td className="px-3 py-2 text-gray-500 capitalize">
                      {tx.category?.replace(/_/g, " ").toLowerCase() ?? "—"}
                    </td>
                    <td className="px-3 py-2 tabular-nums font-bold text-amber-700">
                      {fmt(tx.spend_amount ?? tx.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// BucketSwitcher
// ---------------------------------------------------------------------------

function BucketSwitcher({
  active,
  onChange,
}: {
  active: BucketKind;
  onChange: (kind: BucketKind) => void;
}) {
  return (
    <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
      {(["investments", "banking"] as BucketKind[]).map((kind) => (
        <button
          key={kind}
          onClick={() => onChange(kind)}
          className={clsx(
            "px-4 py-1.5 rounded-md text-sm font-medium transition-colors capitalize",
            active === kind
              ? "bg-white text-gray-900 shadow-sm"
              : "text-gray-500 hover:text-gray-700"
          )}
        >
          {kind}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function AnalyticsPage() {
  const [bucket, setBucket] = useState<BucketKind>("investments");
  const [loading, setLoading] = useState(false);
  const [invOverview, setInvOverview] = useState<AnalyticsEnvelope<InvestmentsOverview> | null>(null);
  const [bankOverview, setBankOverview] = useState<AnalyticsEnvelope<BankingOverview> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadInvestments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await investmentsApi.getOverview();
      setInvOverview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load investments data.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadBanking = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await bankingApi.getOverview();
      setBankOverview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load banking data.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Load data when bucket changes
  useEffect(() => {
    if (bucket === "investments" && !invOverview) {
      loadInvestments();
    } else if (bucket === "banking" && !bankOverview) {
      loadBanking();
    }
  }, [bucket, invOverview, bankOverview, loadInvestments, loadBanking]);

  const handleRefresh = () => {
    if (bucket === "investments") {
      setInvOverview(null);
      loadInvestments();
    } else {
      setBankOverview(null);
      loadBanking();
    }
  };

  const currentEnvelope = bucket === "investments" ? invOverview : bankOverview;
  const warnings = currentEnvelope?.warnings ?? [];
  const partial = currentEnvelope?.partial ?? false;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Analytics</h1>
          <p className="text-xs text-gray-400 mt-0.5">Powered by local data — fully private</p>
        </div>
        <div className="flex items-center gap-3">
          <BucketSwitcher active={bucket} onChange={setBucket} />
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Partial data warning */}
      {partial && <PartialBanner warnings={warnings} />}

      {/* Content */}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading && <LoadingState />}

      {!loading && !error && bucket === "investments" && (
        <>
          {invOverview && invOverview.data.total_portfolio_value !== "0" ? (
            <InvestmentsView overview={invOverview.data} />
          ) : invOverview ? (
            <EmptyState message="No investment data found." />
          ) : null}
        </>
      )}

      {!loading && !error && bucket === "banking" && (
        <>
          {bankOverview && parseFloat(bankOverview.data.total_spend_this_month) > 0 ? (
            <BankingView overview={bankOverview.data} />
          ) : bankOverview ? (
            <EmptyState message="No banking data found." />
          ) : null}
        </>
      )}
    </div>
  );
}
