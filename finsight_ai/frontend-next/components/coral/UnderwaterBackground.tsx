"use client";

import { memo } from "react";
import { usePathname } from "next/navigation";
import Image from "next/image";
import { useAppStore } from "@/store/appStore";
import { coralPageBackgrounds, getBackgroundKeyForPath } from "@/lib/coralBackgrounds";
import { BubbleField } from "./BubbleField";
import ShimmerLayer from "./ShimmerLayer";

function UnderwaterBackground() {
  const pathname = usePathname();
  const theme = useAppStore((s) => s.theme);
  const isLight = theme === "light";

  const key = getBackgroundKeyForPath(pathname ?? "/");
  const bg = coralPageBackgrounds[key];
  const imgSrc = isLight ? bg.lightSrc : bg.src;

  return (
    <div
      aria-hidden
      className="fixed inset-0 -z-10 pointer-events-none select-none overflow-hidden"
    >
      {/* Real photo background */}
      <Image
        key={imgSrc}
        src={imgSrc}
        alt=""
        fill
        priority
        className="object-cover object-center"
        style={{ transition: "opacity 0.5s ease" }}
        sizes="100vw"
      />

      {/* Base gradient wash — keeps text readable without washing out the photo */}
      <div
        className="absolute inset-0"
        style={{
          background: isLight
            ? "linear-gradient(to bottom, rgba(244,251,255,0.30) 0%, rgba(244,251,255,0.18) 38%, rgba(232,246,255,0.62) 100%)"
            : "linear-gradient(to bottom, rgba(3,17,31,0.34) 0%, rgba(3,17,31,0.18) 35%, rgba(3,17,31,0.78) 100%)",
          transition: "background 0.4s ease",
        }}
      />

      {/* Accent ray from top */}
      <div
        className="absolute inset-0"
        style={{
          background: isLight
            ? "radial-gradient(ellipse at 50% 0%, rgba(31,111,139,0.10) 0%, transparent 58%)"
            : "radial-gradient(ellipse at 50% 0%, rgba(34,211,238,0.20) 0%, transparent 60%)",
        }}
      />

      {/* Drifting light rays — present on every page, both themes */}
      <ShimmerLayer
        intensity={isLight ? 0.42 : 0.55}
        color={isLight ? "rgba(95,168,211,0.22)" : "rgba(103,232,249,0.22)"}
      />

      {/* Vignette — dark mode only */}
      {!isLight && (
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse at 50% 50%, transparent 40%, rgba(3,17,31,0.55) 100%)",
          }}
        />
      )}

      {/* Floating bubbles — both themes, theme-aware color */}
      <BubbleField
        intensity={isLight ? 0.85 : 1}
        color={isLight ? "rgba(31,111,139,0.55)" : "rgba(103,232,249,0.65)"}
        fill={isLight ? "rgba(31,111,139,0.10)" : "rgba(34,211,238,0.12)"}
      />
    </div>
  );
}

export default memo(UnderwaterBackground);
