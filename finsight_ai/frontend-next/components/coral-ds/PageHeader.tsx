import type { ReactNode } from "react";
import { clsx } from "clsx";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
  className?: string;
}

export default function PageHeader({ eyebrow, title, subtitle, action, className }: PageHeaderProps) {
  return (
    <div className={clsx("flex items-start justify-between gap-6 flex-wrap mb-8", className)}>
      <div>
        {eyebrow && (
          <p className="eyebrow-text mb-2" style={{ color: "var(--coral-primary)" }}>
            {eyebrow}
          </p>
        )}
        <h1 className="page-title">{title}</h1>
        {subtitle && (
          <p className="body-text max-w-2xl mt-2" style={{ color: "var(--text-secondary)" }}>
            {subtitle}
          </p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
