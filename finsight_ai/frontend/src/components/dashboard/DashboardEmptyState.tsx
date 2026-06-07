import { FileText, Upload } from "lucide-react";
import type { ReactNode } from "react";

interface Props {
  title: string;
  description: string;
  icon?: ReactNode;
  primaryAction?: { label: string; onClick: () => void };
  secondaryAction?: { label: string; onClick: () => void };
  compact?: boolean;
}

export function DashboardEmptyState({
  title,
  description,
  icon,
  primaryAction,
  secondaryAction,
  compact = false,
}: Props) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${compact ? "py-8 px-4" : "py-12 px-6"}`}
      style={{
        background: "var(--empty-bg)",
        borderRadius: "20px",
        border: "1px dashed var(--empty-border)",
      }}
    >
      <div
        className="mb-3 rounded-2xl flex items-center justify-center"
        style={{
          width: compact ? 40 : 52,
          height: compact ? 40 : 52,
          background: "rgba(34,211,238,0.08)",
          border: "1px solid rgba(34,211,238,0.18)",
        }}
      >
        <span style={{ color: "rgba(34,211,238,0.6)", display: "flex" }}>
          {icon ?? <FileText size={compact ? 18 : 22} />}
        </span>
      </div>

      <p
        className={`font-semibold mb-1 ${compact ? "text-[13px]" : "text-[15px]"}`}
        style={{ color: "var(--text-secondary)" }}
      >
        {title}
      </p>
      <p
        className={`leading-relaxed max-w-[280px] ${compact ? "text-[11px]" : "text-[12px]"}`}
        style={{ color: "var(--text-muted)" }}
      >
        {description}
      </p>

      {(primaryAction || secondaryAction) && (
        <div className="flex items-center gap-2 mt-4">
          {primaryAction && (
            <button
              type="button"
              onClick={primaryAction.onClick}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-[12px] font-semibold transition-all hover:-translate-y-0.5"
              style={{
                background: "rgba(34,211,238,0.15)",
                border: "1px solid rgba(34,211,238,0.30)",
                color: "#22d3ee",
              }}
            >
              <Upload size={12} />
              {primaryAction.label}
            </button>
          )}
          {secondaryAction && (
            <button
              type="button"
              onClick={secondaryAction.onClick}
              className="px-4 py-2 rounded-xl text-[12px] font-medium transition-all hover:-translate-y-0.5"
              style={{
                background: "rgba(220,242,250,0.05)",
                border: "1px solid var(--panel-border)",
                color: "var(--text-muted)",
              }}
            >
              {secondaryAction.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
