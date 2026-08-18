import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import PlanVsActualSection from "./PlanVsActualSection";
import type { PlanVsActualResult } from "@/features/overview/api";

const RESULT: PlanVsActualResult = {
  period: { start: "2026-08-01", end: "2026-08-31", label: "2026-08" },
  plan_version_id: "plan-v1",
  plan_version_number: 1,
  plan_effective_from: "2026-01-01",
  plannable_income: "10000.00",
  buckets: [
    {
      bucket: "needs",
      target_percentage: "50",
      actual_percentage: "60",
      target_amount: "5000.00",
      actual_amount: "6000.00",
      variance_amount: "1000.00",
      variance_percentage_points: "10",
      status: "off_track",
      transaction_count: 4,
    },
    {
      bucket: "savings",
      target_percentage: "15",
      actual_percentage: "20",
      target_amount: "1500.00",
      actual_amount: "2000.00",
      variance_amount: "500.00",
      variance_percentage_points: "5",
      status: "on_track",
      transaction_count: 2,
    },
  ],
  completeness: {
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
  },
};

describe("<PlanVsActualSection />", () => {
  afterEach(() => cleanup());

  it("uses backend income when no salary override is supplied", () => {
    render(<PlanVsActualSection result={RESULT} loading={false} error={false} />);

    expect(screen.getByText("Target $5,000 · Actual $6,000 (60% of income)")).toBeInTheDocument();
    expect(screen.getByText("Target $1,500 · Actual $2,000 (20% of income)")).toBeInTheDocument();
  });

  it("recalculates target dollars and actual percentages from monthly targets across the selected period", () => {
    render(
      <PlanVsActualSection
        result={RESULT}
        loading={false}
        error={false}
        monthlyIncome={12000}
        monthlyTargets={{ needs: 6400, savings: 2100 }}
        periodMonths={1}
      />,
    );

    expect(screen.getByText("Target $6,400 · Actual $6,000 (50% of income)")).toBeInTheDocument();
    expect(screen.getByText("Target $2,100 · Actual $2,000 (16.67% of income)")).toBeInTheDocument();
  });

  it("multiplies monthly targets by the selected period month count", () => {
    render(
      <PlanVsActualSection
        result={RESULT}
        loading={false}
        error={false}
        monthlyIncome={12000}
        monthlyTargets={{ needs: 6400, savings: 2100 }}
        periodMonths={6}
      />,
    );

    expect(screen.getByText("Target $38,400 · Actual $6,000 (8.33% of income)")).toBeInTheDocument();
    expect(screen.getByText("Target $12,600 · Actual $2,000 (2.78% of income)")).toBeInTheDocument();
  });
});
