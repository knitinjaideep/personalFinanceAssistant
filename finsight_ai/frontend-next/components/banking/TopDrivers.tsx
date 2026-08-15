"use client";

/**
 * <TopDrivers /> — "Top Drivers" (PR 08, docs/coral-redesign/pr-08-banking-
 * drift.md), section 4 of Banking's page hierarchy (design-rules.md).
 *
 * Anchored at the BUCKET level, not the category level (see
 * docs/coral-redesign/BLOCKED.md, Decision 2, RESOLVED — Option B): Needs/
 * Wants categories have no plan-defined sub-target today
 * (`_DEFAULT_ALLOCATIONS` only defines Savings/Investments sub-targets), so
 * a category-level drift figure is always `null` for Needs/Wants — nothing
 * to rank drivers on. The Needs/Wants master BUCKETS do have real
 * plan-defined targets (50%/20% of income), so Top Drivers picks up to 2
 * off-plan buckets (`buildTopDriverCandidates`, over the same
 * `PlanVsActualResult.buckets` BankingFlowTree.tsx already fetches for this
 * period — no new backend call), then fetches each bucket's
 * backend-aggregated, whole-bucket merchant drivers (`bankingApi
 * .merchantDrivers(bucket, null, period, limit)` — no category filter,
 * already excludes internal transfers/card payments, see backend/app/domain
 * /plan_vs_actual.py::compute_merchant_drivers / _counts_toward_bucket) and
 * renders them as the biggest CONTRIBUTORS to that bucket's drift — never as
 * if a merchant had its own target. The PR's example format:
 *
 *   Wants +$400 above plan
 *     Amazon $250
 *     Target $100
 *     All other merchants $50
 *
 * Framing is dollar-first and always in terms of plan drift — the word "bad"
 * never appears; a merchant total is just a number until compared against
 * the bucket's own drift, and the two are always labelled distinctly (see
 * DriverCard below).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Home, ShoppingBag, TrendingUp } from "lucide-react";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import Surface from "@/components/coral-ds/Surface";
import { bankingApi, type MerchantDriver } from "@/features/banking/api";
import type { BucketDrift, DashboardPeriodParams, DriftStatus } from "@/features/overview/api";
import { formatCurrency } from "@/lib/utils";
import {
  buildTopDriverCandidates,
  buildTopDriverGroup,
  type ConsumptionBucket,
  type TopDriverGroup,
} from "@/lib/bankingDrift";

// Same threshold-aware status -> color mapping as BudgetDriftTable.tsx's
// STATUS_TONE — a "watch"-level driver (small, tolerated overage) is not
// rendered with the same visual weight as an "off_track" one.
const STATUS_COLOR: Record<DriftStatus, string> = {
  on_track: "var(--status-good)",
  watch: "var(--status-warning)",
  off_track: "var(--status-danger)",
  unknown: "var(--status-neutral)",
};

const BUCKET_LABEL: Record<ConsumptionBucket, string> = {
  needs: "Needs",
  wants: "Wants",
};

const BUCKET_ICON: Record<ConsumptionBucket, React.ReactNode> = {
  needs: <Home size={15} />,
  wants: <ShoppingBag size={15} />,
};

interface TopDriversProps {
  /** The same `PlanVsActualResult.buckets` BankingFlowTree.tsx renders — pass
   * it straight through, this component does not fetch it itself. */
  buckets: BucketDrift[] | null;
  loading: boolean;
  error: boolean;
  onRetry?: () => void;
  period: DashboardPeriodParams;
}

const MERCHANTS_PER_DRIVER = 3;

/** Drift figures: always signed, so "+" reads as "above plan". */
function formatSigned(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${formatCurrency(Math.abs(value))}`;
}

/** Actual-spend figures: NOT signed with "+", so a merchant total is never
 * mistaken for a drift contribution. A negative total (net refunds for that
 * merchant, invariant #6) still shows its "-". */
function formatAmount(value: number): string {
  return value < 0 ? `-${formatCurrency(Math.abs(value))}` : formatCurrency(value);
}

function DriverCard({ group }: { group: TopDriverGroup }) {
  const label = BUCKET_LABEL[group.bucket];
  return (
    <div className="px-4 py-3.5 rounded-2xl" style={{ background: "var(--panel-bg, var(--card-bg))", border: "1px solid var(--border-subtle)" }}>
      <div className="flex items-center justify-between gap-2">
        <span className="coral-card-title flex items-center gap-2">
          <span style={{ color: "var(--text-muted)" }}>{BUCKET_ICON[group.bucket]}</span>
          {label}
        </span>
        <span className="small-text font-bold tabular" style={{ color: STATUS_COLOR[group.status] }}>
          {formatSigned(group.driftAmount)}
        </span>
      </div>
      <p className="micro-text mt-0.5" style={{ color: "var(--text-muted)" }}>above plan this period</p>

      {group.merchants.length > 0 || group.other !== null ? (
        <>
          {/* The rows below decompose the BUCKET's actual spend, not its
           * drift — Coral has no per-merchant target, so splitting the
           * drift across merchants would be a fabricated allocation.
           * Framed explicitly as contributors to the bucket's overspend,
           * not as merchants that each missed a target of their own. */}
          <p className="micro-text mt-3" style={{ color: "var(--text-dim)" }}>
            {formatCurrency(group.actualAmount)} spent in {label} — biggest contributors to the overspend
          </p>
          <div className="mt-1.5 space-y-1.5 pl-3" style={{ borderLeft: "2px solid var(--border-subtle)" }}>
            {/* Keyed on merchant + category: this is a WHOLE-bucket fetch
             * (category=null), and the backend groups drivers by
             * (merchant, bucket, category), so the same merchant name can
             * appear twice under one bucket (e.g. Amazon in Shopping and in
             * Groceries). Merging them here would be a frontend
             * re-aggregation of backend-authoritative totals, so each row is
             * kept — and labelled with its category so the two are
             * distinguishable rather than looking like a duplicate. */}
            {group.merchants.map((m) => (
              <div key={`${m.merchant}\u001f${m.category ?? ""}`} className="flex items-center justify-between gap-3">
                <span className="micro-text truncate" style={{ color: "var(--text-secondary)" }}>
                  {m.merchant}
                  {m.category && <span style={{ color: "var(--text-dim)" }}> · {m.category}</span>}
                </span>
                <span className="micro-text font-semibold tabular shrink-0" style={{ color: "var(--text-primary)" }}>
                  {formatAmount(m.amount)}
                </span>
              </div>
            ))}
            {group.other !== null && (
              <div className="flex items-center justify-between gap-3">
                <span className="micro-text" style={{ color: "var(--text-dim)" }}>All other merchants</span>
                <span className="micro-text font-semibold tabular shrink-0" style={{ color: "var(--text-dim)" }}>
                  {formatAmount(group.other)}
                </span>
              </div>
            )}
          </div>
          {/* Precision footnote: the headline number above is the BUCKET's
           * drift, shared across every row in the list — not a per-merchant
           * variance. Stated explicitly so the list is never misread as
           * summing to the headline (it sums to `actualAmount` instead). */}
          <p className="micro-text mt-2" style={{ color: "var(--text-dim)" }}>
            The {formatSigned(group.driftAmount)} above is the total {label} drift vs. plan — shared across every row here, not a target for any single merchant.
          </p>
        </>
      ) : (
        <p className="micro-text mt-2" style={{ color: "var(--text-dim)" }}>No individual merchants stood out this period.</p>
      )}
    </div>
  );
}

interface MerchantFetchState {
  data: MerchantDriver[] | null;
  loading: boolean;
  error: boolean;
}

export default function TopDrivers({ buckets, loading, error, onRetry, period }: TopDriversProps) {
  // The candidate off-plan buckets — up to 2 (Needs/Wants), largest drift $
  // first, strictly above plan (see buildTopDriverCandidates).
  const candidates = buildTopDriverCandidates(buckets);

  const [merchantStates, setMerchantStates] = useState<Record<string, MerchantFetchState>>({});

  const candidateKey = candidates.map((c) => c.bucket).join("|");

  // Bumped on every period/candidate change so a slow (or retried) merchant
  // fetch from a previous period can never resolve into the current one's
  // cards — merchant $ attributed to the wrong period is a financial
  // misstatement, not a cosmetic glitch.
  const generation = useRef(0);

  const fetchMerchants = useCallback(
    (bucket: ConsumptionBucket, forGeneration: number) => {
      setMerchantStates((prev) => ({ ...prev, [bucket]: { data: null, loading: true, error: false } }));
      bankingApi
        .merchantDrivers(bucket, null, period, MERCHANTS_PER_DRIVER)
        .then((data) => {
          if (generation.current !== forGeneration) return;
          setMerchantStates((prev) => ({ ...prev, [bucket]: { data, loading: false, error: false } }));
        })
        .catch(() => {
          if (generation.current !== forGeneration) return;
          setMerchantStates((prev) => ({ ...prev, [bucket]: { data: null, loading: false, error: true } }));
        });
    },
    [period.startDate, period.endDate],
  );

  useEffect(() => {
    const forGeneration = ++generation.current;
    if (candidates.length === 0) {
      setMerchantStates({});
      return;
    }
    setMerchantStates(
      Object.fromEntries(
        candidates.map((c) => [c.bucket, { data: null, loading: true, error: false } as MerchantFetchState]),
      ),
    );
    candidates.forEach((c) => fetchMerchants(c.bucket, forGeneration));
    // Reset/refetch whenever the period changes OR the set of top-driver
    // buckets changes (e.g. new data loaded for the period). Intentionally
    // NOT depending on `candidates`/`period` object identity — `candidateKey`
    // and the individual startDate/endDate strings are the real dependency.
  }, [period.startDate, period.endDate, candidateKey]);

  if (loading) return <SkeletonState variant="card" height="220px" />;
  if (error) return <ErrorState message="Couldn't load Top Drivers for this period." onRetry={onRetry} />;
  if (candidates.length === 0) {
    return (
      <EmptyState
        compact
        icon={<TrendingUp size={22} />}
        title="Nothing significantly off plan this period"
        description="Coral highlights a bucket here once your Needs or Wants spending drifts above its plan target."
      />
    );
  }

  const anyMerchantsLoading = candidates.some((c) => merchantStates[c.bucket]?.loading);
  const anyMerchantsErrored = candidates.some((c) => merchantStates[c.bucket]?.error);

  return (
    <Surface padding="md">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {candidates.map((candidate) => {
          const key = candidate.bucket;
          const state = merchantStates[key];
          if (!state || state.loading) return <SkeletonState key={key} variant="block" height="110px" />;
          if (state.error) {
            return (
              <div key={key}>
                <ErrorState
                  compact
                  message={`Couldn't load merchants for ${BUCKET_LABEL[candidate.bucket]}.`}
                  onRetry={() => fetchMerchants(candidate.bucket, generation.current)}
                />
              </div>
            );
          }
          const group = buildTopDriverGroup(candidate, state.data ?? []);
          return <DriverCard key={key} group={group} />;
        })}
      </div>
      {anyMerchantsErrored && !anyMerchantsLoading && (
        <p className="micro-text mt-3" style={{ color: "var(--text-dim)" }}>
          Some merchant details couldn&apos;t be loaded — try again above.
        </p>
      )}
    </Surface>
  );
}
