import { CheckCircle2, Loader2, Clock, XCircle, FileText } from "lucide-react";
import { motion } from "framer-motion";
import type { DocumentStats } from "../../types";
import { staggerChild } from "../../design/motion";

interface Props {
  stats: DocumentStats;
  /** When true, the Processing card shows a subtle live indicator. */
  liveProcessing?: boolean;
}

const CARDS: Array<{
  key: keyof DocumentStats;
  label: string;
  color: string;
  icon: (live: boolean) => React.ReactNode;
}> = [
  { key: "total", label: "Total", color: "#1F6F8B", icon: () => <FileText size={14} /> },
  { key: "parsed", label: "Parsed", color: "#4CAF93", icon: () => <CheckCircle2 size={14} /> },
  {
    key: "processing",
    label: "Processing",
    color: "#5FA8D3",
    icon: (live) => <Loader2 size={14} className={live ? "animate-spin" : ""} />,
  },
  { key: "uploaded", label: "Uploaded", color: "#c89a00", icon: () => <Clock size={14} /> },
  { key: "failed", label: "Failed", color: "#E45757", icon: () => <XCircle size={14} /> },
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
            className="rounded-2xl p-3.5 text-center"
            style={{
              background: "rgba(3,17,31,0.55)",
              backdropFilter: "blur(16px)",
              WebkitBackdropFilter: "blur(16px)",
              border: "1px solid rgba(34,211,238,0.12)",
              boxShadow: "0 4px 20px rgba(3,17,31,0.30)",
            }}
          >
            <div className="flex items-center justify-center mb-1" style={{ color }}>
              {icon(live)}
            </div>
            <p className="text-[20px] font-bold text-white tabular leading-none">{value}</p>
            <p className="text-[10px] font-medium mt-1" style={{ color: "rgba(255,255,255,0.40)" }}>{label}</p>
          </div>
        );
      })}
    </motion.div>
  );
}
