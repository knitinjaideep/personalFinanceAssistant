"use client";

import { useState } from "react";
import PageShell from "@/components/coral-ds/PageShell";
import PageHeader from "@/components/coral-ds/PageHeader";
import GlobalPeriodFilter, { type PeriodRange } from "@/components/coral-ds/GlobalPeriodFilter";
import SectionHeader from "@/components/coral-ds/SectionHeader";

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
      </div>
    </PageShell>
  );
}
