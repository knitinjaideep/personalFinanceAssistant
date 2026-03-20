/**
 * Motion system — Coral ocean theme
 *
 * Design principles:
 * - All animations 250–500ms (premium feel, not sluggish)
 * - Ease curves feel natural / springy
 * - Stagger used for lists / card grids
 * - Never block the user — animations should feel effortless
 */

import type { Variants, Transition } from "framer-motion";

// ── Base transitions ─────────────────────────────────────────────────────────

export const transitions = {
  /** Default smooth transition */
  smooth: { duration: 0.3, ease: [0.4, 0, 0.2, 1] } satisfies Transition,

  /** Spring-y for interactive elements */
  spring: { type: "spring", stiffness: 400, damping: 30 } satisfies Transition,

  /** Gentle spring for cards */
  cardSpring: { type: "spring", stiffness: 300, damping: 28 } satisfies Transition,

  /** Fast for micro-interactions */
  fast: { duration: 0.15, ease: [0.4, 0, 0.2, 1] } satisfies Transition,

  /** Slow for ambient / background effects */
  ambient: { duration: 0.6, ease: [0.4, 0, 0.2, 1] } satisfies Transition,
} as const;

// ── Page-level variants ──────────────────────────────────────────────────────

/** Full page fade + upward drift on enter */
export const pageVariants: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: [0.4, 0, 0.2, 1], staggerChildren: 0.06 },
  },
};

/** Stagger container — wrap a grid/list in this */
export const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.07, delayChildren: 0.05 },
  },
};

/** Individual stagger child (cards, rows, etc.) */
export const staggerChild: Variants = {
  hidden: { opacity: 0, y: 14, scale: 0.97 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.35, ease: [0.34, 1.1, 0.64, 1] },
  },
};

/** Fade only (no movement — for overlays) */
export const fadeVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.25 } },
  exit: { opacity: 0, transition: { duration: 0.2 } },
};

// ── Component-level variants ─────────────────────────────────────────────────

/** Card hover lift */
export const cardHoverVariants: Variants = {
  rest: { y: 0, boxShadow: "0 4px 24px rgba(11,60,93,0.10)" },
  hover: {
    y: -3,
    boxShadow: "0 12px 40px rgba(11,60,93,0.18)",
    transition: transitions.cardSpring,
  },
};

/** Button press / scale */
export const buttonVariants: Variants = {
  rest: { scale: 1 },
  hover: { scale: 1.03, transition: transitions.spring },
  tap: { scale: 0.97, transition: transitions.fast },
};

/** Chat bubble slide in */
export const userBubbleVariants: Variants = {
  hidden: { opacity: 0, x: 16, scale: 0.96 },
  visible: {
    opacity: 1,
    x: 0,
    scale: 1,
    transition: { duration: 0.3, ease: [0.34, 1.1, 0.64, 1] },
  },
};

export const assistantBubbleVariants: Variants = {
  hidden: { opacity: 0, x: -16, scale: 0.96 },
  visible: {
    opacity: 1,
    x: 0,
    scale: 1,
    transition: { duration: 0.3, ease: [0.34, 1.1, 0.64, 1] },
  },
};

/** Mascot float */
export const mascotVariants: Variants = {
  float: {
    y: [0, -8, 0],
    transition: { duration: 4, ease: "easeInOut", repeat: Infinity },
  },
};

/** Icon gentle bob */
export const iconBobVariants: Variants = {
  rest: { y: 0 },
  hover: {
    y: [-2, 2, -2],
    transition: { duration: 0.6, ease: "easeInOut", repeat: 1 },
  },
};

/** Collapse / expand (height) */
export const collapseVariants: Variants = {
  collapsed: { height: 0, opacity: 0, overflow: "hidden" },
  expanded: {
    height: "auto",
    opacity: 1,
    transition: { duration: 0.3, ease: [0.4, 0, 0.2, 1] },
  },
};

/** Success pulse (for upload complete, etc.) */
export const successPulseVariants: Variants = {
  idle: { scale: 1, opacity: 1 },
  pulse: {
    scale: [1, 1.08, 1],
    opacity: [1, 0.85, 1],
    transition: { duration: 0.5, ease: "easeInOut" },
  },
};

/** Typing indicator dots */
export const dotVariants: Variants = {
  bounce: {
    y: [0, -5, 0],
    transition: { duration: 0.6, ease: "easeInOut", repeat: Infinity },
  },
};
