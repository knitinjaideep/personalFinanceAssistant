import type { ReactNode } from "react";

export type HomeImagePanelOverlay = "left-heavy" | "balanced" | "dark";

export interface HomeImagePanelProps {
  title: ReactNode;
  backgroundSrc: string;
  children: ReactNode;
  className?: string;
  imageClassName?: string;
  imagePosition?: string;
  overlay?: HomeImagePanelOverlay;
  contentClassName?: string;
}

const overlayGradients: Record<HomeImagePanelOverlay, { horizontal: string; vertical: string }> = {
  "left-heavy": {
    horizontal:
      "linear-gradient(to right, rgba(3,17,31,0.92) 0%, rgba(3,17,31,0.58) 45%, rgba(3,17,31,0.18) 100%)",
    vertical:
      "linear-gradient(to top, rgba(3,17,31,0.74) 0%, transparent 42%, rgba(3,17,31,0.22) 100%)",
  },
  balanced: {
    horizontal:
      "linear-gradient(to right, rgba(3,17,31,0.90) 0%, rgba(3,17,31,0.54) 50%, rgba(3,17,31,0.20) 100%)",
    vertical:
      "linear-gradient(to top, rgba(3,17,31,0.78) 0%, transparent 42%, rgba(3,17,31,0.20) 100%)",
  },
  dark: {
    horizontal:
      "linear-gradient(to right, rgba(3,17,31,0.94) 0%, rgba(3,17,31,0.82) 50%, rgba(3,17,31,0.60) 100%)",
    vertical:
      "linear-gradient(to top, rgba(3,17,31,0.75) 0%, rgba(3,17,31,0.30) 32%, transparent 55%)",
  },
};

/**
 * HomeImagePanel — self-contained image-backed card with isolate stacking context.
 *
 * - background image is -z-20 (behind everything in this panel)
 * - overlay divs are -z-10
 * - content is z-10
 * - uses CSS `isolate` so nothing bleeds out to siblings or the page background
 *
 * Tune imagePosition (e.g. "72% 62%") to shift the decorative art left/right/up/down.
 * Tune imageClassName opacity (e.g. "opacity-[0.82]") to adjust image brightness.
 * Tune overlay prop to control left-side text protection vs right-side art visibility.
 */
export function HomeImagePanel({
  title,
  backgroundSrc,
  children,
  className = "",
  imageClassName = "",
  imagePosition = "right bottom",
  overlay = "balanced",
  contentClassName = "p-6 lg:p-7",
}: HomeImagePanelProps) {
  const { horizontal, vertical } = overlayGradients[overlay];

  return (
    <div
      className={`group relative isolate overflow-hidden rounded-[32px] min-h-[340px] h-full ${className}`}
      style={{
        background: "rgba(3,17,31,0.70)",
        border: "1px solid rgba(34,211,238,0.20)",
        boxShadow: "0 24px 80px rgba(0,0,0,0.35)",
      }}
    >
      {/* Background image — stays behind all panel content */}
      <img
        src={backgroundSrc}
        alt=""
        aria-hidden
        className={`absolute inset-0 -z-20 h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-[1.03] ${imageClassName}`}
        style={{ objectPosition: imagePosition }}
      />

      {/* Horizontal overlay — protects text on left, lets art show on right */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 pointer-events-none"
        style={{ background: horizontal }}
      />

      {/* Vertical vignette — readable bottom edge */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 pointer-events-none"
        style={{ background: vertical }}
      />

      {/* Content — always on top */}
      <div className={`relative z-10 ${contentClassName}`}>
        <h2 className="text-[13px] font-bold text-white mb-4 flex items-center gap-1.5">
          {title}
        </h2>
        {children}
      </div>
    </div>
  );
}
