"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

const CONTAINER = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07, delayChildren: 0.04 } },
};

const ITEM = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] as const } },
};

/** Container that staggers the entrance of its <StaggerItem> children. */
export function StaggerGroup({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div variants={CONTAINER} initial="hidden" animate="show" className={className}>
      {children}
    </motion.div>
  );
}

/** Child of <StaggerGroup>. Animates in as part of the parent's stagger sequence. */
export function StaggerItem({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div variants={ITEM} className={className}>
      {children}
    </motion.div>
  );
}
