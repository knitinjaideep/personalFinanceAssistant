import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import NextMonthPlanSection from "./NextMonthPlanSection";
import type { Recommendation } from "@/features/overview/api";

const BASE_RECOMMENDATION: Recommendation = {
  title: "Reduce Wants by $250 next period",
  reason: "Wants is $250 over its $2,000 target this period.",
  estimated_impact: "250.00",
  priority: 1,
  action_type: "reduce_category",
  source_facts: [
    { label: "Bucket", value: "Wants" },
    { label: "Variance vs target", value: "250.00" },
  ],
  bucket: "wants",
  category: null,
  incomplete_source: false,
};

afterEach(() => {
  cleanup();
});

describe("<NextMonthPlanSection />", () => {
  it("renders backend-ranked recommendations without reshaping the advice", () => {
    render(
      <NextMonthPlanSection
        recommendations={[BASE_RECOMMENDATION]}
        loading={false}
        error={false}
      />,
    );

    expect(screen.getByText("Reduce Wants by $250 next period")).toBeInTheDocument();
    expect(screen.getByText("Wants is $250 over its $2,000 target this period.")).toBeInTheDocument();
    expect(screen.getByText("$250")).toBeInTheDocument();
  });

  it("surfaces the incomplete-source caveat from the API contract", () => {
    render(
      <NextMonthPlanSection
        recommendations={[{ ...BASE_RECOMMENDATION, incomplete_source: true }]}
        loading={false}
        error={false}
      />,
    );

    expect(screen.getByText("Based on incomplete data - see details.")).toBeInTheDocument();
  });

  it("can expose source facts for audit-oriented planner surfaces", () => {
    const recommendation = {
      ...BASE_RECOMMENDATION,
      source_facts: [
        ...BASE_RECOMMENDATION.source_facts,
        { label: "Transactions", value: "6" },
        { label: "Data completeness caveat", value: "Incomplete payroll data." },
      ],
    };

    render(
      <NextMonthPlanSection
        recommendations={[recommendation]}
        loading={false}
        error={false}
        showSourceFacts
      />,
    );

    expect(screen.getByText("Bucket")).toBeInTheDocument();
    expect(screen.getByText("Variance vs target")).toBeInTheDocument();
    expect(screen.getByText("Data completeness caveat")).toBeInTheDocument();
  });

  it("renders empty and error states", () => {
    const { rerender } = render(
      <NextMonthPlanSection recommendations={[]} loading={false} error={false} />,
    );
    expect(screen.getByText("Nothing to adjust yet")).toBeInTheDocument();

    rerender(<NextMonthPlanSection recommendations={null} loading={false} error />);
    expect(screen.getByText("Couldn't load next period's plan.")).toBeInTheDocument();
  });
});
