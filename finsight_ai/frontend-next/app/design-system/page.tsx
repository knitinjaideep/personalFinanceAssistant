"use client";

import { useState } from "react";
import PageShell from "@/components/coral-ds/PageShell";
import PageHeader from "@/components/coral-ds/PageHeader";
import FinancialPeriodSelector from "@/components/coral-ds/FinancialPeriodSelector";
import { goToNextMonth, goToPreviousMonth, resolvePeriod, type PeriodSelection } from "@/lib/period";
import SectionHeader from "@/components/coral-ds/SectionHeader";
import Surface from "@/components/coral-ds/Surface";
import StatusBadge from "@/components/coral-ds/StatusBadge";
import VarianceBadge from "@/components/coral-ds/VarianceBadge";
import TargetProgressBar from "@/components/coral-ds/TargetProgressBar";
import MetricComparison from "@/components/coral-ds/MetricComparison";
import InsightCard from "@/components/coral-ds/InsightCard";
import CoralAdvisorCard from "@/components/coral-ds/CoralAdvisorCard";
import { ShoppingBag, PiggyBank, TrendingUp, Landmark } from "lucide-react";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import SkeletonState from "@/components/coral-ds/SkeletonState";

export default function DesignSystemPage() {
  const [periodSelection, setPeriodSelection] = useState<PeriodSelection>({ mode: "current_month" });
  const resolvedPeriod = resolvePeriod(periodSelection);

  return (
    <PageShell width="wide">
      <PageHeader
        eyebrow="Design System"
        title="Coral Design System"
        subtitle="Reusable primitives for the redesigned dashboard — tokens, layout, and content components."
        action={
          <FinancialPeriodSelector
            selection={periodSelection}
            resolved={resolvedPeriod}
            onChange={setPeriodSelection}
            onPrevMonth={() => setPeriodSelection((s) => goToPreviousMonth(s))}
            onNextMonth={() => setPeriodSelection((s) => goToNextMonth(s))}
          />
        }
      />

      <div className="space-y-12">
        <section>
          <SectionHeader eyebrow="Foundations" title="Section header" description="Used above every content section." size="sm" />
        </section>

        <section>
          <SectionHeader title="Surface" size="sm" />
          <Surface className="mt-4 max-w-md">
            <p className="small-text" style={{ color: "var(--text-secondary)" }}>
              A calm base panel used by InsightCard, CoralAdvisorCard, and other content components.
            </p>
          </Surface>
        </section>

        <section>
          <SectionHeader title="Badges" size="sm" />
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <StatusBadge status="good">On track</StatusBadge>
            <StatusBadge status="warning">Slightly behind</StatusBadge>
            <StatusBadge status="danger">Off plan</StatusBadge>
            <StatusBadge status="neutral">No data</StatusBadge>
            <VarianceBadge value={80} />
            <VarianceBadge value={-45} />
            <VarianceBadge value={12} format="percent" direction="negative-good" />
          </div>
        </section>

        <section>
          <SectionHeader title="Target progress" size="sm" />
          <Surface className="mt-4 grid gap-5 max-w-xl">
            <TargetProgressBar label="Needs" actual={48} target={50} bucket="needs" />
            <TargetProgressBar label="Wants" actual={24} target={20} bucket="wants" />
            <TargetProgressBar label="Savings" actual={12} target={15} bucket="savings" />
            <TargetProgressBar label="Investments" actual={16} target={15} bucket="investments" />
          </Surface>
        </section>

        <section>
          <SectionHeader title="Metric comparison" size="sm" />
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricComparison label="401(k)" actual="5.8%" target="6%" />
            <MetricComparison label="Roth IRA" actual="2.1%" target="4%" />
          </div>
        </section>

        <section>
          <SectionHeader title="Insight cards" size="sm" />
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            <InsightCard icon={<ShoppingBag size={17} />} tone="danger" title="Overspending in Wants" description="You're over your Wants target by $80 this month." />
            <InsightCard icon={<PiggyBank size={17} />} tone="warning" title="Under-saving for House Fund" description="You're $45 behind your monthly savings goal." />
            <InsightCard icon={<TrendingUp size={17} />} tone="good" title="On track for 401(k)" description="Great job! You're meeting your retirement contributions." />
          </div>
        </section>

        <section>
          <SectionHeader title="Coral advisor" size="sm" />
          <CoralAdvisorCard
            className="mt-4 max-w-xl"
            headline="You're slightly off plan this month"
            body="Spending in Wants is running above plan, and you're saving a bit less than your target."
          />
        </section>

        <section>
          <SectionHeader title="States" size="sm" />
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            <EmptyState compact icon={<Landmark size={22} />} title="No accounts yet" description="Upload a statement to get started." />
            <ErrorState compact message="Could not load this section." onRetry={() => {}} />
            <Surface padding="sm" className="space-y-2">
              <SkeletonState variant="text" width="60%" />
              <SkeletonState variant="text" width="40%" />
              <SkeletonState variant="block" height="2rem" />
            </Surface>
          </div>
        </section>
      </div>
    </PageShell>
  );
}
