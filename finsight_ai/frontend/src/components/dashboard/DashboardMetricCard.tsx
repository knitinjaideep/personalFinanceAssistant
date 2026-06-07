import { motion } from "framer-motion";
import type { ReactNode } from "react";
import type { TrendResult } from "../../lib/dashboardData";

interface Props {
  title: string;
  value: string;
  subtitle?: string;
  trend?: TrendResult | null;
  status?: "ok" | "warn" | "error" | "missing";
  icon?: ReactNode;
  accentColor?: string;
  onClick?: () => void;
  className?: string;
}

const STATUS_COLORS = {
  ok:      "#4CAF93",
  warn:    "#FFD166",
  error:   "#E45757",
  missing: "rgba(220,242,250,0.35)",
};

export function DashboardMetricCard({
  title,
  value,
  subtitle,
  trend,
  status = "ok",
  icon,
  accentColor,
  onClick,
  className = "",
}: Props) {
  const accent = accentColor ?? STATUS_COLORS[status];
  const isClickable = !!onClick;

  return (
    <motion.div
      whileHover={isClickable ? { y: -3, scale: 1.01 } : undefined}
      transition={{ duration: 0.22, ease: "easeOut" }}
      onClick={onClick}
      className={`relative rounded-[26px] p-5 overflow-hidden ${isClickable ? "cursor-pointer" : ""} ${className}`}
      style={{
        background: "var(--panel-bg)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: `1px solid ${accent}28`,
        boxShadow: "var(--panel-shadow)",
        transition: "box-shadow 0.25s ease, border-color 0.25s ease",
      }}
    >
      {/* Accent glow top-left */}
      <div
        className="absolute top-0 left-0 w-20 h-20 rounded-full pointer-events-none"
        style={{ background: `${accent}10`, filter: "blur(18px)", transform: "translate(-30%,-30%)" }}
      />

      <div className="relative">
        {/* Title row */}
        <div className="flex items-center justify-between mb-3">
          <span className="coral-label" style={{ color: "var(--text-muted)" }}>
            {title}
          </span>
          {icon && (
            <div
              className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
              style={{ background: `${accent}18`, color: accent }}
            >
              {icon}
            </div>
          )}
        </div>

        {/* Primary value */}
        <p
          className="metric-value"
          style={{ color: value === "Needs data" || value === "—" ? "var(--text-dim)" : "var(--text-primary)" }}
        >
          {value}
        </p>

        {/* Subtitle */}
        {subtitle && (
          <p className="coral-muted mt-2 leading-snug" style={{ color: "var(--text-muted)" }}>
            {subtitle}
          </p>
        )}

        {/* Trend pill */}
        {trend && trend.pct !== null && (
          <div className="mt-2 inline-flex items-center gap-1">
            <span
              className="coral-badge-text px-2 py-0.5 rounded-full"
              style={{
                background: trend.direction === "down"
                  ? "rgba(76,175,147,0.15)"
                  : trend.direction === "up"
                    ? "rgba(228,87,87,0.15)"
                    : "rgba(220,242,250,0.10)",
                color: trend.direction === "down"
                  ? "#4CAF93"
                  : trend.direction === "up"
                    ? "#E45757"
                    : "var(--text-muted)",
              }}
            >
              {trend.label}
            </span>
          </div>
        )}

        {/* Status dot for missing */}
        {status === "missing" && (
          <p className="coral-badge-text mt-2" style={{ color: "#FFD166" }}>
            Upload or reprocess statements
          </p>
        )}
      </div>
    </motion.div>
  );
}
