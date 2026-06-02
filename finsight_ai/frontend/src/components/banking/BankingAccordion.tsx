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
    <div
      className="rounded-2xl overflow-hidden"
      style={{
        background: "rgba(255,255,255,0.82)",
        border: "1px solid rgba(205,237,246,0.65)",
        boxShadow: "0 4px 24px rgba(11,60,93,0.07), inset 0 1px 0 rgba(255,255,255,0.90)",
      }}
    >
      {/* Header */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-5 py-4 text-left transition-colors"
        style={{ background: open ? "rgba(240,249,252,0.60)" : "transparent" }}
        aria-expanded={open}
      >
        {/* Accent bar */}
        <div
          className="w-1 h-6 rounded-full shrink-0"
          style={{ background: `linear-gradient(180deg, ${accentColor}, ${accentColor}88)` }}
        />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[15px] font-bold text-ocean-deep">{title}</span>
            {badge && (
              <span
                className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                style={{
                  background: `${accentColor}18`,
                  color: accentColor,
                }}
              >
                {badge}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="text-[11px] text-ocean/38 mt-0.5">{subtitle}</p>
          )}
        </div>

        <motion.div
          animate={{ rotate: open ? 0 : -90 }}
          transition={{ duration: 0.2, ease: "easeInOut" }}
          className="shrink-0"
        >
          <ChevronDown size={16} className="text-ocean/35" />
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
              style={{ borderTop: "1px solid rgba(205,237,246,0.45)" }}
            >
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
