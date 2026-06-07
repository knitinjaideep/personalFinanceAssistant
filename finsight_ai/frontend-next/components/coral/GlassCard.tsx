import { clsx } from "clsx";
import type { ReactNode, CSSProperties } from "react";

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  variant?: "default" | "elevated" | "accent" | "subtle";
  style?: CSSProperties;
  onClick?: () => void;
  as?: "div" | "section" | "article";
}

const variantStyles: Record<NonNullable<GlassCardProps["variant"]>, string> = {
  default:  "glass rounded-3xl p-6",
  elevated: "card-premium p-6",
  accent:   "glass rounded-3xl p-6 border-[var(--border-accent)]",
  subtle:   "glass-light rounded-2xl p-5",
};

export default function GlassCard({
  children,
  className,
  variant = "default",
  style,
  onClick,
  as: Tag = "div",
}: GlassCardProps) {
  return (
    <Tag
      className={clsx(variantStyles[variant], onClick && "cursor-pointer", className)}
      style={style}
      onClick={onClick}
    >
      {children}
    </Tag>
  );
}
