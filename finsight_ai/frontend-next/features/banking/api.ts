import { api } from "@/lib/api-client";
import type { DashboardPeriodParams as PlanPeriodParams, DriftStatus, MasterBucket } from "@/features/overview/api";

export interface SpendByMonth {
  month: string;
  total_spend: number;
  total_spend_fmt: string;
  transaction_count: number;
}

export interface SpendByCategory {
  category: string;
  total: number;
  total_fmt: string;
  transaction_count: number;
}

export interface TopMerchant {
  merchant: string;
  total: number;
  total_fmt: string;
  transaction_count: number;
}

export interface CardSpend {
  account_name: string;
  account_type: string;
  institution_type: string;
  product_label: string;
  total_spend: number;
  total_spend_fmt: string;
  transaction_count: number;
  latest_statement: string | null;
}

export interface CashFlowMonth {
  month: string;
  inflow: number;
  outflow: number;
  net: number;
}

export interface Subscription {
  merchant: string;
  category: string | null;
  avg_monthly_amount: number;
  avg_monthly_amount_fmt: string;
  occurrences: number;
  last_seen: string | null;
  confidence: "high" | "medium";
}

export interface InstitutionCoverage {
  institution: string;
  institution_type: string;
  doc_count: number;
  earliest_statement: string | null;
  latest_statement: string | null;
  missing_recent_data?: boolean;
}

export interface BankingDashboard {
  spend_by_month: SpendByMonth[];
  spend_by_category: SpendByCategory[];
  top_merchants: TopMerchant[];
  card_summary: CardSpend[];
  cash_flow: CashFlowMonth[];
  subscriptions: Subscription[];
  coverage: InstitutionCoverage[];
  /** The resolved {start_date, end_date} the backend actually applied, or
   * null when no range was requested (PR 05 unified period contract). */
  period: { start_date: string; end_date: string } | null;
}

export interface DashboardPeriodParams {
  startDate?: string; // "YYYY-MM-DD"
  endDate?: string;   // "YYYY-MM-DD"
}

// ── Plan vs Actual category drill-down (GET /api/v1/plan-vs-actual/buckets/{bucket}) ──
//
// Bucket-level totals for the same period come from `overviewApi.planVsActual`
// (features/overview/api.ts, PR 04/06) — reused as-is rather than duplicated
// here. This module only adds the category-level drill-down endpoint that
// Banking's flow tree needs on click (PR 07), mirroring the shape of
// `backend/app/domain/plan_vs_actual.py::CategoryDrift` exactly so no
// reshaping happens on the client.

export interface CategoryDrift {
  bucket: MasterBucket;
  category: string;
  target_percentage: string | null;
  actual_percentage: string | null;
  target_amount: string | null;
  actual_amount: string;
  variance_amount: string | null;
  variance_percentage_points: string | null;
  status: DriftStatus;
  transaction_count: number;
}

// ── Merchant / transaction drivers (GET /api/v1/plan-vs-actual/merchants,
// GET /api/v1/plan-vs-actual/transactions) — PR 08, Banking Drift & Top
// Drivers. Mirrors backend/app/domain/plan_vs_actual.py's `MerchantDriver` /
// `TransactionDrift` shapes exactly, same no-reshaping discipline as
// `CategoryDrift` above. Both endpoints already apply the same
// `_counts_toward_bucket` eligibility gate the rest of Plan vs Actual uses —
// internal transfers, origin-only transfer legs, and card payments never
// appear in either response, so no client-side filtering is needed here.

export interface MerchantDriver {
  merchant: string;
  bucket: MasterBucket | null;
  category: string | null;
  amount: string;
  transaction_count: number;
}

export interface TransactionDriver {
  transaction_id: string;
  transaction_date: string;
  description: string;
  merchant: string | null;
  bucket: MasterBucket;
  category: string | null;
  amount: string;
}

// ── Banking Insights (GET /api/v1/dashboard/banking/insights) — PR 10 ─────

export type BankingInsightType =
  | "merchant_overspend"
  | "category_overspend"
  | "persistent_wants_overspend"
  | "unusual_spending_spike"
  | "savings_shortfall"
  | "recurring_charge_increase"
  | "merchant_concentration"
  | "classification_uncertainty"
  | "positive_improvement";

export type BankingInsightSeverity = "positive" | "info" | "warning" | "critical";

export interface BankingInsightFact {
  label: string;
  value: string;
}

export interface BankingInsight {
  type: BankingInsightType;
  severity: BankingInsightSeverity;
  tone: "good" | "neutral" | "warning" | "danger";
  title: string;
  summary: string;
  impact_amount: string | null;
  confidence: string;
  action: string;
  supporting_facts: BankingInsightFact[];
}

export interface BankingInsightsResult {
  period: string;
  insights: BankingInsight[];
}

// ── Classification review queue (GET /api/v1/classification/needs-review,
// POST .../confirm, POST .../reclassify) — PR 09. Mirrors
// backend/app/domain/classification_review.py's response shapes exactly, no
// reshaping on the client. The classification ENGINE/SERVICE (bucket,
// category, confidence, source) already exists (PR 03); this module only
// adds the review-queue row shape and the two write actions.

export type ReviewReason = "unclassified" | "ambiguous_merchant" | "low_confidence";

export interface TransactionReviewItem {
  transaction_id: string;
  transaction_date: string;
  description: string;
  merchant: string | null;
  amount: string;
  master_bucket: MasterBucket;
  category: string | null;
  cash_flow_type: string;
  confidence: number;
  needs_review: boolean;
  classification_source: string;
  review_reason: ReviewReason;
}

export interface ClassificationActionResult {
  transaction_id: string;
  master_bucket: MasterBucket;
  category: string | null;
  cash_flow_type: string;
  confidence: number;
  needs_review: boolean;
  source: string;
}

/** User-facing "Change" bucket choice — a superset of `MasterBucket`
 * ("transfer" is a distinct, meaningful choice the backend resolves to
 * `unclassified` + `cash_flow_type: "transfer"`, see
 * `resolve_reclassify_choice` in classification_review.py). Never resolved
 * to a (bucket, cash_flow_type) pair on the client — that mapping is
 * deterministic backend logic. */
export type ReclassifyChoice = "needs" | "wants" | "savings" | "investments" | "transfer" | "unclassified";

export type ReclassifyScope = "transaction" | "merchant_future" | "merchant_this_month";

export interface ReclassifyRequestBody {
  master_bucket: ReclassifyChoice;
  category?: string | null;
  scope: ReclassifyScope;
}

export interface ReclassifyResponse {
  transaction: ClassificationActionResult;
  scope: ReclassifyScope;
  other_transactions_reclassified: number;
}

export const classificationApi = {
  /** Compact, backend-prioritized review queue — never the full transaction
   * list. `period` follows the same PR 05 unified contract as every other
   * financial fetch: the backend scopes the queue (and its lazy
   * classification backfill) to the selected range, so the rows shown are
   * exactly the ones affecting the Plan vs Actual numbers on screen. */
  needsReview: (limit = 20, period?: PlanPeriodParams): Promise<TransactionReviewItem[]> =>
    api.get<TransactionReviewItem[]>("/classification/needs-review", {
      limit,
      start_date: period?.startDate,
      end_date: period?.endDate,
    }),

  /** "Looks right" — locks in the transaction's current classification, clearing needs_review. */
  confirmTransaction: (transactionId: string): Promise<ClassificationActionResult> =>
    api.post<ClassificationActionResult>(`/classification/transactions/${transactionId}/confirm`, {}),

  /** "Change" — user-decided correction; see ReclassifyScope for the three scope options. */
  reclassifyTransaction: (transactionId: string, body: ReclassifyRequestBody): Promise<ReclassifyResponse> =>
    api.post<ReclassifyResponse>(`/classification/transactions/${transactionId}/reclassify`, body),
};

export const bankingApi = {
  /**
   * `startDate`/`endDate` (PR 05 unified period contract, see
   * lib/period.ts) take precedence over the legacy `months` rolling window
   * when provided — the backend always queries by the resolved range, never
   * fetches everything and filters client-side.
   */
  banking: (months = 12, period?: DashboardPeriodParams): Promise<BankingDashboard> =>
    api.get<BankingDashboard>("/dashboard/banking", {
      months,
      start_date: period?.startDate,
      end_date: period?.endDate,
    }),

  /** Category-level drift within one master bucket (Needs/Wants/Savings/Investments) for the given period. */
  bucketBreakdown: (bucket: MasterBucket, period?: PlanPeriodParams): Promise<CategoryDrift[]> =>
    api.get<CategoryDrift[]>(`/plan-vs-actual/buckets/${bucket}`, {
      start_date: period?.startDate,
      end_date: period?.endDate,
    }),

  /** Top merchant/description drivers, optionally narrowed to one bucket/category — backend-aggregated (PR 08). */
  merchantDrivers: (
    bucket: MasterBucket | null,
    category: string | null,
    period?: PlanPeriodParams,
    limit?: number,
  ): Promise<MerchantDriver[]> =>
    api.get<MerchantDriver[]>("/plan-vs-actual/merchants", {
      bucket: bucket ?? undefined,
      category: category ?? undefined,
      start_date: period?.startDate,
      end_date: period?.endDate,
      limit,
    }),

  /** Individual transactions behind one bucket/category/merchant driver — the leaf of Category -> merchants -> transactions (PR 08). */
  transactionDrivers: (
    bucket: MasterBucket | null,
    category: string | null,
    merchant: string | null,
    period?: PlanPeriodParams,
  ): Promise<TransactionDriver[]> =>
    api.get<TransactionDriver[]>("/plan-vs-actual/transactions", {
      bucket: bucket ?? undefined,
      category: category ?? undefined,
      merchant: merchant ?? undefined,
      start_date: period?.startDate,
      end_date: period?.endDate,
    }),

  /** Deterministic Coral Banking Insights, ranked and capped by the backend. */
  insights: (period?: PlanPeriodParams): Promise<BankingInsightsResult> =>
    api.get<BankingInsightsResult>("/dashboard/banking/insights", {
      start_date: period?.startDate,
      end_date: period?.endDate,
    }),
};
