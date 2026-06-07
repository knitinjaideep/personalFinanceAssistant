import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { BankingAccountRowItem } from "./BankingAccountRow";
import { BankingAccountDetailDrawer } from "./BankingAccountDetailDrawer";
import type { BankingAccountRow } from "../../lib/bankingDashboard";

interface Props {
  title: string;
  subtitle: string;
  rows: BankingAccountRow[];
  accentColor: string;
  defaultOpen?: boolean;
  showCashFlow?: boolean;
  onAskCoral?: () => void;
  onViewDocuments?: () => void;
}

export function BankingAccountGroup({
  title,
  subtitle,
  rows,
  accentColor,
  defaultOpen = false,
  showCashFlow = false,
  onAskCoral,
  onViewDocuments,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [selectedRow, setSelectedRow] = useState<BankingAccountRow | null>(null);

  const withData = rows.filter((r) => r.status !== "missing").length;
  const badge = withData > 0 ? `${withData} active` : "No data";

  return (
    <>
      <div
        className="rounded-[22px] overflow-hidden"
        style={{
          background: "var(--panel-bg)",
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          border: "1px solid var(--panel-border)",
        }}
      >
        {/* Header */}
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full flex items-center gap-3 px-5 py-4 text-left"
          style={{ background: open ? "var(--accordion-open-bg)" : "transparent" }}
        >
          <div className="w-1 h-6 rounded-full shrink-0" style={{ background: accentColor }} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[15px] font-bold" style={{ color: "var(--text-primary)" }}>{title}</span>
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
            </div>
            <p className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>{subtitle}</p>
          </div>
          <motion.div animate={{ rotate: open ? 0 : -90 }} transition={{ duration: 0.2 }} className="shrink-0">
            <ChevronDown size={16} style={{ color: "var(--text-muted)" }} />
          </motion.div>
        </button>

        {/* Rows */}
        <AnimatePresence initial={false}>
          {open && (
            <motion.div
              key="content"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.26, ease: [0.4, 0, 0.2, 1] }}
              style={{ overflow: "hidden" }}
            >
              <div
                className="px-4 pb-4 pt-3 space-y-2"
                style={{ borderTop: "1px solid var(--panel-border)" }}
              >
                {rows.map((row) => (
                  <BankingAccountRowItem
                    key={row.config.key}
                    row={row}
                    showSpend={!showCashFlow}
                    showCashFlow={showCashFlow}
                    onClick={() => setSelectedRow(row)}
                  />
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Detail drawer */}
      <BankingAccountDetailDrawer
        row={selectedRow}
        open={!!selectedRow}
        onClose={() => setSelectedRow(null)}
        onAskCoral={onAskCoral}
        onViewDocuments={onViewDocuments}
      />
    </>
  );
}
