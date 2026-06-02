import { clsx } from "clsx";
import { CoralMascot } from "./CoralMascot";
import type { CoralMascotVariant } from "../lib/mascots";

/**
 * CoralLoadingState — a mascot-led loading / processing indicator with an
 * animated "thinking" dot trail.
 */
interface CoralLoadingStateProps {
  variant?: CoralMascotVariant;
  message: string;
  submessage?: string;
  className?: string;
}

export function CoralLoadingState({
  variant = "main",
  message,
  submessage,
  className,
}: CoralLoadingStateProps) {
  return (
    <div
      className={clsx(
        "flex items-center gap-4 rounded-2xl px-5 py-4",
        className,
      )}
      style={{
        background: "rgba(205,237,246,0.28)",
        border: "1px solid rgba(205,237,246,0.60)",
      }}
    >
      <CoralMascot variant={variant} size="sm" className="shrink-0" />
      <div className="min-w-0">
        <p className="flex items-center gap-1.5 text-[13px] font-semibold text-ocean-deep">
          {message}
          <span className="inline-flex gap-1">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="coral-animated inline-block h-1 w-1 rounded-full bg-ocean/45"
                style={{
                  animation: "coralFloat 0.9s ease-in-out infinite",
                  animationDelay: `${i * 0.15}s`,
                }}
              />
            ))}
          </span>
        </p>
        {submessage && (
          <p className="mt-0.5 text-[11.5px] text-ocean/45 leading-snug">{submessage}</p>
        )}
      </div>
    </div>
  );
}
