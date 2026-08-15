/**
 * Component tests for <ClassificationReviewSection /> (PR 09,
 * docs/coral-redesign/pr-09-classification-review.md).
 *
 * `classificationApi` is mocked at the module boundary — this suite never
 * hits a real backend, and never asserts on financial computation (the
 * component renders backend-supplied numbers verbatim). It covers the
 * behavioral contract the work order asks for: the queue renders, "Looks
 * right" removes a row, "Change" calls the right endpoint with the right
 * body for each scope option, and a failed action leaves the row unchanged
 * with a visible error instead of an optimistic (wrong) update.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ClassificationReviewSection from "./ClassificationReviewSection";
import { classificationApi, type TransactionReviewItem } from "@/features/banking/api";

vi.mock("@/features/banking/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/banking/api")>("@/features/banking/api");
  return {
    ...actual,
    classificationApi: {
      needsReview: vi.fn(),
      confirmTransaction: vi.fn(),
      reclassifyTransaction: vi.fn(),
    },
  };
});

const mockedApi = vi.mocked(classificationApi, true);

const PERIOD = { startDate: "2026-08-01", endDate: "2026-08-31" };

const ITEM_A: TransactionReviewItem = {
  transaction_id: "txn-amazon-1",
  transaction_date: "2026-08-05",
  description: "AMAZON.COM*A1B2C3",
  merchant: "Amazon",
  amount: "-40.00",
  master_bucket: "unclassified",
  category: null,
  cash_flow_type: "expense",
  confidence: 0.35,
  needs_review: true,
  classification_source: "heuristic",
  review_reason: "ambiguous_merchant",
};

const ITEM_B: TransactionReviewItem = {
  transaction_id: "txn-misc-2",
  transaction_date: "2026-08-06",
  description: "MISC POS 99182734",
  merchant: null,
  amount: "-9.00",
  master_bucket: "unclassified",
  category: null,
  cash_flow_type: "expense",
  confidence: 0.0,
  needs_review: true,
  classification_source: "unknown",
  review_reason: "unclassified",
};

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("<ClassificationReviewSection />", () => {
  it("renders the review queue with merchant, date, amount, and reason badge", async () => {
    mockedApi.needsReview.mockResolvedValue([ITEM_A, ITEM_B]);

    render(<ClassificationReviewSection period={PERIOD} />);

    expect(await screen.findByText("Amazon")).toBeInTheDocument();
    expect(screen.getByText("MISC POS 99182734")).toBeInTheDocument();
    expect(screen.getByText("Ambiguous merchant")).toBeInTheDocument();
    // "Unclassified" appears both as the bucket label and (for item B) the
    // review-reason badge — assert count rather than a single unique match.
    expect(screen.getAllByText("Unclassified").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("-$40")).toBeInTheDocument();
  });

  it("fetches the queue scoped to the selected period, and refetches when it changes", async () => {
    mockedApi.needsReview.mockResolvedValue([ITEM_A]);

    const { rerender } = render(<ClassificationReviewSection period={PERIOD} />);
    await screen.findByText("Amazon");
    expect(mockedApi.needsReview).toHaveBeenCalledWith(20, PERIOD);

    const nextPeriod = { startDate: "2026-07-01", endDate: "2026-07-31" };
    rerender(<ClassificationReviewSection period={nextPeriod} />);
    await waitFor(() => expect(mockedApi.needsReview).toHaveBeenCalledWith(20, nextPeriod));
  });

  it("shows an empty state when nothing needs review", async () => {
    mockedApi.needsReview.mockResolvedValue([]);
    render(<ClassificationReviewSection period={PERIOD} />);
    expect(await screen.findByText("Nothing needs review this period")).toBeInTheDocument();
  });

  it("shows an error state and can retry when the queue fails to load", async () => {
    mockedApi.needsReview.mockRejectedValueOnce(new Error("network down"));
    render(<ClassificationReviewSection period={PERIOD} />);
    expect(await screen.findByText("Couldn't load transactions to review.")).toBeInTheDocument();

    mockedApi.needsReview.mockResolvedValueOnce([ITEM_A]);
    fireEvent.click(screen.getByText("Try again"));
    expect(await screen.findByText("Amazon")).toBeInTheDocument();
  });

  it('"Looks right" removes the row on success and notifies the parent', async () => {
    mockedApi.needsReview.mockResolvedValue([ITEM_A]);
    mockedApi.confirmTransaction.mockResolvedValue({
      transaction_id: ITEM_A.transaction_id,
      master_bucket: "unclassified",
      category: null,
      cash_flow_type: "expense",
      confidence: 1.0,
      needs_review: false,
      source: "user",
    });
    const onChanged = vi.fn();

    render(<ClassificationReviewSection period={PERIOD} onChanged={onChanged} />);
    await screen.findByText("Amazon");

    fireEvent.click(screen.getByText("Looks right"));

    await waitFor(() => expect(screen.queryByText("Amazon")).not.toBeInTheDocument());
    expect(mockedApi.confirmTransaction).toHaveBeenCalledWith(ITEM_A.transaction_id);
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it('"Looks right" leaves the row unchanged and shows an error on failure', async () => {
    mockedApi.needsReview.mockResolvedValue([ITEM_A]);
    mockedApi.confirmTransaction.mockRejectedValue(new Error("save failed"));
    const onChanged = vi.fn();

    render(<ClassificationReviewSection period={PERIOD} onChanged={onChanged} />);
    await screen.findByText("Amazon");

    fireEvent.click(screen.getByText("Looks right"));

    expect(await screen.findByText("save failed")).toBeInTheDocument();
    // The row is still present, untouched.
    expect(screen.getByText("Amazon")).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('"Change" with scope=transaction calls reclassify with the right body', async () => {
    mockedApi.needsReview.mockResolvedValue([ITEM_A]);
    mockedApi.reclassifyTransaction.mockResolvedValue({
      transaction: {
        transaction_id: ITEM_A.transaction_id,
        master_bucket: "wants",
        category: "Shopping",
        cash_flow_type: "expense",
        confidence: 1.0,
        needs_review: false,
        source: "user",
      },
      scope: "transaction",
      other_transactions_reclassified: 0,
    });

    render(<ClassificationReviewSection period={PERIOD} />);
    await screen.findByText("Amazon");

    fireEvent.click(screen.getByText("Change"));
    fireEvent.click(screen.getByText("Wants"));
    // Scope defaults to "transaction" — just save.
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() =>
      expect(mockedApi.reclassifyTransaction).toHaveBeenCalledWith(ITEM_A.transaction_id, {
        master_bucket: "wants",
        category: null,
        scope: "transaction",
      })
    );
    await waitFor(() => expect(screen.queryByText("Amazon")).not.toBeInTheDocument());
  });

  it('"Change" with scope=merchant_future calls reclassify with that scope', async () => {
    mockedApi.needsReview.mockResolvedValue([ITEM_A]);
    mockedApi.reclassifyTransaction.mockResolvedValue({
      transaction: {
        transaction_id: ITEM_A.transaction_id,
        master_bucket: "wants",
        category: null,
        cash_flow_type: "expense",
        confidence: 1.0,
        needs_review: false,
        source: "user",
      },
      scope: "merchant_future",
      other_transactions_reclassified: 0,
    });

    render(<ClassificationReviewSection period={PERIOD} />);
    await screen.findByText("Amazon");

    fireEvent.click(screen.getByText("Change"));
    fireEvent.click(screen.getByText("Wants"));
    fireEvent.click(screen.getByText("Future transactions from this merchant"));
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() =>
      expect(mockedApi.reclassifyTransaction).toHaveBeenCalledWith(ITEM_A.transaction_id, {
        master_bucket: "wants",
        category: null,
        scope: "merchant_future",
      })
    );
  });

  it('"Change" with scope=merchant_this_month and a category calls reclassify with that body', async () => {
    mockedApi.needsReview.mockResolvedValue([ITEM_A]);
    mockedApi.reclassifyTransaction.mockResolvedValue({
      transaction: {
        transaction_id: ITEM_A.transaction_id,
        master_bucket: "wants",
        category: "Shopping",
        cash_flow_type: "expense",
        confidence: 1.0,
        needs_review: false,
        source: "user",
      },
      scope: "merchant_this_month",
      other_transactions_reclassified: 2,
    });

    render(<ClassificationReviewSection period={PERIOD} />);
    await screen.findByText("Amazon");

    fireEvent.click(screen.getByText("Change"));
    fireEvent.click(screen.getByText("Wants"));

    const categorySelect = screen.getByRole("combobox");
    fireEvent.change(categorySelect, { target: { value: "Shopping" } });

    fireEvent.click(screen.getByText("All matching transactions this month"));
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() =>
      expect(mockedApi.reclassifyTransaction).toHaveBeenCalledWith(ITEM_A.transaction_id, {
        master_bucket: "wants",
        category: "Shopping",
        scope: "merchant_this_month",
      })
    );
  });

  it("refetches the whole queue when a correction also resolved other rows", async () => {
    // ITEM_B is a second row that the merchant_this_month correction below
    // also resolves server-side; removing only ITEM_A would leave ITEM_B
    // rendering a classification the backend has already changed.
    mockedApi.needsReview.mockResolvedValueOnce([ITEM_A, ITEM_B]).mockResolvedValueOnce([]);
    mockedApi.reclassifyTransaction.mockResolvedValue({
      transaction: {
        transaction_id: ITEM_A.transaction_id,
        master_bucket: "wants",
        category: null,
        cash_flow_type: "expense",
        confidence: 1.0,
        needs_review: false,
        source: "user",
      },
      scope: "merchant_this_month",
      other_transactions_reclassified: 1,
    });
    const onChanged = vi.fn();

    render(<ClassificationReviewSection period={PERIOD} onChanged={onChanged} />);
    await screen.findByText("Amazon");

    fireEvent.click(screen.getAllByText("Change")[0]);
    fireEvent.click(screen.getByText("Wants"));
    fireEvent.click(screen.getByText("All matching transactions this month"));
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => expect(mockedApi.needsReview).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Nothing needs review this period")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it('"Change" leaves the row unchanged and shows an error on failure', async () => {
    mockedApi.needsReview.mockResolvedValue([ITEM_A]);
    mockedApi.reclassifyTransaction.mockRejectedValue(new Error("could not reclassify"));

    render(<ClassificationReviewSection period={PERIOD} />);
    await screen.findByText("Amazon");

    fireEvent.click(screen.getByText("Change"));
    fireEvent.click(screen.getByText("Wants"));
    fireEvent.click(screen.getByText("Save"));

    expect(await screen.findByText("could not reclassify")).toBeInTheDocument();
    // Row still present and still showing its original classification.
    expect(screen.getByText("Amazon")).toBeInTheDocument();
  });

  it("Cancel closes the Change form without calling the API", async () => {
    mockedApi.needsReview.mockResolvedValue([ITEM_A]);
    render(<ClassificationReviewSection period={PERIOD} />);
    await screen.findByText("Amazon");

    fireEvent.click(screen.getByText("Change"));
    expect(screen.getByText("Apply to")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.queryByText("Apply to")).not.toBeInTheDocument();
    expect(mockedApi.reclassifyTransaction).not.toHaveBeenCalled();
  });
});
