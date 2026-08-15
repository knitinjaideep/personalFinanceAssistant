import { cleanup, render, screen, within } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InvestmentsPageClient from "./InvestmentsPageClient";
import { investmentsApi } from "@/features/investments/api";
import type {
  InvestmentContributionPlanResult,
  InvestmentsDashboard,
} from "@/features/investments/api";

vi.mock("@/hooks/useFinancialPeriod", () => ({
  useFinancialPeriod: () => ({
    selection: { mode: "month", year: 2026, month: 8 },
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

vi.mock("next/image", () => ({
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) =>
    React.createElement("img", props),
}));

const CONTRIBUTION_PLAN: InvestmentContributionPlanResult = {
  period: { start: "2026-08-01", end: "2026-08-31", label: "2026-08" },
  plannable_income: "10000.00",
  total_target_pct: "15",
  total_actual_amount: "1230.00",
  total_actual_pct: "12.3",
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
  vehicles: [
    {
      vehicle: "401(k)",
      target_pct: "6",
      actual_pct: "5.8",
      target_amount: "600.00",
      actual_amount: "580.00",
      variance_amount: "-20.00",
      variance_pct_points: "-0.20",
      status: "on_track",
      recommended_next_month_delta: "20.00",
      transaction_count: 1,
      data_completeness: {
        status: "complete",
        is_complete: true,
        income_observed: true,
        plan_available: true,
        payroll_data_complete: true,
        notes: [],
      },
    },
    {
      vehicle: "Roth IRA",
      target_pct: "4",
      actual_pct: "2.1",
      target_amount: "400.00",
      actual_amount: "210.00",
      variance_amount: "-190.00",
      variance_pct_points: "-1.90",
      status: "on_track",
      recommended_next_month_delta: "190.00",
      transaction_count: 1,
      data_completeness: {
        status: "complete",
        is_complete: true,
        income_observed: true,
        plan_available: true,
        payroll_data_complete: true,
        notes: [],
      },
    },
    {
      vehicle: "ESPP",
      target_pct: "3",
      actual_pct: "2.9",
      target_amount: "300.00",
      actual_amount: "290.00",
      variance_amount: "-10.00",
      variance_pct_points: "-0.10",
      status: "on_track",
      recommended_next_month_delta: "10.00",
      transaction_count: 1,
      data_completeness: {
        status: "complete",
        is_complete: true,
        income_observed: true,
        plan_available: true,
        payroll_data_complete: true,
        notes: [],
      },
    },
    {
      vehicle: "Taxable Brokerage",
      target_pct: "2",
      actual_pct: "1.5",
      target_amount: "200.00",
      actual_amount: "150.00",
      variance_amount: "-50.00",
      variance_pct_points: "-0.50",
      status: "on_track",
      recommended_next_month_delta: "50.00",
      transaction_count: 1,
      data_completeness: {
        status: "complete",
        is_complete: true,
        income_observed: true,
        plan_available: true,
        payroll_data_complete: true,
        notes: [],
      },
    },
  ],
};

const DASHBOARD: InvestmentsDashboard = {
  portfolio_summary: {
    total_portfolio_value: 120000,
    total_portfolio_value_fmt: "$120,000.00",
    total_unrealized_gain_loss: 12000,
    total_unrealized_gain_loss_fmt: "$12,000.00",
    last_updated: "2026-08-31",
    accounts: [
      {
        account_name: "Morgan Stanley Joint",
        account_type: "individual_brokerage",
        institution_type: "morgan_stanley",
        total_value: 70000,
        total_value_fmt: "$70,000.00",
        invested_value: 68000,
        cash_value: 2000,
        unrealized_gain_loss: 8000,
        unrealized_gain_loss_fmt: "$8,000.00",
        gain_loss_pct: 12,
        snapshot_date: "2026-08-31",
        latest_statement_date: "2026-08-31",
      },
      {
        account_name: "Roth IRA",
        account_type: "roth_ira",
        institution_type: "morgan_stanley",
        total_value: 50000,
        total_value_fmt: "$50,000.00",
        invested_value: 50000,
        cash_value: 0,
        unrealized_gain_loss: 4000,
        unrealized_gain_loss_fmt: "$4,000.00",
        gain_loss_pct: 8,
        snapshot_date: "2026-08-31",
        latest_statement_date: "2026-08-31",
      },
    ],
  },
  allocation: [
    {
      account_name: "Morgan Stanley Joint",
      account_type: "individual_brokerage",
      institution_type: "morgan_stanley",
      total_value: 70000,
      total_value_fmt: "$70,000.00",
      invested_value: 68000,
      cash_value: 2000,
      unrealized_gain_loss: 8000,
      unrealized_gain_loss_fmt: "$8,000.00",
      gain_loss_pct: 12,
      snapshot_date: "2026-08-31",
      latest_statement_date: "2026-08-31",
      pct_of_portfolio: 58.3,
    },
    {
      account_name: "Roth IRA",
      account_type: "roth_ira",
      institution_type: "morgan_stanley",
      total_value: 50000,
      total_value_fmt: "$50,000.00",
      invested_value: 50000,
      cash_value: 0,
      unrealized_gain_loss: 4000,
      unrealized_gain_loss_fmt: "$4,000.00",
      gain_loss_pct: 8,
      snapshot_date: "2026-08-31",
      latest_statement_date: "2026-08-31",
      pct_of_portfolio: 41.7,
    },
  ],
  top_holdings: [
    {
      symbol: "AAPL",
      description: "Apple Inc",
      market_value: 30000,
      market_value_fmt: "$30,000.00",
      unrealized_gain_loss: 5000,
      unrealized_gain_loss_fmt: "$5,000.00",
      cost_basis: 25000,
      quantity: 100,
      asset_class: "Equity",
      account_name: "Morgan Stanley Joint",
      institution_type: "morgan_stanley",
      portfolio_weight: 25,
    },
  ],
  top_gainers: [],
  top_losers: [],
  balance_history: [],
  coverage: [],
  period: { start_date: "2026-08-01", end_date: "2026-08-31" },
};

describe("<InvestmentsPageClient />", () => {
  beforeEach(() => {
    vi.spyOn(investmentsApi, "investments").mockResolvedValue(DASHBOARD);
    vi.spyOn(investmentsApi, "contributionPlan").mockResolvedValue(CONTRIBUTION_PLAN);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("leads with contribution-plan data from the PR11 API", async () => {
    render(<InvestmentsPageClient />);

    expect((await screen.findAllByText("Am I investing according to plan?"))[0]).toBeInTheDocument();
    expect(await screen.findByText("12.3%")).toBeInTheDocument();
    expect(screen.getAllByText("Target 15%")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Roth IRA")[0]).toBeInTheDocument();
    expect(screen.getByText("Add $190 more")).toBeInTheDocument();
    expect(investmentsApi.contributionPlan).toHaveBeenCalledWith({
      startDate: "2026-08-01",
      endDate: "2026-08-31",
    });
  });

  it("keeps portfolio details accessible below the contribution sections", async () => {
    render(<InvestmentsPageClient />);

    expect(await screen.findByText("Account Allocation")).toBeInTheDocument();
    expect(screen.getByText("Investment Accounts")).toBeInTheDocument();
    expect(screen.getByText("Top Holdings")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("limits Coral Investment Insights to three cards", async () => {
    render(<InvestmentsPageClient />);

    const section = await screen.findByText("Coral Investment Insights");
    const insightRegion = section.closest("section");
    expect(insightRegion).not.toBeNull();
    expect(within(insightRegion!).getAllByRole("link")).toHaveLength(3);
  });

  it("does not present incomplete contribution data as on-track advice", async () => {
    vi.mocked(investmentsApi.contributionPlan).mockResolvedValue({
      ...CONTRIBUTION_PLAN,
      total_actual_pct: null,
      vehicles: CONTRIBUTION_PLAN.vehicles.map((vehicle) => ({
        ...vehicle,
        actual_pct: null,
        variance_amount: null,
        variance_pct_points: null,
        recommended_next_month_delta: null,
        status: "unknown",
        data_completeness: {
          ...vehicle.data_completeness,
          status: "incomplete",
          is_complete: false,
          income_observed: false,
        },
      })),
      completeness: {
        ...CONTRIBUTION_PLAN.completeness,
        income_observed: false,
        notes: ["No income was observed this period; target $ and actual % cannot be computed."],
        is_complete: false,
      },
    });

    render(<InvestmentsPageClient />);

    expect(await screen.findByText("Contribution rate unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("Data unavailable")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Contribution data unavailable")[0]).toBeInTheDocument();
    expect(screen.queryByText("Keep at 6%")).not.toBeInTheDocument();
  });

  it("renders the contribution plan when the secondary portfolio dashboard fails", async () => {
    vi.mocked(investmentsApi.investments).mockRejectedValue(new Error("portfolio unavailable"));

    render(<InvestmentsPageClient />);

    expect(await screen.findByText("12.3%")).toBeInTheDocument();
    expect(screen.getByText("Plan vs Actual Contributions")).toBeInTheDocument();
    expect(screen.getByText("portfolio unavailable")).toBeInTheDocument();
  });
});
