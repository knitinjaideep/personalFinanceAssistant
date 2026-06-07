import type { ReactNode } from "react";
import { clsx } from "clsx";

interface SectionHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  size?: "sm" | "md" | "lg";
}

export default function SectionHeader({
  eyebrow,
  title,
  description,
  action,
  className,
  size = "md",
}: SectionHeaderProps) {
  const titleClass =
    size === "lg"
      ? "page-title"
      : size === "sm"
        ? "card-title-lg"
        : "section-title";

  const descClass =
    size === "lg"
      ? "body-text max-w-2xl"
      : size === "sm"
        ? "small-text"
        : "body-text max-w-xl";

  return (
    <div className={clsx("flex items-start justify-between gap-4 flex-wrap", className)}>
      <div>
        {eyebrow && (
          <p className="eyebrow-text mb-2" style={{ color: "rgba(34,211,238,0.75)" }}>
            {eyebrow}
          </p>
        )}
        <h2 className={titleClass}>{title}</h2>
        {description && (
          <p className={clsx(descClass, "mt-2")} style={{ color: "var(--text-secondary)" }}>
            {description}
          </p>
        )}
      </div>
      {action && <div className="shrink-0 mt-1">{action}</div>}
    </div>
  );
}
