"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, FileCheck2, TrendingDown } from "lucide-react";
import ErrorState from "@/components/coral/ErrorState";
import FinancialPeriodSelector from "@/components/coral-ds/FinancialPeriodSelector";
import PageHeader from "@/components/coral-ds/PageHeader";
import SectionHeader from "@/components/coral-ds/SectionHeader";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import StatusBadge from "@/components/coral-ds/StatusBadge";
import Surface from "@/components/coral-ds/Surface";
import NextMonthPlanSection from "@/components/overview/NextMonthPlanSection";
import { useFinancialPeriod } from "@/hooks/useFinancialPeriod";
import { formatCurrency } from "@/lib/utils";
import { overviewApi, type MonthlyCloseResult, type MonthlyCloseStatus } from "@/features/overview/api";

const STATUS_LABEL: Record<MonthlyCloseStatus, string> = {
  good: "On track",
  warning: "Watch",
  danger: "Off track",
  neutral: "No data",
};

function money(value: string | null) {
  return value === null ? "-" : formatCurrency(Number(value));
}

export default function MonthlyClosePageClient() {
  const { selection, resolved, setSelection, goToPreviousMonth, goToNextMonth } = useFinancialPeriod();
  const [close, setClose] = useState<MonthlyCloseResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    overviewApi
      .monthlyClose({ startDate: resolved.startDate, endDate: resolved.endDate })
      .then(setClose)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [resolved.startDate, resolved.endDate]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Monthly Close"
        title="Monthly Financial Close"
        subtitle="A read-only close report for the selected month."
        action={
          <FinancialPeriodSelector
            selection={selection}
            resolved={resolved}
            onChange={setSelection}
            onPrevMonth={goToPreviousMonth}
            onNextMonth={goToNextMonth}
            loading={loading}
          />
        }
      />

      <Link href="/" className="inline-flex items-center gap-2 small-text font-semibold" style={{ color: "var(--text-secondary)" }}>
        <ArrowLeft size={14} /> Back to overview
      </Link>

      {loading && <SkeletonState variant="card" height="420px" />}
      {error && <ErrorState message={error} onRetry={load} />}

      {close && !loading && !error && (
        <>
          <Surface padding="lg" as="section">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="micro-text font-bold uppercase tracking-[0.18em]" style={{ color: "var(--coral-primary)" }}>
                  {close.period.label}
                </p>
                <h2 className="mt-2 coral-section-title">{close.summary}</h2>
                <p className="mt-2 small-text" style={{ color: "var(--text-muted)" }}>
                  Generated {new Date(close.generated_on).toLocaleDateString()}.
                  {!close.is_completed_month ? " This selected month is not complete yet." : ""}
                </p>
              </div>
              <span
                className="w-12 h-12 rounded-2xl flex items-center justify-center"
                style={{ background: "var(--coral-primary-soft)", color: "var(--coral-primary)" }}
              >
                <FileCheck2 size={20} />
              </span>
            </div>
          </Surface>

          <section>
            <SectionHeader eyebrow="Plan close" title="Income and Bucket Close" size="sm" className="mb-5" />
            <Surface padding="md" className="overflow-x-auto">
              <table className="w-full min-w-[680px] coral-table-text">
                <thead>
                  <tr style={{ color: "var(--table-head)", borderBottom: "1px solid var(--border-subtle)" }}>
                    <th className="py-3 text-left font-semibold">Line</th>
                    <th className="py-3 text-right font-semibold">Target</th>
                    <th className="py-3 text-right font-semibold">Actual</th>
                    <th className="py-3 text-right font-semibold">Variance</th>
                    <th className="py-3 text-right font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {close.line_items.map((item) => (
                    <tr key={item.label} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      <td className="py-3 font-semibold" style={{ color: "var(--text-primary)" }}>{item.label}</td>
                      <td className="py-3 text-right tabular-nums" style={{ color: "var(--text-secondary)" }}>{money(item.target_amount)}</td>
                      <td className="py-3 text-right tabular-nums" style={{ color: "var(--text-primary)" }}>{money(item.actual_amount)}</td>
                      <td className="py-3 text-right tabular-nums" style={{ color: "var(--text-secondary)" }}>{money(item.variance_amount)}</td>
                      <td className="py-3 text-right"><StatusBadge status={item.status}>{STATUS_LABEL[item.status]}</StatusBadge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Surface>
          </section>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <section>
              <SectionHeader eyebrow="Close notes" title="What Went Well" size="sm" className="mb-5" />
              <div className="space-y-3">
                {close.went_well.length === 0 ? (
                  <Surface padding="md"><p className="small-text">No positive close notes yet.</p></Surface>
                ) : close.went_well.map((item) => (
                  <Surface key={item.title} padding="md" className="flex gap-3">
                    <CheckCircle2 size={17} className="shrink-0" style={{ color: "var(--status-good)" }} />
                    <div>
                      <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>{item.title}</p>
                      <p className="micro-text mt-1" style={{ color: "var(--text-muted)" }}>{item.description}</p>
                    </div>
                  </Surface>
                ))}
              </div>
            </section>
            <section>
              <SectionHeader eyebrow="Close notes" title="Needs Attention" size="sm" className="mb-5" />
              <div className="space-y-3">
                {close.needs_attention.length === 0 ? (
                  <Surface padding="md"><p className="small-text">No material attention items for this close.</p></Surface>
                ) : close.needs_attention.map((item) => (
                  <Surface key={item.title} padding="md" className="flex gap-3">
                    <TrendingDown size={17} className="shrink-0" style={{ color: "var(--status-danger)" }} />
                    <div>
                      <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>{item.title}</p>
                      <p className="micro-text mt-1" style={{ color: "var(--text-muted)" }}>{item.description}</p>
                    </div>
                  </Surface>
                ))}
              </div>
            </section>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <section>
              <SectionHeader eyebrow="Drivers" title="Biggest Drivers" size="sm" className="mb-5" />
              <Surface padding="md" className="space-y-3">
                {close.biggest_drivers.length === 0 ? (
                  <p className="small-text">No merchant drivers for this close.</p>
                ) : close.biggest_drivers.map((driver) => (
                  <div key={`${driver.bucket}-${driver.merchant}`} className="flex items-center justify-between gap-4">
                    <div>
                      <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>{driver.merchant}</p>
                      <p className="micro-text" style={{ color: "var(--text-muted)" }}>{driver.bucket}{driver.category ? ` / ${driver.category}` : ""}</p>
                    </div>
                    <p className="small-text font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>{money(driver.amount)}</p>
                  </div>
                ))}
              </Surface>
            </section>
            <section>
              <SectionHeader eyebrow="Goals" title="Goal Progress" size="sm" className="mb-5" />
              <Surface padding="md" className="space-y-3">
                {close.goal_progress.length === 0 ? (
                  <p className="small-text">No savings goals configured yet.</p>
                ) : close.goal_progress.map((goal) => (
                  <div key={goal.name} className="flex items-center justify-between gap-4">
                    <div>
                      <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>{goal.name}</p>
                      <p className="micro-text" style={{ color: "var(--text-muted)" }}>{goal.status}{goal.incomplete_source ? " / incomplete source" : ""}</p>
                    </div>
                    <p className="small-text font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>{money(goal.current_amount)}</p>
                  </div>
                ))}
              </Surface>
            </section>
          </div>

          <section>
            <SectionHeader eyebrow="Next period" title="Next Month Plan" size="sm" className="mb-5" />
            <NextMonthPlanSection
              recommendations={close.next_month_plan}
              loading={false}
              error={false}
              showSourceFacts
            />
          </section>
        </>
      )}
    </div>
  );
}
