import { memo } from "react";

interface Bubble {
  id: number;
  left: string;
  size: number;
  duration: string;
  delay: string;
  opacity: number;
}

// A small, evenly-spread set. Each bubble is a single CSS-animated <span>
// (transform + opacity only) — no JS per-frame work, no React state.
// Kept intentionally sparse so the decorative layer stays cheap.
const BUBBLES: Bubble[] = [
  { id: 0,  left: "7%",  size: 7,  duration: "26s", delay: "0s",    opacity: 0.50 },
  { id: 1,  left: "19%", size: 11, duration: "32s", delay: "5s",    opacity: 0.38 },
  { id: 2,  left: "31%", size: 5,  duration: "24s", delay: "11s",   opacity: 0.55 },
  { id: 3,  left: "43%", size: 9,  duration: "30s", delay: "3s",    opacity: 0.44 },
  { id: 4,  left: "55%", size: 6,  duration: "22s", delay: "14s",   opacity: 0.52 },
  { id: 5,  left: "67%", size: 13, duration: "34s", delay: "7s",    opacity: 0.32 },
  { id: 6,  left: "79%", size: 7,  duration: "27s", delay: "17s",   opacity: 0.48 },
  { id: 7,  left: "90%", size: 9,  duration: "29s", delay: "10s",   opacity: 0.42 },
];

interface BubbleFieldProps {
  className?: string;
  intensity?: number;
  /** Border + fill color for the bubbles. Pass a theme-aware value. */
  color?: string;
  fill?: string;
}

function BubbleFieldImpl({
  className = "",
  intensity = 1,
  color = "rgba(34,211,238,0.60)",
  fill = "rgba(34,211,238,0.10)",
}: BubbleFieldProps) {
  return (
    <div
      aria-hidden
      className={className}
      style={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        pointerEvents: "none",
        zIndex: 0,
      }}
    >
      {BUBBLES.map((b) => (
        <span
          key={b.id}
          style={{
            position: "absolute",
            bottom: 0,
            left: b.left,
            width: b.size,
            height: b.size,
            opacity: b.opacity * intensity,
            borderRadius: "50%",
            border: `1px solid ${color}`,
            background: fill,
            // transform + opacity only (in keyframes) keeps this on the GPU.
            willChange: "transform, opacity",
            animationName: "bubbleRise",
            animationTimingFunction: "ease-in",
            animationIterationCount: "infinite",
            animationDuration: b.duration,
            animationDelay: b.delay,
          }}
        />
      ))}
    </div>
  );
}

export const BubbleField = memo(BubbleFieldImpl);
