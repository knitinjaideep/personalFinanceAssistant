/**
 * BubbleField — decorative floating bubbles that slowly rise from the bottom.
 * Pure CSS animation, pointer-events disabled, reduced-motion safe.
 */

interface Bubble {
  id: number;
  left: string;
  size: number;
  duration: string;
  delay: string;
  opacity: number;
}

const BUBBLES: Bubble[] = [
  { id: 0,  left: "4%",  size: 5,  duration: "22s", delay: "0s",    opacity: 0.38 },
  { id: 1,  left: "11%", size: 8,  duration: "28s", delay: "3.5s",  opacity: 0.28 },
  { id: 2,  left: "19%", size: 4,  duration: "19s", delay: "7s",    opacity: 0.45 },
  { id: 3,  left: "27%", size: 10, duration: "32s", delay: "1.5s",  opacity: 0.22 },
  { id: 4,  left: "35%", size: 6,  duration: "24s", delay: "11s",   opacity: 0.35 },
  { id: 5,  left: "43%", size: 3,  duration: "17s", delay: "5s",    opacity: 0.50 },
  { id: 6,  left: "51%", size: 9,  duration: "30s", delay: "0.8s",  opacity: 0.25 },
  { id: 7,  left: "58%", size: 5,  duration: "21s", delay: "14s",   opacity: 0.40 },
  { id: 8,  left: "65%", size: 7,  duration: "26s", delay: "8.5s",  opacity: 0.30 },
  { id: 9,  left: "72%", size: 4,  duration: "18s", delay: "2.5s",  opacity: 0.48 },
  { id: 10, left: "79%", size: 11, duration: "34s", delay: "6.2s",  opacity: 0.20 },
  { id: 11, left: "86%", size: 5,  duration: "23s", delay: "13s",   opacity: 0.37 },
  { id: 12, left: "93%", size: 6,  duration: "27s", delay: "4s",    opacity: 0.33 },
  { id: 13, left: "8%",  size: 3,  duration: "16s", delay: "18s",   opacity: 0.52 },
  { id: 14, left: "55%", size: 8,  duration: "29s", delay: "10s",   opacity: 0.26 },
  { id: 15, left: "88%", size: 4,  duration: "20s", delay: "16s",   opacity: 0.44 },
];

interface BubbleFieldProps {
  className?: string;
  /** Multiplier applied to all bubble opacities. Default 1. */
  intensity?: number;
}

export function BubbleField({ className = "", intensity = 1 }: BubbleFieldProps) {
  return (
    <div
      aria-hidden
      className={`bubble-field ${className}`}
      style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none", zIndex: 0 }}
    >
      {BUBBLES.map((b) => (
        <span
          key={b.id}
          className="bubble"
          style={{
            left: b.left,
            width: b.size,
            height: b.size,
            opacity: b.opacity * intensity,
            animationDuration: b.duration,
            animationDelay: b.delay,
          }}
        />
      ))}
    </div>
  );
}
