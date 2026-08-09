import { clsx } from "clsx";
import { Calendar, ChevronDown } from "lucide-react";

export type PeriodRange = "1M" | "3M" | "6M" | "YTD";

const RANGE_OPTIONS: PeriodRange[] = ["1M", "3M", "6M", "YTD"];

interface GlobalPeriodFilterProps {
  month: string;
  onMonthClick?: () => void;
  range: PeriodRange;
  onRangeChange: (range: PeriodRange) => void;
  className?: string;
}

/**
 * Presentational month + range picker matching the redesign mockups.
 * No data wiring — callers own state. A future PR connects this to a real
 * backend period parameter (see REDESIGN_GAP_ANALYSIS.md).
 */
export default function GlobalPeriodFilter({
  month,
  onMonthClick,
  range,
  onRangeChange,
  className,
}: GlobalPeriodFilterProps) {
  return (
    <div className={clsx("flex items-center gap-2 flex-wrap", className)}>
      <button
        type="button"
        onClick={onMonthClick}
        className="inline-flex items-center gap-2 rounded-full px-3.5 py-2 coral-nav-text font-semibold"
        style={{ background: "var(--card-bg)", border: "1px solid var(--border-subtle)", color: "var(--text-secondary)" }}
      >
        <Calendar size={15} />
        {month}
        <ChevronDown size={14} />
      </button>

      <div
        className="inline-flex items-center rounded-full p-1 gap-0.5"
        style={{ background: "var(--card-bg)", border: "1px solid var(--border-subtle)" }}
        role="group"
        aria-label="Date range"
      >
        {RANGE_OPTIONS.map((option) => {
          const active = option === range;
          return (
            <button
              key={option}
              type="button"
              onClick={() => onRangeChange(option)}
              aria-pressed={active}
              className="rounded-full px-3 py-1.5 coral-nav-text font-semibold transition-colors"
              style={{
                background: active ? "var(--coral-primary)" : "transparent",
                color: active ? "var(--text-on-accent)" : "var(--text-secondary)",
              }}
            >
              {option}
            </button>
          );
        })}
      </div>
    </div>
  );
}
