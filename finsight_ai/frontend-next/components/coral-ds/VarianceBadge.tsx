import { clsx } from "clsx";
import StatusBadge, { type StatusTone } from "./StatusBadge";

interface VarianceBadgeProps {
  value: number;
  format?: "currency" | "percent";
  direction?: "positive-good" | "negative-good";
  className?: string;
}

function formatValue(value: number, format: "currency" | "percent"): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const body = format === "currency" ? `$${abs.toLocaleString()}` : `${abs}%`;
  return `${sign}${body}`;
}

function toneFor(value: number, direction: "positive-good" | "negative-good"): StatusTone {
  if (value === 0) return "neutral";
  const isPositive = value > 0;
  const isGood = direction === "positive-good" ? isPositive : !isPositive;
  return isGood ? "good" : "danger";
}

/** Delta badge (e.g. "+$80" / "-$45") that auto-colors via StatusBadge based on sign and direction. */
export default function VarianceBadge({ value, format = "currency", direction = "positive-good", className }: VarianceBadgeProps) {
  return (
    <StatusBadge status={toneFor(value, direction)} className={clsx("tabular-nums", className)}>
      {formatValue(value, format)}
    </StatusBadge>
  );
}
