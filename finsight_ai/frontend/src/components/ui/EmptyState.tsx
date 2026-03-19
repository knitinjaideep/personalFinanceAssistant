import { type ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
  showMascot?: boolean;
  icon?: ReactNode;
}

export function EmptyState({
  title,
  description,
  action,
  showMascot = false,
  icon,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      {showMascot ? (
        <img
          src="/mascot.png"
          alt="Coral mascot"
          className="w-28 h-28 object-contain mb-5 opacity-90 drop-shadow-md"
        />
      ) : icon ? (
        <div className="mb-4 text-ocean-aqua opacity-60">{icon}</div>
      ) : null}
      <h3 className="text-base font-semibold text-slate mb-2">{title}</h3>
      {description && (
        <p className="text-sm text-ocean-DEFAULT/50 max-w-xs leading-relaxed">
          {description}
        </p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
