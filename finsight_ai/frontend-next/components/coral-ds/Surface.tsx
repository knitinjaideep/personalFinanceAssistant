import { clsx } from "clsx";
import type { ReactNode, CSSProperties } from "react";

interface SurfaceProps {
  children: ReactNode;
  padding?: "sm" | "md" | "lg";
  className?: string;
  style?: CSSProperties;
  as?: "div" | "section" | "article";
}

const PADDING_CLASS: Record<NonNullable<SurfaceProps["padding"]>, string> = {
  sm: "p-4",
  md: "p-6",
  lg: "p-8",
};

/**
 * Calm base panel — the "fewer cards, less noise" alternative to GlassCard's
 * heavier glass variants. GlassCard is not replaced; it's still used by
 * MetricCard and other existing components.
 */
export default function Surface({ children, padding = "md", className, style, as: Tag = "div" }: SurfaceProps) {
  return (
    <Tag
      className={clsx("rounded-2xl", PADDING_CLASS[padding], className)}
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--border-subtle)",
        boxShadow: "var(--panel-shadow)",
        ...style,
      }}
    >
      {children}
    </Tag>
  );
}
