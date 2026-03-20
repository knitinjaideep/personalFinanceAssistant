import { type ReactNode, useEffect, useRef, useState } from "react";
import { clsx } from "clsx";
import { motion } from "framer-motion";
import { staggerChild } from "../../design/motion";

interface MetricCardProps {
  label: string;
  value: string | number;
  icon: ReactNode;
  accent?: "coral" | "ocean" | "positive" | "highlight";
  trend?: { value: string; up: boolean };
  className?: string;
}

const accentConfig = {
  coral: {
    text:    "text-coral",
    iconBg:  "bg-coral-50 text-coral-600",
    glow:    "hover:shadow-glow",
    badge:   "bg-coral-50 border-coral-100",
    bg:      "bg-metric-coral",
  },
  ocean: {
    text:    "text-ocean",
    iconBg:  "bg-ocean-50 text-ocean",
    glow:    "hover:shadow-glow-ocean",
    badge:   "bg-ocean-50 border-ocean-100",
    bg:      "bg-metric-ocean",
  },
  positive: {
    text:    "text-positive",
    iconBg:  "bg-positive/10 text-positive",
    glow:    "hover:shadow-glow-positive",
    badge:   "bg-positive/8 border-positive/20",
    bg:      "bg-metric-positive",
  },
  highlight: {
    text:    "text-yellow-600",
    iconBg:  "bg-highlight/20 text-yellow-600",
    glow:    "",
    badge:   "bg-highlight/10 border-highlight/30",
    bg:      "bg-metric-highlight",
  },
};

/** Counts up from 0 → target over ~600ms */
function useCountUp(target: number, duration = 600) {
  const [display, setDisplay] = useState(0);
  const raf = useRef<number>(0);

  useEffect(() => {
    const start = performance.now();
    const tick = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out-quart
      const eased = 1 - Math.pow(1 - progress, 4);
      setDisplay(Math.round(eased * target));
      if (progress < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration]);

  return display;
}

export function MetricCard({
  label,
  value,
  icon,
  accent = "ocean",
  trend,
  className,
}: MetricCardProps) {
  const cfg = accentConfig[accent];
  const isNumber = typeof value === "number";
  const animated = useCountUp(isNumber ? (value as number) : 0);
  const displayValue = isNumber ? animated.toLocaleString() : value;

  return (
    <motion.div
      variants={staggerChild}
      whileHover={{ y: -3, transition: { type: "spring", stiffness: 350, damping: 25 } }}
      className={clsx(
        "rounded-3xl p-5 flex flex-col gap-3",
        "bg-white/88 border border-white/30",
        "shadow-glass cursor-default",
        cfg.glow,
        "transition-shadow duration-250",
        className
      )}
      style={{ backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}
    >
      {/* Top row: label + icon */}
      <div className="flex items-start justify-between">
        <span className="text-[11px] font-semibold text-ocean-deep/50 uppercase tracking-widest leading-tight">
          {label}
        </span>
        <motion.div
          whileHover={{ rotate: [0, -8, 8, 0], transition: { duration: 0.4 } }}
          className={clsx("p-2 rounded-xl border", cfg.iconBg, cfg.badge)}
        >
          {icon}
        </motion.div>
      </div>

      {/* Value */}
      <div className="flex items-end justify-between">
        <p className={clsx("text-3xl font-bold tracking-tight tabular", cfg.text)}>
          {displayValue}
        </p>
        {trend && (
          <span
            className={clsx(
              "text-xs font-semibold px-2 py-0.5 rounded-full",
              trend.up
                ? "bg-positive/10 text-positive"
                : "bg-negative/10 text-negative"
            )}
          >
            {trend.up ? "↑" : "↓"} {trend.value}
          </span>
        )}
      </div>
    </motion.div>
  );
}
