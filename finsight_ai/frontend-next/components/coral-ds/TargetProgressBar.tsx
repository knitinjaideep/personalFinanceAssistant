"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { CSSProperties } from "react";

export type FinancialBucket = "needs" | "wants" | "savings" | "investments";

interface TargetProgressBarProps {
  label: string;
  actual: number;
  target: number;
  bucket: FinancialBucket;
  className?: string;
}

const BUCKET_VAR: Record<FinancialBucket, string> = {
  needs: "var(--financial-needs)",
  wants: "var(--financial-wants)",
  savings: "var(--financial-savings)",
  investments: "var(--financial-investments)",
};

/** Labeled progress bar (actual % vs target %), colored by bucket. Includes a screen-reader-only textual summary. */
export default function TargetProgressBar({ label, actual, target, bucket, className }: TargetProgressBarProps) {
  const prefersReducedMotion = useReducedMotion();
  const color = BUCKET_VAR[bucket];
  const clampedActual = Math.max(0, Math.min(actual, 100));
  const targetPosition = Math.max(0, Math.min(target, 100));

  const trackStyle: CSSProperties = { background: "var(--border-subtle)" };

  return (
    <div className={className}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="coral-card-title">{label}</span>
        <span className="small-text" style={{ color: "var(--text-muted)" }}>
          Target {target}%
        </span>
      </div>
      <div className="relative h-2 rounded-full overflow-hidden" style={trackStyle}>
        <motion.div
          className="h-full rounded-full"
          style={{ background: color }}
          initial={{ width: 0 }}
          animate={{ width: `${clampedActual}%` }}
          transition={{ duration: prefersReducedMotion ? 0 : 0.6, ease: [0.22, 1, 0.36, 1] }}
        />
        <div
          className="absolute top-0 bottom-0 w-px"
          style={{ left: `${targetPosition}%`, background: "var(--text-dim)" }}
          aria-hidden
        />
      </div>
      <span className="sr-only">
        {label}: {actual}% actual against a {target}% target.
      </span>
    </div>
  );
}
