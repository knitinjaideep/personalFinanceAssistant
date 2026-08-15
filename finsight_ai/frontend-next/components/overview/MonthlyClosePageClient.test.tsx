import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MonthlyClosePageClient from "./MonthlyClosePageClient";
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

vi.mock("@/components/coral-ds/FinancialPeriodSelector", () => ({
  default: () => <div data-testid="period-selector">August 2026</div>,
}));

const CLOSE_RESULT = {
  period: { start: "2026-08-01", end: "2026-08-31", label: "2026-08" },
  generated_on: "2026-09-05",
  is_completed_month: true,
  summary: "You're slightly off plan this month",
  line_items: [
    {
      label: "Income",
      bucket: null,
      target_amount: null,
      actual_amount: "10000.00",
      variance_amount: null,
      status: "good" as const,
      note: "Observed income",
    },
    {
      label: "Wants",
      bucket: "wants" as const,
      target_amount: "2000.00",
      actual_amount: "2900.00",
      variance_amount: "900.00",
      status: "danger" as const,
      note: null,
    },
  ],
  went_well: [],
  needs_attention: [
    {
      title: "Overspending in Wants",
      description: "Wants is $900 over target.",
      tone: "danger" as const,
      bucket: "wants" as const,
      category: null,
      variance_amount: "900.00",
      target_amount: "2000.00",
      actual_amount: "2900.00",
    },
  ],
  biggest_drivers: [
    {
      merchant: "FANCY RESTAURANT",
      bucket: "wants" as const,
      category: "Dining",
      amount: "2900.00",
      transaction_count: 1,
    },
  ],
  goal_progress: [
    {
      name: "Emergency Fund",
      category_name: "Emergency Fund",
      current_amount: "500.00",
      target_amount_effective: "1000.00",
      variance_amount: "-500.00",
      status: "behind",
      incomplete_source: false,
    },
  ],
  next_month_plan: [
    {
      title: "Reduce Wants by $900 next period",
      reason: "Wants is over target this period.",
      estimated_impact: "900.00",
      priority: 1,
      action_type: "reduce_category" as const,
      source_facts: [{ label: "Bucket", value: "Wants" }],
      bucket: "wants" as const,
      category: null,
      incomplete_source: false,
    },
  ],
  completeness_notes: [],
};

describe("<MonthlyClosePageClient />", () => {
  beforeEach(() => {
    vi.spyOn(overviewApi, "monthlyClose").mockResolvedValue(CLOSE_RESULT);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("renders the close report and fetches the selected period", async () => {
    render(<MonthlyClosePageClient />);

    expect(await screen.findByText("You're slightly off plan this month")).toBeInTheDocument();
    expect(screen.getByText("Income")).toBeInTheDocument();
    expect(screen.getAllByText("Wants").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Overspending in Wants")).toBeInTheDocument();
    expect(screen.getByText("FANCY RESTAURANT")).toBeInTheDocument();
    expect(screen.getByText("Emergency Fund")).toBeInTheDocument();
    expect(screen.getByText("Reduce Wants by $900 next period")).toBeInTheDocument();
    expect(overviewApi.monthlyClose).toHaveBeenCalledWith({
      startDate: "2026-08-01",
      endDate: "2026-08-31",
    });
  });
});
