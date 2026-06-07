import { TrendingUp, TrendingDown, Info, AlertTriangle, CheckCircle } from "lucide-react";
import type { BankingInsight } from "../../lib/bankingDashboard";

interface Props {
  insights: BankingInsight[];
}

function InsightIcon({ type }: { type: BankingInsight["type"] }) {
  if (type === "ok") return <CheckCircle size={13} color="#4CAF93" className="shrink-0 mt-0.5" />;
  if (type === "warn") return <AlertTriangle size={13} color="#FFD166" className="shrink-0 mt-0.5" />;
  return <Info size={13} color="#22d3ee" className="shrink-0 mt-0.5" />;
}

export function BankingInsights({ insights }: Props) {
  return (
    <div
      className="rounded-[20px] p-5"
      style={{
        background: "var(--panel-bg)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: "1px solid var(--panel-border)",
      }}
    >
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp size={15} style={{ color: "#22d3ee" }} />
        <p className="coral-card-title" style={{ color: "var(--text-primary)" }}>
          What changed
        </p>
      </div>

      {insights.length === 0 ? (
        <p className="coral-muted" style={{ color: "var(--text-muted)" }}>
          Coral needs more parsed statements to compare changes.
        </p>
      ) : (
        <div className="space-y-3">
          {insights.map((insight, i) => (
            <div key={i} className="flex items-start gap-2.5">
              <InsightIcon type={insight.type} />
              <p className="coral-table-text leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                {insight.text}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function BankingInsightsInline({ insights }: Props) {
  if (insights.length === 0) return null;
  const first = insights[0];
  const Icon = first.type === "ok" ? CheckCircle : first.type === "warn" ? TrendingDown : Info;
  const color = first.type === "ok" ? "#4CAF93" : first.type === "warn" ? "#FFD166" : "#22d3ee";
  return (
    <div
      className="rounded-2xl px-4 py-3 flex items-start gap-2"
      style={{
        background: `${color}08`,
        border: `1px solid ${color}25`,
      }}
    >
      <Icon size={14} color={color} className="shrink-0 mt-0.5" />
      <p className="coral-table-text leading-relaxed" style={{ color: "var(--text-secondary)" }}>
        {first.text}
      </p>
    </div>
  );
}
