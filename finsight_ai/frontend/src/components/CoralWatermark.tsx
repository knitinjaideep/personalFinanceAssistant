import { clsx } from "clsx";
import { coralMascots, type CoralMascotVariant } from "../lib/mascots";

/**
 * CoralWatermark — a large, faint mascot used as a local decorative accent
 * inside a specific card or page section (not the full-page background).
 *
 * For the full-page fixed watermark that changes per route, use
 * CoralPageWatermark / CoralAppBackground instead.
 *
 * Position it with `className` (e.g. "absolute -bottom-10 -right-10 w-72").
 * Opacity is tunable via the `opacity` prop (default: 0.06).
 */
interface CoralWatermarkProps {
  variant?: CoralMascotVariant;
  /** 0–1. Default: 0.06. */
  opacity?: number;
  className?: string;
}

export function CoralWatermark({
  variant = "main",
  opacity = 0.06,
  className,
}: CoralWatermarkProps) {
  const art = coralMascots[variant];

  if (import.meta.env.DEV) {
    console.debug("[CoralWatermark]", { variant, src: art.src, opacity });
  }

  return (
    <img
      src={art.src}
      alt=""
      aria-hidden
      role="presentation"
      loading="lazy"
      decoding="async"
      className={clsx("pointer-events-none select-none", className)}
      style={{
        opacity,
        filter: "grayscale(0.2) blur(0.3px)",
        objectFit: "contain",
      }}
    />
  );
}
