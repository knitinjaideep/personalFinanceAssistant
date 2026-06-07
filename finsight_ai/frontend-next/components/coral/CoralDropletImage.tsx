"use client";

import Image from "next/image";

export type CoralDropletSize = "xs" | "sm" | "md" | "lg" | "xl" | "hero";

export interface CoralDropletImageProps {
  src: string;
  alt: string;
  size?: CoralDropletSize;
  animated?: boolean;
  glow?: boolean;
  hoverMagnify?: boolean;
  className?: string;
  imageClassName?: string;
  priority?: boolean;
  floatDelay?: string;
}

const SIZE_PX: Record<Exclude<CoralDropletSize, "hero">, number> = {
  xs:  32,
  sm:  48,
  md:  76,
  lg: 128,
  xl: 220,
};

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
  priority = false,
  floatDelay,
}: CoralDropletImageProps) {
  const isHero = size === "hero";
  const dimPx  = isHero ? 340 : SIZE_PX[size as Exclude<CoralDropletSize, "hero">];
  const dim    = isHero ? "clamp(280px, 26vw, 400px)" : `${dimPx}px`;
  const isSmall = size === "xs" || size === "sm";
  const shouldMagnify = hoverMagnify ?? !isSmall;
  const blurPx = GLOW_BLUR[size];

  const shadowSmall = "0 4px 14px rgba(11,60,93,0.28)";
  const shadowLarge = "0 14px 48px rgba(11,60,93,0.22), inset 0 1px 0 rgba(255,255,255,0.45), inset 0 -1px 0 rgba(95,168,211,0.12)";
  const shadow = isSmall ? shadowSmall : shadowLarge;

  return (
    <div
      className={`relative inline-flex items-center justify-center ${className ?? ""}`}
      style={{ width: dim, height: dim }}
    >
      {/* Glow halo behind the bubble */}
      {glow && (
        <span
          aria-hidden
          className={`absolute rounded-full pointer-events-none${animated ? " coral-bubble-glow coral-animated" : ""}`}
          style={{
            inset: isSmall ? "-16%" : "-22%",
            background:
              "radial-gradient(circle at 48% 44%, rgba(95,168,211,0.48) 0%, rgba(255,122,90,0.26) 44%, transparent 70%)",
            filter: `blur(${blurPx}px)`,
            opacity: 0.65,
          }}
        />
      )}

      {/* Droplet bubble */}
      <div
        className={`relative overflow-hidden${animated ? " coral-droplet-float coral-animated" : ""}${shouldMagnify ? " coral-hover-magnify" : ""}`}
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
        <Image
          src={src}
          alt={alt}
          fill
          priority={priority}
          className="object-cover"
          style={{ transform: "scale(1.06)", transformOrigin: "center 42%" }}
          sizes={isHero ? "400px" : `${dimPx}px`}
        />

        {/* Glossy sheen — top-left oval highlight */}
        {!isSmall && (
          <span
            aria-hidden
            className={`absolute pointer-events-none${animated ? " coral-bubble-shimmer coral-animated" : ""}`}
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
