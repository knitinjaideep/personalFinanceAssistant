"use client";

import { memo } from "react";
import { coralMascots, type CoralMascotVariant } from "@/lib/mascots";
import { CoralDropletImage, type CoralDropletSize } from "./CoralDropletImage";

export type CoralMascotSize = CoralDropletSize;

interface CoralMascotProps {
  variant?: CoralMascotVariant;
  size?: CoralMascotSize;
  animated?: boolean;
  glow?: boolean;
  speech?: string;
  hoverMagnify?: boolean;
  className?: string;
  priority?: boolean;
  floatDelay?: string;
}

function CoralMascot({
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
    <div className={`relative inline-flex flex-col items-center ${className ?? ""}`}>
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

export default memo(CoralMascot);
