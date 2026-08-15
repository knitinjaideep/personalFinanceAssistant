import type { ReactNode } from "react";
import { clsx } from "clsx";
import Surface from "./Surface";
import type { StatusTone } from "./StatusBadge";

interface InsightCardProps {
  icon: ReactNode;
  title: string;
  description: string;
  tone: StatusTone;
  action?: ReactNode;
  className?: string;
}

const TONE_ICON_CLASS: Record<StatusTone, string> = {
  good: "bg-status-good-soft text-status-good",
  warning: "bg-status-warning-soft text-status-warning",
  danger: "bg-status-danger-soft text-status-danger",
  neutral: "bg-status-neutral-soft text-status-neutral",
};

/** Icon + title + description insight card, e.g. "Overspending in Wants". */
export default function InsightCard({ icon, title, description, tone, action, className }: InsightCardProps) {
  return (
    <Surface interactive padding="md" className={clsx("flex flex-col gap-3", className)}>
      <span className={clsx("w-9 h-9 rounded-xl flex items-center justify-center shrink-0", TONE_ICON_CLASS[tone])}>
        {icon}
      </span>
      <div>
        <h4 className="coral-card-title mb-1">{title}</h4>
        <p className="small-text" style={{ color: "var(--text-secondary)" }}>{description}</p>
      </div>
      {action && <div className="mt-1">{action}</div>}
    </Surface>
  );
}
