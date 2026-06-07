import type { ReactNode } from "react";
import { FileSearch } from "lucide-react";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  compact?: boolean;
}

export default function EmptyState({
  icon,
  title,
  description,
  action,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center rounded-3xl ${compact ? "py-10 px-6" : "py-20 px-8"}`}
      style={{
        background: "var(--empty-bg)",
        border: "1px solid var(--empty-border)",
      }}
    >
      <div
        className="flex items-center justify-center rounded-3xl mb-5"
        style={{
          width: compact ? 48 : 64,
          height: compact ? 48 : 64,
          background: "var(--glass-light-bg)",
          border: "1px solid var(--border-subtle)",
          color: "var(--empty-icon)",
        }}
      >
        {icon ?? <FileSearch size={compact ? 22 : 28} />}
      </div>

      <h3
        className={compact ? "card-title-lg mb-2" : "section-title mb-3"}
        style={{ color: "var(--heading-primary)" }}
      >
        {title}
      </h3>

      {description && (
        <p
          className={`${compact ? "small-text" : "body-text"} max-w-sm`}
          style={{ color: "var(--empty-text)" }}
        >
          {description}
        </p>
      )}

      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
