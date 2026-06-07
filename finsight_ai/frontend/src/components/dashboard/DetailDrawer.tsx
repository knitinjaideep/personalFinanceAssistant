import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import type { ReactNode } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  width?: number;
}

export function DetailDrawer({ open, onClose, title, subtitle, children, width = 440 }: Props) {
  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40"
            style={{ background: "rgba(3,17,31,0.65)", backdropFilter: "blur(2px)" }}
            onClick={onClose}
          />

          {/* Drawer */}
          <motion.div
            key="drawer"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", bounce: 0.12, duration: 0.45 }}
            className="fixed right-0 top-0 bottom-0 z-50 flex flex-col overflow-hidden"
            style={{
              width: Math.min(width, window.innerWidth),
              background: "var(--bg-base)",
              backdropFilter: "blur(24px)",
              WebkitBackdropFilter: "blur(24px)",
              borderLeft: "1px solid var(--panel-border)",
              boxShadow: "-8px 0 40px rgba(3,17,31,0.5)",
            }}
          >
            {/* Header */}
            <div
              className="shrink-0 flex items-start justify-between px-6 py-5"
              style={{ borderBottom: "1px solid var(--panel-border)" }}
            >
              <div className="min-w-0 pr-4">
                <h2 className="text-[16px] font-bold truncate" style={{ color: "var(--text-primary)" }}>
                  {title}
                </h2>
                {subtitle && (
                  <p className="text-[12px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                    {subtitle}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={onClose}
                className="shrink-0 rounded-xl p-1.5 transition-colors hover:bg-white/5"
                style={{ color: "var(--text-muted)" }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Scrollable body */}
            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
              {children}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
