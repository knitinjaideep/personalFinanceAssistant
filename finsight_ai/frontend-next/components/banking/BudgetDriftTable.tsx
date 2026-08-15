"use client";

/**
 * <BudgetDriftTable /> — "Where You're Off Plan" (PR 08,
 * docs/coral-redesign/pr-08-banking-drift.md), section 3 of Banking's page
 * hierarchy (design-rules.md).
 *
 * Columns: Category / Target / Actual / Drift, sorted by
 * `lib/bankingDrift.ts::buildBudgetDriftRows` — largest ADVERSE drift first
 * (see that module's docstring for why this is not a literal-sign sort).
 *
 * Drift coloring uses the backend's own `DriftStatus`
 * (on_track/watch/off_track/unknown — already threshold-aware, see
 * `compute_status` in backend/app/domain/plan_vs_actual.py) rather than a
 * naive "positive variance = bad" rule, so a Need that's a few dollars over
 * target still reads as on-track instead of automatically red
 * (pr-08-banking-drift.md: "avoid treating every over-target Need as
 * inherently bad").
 *
 * Clicking a category row lazily fetches that category's merchant drivers
 * (`bankingApi.merchantDrivers`) and renders them inline; clicking a
 * merchant row lazily fetches that merchant's individual transactions
 * (`bankingApi.transactionDrivers`) — the full Category -> merchants ->
 * transactions drill-down. Reuses the same loading/error/retry/empty
 * pattern as `CategoryBreakdownPanel` in BankingFlowTree.tsx rather than
 * inventing a new one, and resets all drill-down state on period change
 * (same stale-drilldown guard as BankingFlowTree's own useEffect).
 */

import { useEffect, useRef, useState } from "react";
import { ChevronRight, Home, PiggyBank, ShoppingBag } from "lucide-react";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import StatusBadge, { type StatusTone } from "@/components/coral-ds/StatusBadge";
import Surface from "@/components/coral-ds/Surface";
import { bankingApi, type MerchantDriver, type TransactionDriver } from "@/features/banking/api";
import type { DashboardPeriodParams, DriftStatus } from "@/features/overview/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { DriftBucket, DriftRow } from "@/lib/bankingDrift";

interface BudgetDriftTableProps {
  rows: DriftRow[] | null;
  loading: boolean;
  error: boolean;
  onRetry?: () => void;
  period: DashboardPeriodParams;
}

const BUCKET_ICON: Record<DriftBucket, React.ReactNode> = {
  needs: <Home size={14} />,
  wants: <ShoppingBag size={14} />,
  savings: <PiggyBank size={14} />,
};

const BUCKET_LABEL: Record<DriftBucket, string> = {
  needs: "Needs",
  wants: "Wants",
  savings: "Savings",
};

// Maps the backend's own threshold-aware DriftStatus directly onto a
// StatusTone — never a fresh judgment call, just a display-tone lookup for a
// classification the backend already made (compute_status).
const STATUS_TONE: Record<DriftStatus, StatusTone> = {
  on_track: "good",
  watch: "warning",
  off_track: "danger",
  unknown: "neutral",
};

const STATUS_LABEL: Record<DriftStatus, string> = {
  on_track: "On track",
  watch: "Watch",
  off_track: "Off track",
  unknown: "No target",
};

/** Drift figures only: always signed, so "+" reads as "above plan". */
function formatSigned(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${formatCurrency(Math.abs(value))}`;
}

/** Actual $ (merchant totals, individual transactions): never prefixed with
 * "+", so a spend figure is not misread as a drift contribution. A negative
 * total (net refunds, invariant #6) keeps its "-". */
function formatAmount(value: number): string {
  return value < 0 ? `-${formatCurrency(Math.abs(value))}` : formatCurrency(value);
}

function DriftCell({ row }: { row: DriftRow }) {
  if (row.varianceAmount === null) {
    return <StatusBadge status="neutral">No target</StatusBadge>;
  }
  return (
    <div className="flex flex-col items-end gap-1">
      <StatusBadge status={STATUS_TONE[row.status]} className="tabular-nums">
        {formatSigned(row.varianceAmount)}
      </StatusBadge>
      <span className="micro-text" style={{ color: "var(--text-dim)" }}>{STATUS_LABEL[row.status]}</span>
    </div>
  );
}

function TransactionList({
  loading,
  error,
  rows,
  onRetry,
}: {
  loading: boolean;
  error: boolean;
  rows: TransactionDriver[] | null;
  onRetry: () => void;
}) {
  if (loading) return <SkeletonState variant="block" height="48px" count={2} className="mb-2" />;
  if (error) return <ErrorState compact message="Couldn't load these transactions." onRetry={onRetry} />;
  if (!rows || rows.length === 0) {
    return (
      <p className="micro-text py-2" style={{ color: "var(--text-muted)" }}>
        No individual transactions found for this merchant.
      </p>
    );
  }
  return (
    <div className="space-y-1.5 py-1">
      {rows.map((t) => (
        <div key={t.transaction_id} className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg" style={{ background: "var(--row-bg)" }}>
          <div className="min-w-0">
            <p className="micro-text font-medium truncate" style={{ color: "var(--text-secondary)" }}>{t.description}</p>
            <p className="micro-text" style={{ color: "var(--text-dim)" }}>{formatDate(t.transaction_date)}</p>
          </div>
          <span className="micro-text font-bold tabular shrink-0" style={{ color: "var(--text-primary)" }}>
            {formatAmount(Number(t.amount))}
          </span>
        </div>
      ))}
    </div>
  );
}

function MerchantList({
  loading,
  error,
  rows,
  onRetry,
  expandedMerchant,
  onSelectMerchant,
  transactionState,
  onRetryTransactions,
}: {
  loading: boolean;
  error: boolean;
  rows: MerchantDriver[] | null;
  onRetry: () => void;
  expandedMerchant: string | null;
  onSelectMerchant: (merchant: string) => void;
  transactionState: { loading: boolean; error: boolean; data: TransactionDriver[] | null };
  onRetryTransactions: () => void;
}) {
  if (loading) return <SkeletonState variant="block" height="40px" count={3} className="mb-2" />;
  if (error) return <ErrorState compact message="Couldn't load merchants for this category." onRetry={onRetry} />;
  if (!rows || rows.length === 0) {
    return (
      <EmptyState
        compact
        title="No merchant activity"
        description="Coral didn't find individual merchants for this category and period."
      />
    );
  }

  return (
    <div className="space-y-1.5">
      {rows.map((m) => {
        const selected = expandedMerchant === m.merchant;
        return (
          <div key={m.merchant}>
            <button
              type="button"
              onClick={() => onSelectMerchant(m.merchant)}
              aria-expanded={selected}
              className="w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl text-left transition-colors"
              style={{ background: selected ? "var(--status-neutral-soft)" : "var(--panel-bg, var(--card-bg))", border: "1px solid var(--border-subtle)" }}
            >
              <span className="flex items-center gap-2 min-w-0">
                <ChevronRight
                  size={13}
                  style={{ color: "var(--text-dim)", transform: selected ? "rotate(90deg)" : "none", transition: "transform 0.2s" }}
                />
                <span className="small-text font-semibold truncate" style={{ color: "var(--text-primary)" }}>{m.merchant}</span>
              </span>
              <span className="small-text font-bold tabular shrink-0" style={{ color: "var(--text-primary)" }}>
                {formatAmount(Number(m.amount))}
              </span>
            </button>
            {selected && (
              <div className="pl-6 pr-1">
                <TransactionList
                  loading={transactionState.loading}
                  error={transactionState.error}
                  rows={transactionState.data}
                  onRetry={onRetryTransactions}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

interface LoadState<T> {
  data: T | null;
  loading: boolean;
  error: boolean;
}

const EMPTY_LOAD_STATE = { data: null, loading: false, error: false };

export default function BudgetDriftTable({ rows, loading, error, onRetry, period }: BudgetDriftTableProps) {
  const [expanded, setExpanded] = useState<{ bucket: DriftBucket; category: string } | null>(null);
  const [merchantState, setMerchantState] = useState<LoadState<MerchantDriver[]>>(EMPTY_LOAD_STATE);
  const [expandedMerchant, setExpandedMerchant] = useState<string | null>(null);
  const [transactionState, setTransactionState] = useState<LoadState<TransactionDriver[]>>(EMPTY_LOAD_STATE);

  // Monotonic request tokens: a slow in-flight fetch for a previously selected
  // category/merchant must never resolve into the panel of a different one.
  // Attributing merchants or transactions to the wrong category would be an
  // outright financial misstatement, not just a UI glitch.
  const merchantRequestId = useRef(0);
  const transactionRequestId = useRef(0);

  // Reset every drill-down level whenever the period changes — a merchant/
  // transaction list fetched for a different period must never linger
  // onscreen (same stale-drilldown guard as BankingFlowTree.tsx).
  useEffect(() => {
    merchantRequestId.current += 1;
    transactionRequestId.current += 1;
    setExpanded(null);
    setMerchantState(EMPTY_LOAD_STATE);
    setExpandedMerchant(null);
    setTransactionState(EMPTY_LOAD_STATE);
  }, [period.startDate, period.endDate]);

  const loadMerchants = (bucket: DriftBucket, category: string) => {
    const requestId = ++merchantRequestId.current;
    setMerchantState({ data: null, loading: true, error: false });
    bankingApi
      .merchantDrivers(bucket, category, period)
      .then((data) => {
        if (merchantRequestId.current !== requestId) return;
        setMerchantState({ data, loading: false, error: false });
      })
      .catch(() => {
        if (merchantRequestId.current !== requestId) return;
        setMerchantState({ data: null, loading: false, error: true });
      });
  };

  const handleSelectCategory = (bucket: DriftBucket, category: string) => {
    transactionRequestId.current += 1;
    setExpandedMerchant(null);
    setTransactionState(EMPTY_LOAD_STATE);
    if (expanded?.bucket === bucket && expanded.category === category) {
      merchantRequestId.current += 1;
      setExpanded(null);
      setMerchantState(EMPTY_LOAD_STATE);
      return;
    }
    setExpanded({ bucket, category });
    loadMerchants(bucket, category);
  };

  const loadTransactions = (bucket: DriftBucket, category: string, merchant: string) => {
    const requestId = ++transactionRequestId.current;
    setTransactionState({ data: null, loading: true, error: false });
    bankingApi
      .transactionDrivers(bucket, category, merchant, period)
      .then((data) => {
        if (transactionRequestId.current !== requestId) return;
        setTransactionState({ data, loading: false, error: false });
      })
      .catch(() => {
        if (transactionRequestId.current !== requestId) return;
        setTransactionState({ data: null, loading: false, error: true });
      });
  };

  const handleSelectMerchant = (merchant: string) => {
    if (!expanded) return;
    if (expandedMerchant === merchant) {
      transactionRequestId.current += 1;
      setExpandedMerchant(null);
      setTransactionState(EMPTY_LOAD_STATE);
      return;
    }
    setExpandedMerchant(merchant);
    loadTransactions(expanded.bucket, expanded.category, merchant);
  };

  if (loading) return <SkeletonState variant="card" height="280px" />;
  if (error) return <ErrorState message="Couldn't load your Plan vs Actual breakdown for this period." onRetry={onRetry} />;
  if (!rows || rows.length === 0) {
    return (
      <EmptyState
        title="Nothing to compare yet"
        description="Once Coral sees categorized income and spending for this period it can show where you're off plan."
      />
    );
  }

  return (
    <Surface padding="md">
      {/* Header row */}
      <div
        className="hidden sm:grid gap-3 px-3 pb-3 micro-text font-semibold uppercase tracking-wide"
        style={{ gridTemplateColumns: "2fr 1fr 1fr 1fr", color: "var(--text-dim)", borderBottom: "1px solid var(--border-subtle)" }}
      >
        <span>Category</span>
        <span className="text-right">Target</span>
        <span className="text-right">Actual</span>
        <span className="text-right">Drift</span>
      </div>

      <div className="divide-y" style={{ borderColor: "var(--border-subtle)" }}>
        {rows.map((row) => {
          const key = `${row.bucket}:${row.category}`;
          const isExpanded = expanded?.bucket === row.bucket && expanded.category === row.category;
          return (
            <div key={key}>
              <button
                type="button"
                onClick={() => handleSelectCategory(row.bucket, row.category)}
                className="w-full grid grid-cols-1 sm:grid-cols-[2fr_1fr_1fr_1fr] gap-2 sm:gap-3 px-3 py-3.5 text-left transition-colors hover:bg-white/[0.02] items-center"
                aria-expanded={isExpanded}
              >
                <span className="flex items-center gap-2.5 min-w-0">
                  <ChevronRight
                    size={13}
                    style={{ color: "var(--text-dim)", transform: isExpanded ? "rotate(90deg)" : "none", transition: "transform 0.2s" }}
                  />
                  <span
                    className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                    style={{ background: `var(--financial-${row.bucket}-soft)`, color: `var(--financial-${row.bucket})` }}
                  >
                    {BUCKET_ICON[row.bucket]}
                  </span>
                  <span className="min-w-0">
                    <span className="small-text font-semibold block truncate" style={{ color: "var(--text-primary)" }}>{row.category}</span>
                    <span className="micro-text" style={{ color: "var(--text-dim)" }}>{BUCKET_LABEL[row.bucket]}</span>
                  </span>
                </span>

                {/* Column labels: the header row is hidden below `sm`, where
                 * the cells stack — without them the stacked $ figures would
                 * be unlabelled for sighted mobile users and for screen
                 * readers reading the row button's flat text content. */}
                <span className="text-left sm:text-right small-text" style={{ color: "var(--text-secondary)" }}>
                  <span className="micro-text sm:sr-only mr-1.5" style={{ color: "var(--text-dim)" }}>Target</span>
                  {row.targetAmount !== null ? formatCurrency(row.targetAmount) : "—"}
                  {row.targetPercentage !== null && (
                    <span className="micro-text block" style={{ color: "var(--text-dim)" }}>{row.targetPercentage}% of income</span>
                  )}
                </span>

                <span className="text-left sm:text-right small-text font-bold tabular" style={{ color: "var(--text-primary)" }}>
                  <span className="micro-text font-normal sm:sr-only mr-1.5" style={{ color: "var(--text-dim)" }}>Actual</span>
                  {formatCurrency(row.actualAmount)}
                  {row.actualPercentage !== null && (
                    <span className="micro-text block font-normal" style={{ color: "var(--text-dim)" }}>{row.actualPercentage}% of income</span>
                  )}
                </span>

                <span className="flex items-center gap-1.5 sm:justify-end">
                  <span className="micro-text sm:sr-only" style={{ color: "var(--text-dim)" }}>Drift</span>
                  <DriftCell row={row} />
                </span>
              </button>

              {isExpanded && (
                <div className="px-3 pb-4 pl-9">
                  <MerchantList
                    loading={merchantState.loading}
                    error={merchantState.error}
                    rows={merchantState.data}
                    onRetry={() => loadMerchants(row.bucket, row.category)}
                    expandedMerchant={expandedMerchant}
                    onSelectMerchant={handleSelectMerchant}
                    transactionState={transactionState}
                    onRetryTransactions={() =>
                      expandedMerchant && loadTransactions(row.bucket, row.category, expandedMerchant)
                    }
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Surface>
  );
}
