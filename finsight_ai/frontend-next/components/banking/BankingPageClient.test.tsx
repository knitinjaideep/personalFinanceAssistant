import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BankingPageClient from "./BankingPageClient";
import { bankingApi } from "@/features/banking/api";
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
vi.mock("@/components/banking/BankingFlowTree", () => ({
  default: () => <div>Banking flow tree</div>,
}));
vi.mock("@/components/banking/BudgetDriftTable", () => ({
  default: () => <div>Budget drift table</div>,
}));
vi.mock("@/components/banking/TopDrivers", () => ({
  default: () => <div>Top drivers table</div>,
}));
vi.mock("@/components/banking/ClassificationReviewSection", () => ({
  default: () => <div>Classification review</div>,
}));
vi.mock("@/components/banking/BankingInsightsSection", () => ({
  default: () => <div>Banking insights</div>,
}));

const BANKING_DASHBOARD = {
  spend_by_month: [],
  spend_by_category: [],
  top_merchants: [],
  card_summary: [],
  account_value_history: [],
  cash_flow: [],
  subscriptions: [],
  coverage: [],
  period: { start_date: "2026-08-01", end_date: "2026-08-31" },
};

const PLAN_VS_ACTUAL = {
  period: { start: "2026-08-01", end: "2026-08-31", label: "2026-08" },
  plan_version_id: "plan-v1",
  plan_version_number: 1,
  plan_effective_from: "2026-01-01",
  plannable_income: "10000.00",
  buckets: [],
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

const OVERVIEW_INSIGHTS = {
  period: PLAN_VS_ACTUAL.period,
  status: {
    headline: "You're slightly off plan this month",
    body: "Wants is above plan.",
    tone: "warning" as const,
    data_available: true,
  },
  insights: [],
  next_month_plan: [],
  completeness: PLAN_VS_ACTUAL.completeness,
};

const NEXT_MONTH_PLAN = {
  period: PLAN_VS_ACTUAL.period,
  recommendations: [
    {
      title: "Reduce Wants by $250 next period",
      reason: "Wants is $250 over target this period.",
      estimated_impact: "250.00",
      priority: 1,
      action_type: "reduce_category" as const,
      source_facts: [{ label: "Bucket", value: "Wants" }],
      bucket: "wants" as const,
      category: null,
      incomplete_source: false,
    },
    {
      title: "Increase Roth IRA contribution by $190 next period",
      reason: "Roth IRA is behind target.",
      estimated_impact: "190.00",
      priority: 2,
      action_type: "increase_investment_contribution" as const,
      source_facts: [{ label: "Vehicle", value: "Roth IRA" }],
      bucket: "investments" as const,
      category: "Roth IRA",
      incomplete_source: false,
    },
  ],
};

describe("<BankingPageClient />", () => {
  beforeEach(() => {
    vi.spyOn(bankingApi, "banking").mockResolvedValue(BANKING_DASHBOARD);
    vi.spyOn(bankingApi, "bucketBreakdown").mockResolvedValue([]);
    vi.spyOn(bankingApi, "insights").mockResolvedValue({ period: "2026-08", insights: [] });
    vi.spyOn(overviewApi, "planVsActual").mockResolvedValue(PLAN_VS_ACTUAL);
    vi.spyOn(overviewApi, "insights").mockResolvedValue(OVERVIEW_INSIGHTS);
    vi.spyOn(overviewApi, "nextMonthPlan").mockResolvedValue(NEXT_MONTH_PLAN);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("exposes banking-relevant recommendations from the shared PR14 planner", async () => {
    render(<BankingPageClient />);

    expect(await screen.findByText("Banking Next Month Plan")).toBeInTheDocument();
    expect(screen.getByText("Reduce Wants by $250 next period")).toBeInTheDocument();
    expect(screen.queryByText("Increase Roth IRA contribution by $190 next period")).not.toBeInTheDocument();
    expect(overviewApi.nextMonthPlan).toHaveBeenCalledWith({
      startDate: "2026-08-01",
      endDate: "2026-08-31",
    });
  });
});
