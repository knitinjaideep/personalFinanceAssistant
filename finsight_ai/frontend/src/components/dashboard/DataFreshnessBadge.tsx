import { CheckCircle, AlertCircle, Clock } from "lucide-react";
import { getDataFreshnessStatus, formatDate } from "../../lib/dashboardData";

interface Props {
  label: string;
  latestDate: string | null | undefined;
  className?: string;
}

export function DataFreshnessBadge({ label, latestDate, className = "" }: Props) {
  const status = getDataFreshnessStatus(latestDate);

  if (status === "missing") {
    return (
      <div className={`flex items-center gap-1.5 text-[11px] ${className}`}>
        <AlertCircle size={12} color="#E45757" />
        <span style={{ color: "var(--text-muted)" }}>
          <span className="font-medium" style={{ color: "var(--text-secondary)" }}>{label}:</span>{" "}
          <span style={{ color: "#E45757" }}>Missing</span>
        </span>
      </div>
    );
  }

  if (status === "stale") {
    return (
      <div className={`flex items-center gap-1.5 text-[11px] ${className}`}>
        <Clock size={12} color="#FFD166" />
        <span style={{ color: "var(--text-muted)" }}>
          <span className="font-medium" style={{ color: "var(--text-secondary)" }}>{label}:</span>{" "}
          <span style={{ color: "#FFD166" }}>{formatDate(latestDate)}</span>
        </span>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-1.5 text-[11px] ${className}`}>
      <CheckCircle size={12} color="#4CAF93" />
      <span style={{ color: "var(--text-muted)" }}>
        <span className="font-medium" style={{ color: "var(--text-secondary)" }}>{label}:</span>{" "}
        <span style={{ color: "#4CAF93" }}>{formatDate(latestDate)}</span>
      </span>
    </div>
  );
}
