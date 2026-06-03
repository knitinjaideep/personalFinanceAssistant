import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import type { CoralMascotVariant } from "../../lib/mascots";
import { getCoralFeatureIcon, type CoralFeatureIconKey } from "../../lib/coralFeatureIcons";

export interface CoralImageFeatureCardProps {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  variant: CoralMascotVariant;
  iconKey: CoralFeatureIconKey;
  floatDelay?: string;
  className?: string;
}

export function CoralImageFeatureCard({
  title,
  description,
  actionLabel,
  onAction,
  iconKey,
  floatDelay = "0ms",
  className,
}: CoralImageFeatureCardProps) {
  const icon = getCoralFeatureIcon(iconKey);

  return (
    <motion.button
      type="button"
      onClick={onAction}
      aria-label={`${title} — ${description}`}
      className={`group relative overflow-hidden rounded-[28px] text-left cursor-pointer w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent ${className ?? ""}`}
      style={{
        minHeight: "280px",
        background: "rgba(7,24,38,0.50)",
        backdropFilter: "blur(1px)",
        WebkitBackdropFilter: "blur(1px)",
        border: "1px solid rgba(34,211,238,0.32)",
        boxShadow:
          "0 24px 80px rgba(4,14,26,0.38), 0 4px 16px rgba(4,14,26,0.22), 0 0 0 1px rgba(34,211,238,0.08), inset 0 1px 0 rgba(34,211,238,0.18)",
        animation: `coralFeatureFloat 4.8s ease-in-out infinite`,
        animationDelay: floatDelay,
      }}
      whileHover={{ scale: 1.025, y: -5, transition: { type: "spring", stiffness: 280, damping: 22 } }}
      whileTap={{ scale: 0.98, transition: { duration: 0.12 } }}
    >
      {/* Top light wash */}
      <div
        className="absolute inset-0 rounded-[28px] pointer-events-none"
        style={{ background: "linear-gradient(180deg, rgba(255,255,255,0.06) 0%, transparent 30%)" }}
      />

      {/* Hover glow ring */}
      <div
        className="absolute inset-0 rounded-[28px] pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-300"
        style={{ boxShadow: "inset 0 0 0 1.5px rgba(255,255,255,0.22), 0 0 50px rgba(95,168,211,0.22)" }}
      />

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center text-center h-full p-7" style={{ minHeight: "280px" }}>
        {/* Icon — centered, no chip */}
        <div className="mb-5 flex items-center justify-center">
          <img
            src={icon.src}
            alt={icon.alt}
            className="h-28 w-28 object-contain drop-shadow-[0_4px_16px_rgba(0,0,0,0.60)] transition-transform duration-300 group-hover:scale-110"
          />
        </div>

        {/* Title */}
        <h3 className="text-[20px] font-extrabold leading-tight tracking-tight text-white">
          {title}
        </h3>

        {/* Description */}
        <p
          className="mt-2 text-[13px] leading-relaxed flex-1"
          style={{ color: "rgba(186,230,255,0.65)" }}
        >
          {description}
        </p>

        {/* Action label */}
        <div
          className="mt-5 inline-flex items-center gap-1.5 text-[13px] font-bold"
          style={{ color: "rgba(34,211,238,0.85)" }}
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
