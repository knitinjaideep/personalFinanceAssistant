import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HomePageClient from "./HomePageClient";
import { documentsApi } from "@/features/documents/api";
import { overviewApi } from "@/features/overview/api";

vi.mock("@/hooks/useFinancialPeriod", () => ({
  useFinancialPeriod: () => ({
    selection: { mode: "current_month", year: 2026, month: 8 },
    resolved: { startDate: "2026-08-01", endDate: "2026-08-31", label: "August 2026" },
    setSelection: vi.fn(),
    goToPreviousMonth: vi.fn(),
    goToNextMonth: vi.fn(),
  }),
}));

vi.mock("@/store/appStore", () => ({
  useAppStore: () => vi.fn(),
}));

vi.mock("@/components/coral-ds/FinancialPeriodSelector", () => ({
  default: () => <div data-testid="period-selector">August 2026</div>,
}));
vi.mock("@/components/coral/CoralMascot", () => ({
  default: () => <div data-testid="mascot" />,
}));

const COMPLETENESS = {
  plan_available: true,
  plan_version_changed_mid_period: false,
  income_observed: true,
  unclassified_transaction_count: 0,
  unclassified_amount: "0.00",
  needs_review_count: 0,
  origin_only_transfer_legs_count: 0,
  origin_only_transfer_legs_amount: "0.00",
  payroll_deduction_signal_detected: false,
  notes: [],
  is_complete: true,
};

const PERIOD = { start: "2026-08-01", end: "2026-08-31", label: "2026-08" };

describe("<HomePageClient />", () => {
  beforeEach(() => {
    vi.spyOn(documentsApi, "stats").mockResolvedValue({
      total: 1,
      parsed: 1,
      processing: 0,
      uploaded: 0,
      failed: 0,
    });
    vi.spyOn(overviewApi, "planVsActual").mockResolvedValue({
      period: PERIOD,
      plan_version_id: "plan-v1",
      plan_version_number: 1,
      plan_effective_from: "2026-01-01",
      plannable_income: "10000.00",
      buckets: [],
      completeness: COMPLETENESS,
    });
    vi.spyOn(overviewApi, "insights").mockResolvedValue({
      period: PERIOD,
      status: {
        headline: "You're slightly off plan this month",
        body: "Wants is above plan.",
        tone: "warning",
        data_available: true,
      },
      insights: [],
      next_month_plan: [],
      completeness: COMPLETENESS,
    });
    vi.spyOn(overviewApi, "monthlyFlow").mockResolvedValue([
      {
        period_label: "2026-08",
        start: "2026-08-01",
        end: "2026-08-31",
        income: "10000.00",
        spent: "2900.00",
        saved_invested: "0.00",
        income_observed: true,
      },
    ]);
    vi.spyOn(overviewApi, "nextMonthPlan").mockResolvedValue({
      period: PERIOD,
      recommendations: [
        {
          title: "Reduce Wants by $250 next period",
          reason: "Wants is $250 over target this period.",
          estimated_impact: "250.00",
          priority: 1,
          action_type: "reduce_category",
          source_facts: [{ label: "Bucket", value: "Wants" }],
          bucket: "wants",
          category: null,
          incomplete_source: false,
        },
      ],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("uses the PR14 planner endpoint and links to the selected monthly close", async () => {
    render(<HomePageClient />);

    expect(await screen.findByText("Reduce Wants by $250 next period")).toBeInTheDocument();
    expect(screen.getByText("Bucket")).toBeInTheDocument();
    const closeLink = screen.getByRole("link", { name: "Open close" });
    expect(closeLink).toHaveAttribute(
      "href",
      "/monthly-close?period=custom&start=2026-08-01&end=2026-08-31",
    );
    expect(overviewApi.nextMonthPlan).toHaveBeenCalledWith({
      startDate: "2026-08-01",
      endDate: "2026-08-31",
    });
  });
});
