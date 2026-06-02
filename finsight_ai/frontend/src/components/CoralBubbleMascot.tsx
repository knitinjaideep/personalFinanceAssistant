import { clsx } from "clsx";
import { coralMascots, type CoralMascotVariant } from "../lib/mascots";

/**
 * CoralBubbleMascot — the mascot clipped inside an organic water-droplet bubble.
 *
 * Sizes (px footprint of the bubble container):
 *   md   → 100   (inline / chat empty state)
 *   lg   → 150   (callout states)
 *   xl   → 220   (large cards)
 *   hero → responsive clamp(260px, 28vw, 360px)  (dashboard hero)
 *
 * The bubble uses an animated organic border-radius that gently morphs so the
 * mascot appears to float inside a living water droplet.
 *
 * ── Disable animation ────────────────────────────────────────────────────────
 * Pass animated={false}. The CSS also honours prefers-reduced-motion.
 *
 * ── Adjust glow ──────────────────────────────────────────────────────────────
 * Pass glow={false} to remove the soft radial halo.
 */

export type CoralBubbleSize = "md" | "lg" | "xl" | "hero";

interface CoralBubbleMascotProps {
  variant?: CoralMascotVariant;
  size?: CoralBubbleSize;
  speech?: string;
  animated?: boolean;
  glow?: boolean;
  className?: string;
  priority?: boolean;
}

const SIZE_PX: Record<Exclude<CoralBubbleSize, "hero">, number> = {
  md: 100,
  lg: 150,
  xl: 220,
};

export function CoralBubbleMascot({
  variant = "main",
  size = "md",
  speech,
  animated = true,
  glow = true,
  className,
  priority = false,
}: CoralBubbleMascotProps) {
  const art = coralMascots[variant];
  const isHero = size === "hero";
  const dim = isHero ? "clamp(260px, 28vw, 360px)" : `${SIZE_PX[size]}px`;

  if (import.meta.env.DEV) {
    console.debug("[CoralBubbleMascot]", { variant, src: art.src, size });
  }

  return (
    <div className={clsx("relative inline-flex flex-col items-center", className)}>
      {/* ── Speech bubble ──────────────────────────────────────────────────── */}
      {speech && (
        <div
          className="relative mb-4 max-w-[260px] rounded-2xl px-4 py-2.5 text-center text-[12.5px] font-medium leading-snug"
          style={{
            background: "rgba(255,255,255,0.96)",
            border: "1px solid rgba(205,237,246,0.85)",
            color: "rgba(11,60,93,0.80)",
            boxShadow: "0 6px 22px rgba(11,60,93,0.13)",
          }}
        >
          {speech}
          {/* tail */}
          <span
            aria-hidden
            className="absolute left-1/2"
            style={{
              bottom: -7,
              width: 13,
              height: 13,
              background: "rgba(255,255,255,0.96)",
              borderRight: "1px solid rgba(205,237,246,0.85)",
              borderBottom: "1px solid rgba(205,237,246,0.85)",
              transform: "translateX(-50%) rotate(45deg)",
            }}
          />
        </div>
      )}

      {/* ── Bubble wrapper ─────────────────────────────────────────────────── */}
      <div
        className="relative inline-flex items-center justify-center"
        style={{ width: dim, height: dim }}
      >
        {/* Soft radial glow halo behind the bubble */}
        {glow && (
          <span
            aria-hidden
            className={clsx(
              "absolute rounded-full",
              animated && "coral-bubble-glow coral-animated",
            )}
            style={{
              inset: "-22%",
              background:
                "radial-gradient(circle at 48% 44%, rgba(95,168,211,0.50) 0%, rgba(255,122,90,0.28) 44%, transparent 70%)",
              filter: "blur(10px)",
              opacity: 0.65,
            }}
          />
        )}

        {/* Coral accent glow (warm) behind bubble */}
        {glow && (
          <span
            aria-hidden
            className="absolute rounded-full pointer-events-none"
            style={{
              inset: "-10%",
              background:
                "radial-gradient(circle at 55% 75%, rgba(255,122,90,0.22) 0%, transparent 65%)",
              filter: "blur(14px)",
            }}
          />
        )}

        {/* ── The droplet bubble ─────────────────────────────────────────── */}
        <div
          className={clsx(
            "relative overflow-hidden",
            animated && "coral-droplet-float coral-animated",
          )}
          style={{
            width: dim,
            height: dim,
            /* Organic droplet border-radius — morphs via keyframe */
            borderRadius: "45% 55% 52% 48% / 48% 42% 58% 52%",
            background: "rgba(255,255,255,0.12)",
            backdropFilter: "blur(12px)",
            WebkitBackdropFilter: "blur(12px)",
            border: "1px solid rgba(255,255,255,0.30)",
            boxShadow:
              "0 16px 48px rgba(11,60,93,0.24), inset 0 1px 0 rgba(255,255,255,0.45), inset 0 -2px 0 rgba(95,168,211,0.12)",
          }}
        >
          {/* Mascot image — fills bubble, slightly scaled so it looks cropped in */}
          <img
            src={art.src}
            alt={art.alt}
            loading={priority ? "eager" : "lazy"}
            decoding="async"
            fetchPriority={priority ? "high" : "auto"}
            className="absolute inset-0 w-full h-full object-cover"
            style={{ transform: "scale(1.08)", transformOrigin: "center 40%" }}
          />

          {/* Glossy highlight — top-left oval sheen */}
          <span
            aria-hidden
            className={clsx(
              "absolute pointer-events-none",
              animated && "coral-bubble-shimmer coral-animated",
            )}
            style={{
              top: "6%",
              left: "10%",
              width: "42%",
              height: "28%",
              borderRadius: "50%",
              background:
                "radial-gradient(ellipse at 40% 30%, rgba(255,255,255,0.62) 0%, rgba(255,255,255,0) 100%)",
              transform: "rotate(-18deg)",
              opacity: 0.55,
            }}
          />

          {/* Subtle cyan tint overlay at bottom */}
          <span
            aria-hidden
            className="absolute inset-0 pointer-events-none"
            style={{
              background:
                "linear-gradient(to bottom, transparent 55%, rgba(95,168,211,0.14) 100%)",
            }}
          />
        </div>
      </div>
    </div>
  );
}
