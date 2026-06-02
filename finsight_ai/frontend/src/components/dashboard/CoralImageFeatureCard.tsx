import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import type { CoralMascotVariant } from "../../lib/mascots";
import { coralMascots } from "../../lib/mascots";

export interface CoralImageFeatureCardProps {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  variant: CoralMascotVariant;
  floatDelay?: string;
  className?: string;
}

export function CoralImageFeatureCard({
  title,
  description,
  actionLabel,
  onAction,
  variant,
  floatDelay = "0ms",
  className,
}: CoralImageFeatureCardProps) {
  const mascot = coralMascots[variant];

  return (
    <motion.button
      type="button"
      onClick={onAction}
      aria-label={`${title} — ${description}`}
      className={`group relative overflow-hidden rounded-[28px] text-left cursor-pointer w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent ${className ?? ""}`}
      style={{
        minHeight: "340px",
        background: "#071826",
        border: "1px solid rgba(255,255,255,0.10)",
        boxShadow: "0 24px 80px rgba(4,14,26,0.38), 0 4px 16px rgba(4,14,26,0.22)",
        animation: `coralFeatureFloat 4.8s ease-in-out infinite`,
        animationDelay: floatDelay,
      }}
      whileHover={{ scale: 1.045, y: -6, transition: { type: "spring", stiffness: 280, damping: 22 } }}
      whileTap={{ scale: 0.98, transition: { duration: 0.12 } }}
    >
      {/* ── Full-bleed mascot background image ─── */}
      <div
        className="absolute inset-0 transition-transform duration-500 ease-out group-hover:scale-110"
        style={{
          backgroundImage: `url(${mascot.src})`,
          backgroundSize: "cover",
          backgroundPosition: "center 20%",
          backgroundRepeat: "no-repeat",
        }}
        role="img"
        aria-label={mascot.alt}
      />

      {/* ── Gradient overlays ──────────────────── */}

      {/* Top light wash */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "linear-gradient(180deg, rgba(255,255,255,0.08) 0%, transparent 32%)",
        }}
      />

      {/* Ambient glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(circle at 28% 20%, rgba(255,255,255,0.14) 0%, transparent 42%), radial-gradient(circle at 78% 78%, rgba(255,127,102,0.18) 0%, transparent 40%)",
        }}
      />

      {/* Bottom readability gradient — heavy enough to guarantee contrast */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "linear-gradient(to top, rgba(4,22,38,0.96) 0%, rgba(4,22,38,0.75) 35%, rgba(4,22,38,0.25) 60%, transparent 100%)",
        }}
      />

      {/* ── Hover glow ring ────────────────────── */}
      <div
        className="absolute inset-0 rounded-[28px] pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-300"
        style={{
          boxShadow: "inset 0 0 0 1.5px rgba(255,255,255,0.22), 0 0 50px rgba(95,168,211,0.22)",
        }}
      />

      {/* ── Text content ──────────────────────── */}
      <div className="absolute bottom-0 left-0 right-0 p-7">
        <h3
          className="text-[22px] font-extrabold leading-tight tracking-tight text-white"
          style={{ textShadow: "0 2px 12px rgba(4,14,26,0.60)" }}
        >
          {title}
        </h3>
        <p
          className="mt-2 text-[13px] leading-relaxed"
          style={{ color: "rgba(255,255,255,0.80)", textShadow: "0 1px 6px rgba(4,14,26,0.50)" }}
        >
          {description}
        </p>
        <div
          className="mt-5 inline-flex items-center gap-1.5 text-[13px] font-bold"
          style={{ color: "#FF9B85" }}
        >
          <span>{actionLabel}</span>
          <ArrowRight
            size={14}
            className="transition-transform duration-200 group-hover:translate-x-1"
          />
        </div>
      </div>
    </motion.button>
  );
}
