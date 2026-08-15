import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import BankingInsightsSection from "./BankingInsightsSection";
import type { BankingInsight } from "@/features/banking/api";

afterEach(() => {
  cleanup();
});

const INSIGHT: BankingInsight = {
  type: "merchant_overspend",
  severity: "critical",
  tone: "danger",
  title: "Amazon is driving Wants overspend",
  summary: "Amazon accounts for $420 while Wants is $300 over plan.",
  impact_amount: "420.00",
  confidence: "0.95",
  action: "Trim or recategorize Amazon spending before next period.",
  supporting_facts: [
    { label: "Merchant spend", value: "420.00" },
    { label: "Transactions", value: "6" },
  ],
};

describe("<BankingInsightsSection />", () => {
  it("renders backend-supplied insight title, summary, and action", () => {
    render(<BankingInsightsSection insights={[INSIGHT]} loading={false} error={false} />);

    expect(screen.getByText("Amazon is driving Wants overspend")).toBeInTheDocument();
    expect(screen.getByText("Amazon accounts for $420 while Wants is $300 over plan.")).toBeInTheDocument();
    expect(screen.getByText("Trim or recategorize Amazon spending before next period.")).toBeInTheDocument();
  });

  it("shows an empty state when the backend returns no insights", () => {
    render(<BankingInsightsSection insights={[]} loading={false} error={false} />);

    expect(screen.getByText("No banking insights yet")).toBeInTheDocument();
  });

  it("shows an error state when loading fails", () => {
    render(<BankingInsightsSection insights={null} loading={false} error />);

    expect(screen.getByText("Couldn't load Banking Insights for this period.")).toBeInTheDocument();
  });
});
