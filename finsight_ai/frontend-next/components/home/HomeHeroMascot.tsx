"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";

/**
 * Mascot for the Home hero.
 * - No glass bubble — coral floats freely with a drop-shadow.
 * - On hover a comment card slides in from the right, top-aligned.
 * - The card uses CSS transitions (not Framer) so it stays cheap.
 */
export function HomeHeroMascot() {
  const router = useRouter();

  return (
    <div className="group relative flex items-start justify-end">

      {/* ── Comment card — overlaps top-right of mascot ── */}
      <div
        className="
          pointer-events-none
          absolute top-0 left-full ml-5
          w-60
          opacity-0 -translate-x-3
          transition-[opacity,transform] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]
          group-hover:opacity-100 group-hover:translate-x-0
          group-focus-within:opacity-100 group-focus-within:translate-x-0

        "
        aria-hidden
      >
        <div
          className="relative rounded-2xl px-5 py-4 text-sm font-medium leading-relaxed"
          style={{
            background: "rgba(4,22,40,0.78)",
            border: "1px solid rgba(34,211,238,0.20)",
            backdropFilter: "blur(18px)",
            WebkitBackdropFilter: "blur(18px)",
            boxShadow:
              "0 16px 48px rgba(3,17,31,0.60), 0 0 0 1px rgba(34,211,238,0.06)",
            color: "rgba(186,230,255,0.86)",
          }}
        >
          {/* Name chip */}
          <span
            className="mb-2 inline-flex items-center gap-1.5 text-[10px] font-bold tracking-[0.14em] uppercase"
            style={{ color: "rgba(34,211,238,0.72)" }}
          >
            <span
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{ background: "rgba(34,211,238,0.72)" }}
            />
            Coral
          </span>

          <p className="mt-0">
            Ask me anything about your spending, statements, fees, or investments.
          </p>

          {/* Arrow pointing left toward the mascot */}
          <span
            aria-hidden
            className="absolute top-6 -left-[9px] h-4 w-4 rotate-[225deg]"
            style={{
              background: "rgba(4,22,40,0.78)",
              borderRight: "1px solid rgba(34,211,238,0.20)",
              borderTop: "1px solid rgba(34,211,238,0.20)",
            }}
          />
        </div>
      </div>

      {/* ── Clickable mascot ── */}
      <button
        type="button"
        onClick={() => router.push("/chat")}
        aria-label="Open Coral chat"
        className="relative block cursor-pointer bg-transparent border-0 p-0 outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/60 focus-visible:ring-offset-2 rounded-full"
      >
        {/* Environmental glow — appears on hover */}
        <div
          aria-hidden
          className="pointer-events-none absolute -z-10 rounded-full opacity-0 transition-opacity duration-500 group-hover:opacity-100"
          style={{
            inset: "-24px",
            background: "radial-gradient(circle, rgba(34,211,238,0.14) 0%, transparent 70%)",
            filter: "blur(24px)",
          }}
        />

        {/* Mascot image — no bubble, just the character */}
        <Image
          src="/mascots/coral/coral-mascot-transparent.png"
          alt="Coral financial assistant"
          width={520}
          height={520}
          priority
          className="
            coral-soft-float relative z-10
            h-auto select-none
            transition-transform duration-300
            group-hover:-translate-y-2 group-hover:scale-[1.03]
          "
          style={{
            width: "clamp(320px, 30vw, 480px)",
            filter:
              "drop-shadow(0 28px 48px rgba(0,0,0,0.42)) drop-shadow(0 4px 14px rgba(34,211,238,0.24))",
          }}
        />
      </button>
    </div>
  );
}
