/**
 * HomePage — redesigned widget-based dashboard with analytics, upload, and document management.
 *
 * Features:
 *   - Bucket toggle (Investments / Banking)
 *   - Widget-based analytics cards
 *   - Drag-and-drop upload
 *   - Collapsible document list with delete action
 *   - Auto-refresh analytics after successful upload or deletion
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart2,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  CreditCard,
  DollarSign,
  File,
  Loader2,
  RefreshCw,
  Trash2,
  TrendingUp,
  UploadCloud,
  Wallet,
  XCircle,
} from "lucide-react";
import { clsx } from "clsx";
import { useDropzone } from "react-dropzone";
import { useAppStore } from "../store/appStore";
import { useDocuments } from "../hooks/useDocuments";
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
  StatementDocument,
  Subscription,
} from "../types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(value: string | null | undefined, prefix = "$"): string {
  if (!value) return "--";
  const n = parseFloat(value);
  if (isNaN(n)) return value;
  return `${prefix}${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(value: string | null | undefined): string {
  if (!value) return "--";
  return `${parseFloat(value).toFixed(1)}%`;
}

function monthName(month: number): string {
  return new Date(2000, month - 1, 1).toLocaleString("en-US", { month: "short" });
}

// ---------------------------------------------------------------------------
// Shared UI pieces
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
  accent?: "blue" | "green" | "amber" | "purple" | "red";
}) {
  const colors: Record<string, string> = {
    blue: "bg-blue-50 text-blue-600",
    green: "bg-green-50 text-green-600",
    amber: "bg-amber-50 text-amber-600",
    purple: "bg-purple-50 text-purple-600",
    red: "bg-red-50 text-red-500",
  };
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-sm transition-shadow">
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

function SectionHeader({ title, count, right }: { title: string; count?: number; right?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-gray-800">{title}</h2>
        {count != null && (
          <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
            {count}
          </span>
        )}
      </div>
      {right}
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

function SoftEmpty({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center gap-2">
      <BarChart2 size={36} className="text-gray-300" />
      <p className="text-sm text-gray-400">{message}</p>
      <p className="text-xs text-gray-300">Upload statements to see data here.</p>
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
// Investments widgets
// ---------------------------------------------------------------------------

function AccountAllocationList({ accounts }: { accounts: AccountSummary[] }) {
  if (!accounts.length) return null;
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
                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${barWidth}%` }} />
              </div>
              <span className="text-xs text-gray-400 w-10 text-right">{fmtPct(acc.portfolio_pct)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function HoldingsTable({ holdings }: { holdings: HoldingRow[] }) {
  if (!holdings.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-gray-50">
            {["Symbol", "Description", "Market Value", "Unrealized G/L", "Account"].map((col) => (
              <th key={col} className="px-3 py-2 text-left font-medium text-gray-500 whitespace-nowrap">{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {holdings.slice(0, 20).map((h, i) => (
            <tr key={i} className={clsx("border-t border-gray-50", i % 2 === 0 ? "bg-white" : "bg-gray-50/40")}>
              <td className="px-3 py-2 font-mono font-semibold text-gray-800">{h.symbol ?? "--"}</td>
              <td className="px-3 py-2 text-gray-700 max-w-[180px] truncate">{h.description}</td>
              <td className="px-3 py-2 tabular-nums font-medium text-gray-900">{fmt(h.market_value)}</td>
              <td className="px-3 py-2 tabular-nums">
                {h.unrealized_gain_loss ? (
                  <span className={clsx("font-medium", parseFloat(h.unrealized_gain_loss) >= 0 ? "text-green-600" : "text-red-500")}>
                    {fmt(h.unrealized_gain_loss)}
                  </span>
                ) : "--"}
              </td>
              <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{h.account_name}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {holdings.length > 20 && (
        <p className="text-xs text-gray-400 text-center py-2">Showing 20 of {holdings.length}</p>
      )}
    </div>
  );
}

function FeeTrendChart({ feeTrend }: { feeTrend: InvestmentsOverview["fee_trend"] }) {
  if (!feeTrend.length) return null;
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

function InvestmentsView({ overview }: { overview: InvestmentsOverview }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard label="Total Portfolio Value" value={fmt(overview.total_portfolio_value)} icon={TrendingUp} accent="blue" />
        <MetricCard label="Accounts" value={String(overview.accounts.length)} sub="investment accounts" icon={Wallet} accent="purple" />
        <MetricCard label="Holdings" value={String(overview.holdings_breakdown.length)} sub="positions tracked" icon={BarChart2} accent="green" />
      </div>

      {overview.period_changes.length > 0 && (
        <section>
          <SectionHeader title="Period changes" count={overview.period_changes.length} />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {overview.period_changes.map((c) => {
              const isUp = c.change_amount && parseFloat(c.change_amount) >= 0;
              return (
                <div key={c.account_id} className="bg-white border border-gray-200 rounded-xl p-3">
                  <p className="text-xs text-gray-500">{c.account_name}</p>
                  <div className="flex items-end gap-2">
                    <span className="text-lg font-bold tabular-nums text-gray-900">{fmt(c.current_value)}</span>
                    {c.change_pct && (
                      <span className={clsx("flex items-center gap-0.5 text-xs font-semibold mb-0.5", isUp ? "text-green-600" : "text-red-500")}>
                        {isUp ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                        {fmtPct(c.change_pct)}
                      </span>
                    )}
                  </div>
                  {c.period_end && <p className="text-xs text-gray-400 mt-0.5">as of {c.period_end}</p>}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {overview.accounts.length > 0 && (
        <section>
          <SectionHeader title="Account allocation" count={overview.accounts.length} />
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <AccountAllocationList accounts={overview.accounts} />
          </div>
        </section>
      )}

      {overview.holdings_breakdown.length > 0 && (
        <section>
          <SectionHeader title="Holdings" count={overview.holdings_breakdown.length} />
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <HoldingsTable holdings={overview.holdings_breakdown} />
          </div>
        </section>
      )}

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
// Banking widgets
// ---------------------------------------------------------------------------

function CategoryBars({ categories }: { categories: Record<string, string> }) {
  const entries = Object.entries(categories).slice(0, 10);
  if (!entries.length) return null;
  const max = Math.max(...entries.map(([, v]) => parseFloat(v) || 0), 1);
  return (
    <div className="space-y-2">
      {entries.map(([cat, val]) => {
        const pct = Math.round(((parseFloat(val) || 0) / max) * 100);
        return (
          <div key={cat} className="flex items-center gap-3">
            <span className="text-xs text-gray-600 w-28 shrink-0 capitalize">{cat.replace(/_/g, " ").toLowerCase()}</span>
            <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
              <div className="h-full bg-blue-500 rounded-full" style={{ width: `${pct}%` }} />
            </div>
            <span className="text-xs tabular-nums font-semibold text-gray-800 w-20 text-right">{fmt(val)}</span>
          </div>
        );
      })}
    </div>
  );
}

function MerchantTable({ merchants }: { merchants: MerchantSpend[] }) {
  if (!merchants.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-gray-50">
            {["Merchant", "Category", "Total Spend", "# Txns"].map((col) => (
              <th key={col} className="px-3 py-2 text-left font-medium text-gray-500">{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {merchants.slice(0, 15).map((m, i) => (
            <tr key={i} className={clsx("border-t border-gray-50", i % 2 === 0 ? "bg-white" : "bg-gray-50/40")}>
              <td className="px-3 py-2 font-medium text-gray-800">{m.merchant_name}</td>
              <td className="px-3 py-2 text-gray-500 capitalize">{m.category?.replace(/_/g, " ").toLowerCase() ?? "--"}</td>
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
  if (!subscriptions.length) return null;
  return (
    <div className="space-y-2">
      {subscriptions.map((s, i) => (
        <div key={i} className="flex items-center justify-between px-3 py-2 bg-white rounded-lg border border-gray-100">
          <div>
            <p className="text-xs font-medium text-gray-800">{s.merchant_name}</p>
            <p className="text-xs text-gray-400">
              Every ~{s.frequency_days}d · Last {s.last_charged}
            </p>
          </div>
          <span className="text-xs font-bold tabular-nums text-gray-900">{fmt(s.typical_amount)}</span>
        </div>
      ))}
    </div>
  );
}

function CardBalanceList({ balances }: { balances: CardBalance[] }) {
  if (!balances.length) return null;
  return (
    <div className="space-y-2">
      {balances.map((cb, i) => (
        <div key={i} className="flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-gray-700">{cb.account_name}</p>
            <p className="text-xs text-gray-400">{cb.institution}</p>
          </div>
          <span className="text-sm font-bold tabular-nums text-gray-900">{fmt(cb.current_balance)}</span>
        </div>
      ))}
    </div>
  );
}

function BankingView({ overview }: { overview: BankingOverview }) {
  const cs = overview.checking_summary;
  const net = parseFloat(cs.net);
  const netPositive = net >= 0;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard label="Total Spend" value={fmt(overview.total_spend_this_month)} icon={DollarSign} accent="amber" />
        <MetricCard
          label="Card Balances"
          value={overview.credit_card_balances.length > 0
            ? fmt(String(overview.credit_card_balances.reduce((acc, cb) => acc + parseFloat(cb.current_balance || "0"), 0)))
            : "--"}
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

      {Object.keys(overview.spend_by_category).length > 0 && (
        <section>
          <SectionHeader title="Spend by category" count={Object.keys(overview.spend_by_category).length} />
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <CategoryBars categories={overview.spend_by_category} />
          </div>
        </section>
      )}

      {overview.spend_by_merchant.length > 0 && (
        <section>
          <SectionHeader title="Top merchants" count={overview.spend_by_merchant.length} />
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <MerchantTable merchants={overview.spend_by_merchant} />
          </div>
        </section>
      )}

      {overview.subscriptions.length > 0 && (
        <section>
          <SectionHeader title="Recurring subscriptions" count={overview.subscriptions.length} />
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <SubscriptionList subscriptions={overview.subscriptions} />
          </div>
        </section>
      )}

      {overview.credit_card_balances.length > 0 && (
        <section>
          <SectionHeader title="Credit card balances" count={overview.credit_card_balances.length} />
          <div className="bg-white border border-gray-200 rounded-xl p-4">
            <CardBalanceList balances={overview.credit_card_balances} />
          </div>
        </section>
      )}

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
    </div>
  );
}

// ---------------------------------------------------------------------------
// Document list with delete action
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  uploaded:         { label: "Uploaded",    color: "text-gray-500",   icon: <Loader2 size={12} className="animate-spin" /> },
  queued:           { label: "Queued",      color: "text-yellow-600", icon: <Loader2 size={12} className="animate-spin" /> },
  processing:       { label: "Processing",  color: "text-blue-600",   icon: <Loader2 size={12} className="animate-spin" /> },
  parsed:           { label: "Parsed",      color: "text-indigo-600", icon: <Loader2 size={12} className="animate-spin" /> },
  partially_parsed: { label: "Partial",     color: "text-orange-500", icon: <AlertTriangle size={12} /> },
  embedded:         { label: "Embedded",    color: "text-teal-600",   icon: <Loader2 size={12} className="animate-spin" /> },
  processed:        { label: "Processed",   color: "text-green-600",  icon: <CheckCircle size={12} /> },
  failed:           { label: "Failed",      color: "text-red-600",    icon: <XCircle size={12} /> },
};

function DocumentRow({
  doc,
  onDelete,
}: {
  doc: StatementDocument;
  onDelete: (id: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const cfg = STATUS_CONFIG[doc.document_status] ?? STATUS_CONFIG.uploaded;

  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg bg-white border border-gray-100 group">
      <div className="flex items-center gap-2 min-w-0">
        <File size={13} className="text-gray-400 shrink-0" />
        <span className="text-xs text-gray-700 truncate">{doc.original_filename}</span>
        {doc.institution_type !== "unknown" && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 shrink-0 capitalize">
            {doc.institution_type.replace(/_/g, " ")}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0 ml-2">
        <div className={clsx("flex items-center gap-1 text-xs", cfg.color)}>
          {cfg.icon}
          <span>{cfg.label}</span>
        </div>
        {confirming ? (
          <div className="flex items-center gap-1">
            <button
              onClick={() => { onDelete(doc.id); setConfirming(false); }}
              className="text-[10px] px-1.5 py-0.5 rounded bg-red-600 text-white hover:bg-red-700 transition-colors"
            >
              Confirm
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            className="opacity-0 group-hover:opacity-100 p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 transition-all"
            title="Delete document"
          >
            <Trash2 size={12} />
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Compact upload zone
// ---------------------------------------------------------------------------

function CompactUpload({ onUpload, isUploading }: { onUpload: (files: File[]) => void; isUploading: boolean }) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: onUpload,
    accept: { "application/pdf": [".pdf"] },
    multiple: true,
    disabled: isUploading,
  });

  return (
    <div
      {...getRootProps()}
      className={clsx(
        "border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors",
        isDragActive ? "border-blue-400 bg-blue-50" : "border-gray-200 hover:border-blue-300 hover:bg-gray-50",
        isUploading && "opacity-60 cursor-not-allowed"
      )}
    >
      <input {...getInputProps()} />
      <UploadCloud size={24} className={clsx("mx-auto mb-2", isDragActive ? "text-blue-500" : "text-gray-400")} />
      {isUploading ? (
        <p className="text-xs text-blue-600 font-medium">Uploading...</p>
      ) : (
        <>
          <p className="text-sm font-medium text-gray-600">Drop PDFs here or click to upload</p>
          <p className="text-xs text-gray-400 mt-0.5">Statements are auto-assigned to the correct bucket</p>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function HomePage() {
  const { selectedBucket, setSelectedBucket } = useAppStore();

  const [loading, setLoading] = useState(false);
  const [invOverview, setInvOverview] = useState<AnalyticsEnvelope<InvestmentsOverview> | null>(null);
  const [bankOverview, setBankOverview] = useState<AnalyticsEnvelope<BankingOverview> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [docsVisible, setDocsVisible] = useState(true);

  const bucket = selectedBucket as BucketKind;

  // Analytics loaders
  const loadInvestments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setInvOverview(await investmentsApi.getOverview());
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
      setBankOverview(await bankingApi.getOverview());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load banking data.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Refresh analytics for current bucket
  const refreshAnalytics = useCallback(() => {
    if (bucket === "investments") {
      setInvOverview(null);
      loadInvestments();
    } else {
      setBankOverview(null);
      loadBanking();
    }
  }, [bucket, loadInvestments, loadBanking]);

  // Pass refreshAnalytics as callback so upload/delete auto-refreshes dashboard
  const { documents, isUploading, uploadDocument, deleteDocument } = useDocuments(refreshAnalytics);

  useEffect(() => {
    if (bucket === "investments" && !invOverview) loadInvestments();
    else if (bucket === "banking" && !bankOverview) loadBanking();
  }, [bucket, invOverview, bankOverview, loadInvestments, loadBanking]);

  const handleBucketChange = (kind: BucketKind) => {
    setSelectedBucket(kind as "investments" | "banking");
  };

  const handleUpload = useCallback(
    async (files: File[]) => {
      for (const file of files) {
        await uploadDocument(file);
      }
    },
    [uploadDocument]
  );

  const handleDelete = useCallback(
    async (documentId: string) => {
      await deleteDocument(documentId);
    },
    [deleteDocument]
  );

  const currentEnvelope = bucket === "investments" ? invOverview : bankOverview;
  const warnings = currentEnvelope?.warnings ?? [];
  const partial = currentEnvelope?.partial ?? false;

  // Filter docs to show relevant ones for current bucket
  const investmentInstitutions = new Set(["morgan_stanley", "etrade"]);
  const bankingInstitutions = new Set(["chase", "amex", "discover"]);
  const relevantDocs = documents.filter((d) => {
    if (d.document_status === "deleted") return false;
    const instSet = bucket === "investments" ? investmentInstitutions : bankingInstitutions;
    return d.institution_type === "unknown" || instSet.has(d.institution_type);
  });

  const hasInvData = invOverview && invOverview.data.total_portfolio_value !== "0";
  const hasBankData = bankOverview && parseFloat(bankOverview.data.total_spend_this_month) > 0;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Dashboard</h1>
          <p className="text-xs text-gray-400 mt-0.5">All data stays local on your machine</p>
        </div>
        <div className="flex items-center gap-3">
          <BucketSwitcher active={bucket} onChange={handleBucketChange} />
          <button
            onClick={refreshAnalytics}
            disabled={loading}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Warnings */}
      {partial && <PartialBanner warnings={warnings} />}

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">{error}</div>
      )}

      {/* Analytics widgets */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin text-blue-500" />
        </div>
      )}

      {!loading && !error && bucket === "investments" && (
        hasInvData ? <InvestmentsView overview={invOverview!.data} /> : invOverview ? <SoftEmpty message="No investment data yet." /> : null
      )}

      {!loading && !error && bucket === "banking" && (
        hasBankData ? <BankingView overview={bankOverview!.data} /> : bankOverview ? <SoftEmpty message="No banking data yet." /> : null
      )}

      {/* Divider */}
      <hr className="border-gray-200" />

      {/* Upload + Documents */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Upload */}
        <div>
          <SectionHeader title="Upload statements" />
          <CompactUpload onUpload={handleUpload} isUploading={isUploading} />
        </div>

        {/* Document list with collapsible toggle */}
        <div>
          <SectionHeader
            title="Documents"
            count={relevantDocs.length}
            right={
              relevantDocs.length > 0 ? (
                <button
                  onClick={() => setDocsVisible((v) => !v)}
                  className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
                >
                  {docsVisible ? (
                    <>
                      <ChevronUp size={12} />
                      <span>Hide</span>
                    </>
                  ) : (
                    <>
                      <ChevronDown size={12} />
                      <span>Show</span>
                    </>
                  )}
                </button>
              ) : undefined
            }
          />
          {relevantDocs.length === 0 ? (
            <div className="text-center py-8">
              <File size={24} className="mx-auto text-gray-300 mb-2" />
              <p className="text-xs text-gray-400">No documents uploaded yet.</p>
            </div>
          ) : docsVisible ? (
            <div className="space-y-1.5 max-h-80 overflow-y-auto">
              {relevantDocs.map((doc) => (
                <DocumentRow key={doc.id} doc={doc} onDelete={handleDelete} />
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
