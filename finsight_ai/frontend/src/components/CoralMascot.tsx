import { clsx } from "clsx";
import { coralMascots, type CoralMascotVariant } from "../lib/mascots";
import { CoralDropletImage, type CoralDropletSize } from "./CoralDropletImage";

/**
 * CoralMascot — the friendly face of Coral, rendered inside an organic
 * water-droplet bubble via CoralDropletImage.
 *
 * Every place that uses CoralMascot automatically gets droplet styling —
 * no mascot ever appears as a plain square image.
 *
 * Sizes:
 *   xs   →  32 px   typing indicator, row avatars
 *   sm   →  48 px   sidebar brand, header chip, floating button
 *   md   →  76 px   empty-state accents, inline callouts
 *   lg   → 128 px   empty states, category cards
 *   xl   → 220 px   large feature cards
 *   hero → clamp(280px, 26vw, 400px)  dashboard hero
 *
 * ── Disable animation globally ───────────────────────────────────────────────
 * Pass animated={false}, or let prefers-reduced-motion handle it via CSS.
 */

export type CoralMascotSize = CoralDropletSize;

interface CoralMascotProps {
  variant?: CoralMascotVariant;
  size?: CoralMascotSize;
  animated?: boolean;
  glow?: boolean;
  /** Optional speech bubble rendered above the mascot. */
  speech?: string;
  /** Scale up on hover (defaults: false for xs/sm/md, true for lg+). */
  hoverMagnify?: boolean;
  className?: string;
  /** Eager-load the image (use on above-the-fold hero only). */
  priority?: boolean;
  /** CSS animation-delay for staggered card groups. */
  floatDelay?: string;
}

export function CoralMascot({
  variant = "main",
  size = "md",
  animated = true,
  glow = true,
  speech,
  hoverMagnify,
  className,
  priority = false,
  floatDelay,
}: CoralMascotProps) {
  const art = coralMascots[variant];

  return (
    <div className={clsx("relative inline-flex flex-col items-center", className)}>
      {/* ── Speech bubble ─────────────────────────────────────────────────── */}
      {speech && (
        <div
          className="relative mb-3 max-w-[240px] rounded-2xl px-3.5 py-2 text-center text-[12px] font-medium leading-snug"
          style={{
            background: "rgba(255,255,255,0.95)",
            border: "1px solid rgba(205,237,246,0.85)",
            color: "rgba(11,60,93,0.80)",
            boxShadow: "0 6px 22px rgba(11,60,93,0.14)",
          }}
        >
          {speech}
          <span
            aria-hidden
            className="absolute left-1/2"
            style={{
              bottom: -6,
              width: 12,
              height: 12,
              background: "rgba(255,255,255,0.95)",
              borderRight: "1px solid rgba(205,237,246,0.85)",
              borderBottom: "1px solid rgba(205,237,246,0.85)",
              transform: "translateX(-50%) rotate(45deg)",
            }}
          />
        </div>
      )}

      {/* ── Droplet bubble ────────────────────────────────────────────────── */}
      <CoralDropletImage
        src={art.src}
        alt={art.alt}
        size={size}
        animated={animated}
        glow={glow}
        hoverMagnify={hoverMagnify}
        priority={priority}
        floatDelay={floatDelay}
      />
    </div>
  );
}
