"use client";

import { useState } from "react";
import PageShell from "@/components/coral-ds/PageShell";
import PageHeader from "@/components/coral-ds/PageHeader";
import GlobalPeriodFilter, { type PeriodRange } from "@/components/coral-ds/GlobalPeriodFilter";
import SectionHeader from "@/components/coral-ds/SectionHeader";
import Surface from "@/components/coral-ds/Surface";
import StatusBadge from "@/components/coral-ds/StatusBadge";
import VarianceBadge from "@/components/coral-ds/VarianceBadge";
import TargetProgressBar from "@/components/coral-ds/TargetProgressBar";
import MetricComparison from "@/components/coral-ds/MetricComparison";

export default function DesignSystemPage() {
  const [month, setMonth] = useState("August 2026");
  const [range, setRange] = useState<PeriodRange>("1M");

  return (
    <PageShell width="wide">
      <PageHeader
        eyebrow="Design System"
        title="Coral Design System"
        subtitle="Reusable primitives for the redesigned dashboard — tokens, layout, and content components."
        action={
          <GlobalPeriodFilter
            month={month}
            onMonthClick={() => setMonth("August 2026")}
            range={range}
            onRangeChange={setRange}
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
      </div>
    </PageShell>
  );
}
