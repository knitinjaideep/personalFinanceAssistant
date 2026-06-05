import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown } from "lucide-react";

interface Props {
  title: string;
  subtitle?: string;
  badge?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
  accentColor?: string;
}

export function BankingAccordion({
  title,
  subtitle,
  badge,
  defaultOpen = true,
  children,
  accentColor = "#FF7A5A",
}: Props) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="overflow-hidden">
      {/* Header */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-5 py-4 text-left transition-colors"
        style={{ background: open ? "var(--accordion-open-bg)" : "transparent" }}
        aria-expanded={open}
      >
        {/* Accent bar */}
        <div
          className="w-1 h-6 rounded-full shrink-0"
          style={{ background: `linear-gradient(180deg, ${accentColor}, ${accentColor}88)` }}
        />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[15px] font-bold" style={{ color: "var(--text-primary)" }}>{title}</span>
            {badge && (
              <span
                className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                style={{
                  background: `${accentColor}22`,
                  color: accentColor,
                  border: `1px solid ${accentColor}40`,
                }}
              >
                {badge}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>{subtitle}</p>
          )}
        </div>

        <motion.div
          animate={{ rotate: open ? 0 : -90 }}
          transition={{ duration: 0.2, ease: "easeInOut" }}
          className="shrink-0"
        >
          <ChevronDown size={16} style={{ color: "var(--text-muted)" }} />
        </motion.div>
      </button>

      {/* Content */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
            style={{ overflow: "hidden" }}
          >
            <div
              className="px-5 pb-5 pt-2"
              style={{ borderTop: "1px solid var(--panel-border)" }}
            >
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
