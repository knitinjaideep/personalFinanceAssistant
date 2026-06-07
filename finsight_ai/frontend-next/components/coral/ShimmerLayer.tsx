import { memo } from "react";

interface ShimmerLayerProps {
  /** 0..1 — overall intensity of the rays. */
  intensity?: number;
  /** Ray color (theme-aware). */
  color?: string;
}

/**
 * Slow, soft light rays that drift across the page — adds underwater depth and
 * a premium ambient shimmer. Rendered behind content, pointer-events-none, and
 * respects prefers-reduced-motion (handled in globals.css).
 */
function ShimmerLayer({
  intensity = 0.5,
  color = "rgba(103,232,249,0.20)",
}: ShimmerLayerProps) {
  // Kept to 3 rays — each is a single blurred element animated on transform
  // only. Fewer large blurred layers = far cheaper compositing.
  const rays = [
    { left: "14%", delay: "0s",  scale: 1 },
    { left: "50%", delay: "-7s", scale: 1.1 },
    { left: "84%", delay: "-3s", scale: 0.8 },
  ];

  return (
    <div
      className="coral-shimmer-layer"
      style={{ ["--shimmer-opacity" as string]: intensity, ["--shimmer-color" as string]: color }}
    >
      {rays.map((r, i) => (
        <span
          key={i}
          className="coral-shimmer-ray"
          style={{ left: r.left, animationDelay: r.delay, transform: `rotate(14deg) scaleX(${r.scale})` }}
        />
      ))}
    </div>
  );
}

export default memo(ShimmerLayer);
