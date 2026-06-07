import { motion } from "framer-motion";

export interface TabDef {
  key: string;
  label: string;
  badge?: string | number;
}

interface Props {
  tabs: TabDef[];
  active: string;
  onChange: (key: string) => void;
  className?: string;
}

export function DashboardTabs({ tabs, active, onChange, className = "" }: Props) {
  return (
    <div
      className={`flex items-center gap-1 p-1 rounded-2xl overflow-x-auto scrollbar-none ${className}`}
      style={{
        background: "var(--panel-bg)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: "1px solid var(--panel-border)",
      }}
    >
      {tabs.map((tab) => {
        const isActive = tab.key === active;
        return (
          <button
            key={tab.key}
            type="button"
            onClick={() => onChange(tab.key)}
            className="relative shrink-0 flex items-center gap-1.5 px-4 py-2.5 rounded-[14px] coral-nav-text font-semibold transition-colors"
            style={{
              color: isActive ? "#fff" : "var(--text-muted)",
              background: "transparent",
            }}
          >
            {isActive && (
              <motion.div
                layoutId="tab-pill"
                className="absolute inset-0 rounded-[14px]"
                style={{ background: "rgba(34,211,238,0.18)", border: "1px solid rgba(34,211,238,0.35)" }}
                transition={{ type: "spring", bounce: 0.2, duration: 0.4 }}
              />
            )}
            <span className="relative">{tab.label}</span>
            {tab.badge !== undefined && (
              <span
                className="relative coral-badge-text px-1.5 py-0.5 rounded-full leading-none"
                style={{
                  background: isActive ? "rgba(34,211,238,0.25)" : "rgba(220,242,250,0.10)",
                  color: isActive ? "#22d3ee" : "var(--text-dim)",
                }}
              >
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
