/**
 * OceanBackground — ambient underwater atmosphere
 *
 * Renders:
 * 1. Deep ocean gradient (full viewport, fixed)
 * 2. Sun ray overlay (top radial glow)
 * 3. Floating bubbles (very subtle, slow)
 *
 * Performance: all CSS animations, no JS loops.
 * Opacity kept very low so data remains primary focus.
 */

import { memo } from "react";

const BUBBLES = [
  { size: 6, left: "8%", delay: "0s", duration: "14s", opacity: 0.18 },
  { size: 4, left: "18%", delay: "3s", duration: "18s", opacity: 0.12 },
  { size: 8, left: "32%", delay: "1s", duration: "16s", opacity: 0.15 },
  { size: 3, left: "48%", delay: "5s", duration: "20s", opacity: 0.10 },
  { size: 5, left: "62%", delay: "2s", duration: "15s", opacity: 0.14 },
  { size: 7, left: "74%", delay: "7s", duration: "17s", opacity: 0.13 },
  { size: 4, left: "86%", delay: "4s", duration: "19s", opacity: 0.11 },
  { size: 6, left: "94%", delay: "9s", duration: "13s", opacity: 0.16 },
];

export const OceanBackground = memo(function OceanBackground() {
  return (
    <div
      className="fixed inset-0 pointer-events-none overflow-hidden"
      style={{ zIndex: 0 }}
      aria-hidden="true"
    >
      {/* Base ocean gradient */}
      <div
        className="absolute inset-0"
        style={{
          background: "linear-gradient(180deg, #0B3C5D 0%, #1F6F8B 40%, #5FA8D3 100%)",
        }}
      />

      {/* Underwater sun rays from top */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 80% 50% at 50% -10%, rgba(95,168,211,0.28) 0%, transparent 65%)",
        }}
      />

      {/* Subtle depth vignette at bottom */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 120% 60% at 50% 120%, rgba(11,30,50,0.35) 0%, transparent 60%)",
        }}
      />

      {/* Floating bubbles */}
      {BUBBLES.map((b, i) => (
        <div
          key={i}
          className="absolute rounded-full"
          style={{
            width: b.size,
            height: b.size,
            left: b.left,
            bottom: "-20px",
            opacity: b.opacity,
            background:
              "radial-gradient(circle at 35% 35%, rgba(255,255,255,0.9), rgba(205,237,246,0.4))",
            border: "1px solid rgba(255,255,255,0.35)",
            animation: `bubbleRise ${b.duration} ease-in ${b.delay} infinite`,
          }}
        />
      ))}
    </div>
  );
});
