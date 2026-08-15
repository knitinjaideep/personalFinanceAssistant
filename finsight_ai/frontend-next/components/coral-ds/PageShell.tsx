"use client";

import { clsx } from "clsx";
import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";

export type PageShellWidth = "narrow" | "default" | "wide";

interface PageShellProps {
  children: ReactNode;
  width?: PageShellWidth;
  className?: string;
}

const MAX_WIDTH: Record<PageShellWidth, string> = {
  narrow: "1120px",
  default: "1680px",
  wide: "1920px",
};

/**
 * Standard page wrapper: nav-offset margin, internal scroll container with a
 * top mask-fade, and a centered max-width column. Replaces the ~25-line
 * wrapper previously duplicated in app/page.tsx, app/banking/page.tsx, and
 * app/investments/page.tsx.
 */
export default function PageShell({ children, width = "default", className }: PageShellProps) {
  const reduceMotion = useReducedMotion();

  return (
    <div
      className="flex flex-col"
      style={{ marginTop: "var(--nav-height)", height: "calc(100dvh - var(--nav-height))" }}
    >
      <div
        className="flex-1 min-h-0 overflow-y-auto"
        style={{
          maskImage: "linear-gradient(to bottom, transparent 0px, black 32px)",
          WebkitMaskImage: "linear-gradient(to bottom, transparent 0px, black 32px)",
        }}
      >
        <motion.div
          initial={reduceMotion ? false : { opacity: 0, y: 8 }}
          animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          className={clsx("mx-auto w-full pb-12", className)}
          style={{
            maxWidth: MAX_WIDTH[width],
            paddingLeft: "var(--page-x-padding)",
            paddingRight: "var(--page-x-padding)",
            paddingTop: "1.5rem",
          }}
        >
          {children}
        </motion.div>
      </div>
    </div>
  );
}
