import { clsx } from "clsx";
import { ArrowRight } from "lucide-react";
import { CoralMascot } from "./CoralMascot";
import type { CoralMascotVariant } from "../lib/mascots";

/**
 * CoralCategoryBubble — a large, centred, glassmorphism feature card.
 *
 * Displays a prominent droplet mascot, title, description, and an action
 * button. Each card gently floats at a staggered delay so the four category
 * bubbles on the Overview page move independently.
 *
 * ── Adjust card size ─────────────────────────────────────────────────────────
 * Change MIN_HEIGHT_PX below, or override via className.
 *
 * ── Adjust hover magnification ───────────────────────────────────────────────
 * Change the `coral-category-bubble` CSS class in index.css (scale value).
 * Or pass hoverScale as a prop (inline style override).
 *
 * ── Disable floating animation ───────────────────────────────────────────────
 * Remove the `coral-category-float` class below, or set animated={false}.
 * The CSS prefers-reduced-motion block handles it automatically.
 *
 * ── Card float delays ────────────────────────────────────────────────────────
 * Pass floatDelay="0ms" | "250ms" | "500ms" | "750ms" to stagger the group.
 */

interface CoralCategoryBubbleProps {
  variant: CoralMascotVariant;
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  /** CSS animation-delay for staggered floating. e.g. "250ms" */
  floatDelay?: string;
  animated?: boolean;
  className?: string;
}

export function CoralCategoryBubble({
  variant,
  title,
  description,
  actionLabel,
  onAction,
  floatDelay = "0ms",
  animated = true,
  className,
}: CoralCategoryBubbleProps) {
  return (
    <button
      type="button"
      onClick={onAction}
      className={clsx(
        "group relative w-full text-center overflow-hidden outline-none",
        "focus-visible:ring-4 focus-visible:ring-coral/40 focus-visible:ring-offset-2",
        "coral-category-bubble",
        animated && "coral-category-float coral-animated",
        className,
      )}
      style={{
        borderRadius: "32px",
        background:
          "linear-gradient(155deg, rgba(255,255,255,0.92) 0%, rgba(240,249,252,0.86) 100%)",
        border: "1px solid rgba(205,237,246,0.70)",
        boxShadow:
          "0 8px 40px rgba(11,60,93,0.09), inset 0 1px 0 rgba(255,255,255,0.95)",
        padding: "32px 24px 28px",
        minHeight: "280px",
        animationDelay: floatDelay,
        /* pause the float on hover — CSS overrides in index.css handle scale */
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "16px",
        cursor: "pointer",
        transition:
          "transform 0.30s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.30s ease",
      }}
    >
      {/* ── Ambient background glow (stays inside card, no overflow) ──────── */}
      <span
        aria-hidden
        className="pointer-events-none absolute -top-12 -right-12 w-44 h-44 rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(95,168,211,0.18) 0%, transparent 70%)",
          filter: "blur(10px)",
        }}
      />
      <span
        aria-hidden
        className="pointer-events-none absolute -bottom-10 -left-10 w-36 h-36 rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(255,122,90,0.13) 0%, transparent 70%)",
          filter: "blur(10px)",
        }}
      />

      {/* ── Mascot bubble ─────────────────────────────────────────────────── */}
      <div className="relative z-10 flex-shrink-0">
        <CoralMascot
          variant={variant}
          size="lg"
          animated={animated}
          glow
          hoverMagnify={false}
          className="transition-transform duration-300 ease-out group-hover:scale-110"
        />
      </div>

      {/* ── Text content ──────────────────────────────────────────────────── */}
      <div className="relative z-10 flex-1 flex flex-col items-center justify-center gap-2">
        <h3 className="text-[16px] font-bold text-ocean-deep leading-tight tracking-tight">
          {title}
        </h3>
        <p className="text-[12.5px] text-ocean/50 leading-relaxed max-w-[180px]">
          {description}
        </p>
      </div>

      {/* ── Action ────────────────────────────────────────────────────────── */}
      <div className="relative z-10 flex-shrink-0">
        <span
          className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-coral transition-all duration-200 group-hover:gap-2.5"
        >
          {actionLabel}
          <ArrowRight
            size={13}
            className="transition-transform duration-200 group-hover:translate-x-0.5"
          />
        </span>
      </div>
    </button>
  );
}
