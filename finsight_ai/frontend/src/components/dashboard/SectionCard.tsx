import type { ReactNode } from "react";

interface Props {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
  noPadding?: boolean;
  accentColor?: string;
  action?: ReactNode;
}

export function SectionCard({
  title,
  subtitle,
  children,
  className = "",
  noPadding = false,
  accentColor,
  action,
}: Props) {
  return (
    <div
      className={`rounded-[24px] overflow-hidden ${className}`}
      style={{
        background: "var(--panel-bg)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: "1px solid var(--panel-border)",
        boxShadow: "var(--panel-shadow)",
      }}
    >
      {(title || subtitle || action) && (
        <div
          className="flex items-start justify-between px-5 pt-5 pb-4"
          style={{ borderBottom: "1px solid var(--panel-border)" }}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            {accentColor && (
              <div className="w-1 h-5 rounded-full shrink-0" style={{ background: accentColor }} />
            )}
            <div className="min-w-0">
              {title && (
                <p className="text-[14px] font-bold truncate" style={{ color: "var(--text-primary)" }}>
                  {title}
                </p>
              )}
              {subtitle && (
                <p className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {subtitle}
                </p>
              )}
            </div>
          </div>
          {action && <div className="shrink-0 ml-3">{action}</div>}
        </div>
      )}
      <div className={noPadding ? "" : "p-5"}>{children}</div>
    </div>
  );
}
