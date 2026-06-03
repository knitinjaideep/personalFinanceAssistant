import { useAppStore } from "../../store/appStore";

/**
 * Glass-bubble mascot for the Home hero.
 * Clicking navigates to the chat page. Speech bubble is hover/focus-only.
 */
export function HomeHeroMascot() {
  const setActivePage = useAppStore((s) => s.setActivePage);

  return (
    <button
      type="button"
      onClick={() => setActivePage("chat")}
      aria-label="Open Coral chat"
      className="group relative block w-fit cursor-pointer bg-transparent border-0 p-0 outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/60 focus-visible:ring-offset-2 focus-visible:ring-offset-[#03111f] rounded-full"
    >
      {/* Hover-only speech bubble */}
      <div
        className="pointer-events-none absolute z-30 w-72 -translate-x-1/2 translate-y-2 rounded-2xl px-5 py-3 text-center text-sm font-semibold leading-5 opacity-0 shadow-2xl backdrop-blur-xl transition-all duration-300 group-hover:translate-y-0 group-hover:opacity-100 group-focus-visible:translate-y-0 group-focus-visible:opacity-100"
        style={{
          top: "-4.5rem",
          left: "50%",
          background: "rgba(6,31,51,0.88)",
          border: "1px solid rgba(34,211,238,0.20)",
          color: "rgba(186,230,255,0.85)",
        }}
      >
        Ask me anything about your spending, statements, fees, or investments.
        {/* bubble tail */}
        <span
          aria-hidden
          className="absolute -bottom-2 left-1/2 h-4 w-4 -translate-x-1/2 rotate-45"
          style={{
            background: "rgba(6,31,51,0.88)",
            borderRight: "1px solid rgba(34,211,238,0.20)",
            borderBottom: "1px solid rgba(34,211,238,0.20)",
          }}
        />
      </div>

      {/* Environmental glow behind bubble */}
      <div
        aria-hidden
        className="pointer-events-none absolute -z-20 rounded-full transition-opacity duration-300 group-hover:opacity-100"
        style={{
          inset: "-18px",
          background: "rgba(34,211,238,0.10)",
          filter: "blur(80px)",
        }}
      />
      {/* Ground shadow beneath bubble */}
      <div
        aria-hidden
        className="pointer-events-none absolute -z-20 rounded-full"
        style={{
          bottom: "24px",
          left: "50%",
          transform: "translateX(-50%)",
          width: "72%",
          height: "64px",
          background: "rgba(0,0,0,0.30)",
          filter: "blur(24px)",
        }}
      />

      {/* Glass bubble */}
      <div
        className="coral-soft-float relative z-10 flex aspect-square items-center justify-center overflow-hidden rounded-full transition-transform duration-300 group-hover:-translate-y-1 group-hover:scale-[1.025]"
        style={{
          width: "clamp(300px, 28vw, 430px)",
          background: "rgba(186,230,255,0.055)",
          border: "1px solid rgba(186,230,255,0.35)",
          backdropFilter: "blur(2px)",
          WebkitBackdropFilter: "blur(2px)",
          boxShadow:
            "inset 0 0 40px rgba(255,255,255,0.10), inset 0 -30px 60px rgba(8,47,73,0.24), 0 24px 90px rgba(0,0,0,0.42), 0 0 55px rgba(34,211,238,0.16)",
        }}
      >
        {/* Top glass gradient */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-full"
          style={{
            background: "linear-gradient(135deg, rgba(255,255,255,0.22) 0%, rgba(186,230,255,0.05) 40%, transparent 100%)",
          }}
        />

        {/* Underwater tint bottom */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-full"
          style={{
            background: "linear-gradient(to top, rgba(3,17,31,0.22) 0%, transparent 50%, rgba(255,255,255,0.08) 100%)",
          }}
        />

        {/* Large highlight sweep (top-left) */}
        <div
          aria-hidden
          className="pointer-events-none absolute rounded-full"
          style={{
            top: "12%",
            left: "18%",
            width: "32%",
            height: "20%",
            background: "rgba(255,255,255,0.22)",
            filter: "blur(20px)",
            transform: "rotate(-28deg)",
          }}
        />
        {/* Small specular dot 1 */}
        <div
          aria-hidden
          className="pointer-events-none absolute rounded-full"
          style={{
            top: "18%",
            right: "18%",
            width: "24px",
            height: "24px",
            background: "rgba(255,255,255,0.45)",
            filter: "blur(1px)",
          }}
        />
        {/* Small specular dot 2 */}
        <div
          aria-hidden
          className="pointer-events-none absolute rounded-full"
          style={{
            top: "25%",
            right: "25%",
            width: "12px",
            height: "12px",
            background: "rgba(255,255,255,0.35)",
            filter: "blur(1px)",
          }}
        />

        {/* Mascot image */}
        <img
          src="/mascots/coral/coral-mascot-transparent.png"
          alt="Coral financial assistant"
          loading="eager"
          decoding="async"
          className="relative z-10 h-auto w-[88%] translate-y-4 object-contain select-none"
          style={{
            filter:
              "drop-shadow(0 24px 50px rgba(0,0,0,0.38)) drop-shadow(0 4px 12px rgba(34,211,238,0.22))",
          }}
        />

        {/* Bottom water haze */}
        <div
          aria-hidden
          className="pointer-events-none absolute bottom-0 rounded-full"
          style={{
            left: "50%",
            transform: "translateX(-50%)",
            width: "85%",
            height: "80px",
            background: "rgba(34,211,238,0.10)",
            filter: "blur(24px)",
          }}
        />
      </div>
    </button>
  );
}
