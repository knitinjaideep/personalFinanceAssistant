import { clsx } from "clsx";
import { ArrowRight } from "lucide-react";
import { CoralMascot } from "./CoralMascot";
import type { CoralMascotVariant } from "../lib/mascots";

/**
 * CoralMascotCard — a large glassmorphism callout card fronted by a mascot.
 * Used for dashboard feature cards and big calls to action.
 */
interface CoralMascotCardProps {
  variant: CoralMascotVariant;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  href?: string;
  className?: string;
}

export function CoralMascotCard({
  variant,
  title,
  description,
  actionLabel,
  onAction,
  href,
  className,
}: CoralMascotCardProps) {
  const interactive = Boolean(onAction || href);

  const inner = (
    <div
      className={clsx(
        "group relative h-full overflow-hidden rounded-3xl p-5 text-left transition-all duration-200",
        interactive && "hover:-translate-y-0.5",
      )}
      style={{
        background:
          "linear-gradient(135deg, rgba(255,255,255,0.90) 0%, rgba(240,249,252,0.82) 100%)",
        border: "1px solid rgba(205,237,246,0.65)",
        boxShadow:
          "0 4px 24px rgba(11,60,93,0.08), inset 0 1px 0 rgba(255,255,255,0.9)",
      }}
    >
      {/* soft teal glow accent */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-10 -right-8 h-32 w-32 rounded-full opacity-70"
        style={{
          background:
            "radial-gradient(circle, rgba(95,168,211,0.22) 0%, transparent 70%)",
        }}
      />
      <div className="relative flex items-start gap-3.5">
        <CoralMascot variant={variant} size="md" animated className="shrink-0" />
        <div className="min-w-0 flex-1">
          <h3 className="text-[14px] font-bold text-ocean-deep leading-tight">{title}</h3>
          <p className="mt-1 text-[12px] text-ocean/50 leading-relaxed">{description}</p>
          {actionLabel && (
            <span className="mt-3 inline-flex items-center gap-1 text-[12px] font-semibold text-coral">
              {actionLabel}
              <ArrowRight
                size={12}
                className="transition-transform duration-200 group-hover:translate-x-0.5"
              />
            </span>
          )}
        </div>
      </div>
    </div>
  );

  if (href) {
    return (
      <a href={href} className={clsx("block", className)}>
        {inner}
      </a>
    );
  }
  if (onAction) {
    return (
      <button type="button" onClick={onAction} className={clsx("block w-full", className)}>
        {inner}
      </button>
    );
  }
  return <div className={className}>{inner}</div>;
}
