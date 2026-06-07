"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

/**
 * Per-page entrance wrapper — a slightly stronger float than <FadeIn>.
 * Use at the top of a page's content tree when the page is not already wrapped
 * by the global <PageTransition>, or to add a secondary inner float.
 */
export default function FloatingPage({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
