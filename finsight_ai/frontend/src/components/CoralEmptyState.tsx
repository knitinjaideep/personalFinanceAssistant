import { clsx } from "clsx";
import { CoralMascot } from "./CoralMascot";
import type { CoralMascotVariant } from "../lib/mascots";

/**
 * CoralEmptyState — a friendly, mascot-led empty / no-data state.
 */
interface CoralEmptyStateProps {
  variant: CoralMascotVariant;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  href?: string;
  className?: string;
}

export function CoralEmptyState({
  variant,
  title,
  description,
  actionLabel,
  onAction,
  href,
  className,
}: CoralEmptyStateProps) {
  const action =
    actionLabel &&
    (href ? (
      <a
        href={href}
        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-[13px] font-semibold text-white"
        style={{
          background: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
          boxShadow: "0 4px 14px rgba(255,122,90,0.32)",
        }}
      >
        {actionLabel}
      </a>
    ) : (
      <button
        type="button"
        onClick={onAction}
        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-[13px] font-semibold text-white"
        style={{
          background: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
          boxShadow: "0 4px 14px rgba(255,122,90,0.32)",
        }}
      >
        {actionLabel}
      </button>
    ));

  return (
    <div
      className={clsx(
        "flex flex-col items-center justify-center py-14 px-6 text-center",
        className,
      )}
    >
      <div className="mb-5">
        <CoralMascot variant={variant} size="lg" />
      </div>
      <h3 className="text-[15px] font-semibold text-ocean-deep mb-2">{title}</h3>
      {description && (
        <p className="text-[13px] text-ocean/50 max-w-sm leading-relaxed">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
