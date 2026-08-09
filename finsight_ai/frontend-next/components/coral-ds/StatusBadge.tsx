import { clsx } from "clsx";
import type { ReactNode } from "react";

export type StatusTone = "good" | "warning" | "danger" | "neutral";

interface StatusBadgeProps {
  status: StatusTone;
  children: ReactNode;
  className?: string;
}

const TONE_CLASS: Record<StatusTone, string> = {
  good: "bg-status-good-soft text-status-good",
  warning: "bg-status-warning-soft text-status-warning",
  danger: "bg-status-danger-soft text-status-danger",
  neutral: "bg-status-neutral-soft text-status-neutral",
};

export default function StatusBadge({ status, children, className }: StatusBadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 coral-badge-text font-semibold",
        TONE_CLASS[status],
        className
      )}
    >
      {children}
    </span>
  );
}
