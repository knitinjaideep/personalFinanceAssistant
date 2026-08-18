import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InvestmentsPageClient from "./InvestmentsPageClient";
import { investmentsApi } from "@/features/investments/api";
import type { InvestmentsDashboard } from "@/features/investments/api";

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

vi.mock("@/components/coral/CoralMascot", () => ({
  default: () => <div data-testid="mascot" />,
}));

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
  balance_history: [
    {
      date: "2026-07-31",
      total_value: 65000,
      account_name: "Morgan Stanley Joint",
      institution_type: "morgan_stanley",
    },
    {
      date: "2026-08-31",
      total_value: 70000,
      account_name: "Morgan Stanley Joint",
      institution_type: "morgan_stanley",
    },
    {
      date: "2026-07-31",
      total_value: 50000,
      account_name: "Roth IRA",
      institution_type: "morgan_stanley",
    },
    {
      date: "2026-08-31",
      total_value: 50000,
      account_name: "Roth IRA",
      institution_type: "morgan_stanley",
    },
  ],
  coverage: [],
  period: { start_date: "2026-08-01", end_date: "2026-08-31" },
};

describe("<InvestmentsPageClient />", () => {
  beforeEach(() => {
    vi.spyOn(investmentsApi, "investments").mockResolvedValue(DASHBOARD);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("leads with statement-backed portfolio intelligence instead of contribution-plan data", async () => {
    render(<InvestmentsPageClient />);

    expect(await screen.findByText("Portfolio Account Value Trends")).toBeInTheDocument();
    expect(screen.getByText("What Coral Can Trust From Your Statements")).toBeInTheDocument();
    expect(screen.getByText("Largest account")).toBeInTheDocument();
    expect(screen.getByText("Largest holding")).toBeInTheDocument();
    expect(screen.getByText("Cash position")).toBeInTheDocument();
    expect(screen.queryByText("Investment Contribution Planning")).not.toBeInTheDocument();
    expect(screen.queryByText("Plan vs Actual Contributions")).not.toBeInTheDocument();
  });

  it("keeps portfolio details accessible in the account-value experience", async () => {
    render(<InvestmentsPageClient />);

    expect(await screen.findByText("Portfolio Account Value Trends")).toBeInTheDocument();
    expect(screen.queryByText("Latest Portfolio Snapshot")).not.toBeInTheDocument();
    expect(await screen.findByText("Account Allocation")).toBeInTheDocument();
    expect(screen.getByText("Top Holdings")).toBeInTheDocument();
    expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
  });

  it("renders portfolio intelligence facts from imported allocation and holdings", async () => {
    render(<InvestmentsPageClient />);

    const heading = await screen.findByText("What Coral Can Trust From Your Statements");
    const insightRegion = heading.closest("section");
    expect(insightRegion).not.toBeNull();
    expect(within(insightRegion!).getAllByText("Morgan Stanley Joint").length).toBeGreaterThan(0);
    expect(within(insightRegion!).getAllByText("AAPL").length).toBeGreaterThan(0);
    expect(within(insightRegion!).getByText("$2,000")).toBeInTheDocument();
  });

  it("does not render contribution-derived planner recommendations on Investments", async () => {
    render(<InvestmentsPageClient />);

    expect(await screen.findByText("What Coral Can Trust From Your Statements")).toBeInTheDocument();
    expect(screen.queryByText("Investment Next Month Plan")).not.toBeInTheDocument();
    expect(screen.queryByText("Increase Roth IRA contribution by $190 next period")).not.toBeInTheDocument();
  });
});
