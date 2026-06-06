import { CheckCircle2, Loader2, Clock, XCircle, FileText } from "lucide-react";
import { motion } from "framer-motion";
import type { DocumentStats } from "../../types";
import { staggerChild } from "../../design/motion";

interface Props {
  stats: DocumentStats;
  liveProcessing?: boolean;
}

const CARDS: Array<{
  key: keyof DocumentStats;
  label: string;
  color: string;
  icon: (live: boolean) => React.ReactNode;
}> = [
  { key: "total",      label: "Total",      color: "#22d3ee", icon: () => <FileText size={14} /> },
  { key: "parsed",     label: "Parsed",     color: "#3db886", icon: () => <CheckCircle2 size={14} /> },
  {
    key: "processing",
    label: "Processing",
    color: "#5FA8D3",
    icon: (live) => <Loader2 size={14} className={live ? "animate-spin" : ""} />,
  },
  { key: "uploaded",  label: "Uploaded",  color: "#c89a00", icon: () => <Clock size={14} /> },
  { key: "failed",    label: "Failed",    color: "#E45757", icon: () => <XCircle size={14} /> },
];

export function DocumentStatsCards({ stats, liveProcessing = false }: Props) {
  return (
    <motion.div variants={staggerChild} className="grid grid-cols-5 gap-3">
      {CARDS.map(({ key, label, color, icon }) => {
        const isProcessing = key === "processing";
        const value = stats[key];
        const live = isProcessing && liveProcessing && value > 0;
        return (
          <div
            key={key}
            className="relative rounded-2xl p-3.5 text-center card-shimmer-hover gradient-border-hover"
            style={{
              background: "var(--panel-bg)",
              backdropFilter: "blur(16px)",
              WebkitBackdropFilter: "blur(16px)",
              border: "1px solid var(--panel-border-accent)",
              boxShadow: "var(--panel-shadow)",
              transition: "box-shadow 0.25s ease, border-color 0.25s ease",
            }}
          >
            <div className="flex items-center justify-center mb-1.5" style={{ color }}>
              {icon(live)}
            </div>
            <p className="text-[20px] font-bold tabular leading-none" style={{ color }}>
              {value}
            </p>
            <p className="text-[10px] font-semibold mt-1.5" style={{ color: "var(--text-muted)" }}>
              {label}
            </p>
          </div>
        );
      })}
    </motion.div>
  );
}
