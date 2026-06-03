import { useAppStore } from "../store/appStore";
import { coralPageBackgrounds, getBackgroundForPage } from "../lib/coralBackgrounds";

/**
 * CoralPageBackground — fixed full-viewport photo background.
 *
 * Mount ONCE in App.tsx, outside any overflow:hidden container.
 * Switches background image based on the active page.
 * pointer-events-none so it never blocks clicks.
 */
export function CoralPageBackground() {
  const activePage = useAppStore((s) => s.activePage);
  const key = getBackgroundForPage(activePage);
  const bg = coralPageBackgrounds[key];

  return (
    <div
      aria-hidden
      className="pointer-events-none select-none"
      style={{ position: "fixed", inset: 0, zIndex: 0, overflow: "hidden" }}
    >
      {/* Background image */}
      <img
        key={bg.src}
        src={bg.src}
        alt=""
        role="presentation"
        loading="eager"
        decoding="async"
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: "center",
          transition: "opacity 0.5s ease",
        }}
      />

      {/* Dark gradient overlay — lighter at top for immersive look, heavier at bottom for readability */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "linear-gradient(to bottom, rgba(3,17,31,0.30) 0%, rgba(3,17,31,0.15) 35%, rgba(3,17,31,0.75) 100%)",
        }}
      />

      {/* Radial teal light ray from top */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(ellipse at 50% 0%, rgba(34,211,238,0.18) 0%, transparent 60%)",
        }}
      />

      {/* Subtle vignette */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(ellipse at 50% 50%, transparent 40%, rgba(3,17,31,0.55) 100%)",
        }}
      />
    </div>
  );
}
