import type { ReactNode } from "react";
import Surface from "./Surface";
import CoralMascot from "@/components/coral/CoralMascot";

interface CoralAdvisorCardProps {
  headline: string;
  body: string;
  actions?: ReactNode;
  className?: string;
}

/** Mascot + headline insight pattern from the top of each mockup page (e.g. "You're slightly off plan this month"). */
export default function CoralAdvisorCard({ headline, body, actions, className }: CoralAdvisorCardProps) {
  return (
    <Surface padding="md" className={className}>
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
