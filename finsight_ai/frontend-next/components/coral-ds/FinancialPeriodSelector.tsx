"use client";

/**
 * FinancialPeriodSelector — the shared Global Period Filter control (PR 05).
 *
 * Supports Current Month (with prev/next month navigation), 1M/3M/6M/YTD/1Y
 * rolling windows, and a Custom date range. Purely presentational + a11y —
 * all date-math lives in lib/period.ts, and all state lives wherever the
 * caller's `useFinancialPeriod()` hook call is (Overview/Banking/Investments
 * pages), consistent with "financial calculations live outside components".
 *
 * Formerly `GlobalPeriodFilter` (design-system showcase only, no data
 * wiring). Renamed for PR 05 now that it's connected to a real backend
 * period parameter — see docs/coral-redesign/pr-05-period-filter.md.
 */

import { useRef } from "react";
import { clsx } from "clsx";
import { Calendar, ChevronLeft, ChevronRight } from "lucide-react";
import {
  PERIOD_MODES,
  PERIOD_MODE_LABELS,
  type PeriodMode,
  type PeriodSelection,
  type ResolvedPeriod,
} from "@/lib/period";

interface FinancialPeriodSelectorProps {
  selection: PeriodSelection;
  resolved: ResolvedPeriod;
  onChange: (next: PeriodSelection) => void;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  /** Dims and disables interaction while the page is fetching data for a
   * just-changed period — the "loading transition" called out in the PR 05
   * work order. Purely visual; the caller owns the actual fetch. */
  loading?: boolean;
  className?: string;
}

export default function FinancialPeriodSelector({
  selection,
  resolved,
  onChange,
  onPrevMonth,
  onNextMonth,
  loading = false,
  className,
}: FinancialPeriodSelectorProps) {
  const groupRef = useRef<HTMLDivElement>(null);

  const selectMode = (mode: PeriodMode) => {
    if (mode === selection.mode) return;
    if (mode === "custom") {
      onChange({ mode, customStart: resolved.startDate, customEnd: resolved.endDate });
    } else {
      onChange({ mode });
    }
  };

  // Roving-tabindex-style arrow key navigation across the pill group, per
  // the work order's keyboard-accessibility requirement (ArrowLeft/Right
  // moves focus + selection, matching native radiogroup behavior).
  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const currentIndex = PERIOD_MODES.indexOf(selection.mode);
    const delta = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex = (currentIndex + delta + PERIOD_MODES.length) % PERIOD_MODES.length;
    const nextMode = PERIOD_MODES[nextIndex];
    selectMode(nextMode);
    const nextButton = groupRef.current?.querySelectorAll<HTMLButtonElement>("[role='radio']")[nextIndex];
    nextButton?.focus();
  };

  return (
    <div
      className={clsx("flex items-center gap-2 flex-wrap", loading && "opacity-60 pointer-events-none", className)}
      style={{ transition: "opacity 0.2s ease" }}
      aria-busy={loading}
    >
      {selection.mode === "current_month" && (
        <div
          className="inline-flex items-center gap-1 rounded-full px-1.5 py-1"
          style={{ background: "var(--card-bg)", border: "1px solid var(--border-subtle)" }}
        >
          <button
            type="button"
            onClick={onPrevMonth}
            aria-label="Previous month"
            className="w-7 h-7 rounded-full flex items-center justify-center transition-colors hover:bg-white/[0.06]"
            style={{ color: "var(--text-secondary)" }}
          >
            <ChevronLeft size={14} />
          </button>
          <span
            className="inline-flex items-center gap-1.5 px-2 coral-nav-text font-semibold"
            style={{ color: "var(--text-secondary)" }}
          >
            <Calendar size={13} />
            {resolved.label}
          </span>
          <button
            type="button"
            onClick={onNextMonth}
            disabled={resolved.isAtLatestMonth}
            aria-label="Next month"
            className="w-7 h-7 rounded-full flex items-center justify-center transition-colors hover:bg-white/[0.06] disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ color: "var(--text-secondary)" }}
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}

      <div
        ref={groupRef}
        role="radiogroup"
        aria-label="Financial period"
        onKeyDown={handleKeyDown}
        className="inline-flex items-center rounded-full p-1 gap-0.5 flex-wrap"
        style={{ background: "var(--card-bg)", border: "1px solid var(--border-subtle)" }}
      >
        {PERIOD_MODES.map((mode) => {
          const active = mode === selection.mode;
          return (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={active ? 0 : -1}
              onClick={() => selectMode(mode)}
              className="rounded-full px-3 py-1.5 coral-nav-text font-semibold transition-colors"
              style={{
                background: active ? "var(--coral-primary)" : "transparent",
                color: active ? "var(--text-on-accent)" : "var(--text-secondary)",
              }}
            >
              {mode === "current_month" ? "Month" : PERIOD_MODE_LABELS[mode]}
            </button>
          );
        })}
      </div>

      {selection.mode === "custom" && (
        <div className="inline-flex items-center gap-2 flex-wrap">
          <label className="sr-only" htmlFor="period-custom-start">Start date</label>
          <input
            id="period-custom-start"
            type="date"
            value={selection.customStart ?? resolved.startDate}
            max={selection.customEnd ?? resolved.endDate}
            onChange={(e) =>
              onChange({ mode: "custom", customStart: e.target.value, customEnd: selection.customEnd ?? resolved.endDate })
            }
            className="rounded-full px-3 py-1.5 coral-nav-text font-semibold"
            style={{ background: "var(--card-bg)", border: "1px solid var(--border-subtle)", color: "var(--text-secondary)" }}
          />
          <span className="micro-text" style={{ color: "var(--text-dim)" }}>to</span>
          <label className="sr-only" htmlFor="period-custom-end">End date</label>
          <input
            id="period-custom-end"
            type="date"
            value={selection.customEnd ?? resolved.endDate}
            min={selection.customStart ?? resolved.startDate}
            onChange={(e) =>
              onChange({ mode: "custom", customStart: selection.customStart ?? resolved.startDate, customEnd: e.target.value })
            }
            className="rounded-full px-3 py-1.5 coral-nav-text font-semibold"
            style={{ background: "var(--card-bg)", border: "1px solid var(--border-subtle)", color: "var(--text-secondary)" }}
          />
        </div>
      )}
    </div>
  );
}
