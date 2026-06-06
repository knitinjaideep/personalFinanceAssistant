/**
 * CausticOverlay — animated water-light shimmer effect.
 * Renders a slow-drifting radial gradient that simulates light through water.
 * Pointer-events disabled, zero layout impact, reduced-motion safe.
 */

interface CausticOverlayProps {
  className?: string;
  /** 0–1, controls how intense the shimmer is. Default 1. */
  intensity?: number;
  /** Override the z-index. Default 0 (sits behind content). */
  zIndex?: number;
}

export function CausticOverlay({ className = "", intensity = 1, zIndex = 0 }: CausticOverlayProps) {
  const alpha = intensity * 0.07;

  return (
    <div
      aria-hidden
      className={className}
      style={{
        position: "absolute",
        inset: "-50%",
        width: "200%",
        height: "200%",
        background: [
          `radial-gradient(ellipse 65% 45% at 28% 28%, rgba(34,211,238,${alpha}) 0%, transparent 60%)`,
          `radial-gradient(ellipse 50% 38% at 72% 62%, rgba(34,211,238,${(alpha * 0.75).toFixed(3)}) 0%, transparent 55%)`,
          `radial-gradient(ellipse 42% 30% at 54% 18%, rgba(95,168,211,${(alpha * 0.60).toFixed(3)}) 0%, transparent 50%)`,
        ].join(", "),
        animation: "causticDrift 20s ease-in-out infinite alternate",
        pointerEvents: "none",
        zIndex,
        borderRadius: "inherit",
      }}
    />
  );
}
