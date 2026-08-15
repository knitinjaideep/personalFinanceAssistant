"use client";

/**
 * <ClassificationReviewSection /> — "Transactions to Review" (PR 09,
 * docs/coral-redesign/pr-09-classification-review.md), a compact section on
 * the Banking page.
 *
 * The classification ENGINE and SERVICE already exist (PR 03) — this
 * component only renders `GET /api/v1/classification/needs-review` (already
 * prioritized/capped server-side, never the full transaction list) and wires
 * the two write actions ("Looks right" / "Change") to
 * `POST .../confirm` and `POST .../reclassify`. No financial value is
 * computed here — bucket/category/confidence/amount are all rendered
 * verbatim from the backend response; the only client-side logic is a
 * display-label lookup from the backend's own `review_reason` enum (never a
 * recomputed threshold).
 *
 * Row lifecycle: "Looks right" and every "Change" scope always resolve the
 * REVIEWED transaction itself via a tier-1 override (see
 * TransactionClassificationService.reclassify_transaction's docstring), so a
 * successful action always removes that row from the list. A failed action
 * leaves the row exactly as it was (no optimistic mutation before the
 * request resolves) and shows an inline error with a retry affordance.
 */

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, HelpCircle, Pencil, X } from "lucide-react";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import StatusBadge from "@/components/coral-ds/StatusBadge";
import Surface from "@/components/coral-ds/Surface";
import {
  classificationApi,
  type DashboardPeriodParams,
  type ReclassifyChoice,
  type ReclassifyScope,
  type ReviewReason,
  type TransactionReviewItem,
} from "@/features/banking/api";
import { formatCurrency, formatDate } from "@/lib/utils";

// Mirrors the fixed taxonomy in backend/app/domain/transaction_classification.py
// (NEEDS_CATEGORIES / WANTS_CATEGORIES / SAVINGS_CATEGORIES /
// INVESTMENTS_CATEGORIES) — a static presentation list, not user data or a
// computed value. Transfer/Unclassified intentionally have no sub-categories.
const CATEGORIES_BY_CHOICE: Record<ReclassifyChoice, string[]> = {
  needs: ["Housing", "Utilities", "Connectivity", "Groceries", "Transportation", "Insurance", "Healthcare", "Minimum Debt"],
  wants: ["Dining", "Entertainment", "Travel", "Shopping", "Personal Care", "Fitness/Hobbies", "Home Decor", "Gifts/Celebrations"],
  savings: ["Emergency Fund", "House / Goals", "Child Savings"],
  investments: ["401(k)", "Roth IRA", "ESPP", "Taxable Brokerage"],
  transfer: [],
  unclassified: [],
};

const CHOICE_OPTIONS: { value: ReclassifyChoice; label: string }[] = [
  { value: "needs", label: "Needs" },
  { value: "wants", label: "Wants" },
  { value: "savings", label: "Savings" },
  { value: "investments", label: "Investments" },
  { value: "transfer", label: "Transfer" },
  { value: "unclassified", label: "Other / Unclassified" },
];

const SCOPE_OPTIONS: { value: ReclassifyScope; label: string; hint: string }[] = [
  { value: "transaction", label: "Only this transaction", hint: "Corrects just this one." },
  { value: "merchant_future", label: "Future transactions from this merchant", hint: "Applies going forward; past transactions are untouched." },
  { value: "merchant_this_month", label: "All matching transactions this month", hint: "Also corrects this merchant's other transactions in the same month." },
];

const BUCKET_LABEL: Record<string, string> = {
  needs: "Needs",
  wants: "Wants",
  savings: "Savings",
  investments: "Investments",
  unclassified: "Unclassified",
};

// Presentation-only label lookup from the backend's OWN `review_reason` enum
// (see classification_review.py::describe_review_reason) — never a fresh
// confidence threshold computed on the client.
const REASON_LABEL: Record<ReviewReason, string> = {
  low_confidence: "Low confidence",
  ambiguous_merchant: "Ambiguous merchant",
  unclassified: "Unclassified",
};

function ReasonBadge({ reason }: { reason: ReviewReason }) {
  const tone = reason === "unclassified" ? "neutral" : "warning";
  return (
    <StatusBadge status={tone}>
      <HelpCircle size={11} />
      {REASON_LABEL[reason]}
    </StatusBadge>
  );
}

interface ChangeFormState {
  bucket: ReclassifyChoice;
  category: string;
  scope: ReclassifyScope;
}

function ChangeForm({
  transactionId,
  merchantLabel,
  initialBucket,
  submitting,
  onCancel,
  onSubmit,
}: {
  transactionId: string;
  merchantLabel: string;
  initialBucket: string;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (form: ChangeFormState) => void;
}) {
  const defaultBucket: ReclassifyChoice =
    (CHOICE_OPTIONS.find((o) => o.value === initialBucket)?.value as ReclassifyChoice) ?? "unclassified";
  const [form, setForm] = useState<ChangeFormState>({ bucket: defaultBucket, category: "", scope: "transaction" });

  const categoryOptions = CATEGORIES_BY_CHOICE[form.bucket];
  const categorySelectId = `reclassify-category-${transactionId}`;

  return (
    <div
      className="mt-3 rounded-2xl p-4 space-y-4"
      style={{ background: "var(--row-bg)", border: "1px solid var(--border-subtle)" }}
    >
      <div>
        <p className="micro-text font-semibold mb-2" style={{ color: "var(--text-dim)" }}>Bucket</p>
        <div className="flex flex-wrap gap-2" role="group" aria-label={`Bucket for ${merchantLabel}`}>
          {CHOICE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              aria-pressed={form.bucket === opt.value}
              onClick={() => setForm((f) => ({ ...f, bucket: opt.value, category: "" }))}
              className="px-3 py-1.5 rounded-xl micro-text font-semibold transition-colors"
              style={{
                background: form.bucket === opt.value ? "var(--accent-strong)" : "var(--panel-bg)",
                color: form.bucket === opt.value ? "#0B1220" : "var(--text-secondary)",
                border: "1px solid var(--border-subtle)",
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {categoryOptions.length > 0 && (
        <div>
          <label
            htmlFor={categorySelectId}
            className="micro-text font-semibold mb-2 block"
            style={{ color: "var(--text-dim)" }}
          >
            Category (optional)
          </label>
          <select
            id={categorySelectId}
            value={form.category}
            onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
            className="w-full sm:w-auto px-3 py-2 rounded-xl small-text"
            style={{ background: "var(--panel-bg)", color: "var(--text-primary)", border: "1px solid var(--border-subtle)" }}
          >
            <option value="">No specific category</option>
            {categoryOptions.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
      )}

      <div>
        <p className="micro-text font-semibold mb-2" style={{ color: "var(--text-dim)" }}>Apply to</p>
        <div className="space-y-1.5" role="radiogroup" aria-label={`Apply this correction to, for ${merchantLabel}`}>
          {SCOPE_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className="flex items-start gap-2.5 px-3 py-2 rounded-xl cursor-pointer transition-colors"
              style={{
                background: form.scope === opt.value ? "var(--status-neutral-soft)" : "transparent",
                border: "1px solid var(--border-subtle)",
              }}
            >
              <input
                type="radio"
                // Unique per row — more than one row can have its Change
                // form open at once, and a shared radio `name` would make
                // the browser treat them as one group.
                name={`reclassify-scope-${transactionId}`}
                checked={form.scope === opt.value}
                onChange={() => setForm((f) => ({ ...f, scope: opt.value }))}
                className="mt-1"
              />
              <span>
                <span className="small-text font-semibold block" style={{ color: "var(--text-primary)" }}>{opt.label}</span>
                <span className="micro-text" style={{ color: "var(--text-dim)" }}>{opt.hint}</span>
              </span>
            </label>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2 justify-end pt-1">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="px-4 py-2 rounded-xl small-text font-semibold btn-glass"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => onSubmit(form)}
          disabled={submitting}
          className="px-4 py-2 rounded-xl small-text font-semibold text-white btn-coral disabled:opacity-60"
        >
          {submitting ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}

interface RowUiState {
  editing: boolean;
  submitting: boolean;
  error: string | null;
}

const ROW_IDLE: RowUiState = { editing: false, submitting: false, error: null };

export interface ClassificationReviewSectionProps {
  /** The globally-selected financial period (PR 05). The queue is scoped to
   * it server-side so the rows shown are exactly the ones affecting the
   * Plan vs Actual numbers on this page — correcting one visibly moves them. */
  period: DashboardPeriodParams;
  /** Called after any successful confirm/reclassify so the caller can
   * refetch the flow tree / drift table / top drivers for this period —
   * Plan vs Actual is naturally live server-side, so a plain refetch is
   * enough (no separate invalidation plumbing). */
  onChanged?: () => void;
}

export default function ClassificationReviewSection({ period, onChanged }: ClassificationReviewSectionProps) {
  const [items, setItems] = useState<TransactionReviewItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [rowState, setRowState] = useState<Record<string, RowUiState>>({});

  const { startDate, endDate } = period;

  const load = useCallback(() => {
    setLoading(true);
    setError(false);
    // Any in-flight row UI (open Change form, stale inline error) belongs to
    // the previous result set — never carry it across a refetch.
    setRowState({});
    classificationApi
      .needsReview(20, { startDate, endDate })
      .then((data) => {
        setItems(data);
        setLoading(false);
      })
      .catch(() => {
        setItems(null);
        setLoading(false);
        setError(true);
      });
  }, [startDate, endDate]);

  useEffect(() => { load(); }, [load]);

  const getRowState = (id: string): RowUiState => rowState[id] ?? ROW_IDLE;
  const setRow = (id: string, patch: Partial<RowUiState>) =>
    setRowState((s) => ({ ...s, [id]: { ...getRowState(id), ...patch } }));

  const removeRow = (id: string) => setItems((prev) => (prev ? prev.filter((r) => r.transaction_id !== id) : prev));

  const handleConfirm = (id: string) => {
    setRow(id, { submitting: true, error: null });
    classificationApi
      .confirmTransaction(id)
      .then(() => {
        removeRow(id);
        setRowState((s) => { const next = { ...s }; delete next[id]; return next; });
        onChanged?.();
      })
      .catch((e) => {
        setRow(id, { submitting: false, error: e?.message ?? "Couldn't save. Try again." });
      });
  };

  const handleReclassify = (id: string, form: ChangeFormState) => {
    setRow(id, { submitting: true, error: null });
    classificationApi
      .reclassifyTransaction(id, {
        master_bucket: form.bucket,
        category: form.category || null,
        scope: form.scope,
      })
      .then((res) => {
        if (res.other_transactions_reclassified > 0) {
          // A `merchant_this_month` correction can also resolve OTHER rows
          // currently sitting in this queue. Removing only the row the user
          // touched would leave those showing a classification the backend
          // has already changed — refetch instead of guessing which ones.
          load();
          onChanged?.();
          return;
        }
        removeRow(id);
        setRowState((s) => { const next = { ...s }; delete next[id]; return next; });
        onChanged?.();
      })
      .catch((e) => {
        setRow(id, { submitting: false, error: e?.message ?? "Couldn't save. Try again." });
      });
  };

  if (loading) return <SkeletonState variant="card" height="220px" />;
  if (error) return <ErrorState message="Couldn't load transactions to review." onRetry={load} />;
  if (!items || items.length === 0) {
    return (
      <EmptyState
        compact
        title="Nothing needs review this period"
        description="Coral will flag low-confidence or ambiguous transactions here as they come in."
      />
    );
  }

  return (
    <Surface padding="md" className="space-y-3">
      {items.map((item) => {
        const state = getRowState(item.transaction_id);
        const amount = Number(item.amount);
        const label = item.merchant || item.description;
        return (
          <div
            key={item.transaction_id}
            className="rounded-2xl px-4 py-3.5"
            style={{ background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" }}
          >
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
              <div className="min-w-0 flex-1">
                <p className="small-text font-semibold truncate" style={{ color: "var(--text-primary)" }} title={item.description}>
                  {label}
                </p>
                <div className="flex flex-wrap items-center gap-2 mt-1">
                  <span className="micro-text" style={{ color: "var(--text-dim)" }}>{formatDate(item.transaction_date)}</span>
                  <span className="micro-text" style={{ color: "var(--text-dim)" }}>·</span>
                  <span className="micro-text" style={{ color: "var(--text-dim)" }}>
                    {BUCKET_LABEL[item.master_bucket] ?? item.master_bucket}
                    {item.category ? ` · ${item.category}` : ""}
                  </span>
                  <ReasonBadge reason={item.review_reason} />
                </div>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <span className="small-text font-bold tabular" style={{ color: "var(--text-primary)" }}>
                  {amount < 0 ? `-${formatCurrency(Math.abs(amount))}` : formatCurrency(amount)}
                </span>
                {!state.editing && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleConfirm(item.transaction_id)}
                      disabled={state.submitting}
                      aria-label={`Confirm the current classification for ${label}`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl micro-text font-semibold btn-glass disabled:opacity-60"
                    >
                      <Check size={12} aria-hidden /> Looks right
                    </button>
                    <button
                      type="button"
                      onClick={() => setRow(item.transaction_id, { editing: true, error: null })}
                      disabled={state.submitting}
                      aria-label={`Change the classification for ${label}`}
                      aria-expanded={false}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl micro-text font-semibold btn-glass disabled:opacity-60"
                    >
                      <Pencil size={12} aria-hidden /> Change
                    </button>
                  </div>
                )}
                {state.editing && (
                  <button
                    type="button"
                    onClick={() => setRow(item.transaction_id, { editing: false, error: null })}
                    disabled={state.submitting}
                    aria-label={`Close the classification editor for ${label}`}
                    aria-expanded
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl micro-text font-semibold btn-glass disabled:opacity-60"
                  >
                    <X size={12} aria-hidden /> Close
                  </button>
                )}
              </div>
            </div>

            {state.error && (
              <div
                role="alert"
                className="mt-3 flex items-center gap-2 px-3 py-2 rounded-xl micro-text"
                style={{ background: "var(--status-danger-soft)", color: "var(--status-danger)" }}
              >
                <AlertTriangle size={12} aria-hidden />
                {state.error}
              </div>
            )}

            {state.editing && (
              <ChangeForm
                transactionId={item.transaction_id}
                merchantLabel={label}
                initialBucket={item.master_bucket}
                submitting={state.submitting}
                onCancel={() => setRow(item.transaction_id, { editing: false, error: null })}
                onSubmit={(form) => handleReclassify(item.transaction_id, form)}
              />
            )}
          </div>
        );
      })}
    </Surface>
  );
}
