import { coralMascots, type CoralMascotVariant } from "../lib/mascots";

/**
 * CoralPageWatermark — fixed, full-viewport branded background watermark.
 *
 * Always mounted at `position: fixed` so it spans the entire screen regardless
 * of any parent overflow:hidden containers.  Content must sit at z-10 or above.
 *
 * ── Tuning opacity ────────────────────────────────────────────────────────────
 * Change DEFAULT_WATERMARK_OPACITY, or pass `opacity` per use.
 * Recommended range: 0.04 – 0.08.
 *
 * ── Disabling the secondary accent ───────────────────────────────────────────
 * Pass showSecondary={false} (the default) to suppress the top-left accent.
 * Set to true only when you deliberately want a second accent mascot.
 */

export const DEFAULT_WATERMARK_OPACITY = 0.06;

export interface CoralPageWatermarkProps {
  variant?: CoralMascotVariant;
  /** Override opacity (0–1). Defaults to DEFAULT_WATERMARK_OPACITY. */
  opacity?: number;
  /**
   * Render a smaller mirrored accent in the top-left corner.
   * Default: false — only one primary watermark is shown.
   */
  showSecondary?: boolean;
  className?: string;
}

export function CoralPageWatermark({
  variant = "main",
  opacity = DEFAULT_WATERMARK_OPACITY,
  showSecondary = false,
  className,
}: CoralPageWatermarkProps) {
  const art = coralMascots[variant];

  return (
    <div
      aria-hidden
      className={`pointer-events-none select-none ${className ?? ""}`}
      style={{ position: "fixed", inset: 0, zIndex: 0, overflow: "hidden" }}
    >
      {/* ── Primary watermark — bottom-right ──────────────────────────────── */}
      <img
        src={art.src}
        alt=""
        role="presentation"
        loading="lazy"
        decoding="async"
        className="absolute object-contain"
        style={{
          bottom: "clamp(-160px, -8vw, -80px)",
          right: "clamp(-160px, -8vw, -80px)",
          width: "clamp(420px, 48vw, 820px)",
          height: "auto",
          opacity,
          filter: "grayscale(0.15) blur(0.4px)",
          transform: "translateZ(0)",
        }}
      />

      {/* ── Secondary accent — top-left (opt-in only) ─────────────────────── */}
      {showSecondary && (
        <img
          src={art.src}
          alt=""
          role="presentation"
          loading="lazy"
          decoding="async"
          className="absolute object-contain hidden md:block"
          style={{
            top: "-60px",
            left: "-60px",
            width: "clamp(140px, 16vw, 240px)",
            height: "auto",
            opacity: opacity * 0.45,
            filter: "grayscale(0.25) blur(0.6px)",
            transform: "scaleX(-1) translateZ(0)",
          }}
        />
      )}

      {/* ── Soft teal radial glow behind primary watermark ────────────────── */}
      <div
        className="absolute"
        style={{
          bottom: "clamp(-200px, -12vw, -120px)",
          right: "clamp(-200px, -12vw, -120px)",
          width: "clamp(500px, 60vw, 1000px)",
          height: "clamp(500px, 60vw, 1000px)",
          borderRadius: "50%",
          background:
            "radial-gradient(circle at 60% 60%, rgba(95,168,211,0.10) 0%, rgba(255,122,90,0.05) 40%, transparent 70%)",
          filter: "blur(32px)",
          opacity: opacity * 1.4,
        }}
      />
    </div>
  );
}
