import type { ReactNode } from "react";
import Surface from "./Surface";
import CoralMascot from "@/components/coral/CoralMascot";
import type { StatusTone } from "./StatusBadge";

interface CoralAdvisorCardProps {
  headline: string;
  body: string;
  /** Optional status tone (e.g. Overview's financial status header —
   * PR 06) rendered as a subtle left accent so the card's overall
   * good/watch/off-track read is visible at a glance without repeating a
   * badge that duplicates the headline's own wording. */
  tone?: StatusTone;
  actions?: ReactNode;
  className?: string;
}

const TONE_ACCENT: Record<StatusTone, string> = {
  good: "var(--status-good)",
  warning: "var(--status-warning)",
  danger: "var(--status-danger)",
  neutral: "var(--status-neutral)",
};

/** Mascot + headline insight pattern from the top of each mockup page (e.g. "You're slightly off plan this month"). */
export default function CoralAdvisorCard({ headline, body, tone, actions, className }: CoralAdvisorCardProps) {
  return (
    <Surface
      padding="md"
      className={className}
      style={tone ? { borderLeft: `3px solid ${TONE_ACCENT[tone]}` } : undefined}
    >
      <div className="flex items-start gap-4">
        <CoralMascot size="sm" animated={false} />
        <div className="flex-1 min-w-0">
          <h3 className="coral-card-title mb-1.5">{headline}</h3>
          <p className="small-text" style={{ color: "var(--text-secondary)" }}>{body}</p>
          {actions && <div className="mt-3 flex flex-col gap-2">{actions}</div>}
        </div>
      </div>
    </Surface>
  );
}
