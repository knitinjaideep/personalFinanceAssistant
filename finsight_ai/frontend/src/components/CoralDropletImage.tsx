import { clsx } from "clsx";

/**
 * CoralDropletImage — universal organic-bubble wrapper for every mascot image.
 *
 * All mascot surfaces in the app should render through this component so
 * no mascot appears as a plain square.  It handles:
 *   - Organic morphing border-radius (water-droplet shape)
 *   - object-cover so the image always fills the bubble
 *   - Glossy highlight overlay (top-left sheen)
 *   - Soft cyan tint at the bottom (underwater feel)
 *   - Optional glow halo behind the bubble
 *   - Optional floating animation (pauses on hover for cleaner UX)
 *   - Optional hover-magnify (scale-up the entire bubble)
 *
 * Size map (sets the square footprint of the bubble):
 *   xs   →  32 px   sidebar badge, typing indicator avatar
 *   sm   →  48 px   sidebar brand, header chip, floating button
 *   md   →  76 px   inline states, empty-state accents
 *   lg   → 128 px   category cards, callout sections
 *   xl   → 220 px   large feature cards
 *   hero → clamp(280px, 26vw, 400px)  dashboard hero
 *
 * ── Disable animation ────────────────────────────────────────────────────────
 * Pass animated={false}  — or the user's OS prefers-reduced-motion fires it.
 *
 * ── Disable hover magnify ────────────────────────────────────────────────────
 * Pass hoverMagnify={false} (default true for lg+, false for xs/sm).
 *
 * ── Adjust glow ──────────────────────────────────────────────────────────────
 * Pass glow={false} to remove the radial halo entirely.
 */

export type CoralDropletSize = "xs" | "sm" | "md" | "lg" | "xl" | "hero";

export interface CoralDropletImageProps {
  src: string;
  alt: string;
  size?: CoralDropletSize;
  animated?: boolean;
  glow?: boolean;
  /** Scale up on hover. Defaults true for lg/xl/hero, false for xs/sm/md. */
  hoverMagnify?: boolean;
  className?: string;
  imageClassName?: string;
  priority?: boolean;
  /** Animation delay for staggered card groups (CSS animation-delay value). */
  floatDelay?: string;
}

const SIZE_PX: Record<Exclude<CoralDropletSize, "hero">, number> = {
  xs:  32,
  sm:  48,
  md:  76,
  lg: 128,
  xl: 220,
};

/** Blur radius on the glow halo — scales with bubble size */
const GLOW_BLUR: Record<CoralDropletSize, number> = {
  xs:   6,
  sm:   8,
  md:  10,
  lg:  14,
  xl:  18,
  hero: 22,
};

export function CoralDropletImage({
  src,
  alt,
  size = "md",
  animated = true,
  glow = true,
  hoverMagnify,
  className,
  imageClassName,
  priority = false,
  floatDelay,
}: CoralDropletImageProps) {
  const isHero = size === "hero";
  const dim = isHero ? "clamp(280px, 26vw, 400px)" : `${SIZE_PX[size]}px`;
  const isSmall = size === "xs" || size === "sm";
  const shouldMagnify = hoverMagnify ?? !isSmall;
  const blurPx = GLOW_BLUR[size];

  /* Shadow intensity scales with size */
  const shadowSmall = "0 4px 14px rgba(11,60,93,0.28)";
  const shadowLarge = "0 14px 48px rgba(11,60,93,0.22), inset 0 1px 0 rgba(255,255,255,0.45), inset 0 -1px 0 rgba(95,168,211,0.12)";
  const shadow = isSmall ? shadowSmall : shadowLarge;

  return (
    <div
      className={clsx("relative inline-flex items-center justify-center", className)}
      style={{ width: dim, height: dim }}
    >
      {/* ── Glow halo behind the bubble ──────────────────────────────────── */}
      {glow && (
        <span
          aria-hidden
          className={clsx(
            "absolute rounded-full pointer-events-none",
            animated && "coral-bubble-glow coral-animated",
          )}
          style={{
            inset: isSmall ? "-16%" : "-22%",
            background:
              "radial-gradient(circle at 48% 44%, rgba(95,168,211,0.48) 0%, rgba(255,122,90,0.26) 44%, transparent 70%)",
            filter: `blur(${blurPx}px)`,
            opacity: 0.65,
          }}
        />
      )}

      {/* ── Droplet bubble ───────────────────────────────────────────────── */}
      <div
        className={clsx(
          "relative overflow-hidden",
          animated && "coral-droplet-float coral-animated",
          shouldMagnify && "coral-hover-magnify",
        )}
        style={{
          width: dim,
          height: dim,
          borderRadius: "45% 55% 52% 48% / 48% 42% 58% 52%",
          background: "rgba(255,255,255,0.10)",
          backdropFilter: isSmall ? undefined : "blur(10px)",
          WebkitBackdropFilter: isSmall ? undefined : "blur(10px)",
          border: "1px solid rgba(255,255,255,0.26)",
          boxShadow: shadow,
          animationDelay: floatDelay,
          cursor: shouldMagnify ? "pointer" : undefined,
        }}
      >
        {/* Mascot image — fills bubble */}
        <img
          src={src}
          alt={alt}
          loading={priority ? "eager" : "lazy"}
          decoding="async"
          fetchPriority={priority ? "high" : "auto"}
          className={clsx(
            "absolute inset-0 w-full h-full object-cover",
            imageClassName,
          )}
          style={{ transform: "scale(1.06)", transformOrigin: "center 42%" }}
        />

        {/* Glossy sheen — top-left oval highlight */}
        {!isSmall && (
          <span
            aria-hidden
            className={clsx(
              "absolute pointer-events-none",
              animated && "coral-bubble-shimmer coral-animated",
            )}
            style={{
              top: "5%",
              left: "8%",
              width: "44%",
              height: "26%",
              borderRadius: "50%",
              background:
                "radial-gradient(ellipse at 40% 30%, rgba(255,255,255,0.65) 0%, rgba(255,255,255,0) 100%)",
              transform: "rotate(-18deg)",
              opacity: 0.55,
            }}
          />
        )}

        {/* Cyan tint at bottom — underwater depth */}
        <span
          aria-hidden
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "linear-gradient(to bottom, transparent 50%, rgba(95,168,211,0.13) 100%)",
          }}
        />
      </div>
    </div>
  );
}
