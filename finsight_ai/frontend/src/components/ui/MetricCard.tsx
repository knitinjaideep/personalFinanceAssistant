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
    valueColor: "#FF7A5A",
    iconBg:     "rgba(255,122,90,0.12)",
    iconBorder: "rgba(255,122,90,0.22)",
    iconColor:  "#FF7A5A",
    glow:       "0 0 28px rgba(255,122,90,0.22), 0 8px 24px rgba(255,122,90,0.12)",
    hoverGlow:  "0 0 40px rgba(255,122,90,0.32), 0 12px 36px rgba(255,122,90,0.18)",
    accentLine: "linear-gradient(90deg, rgba(255,122,90,0.70), transparent)",
  },
  ocean: {
    valueColor: "#22d3ee",
    iconBg:     "rgba(34,211,238,0.10)",
    iconBorder: "rgba(34,211,238,0.20)",
    iconColor:  "#22d3ee",
    glow:       "0 0 28px rgba(34,211,238,0.20), 0 8px 24px rgba(34,211,238,0.10)",
    hoverGlow:  "0 0 40px rgba(34,211,238,0.30), 0 12px 36px rgba(34,211,238,0.16)",
    accentLine: "linear-gradient(90deg, rgba(34,211,238,0.70), transparent)",
  },
  positive: {
    valueColor: "#3db886",
    iconBg:     "rgba(61,184,134,0.10)",
    iconBorder: "rgba(61,184,134,0.20)",
    iconColor:  "#3db886",
    glow:       "0 0 28px rgba(61,184,134,0.20), 0 8px 24px rgba(61,184,134,0.10)",
    hoverGlow:  "0 0 40px rgba(61,184,134,0.30), 0 12px 36px rgba(61,184,134,0.16)",
    accentLine: "linear-gradient(90deg, rgba(61,184,134,0.70), transparent)",
  },
  highlight: {
    valueColor: "#FFD166",
    iconBg:     "rgba(255,209,102,0.10)",
    iconBorder: "rgba(255,209,102,0.22)",
    iconColor:  "#FFD166",
    glow:       "0 0 28px rgba(255,209,102,0.18), 0 8px 24px rgba(255,209,102,0.10)",
    hoverGlow:  "0 0 40px rgba(255,209,102,0.28), 0 12px 36px rgba(255,209,102,0.14)",
    accentLine: "linear-gradient(90deg, rgba(255,209,102,0.70), transparent)",
  },
};

/** Counts up from 0 → target over ~700ms with ease-out-quart */
function useCountUp(target: number, duration = 700) {
  const [display, setDisplay] = useState(0);
  const raf = useRef<number>(0);

  useEffect(() => {
    const start = performance.now();
    const tick = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
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
      whileHover={{
        y: -4,
        transition: { type: "spring", stiffness: 360, damping: 26 },
      }}
      className={clsx(
        "group relative rounded-3xl p-6 flex flex-col gap-4",
        "card-shimmer-hover",
        className
      )}
      style={{
        background: "var(--card-bg)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: "1px solid var(--border-accent)",
        boxShadow: `var(--panel-shadow), ${cfg.glow}`,
        cursor: "default",
        transition: "box-shadow 0.28s ease, border-color 0.28s ease",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow =
          `0 28px 80px var(--card-hover-shadow), ${cfg.hoverGlow}`;
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow =
          `var(--panel-shadow), ${cfg.glow}`;
      }}
    >
      {/* Accent line at top */}
      <div
        aria-hidden
        className="absolute top-0 left-6 right-6 rounded-full"
        style={{ height: 2, background: cfg.accentLine, opacity: 0.60 }}
      />

      {/* Top row: label + icon */}
      <div className="flex items-start justify-between pt-1">
        <span className="metric-label">
          {label}
        </span>
        <motion.div
          whileHover={{ rotate: [0, -8, 8, 0], transition: { duration: 0.4 } }}
          aria-hidden
          className="flex items-center justify-center rounded-xl"
          style={{
            width: 40,
            height: 40,
            background: cfg.iconBg,
            border: `1px solid ${cfg.iconBorder}`,
            color: cfg.iconColor,
          }}
        >
          {icon}
        </motion.div>
      </div>

      {/* Value */}
      <div className="flex items-end justify-between">
        <p
          className="metric-value tabular"
          style={{ color: cfg.valueColor }}
        >
          {displayValue}
        </p>
        {trend && (
          <span
            className="text-xs font-semibold px-2.5 py-1 rounded-full mb-1"
            style={{
              background: trend.up ? "var(--success-soft)" : "var(--danger-soft)",
              color: trend.up ? "#3db886" : "#E45757",
              border: `1px solid ${trend.up ? "rgba(61,184,134,0.20)" : "rgba(228,87,87,0.20)"}`,
            }}
          >
            {trend.up ? "↑" : "↓"} {trend.value}
          </span>
        )}
      </div>
    </motion.div>
  );
}
