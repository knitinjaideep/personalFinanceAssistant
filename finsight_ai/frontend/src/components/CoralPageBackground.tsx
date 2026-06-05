import { useAppStore } from "../store/appStore";
import { coralPageBackgrounds, getBackgroundForPage } from "../lib/coralBackgrounds";

export function CoralPageBackground() {
  const activePage = useAppStore((s) => s.activePage);
  const theme = useAppStore((s) => s.theme);
  const key = getBackgroundForPage(activePage);
  const bg = coralPageBackgrounds[key];

  const isLight = theme === "light";
  const imgSrc = isLight ? bg.lightSrc : bg.src;

  return (
    <div
      aria-hidden
      className="pointer-events-none select-none"
      style={{ position: "fixed", inset: 0, zIndex: 0, overflow: "hidden" }}
    >
      {/* Background image */}
      <img
        key={imgSrc}
        src={imgSrc}
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
          opacity: 1,
        }}
      />

      {/* Base color wash */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: isLight
            ? "linear-gradient(to bottom, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0.05) 40%, rgba(240,250,255,0.55) 100%)"
            : "linear-gradient(to bottom, rgba(3,17,31,0.30) 0%, rgba(3,17,31,0.15) 35%, rgba(3,17,31,0.75) 100%)",
          transition: "background 0.4s ease",
        }}
      />

      {/* Accent ray from top */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: isLight
            ? "none"
            : "radial-gradient(ellipse at 50% 0%, rgba(34,211,238,0.18) 0%, transparent 60%)",
          transition: "background 0.4s ease",
        }}
      />

      {/* Subtle vignette */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: isLight
            ? "none"
            : "radial-gradient(ellipse at 50% 50%, transparent 40%, rgba(3,17,31,0.55) 100%)",
          transition: "background 0.4s ease",
        }}
      />
    </div>
  );
}
