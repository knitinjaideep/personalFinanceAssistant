import { type ReactNode } from "react";
import { clsx } from "clsx";
import { motion } from "framer-motion";
import { cardHoverVariants } from "../../design/motion";

interface CardProps {
  children: ReactNode;
  className?: string;
  variant?: "default" | "ocean" | "coral" | "sand" | "glass";
  padding?: "none" | "sm" | "md" | "lg";
  hover?: boolean;
  animate?: boolean;
}

const variantClasses = {
  default: "bg-white/88 border border-white/25 shadow-glass",
  glass:   "glass shadow-glass",
  ocean:   "bg-ocean-deep/90 text-white border border-white/10 shadow-glass",
  coral:   "bg-coral-50/90 border border-coral-100/60",
  sand:    "bg-sand-50/90 border border-sand-100/60",
};

const paddingClasses = {
  none: "",
  sm:   "p-4",
  md:   "p-5",
  lg:   "p-6",
};

export function Card({
  children,
  className,
  variant = "default",
  padding = "md",
  hover = false,
  animate = false,
}: CardProps) {
  const base = clsx(
    "rounded-3xl",
    variantClasses[variant],
    paddingClasses[padding],
    className
  );

  if (hover || animate) {
    return (
      <motion.div
        className={base}
        variants={hover ? cardHoverVariants : undefined}
        initial={hover ? "rest" : undefined}
        whileHover={hover ? "hover" : undefined}
        style={{ backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}
      >
        {children}
      </motion.div>
    );
  }

  return (
    <div
      className={base}
      style={{ backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}
    >
      {children}
    </div>
  );
}
