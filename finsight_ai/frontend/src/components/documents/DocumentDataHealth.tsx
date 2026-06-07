import { CheckCircle2, AlertTriangle, Landmark, Loader2 } from "lucide-react";
import type { LibraryHealthSummary } from "../../lib/documentLibrary";

interface Props {
  health: LibraryHealthSummary;
  loading?: boolean;
}

export function DocumentDataHealth({ health, loading }: Props) {
  const cards = [
    {
      icon: <CheckCircle2 size={15} />,
      label: "Parsed Statements",
      value: loading ? "—" : String(health.totalParsed),
      color: "#3db886",
      bg: "rgba(61,184,134,0.08)",
      border: "rgba(61,184,134,0.18)",
    },
    {
      icon: <AlertTriangle size={15} />,
      label: "Needs Review",
      value: loading ? "—" : health.needsReview > 0 ? String(health.needsReview) : "0",
      color: health.needsReview > 0 ? "#c89a00" : "#3db886",
      bg: health.needsReview > 0 ? "rgba(200,154,0,0.08)" : "rgba(61,184,134,0.06)",
      border: health.needsReview > 0 ? "rgba(200,154,0,0.18)" : "rgba(61,184,134,0.14)",
    },
    {
      icon: <Landmark size={15} />,
      label: "Institutions",
      value: loading ? "—" : String(health.institutionCount),
      color: "#22d3ee",
      bg: "rgba(34,211,238,0.07)",
      border: "rgba(34,211,238,0.16)",
    },
    {
      icon: <Loader2 size={15} className={health.processingCount > 0 ? "animate-spin" : ""} />,
      label: "Processing",
      value: loading ? "—" : String(health.processingCount),
      color: health.processingCount > 0 ? "#22d3ee" : "#94a3b8",
      bg: health.processingCount > 0 ? "rgba(34,211,238,0.07)" : "rgba(148,163,184,0.06)",
      border: health.processingCount > 0 ? "rgba(34,211,238,0.16)" : "rgba(148,163,184,0.12)",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-2xl px-4 py-3.5 flex items-center gap-3"
          style={{
            background: card.bg,
            border: `1px solid ${card.border}`,
            backdropFilter: "blur(12px)",
            WebkitBackdropFilter: "blur(12px)",
          }}
        >
          <span style={{ color: card.color }}>{card.icon}</span>
          <div className="min-w-0">
            <p
              className="text-[18px] font-bold tabular-nums leading-none"
              style={{ color: card.color }}
            >
              {card.value}
            </p>
            <p className="text-[10.5px] mt-0.5 font-medium" style={{ color: "var(--text-muted)" }}>
              {card.label}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
