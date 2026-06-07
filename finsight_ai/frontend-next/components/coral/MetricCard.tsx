import type { ReactNode } from "react";
import { clsx } from "clsx";
import GlassCard from "./GlassCard";

interface TrendProps {
  value: string;
  direction?: "up" | "down" | "neutral";
}

interface MetricCardProps {
  title: string;
  value?: string | number | null;
  subtitle?: string;
  icon?: ReactNode;
  trend?: TrendProps;
  status?: "positive" | "negative" | "neutral" | "warning";
  size?: "compact" | "sm" | "md" | "lg" | "featured";
  loading?: boolean;
  empty?: boolean;
  emptyText?: string;
  className?: string;
  accentColor?: string;
  /** Full, untruncated value shown on hover (e.g. exact currency). */
  fullValue?: string;
}

const VALUE_CLASS: Record<NonNullable<MetricCardProps["size"]>, string> = {
  compact:  "metric-value-sm",
  sm:       "metric-value-sm",
  md:       "metric-value",
  lg:       "metric-value-lg",
  featured: "metric-value-lg",
};

// Long values (≥ ~9 visible chars, e.g. "$1,206,669") get a slightly smaller
// type ramp so they never clip or wrap awkwardly inside the card.
function valueLengthClass(value: string): string {
  const len = value.replace(/\s/g, "").length;
  if (len >= 13) return "text-[1.05rem]";
  if (len >= 10) return "text-[1.35rem]";
  return "";
}

function Skeleton() {
  return (
    <div className="space-y-1.5 pt-1">
      <div className="skeleton h-7 w-24 rounded-lg" />
      <div className="skeleton h-3 w-16 rounded-md" />
    </div>
  );
}

export default function MetricCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  status = "neutral",
  size = "md",
  loading = false,
  empty = false,
  emptyText = "No data yet",
  className,
  accentColor,
  fullValue,
}: MetricCardProps) {
  const trendColor =
    trend?.direction === "up"
      ? "#4CAF93"
      : trend?.direction === "down"
        ? "#E45757"
        : "var(--text-muted)";

  const statusValueColor =
    status === "positive"
      ? "#4CAF93"
      : status === "negative"
        ? "#E45757"
        : status === "warning"
          ? "#FFD166"
          : "var(--text-strong)";

  const valueClass = VALUE_CLASS[size];

  return (
    <GlassCard
      variant="default"
      className={clsx(
        "relative overflow-hidden group flex flex-col transition-transform duration-200 hover:-translate-y-0.5",
        size === "featured" ? "min-h-[132px]" : "min-h-[96px]",
        className
      )}
    >
      {/* Accent ray */}
      {accentColor && (
        <div
          className="absolute top-0 right-0 w-20 h-20 pointer-events-none"
          style={{
            background: `radial-gradient(ellipse at top right, ${accentColor} 0%, transparent 70%)`,
          }}
        />
      )}

      <div className="relative z-10">
        <div className="flex items-start justify-between mb-2">
          <p className="eyebrow-text">{title}</p>
          {icon && (
            <span
              className="w-7 h-7 rounded-xl flex items-center justify-center shrink-0"
              style={{
                background: accentColor
                  ? `${accentColor.replace("0.25", "0.10")}`
                  : "var(--glass-light-bg)",
                border: "1px solid var(--border-subtle)",
              }}
            >
              {icon}
            </span>
          )}
        </div>

        {loading ? (
          <Skeleton />
        ) : empty || value == null ? (
          <div className="pt-0.5">
            <p className={valueClass} style={{ color: "var(--text-dim)", opacity: 0.5 }}>—</p>
            <p className="small-text mt-1" style={{ color: "var(--text-dim)" }}>{emptyText}</p>
          </div>
        ) : (
          <div>
            <p
              className={clsx(valueClass, valueLengthClass(String(value)), "transition-colors break-words tabular-nums")}
              style={{ color: statusValueColor }}
              title={fullValue ?? String(value)}
            >
              {value}
            </p>

            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {subtitle && (
                <p className="small-text" style={{ color: "var(--text-muted)" }}>{subtitle}</p>
              )}
              {trend && (
                <span
                  className="micro-text font-semibold flex items-center gap-0.5"
                  style={{ color: trendColor }}
                >
                  {trend.direction === "up" ? "↑" : trend.direction === "down" ? "↓" : "→"}
                  {trend.value}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </GlassCard>
  );
}
