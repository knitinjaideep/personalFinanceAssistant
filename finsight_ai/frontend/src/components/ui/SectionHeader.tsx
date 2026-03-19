import { type ReactNode } from "react";

interface SectionHeaderProps {
  title: string;
  action?: ReactNode;
  subtitle?: string;
}

export function SectionHeader({ title, action, subtitle }: SectionHeaderProps) {
  return (
    <div className="flex items-start justify-between">
      <div>
        <h2 className="text-base font-semibold text-slate">{title}</h2>
        {subtitle && <p className="text-xs text-ocean-DEFAULT/50 mt-0.5">{subtitle}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
