"use client";

import { usePathname } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

/**
 * Lightweight page transition for the App Router.
 *
 * We key a single motion.div on the pathname so each navigation remounts and
 * replays a cheap entrance (opacity + small translateY only — no blur/scale,
 * which force expensive repaints). Entrance-only avoids the App Router blank
 * frame that AnimatePresence exit would cause. Reduced-motion → instant render.
 */
export default function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const reduce = useReducedMotion();

  if (reduce) return <div>{children}</div>;

  return (
    <motion.div
      key={pathname}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
      style={{ willChange: "transform, opacity" }}
    >
      {children}
    </motion.div>
  );
}
