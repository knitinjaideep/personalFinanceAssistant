import { Sparkles, AlertTriangle, CheckCircle, Info } from "lucide-react";
import type { InvestmentInsight } from "../../lib/investmentsDashboard";

interface Props {
  insights: InvestmentInsight[];
}

function InsightIcon({ type }: { type: InvestmentInsight["type"] }) {
  if (type === "ok") return <CheckCircle size={13} color="#4CAF93" className="shrink-0 mt-0.5" />;
  if (type === "warn") return <AlertTriangle size={13} color="#FFD166" className="shrink-0 mt-0.5" />;
  return <Info size={13} color="#22d3ee" className="shrink-0 mt-0.5" />;
}

export function InvestmentInsights({ insights }: Props) {
  return (
    <div
      className="relative rounded-[20px] p-5 overflow-hidden"
      style={{
        background: "var(--panel-bg)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: "1px solid var(--panel-border)",
      }}
    >
      <span aria-hidden className="glitter-star" style={{ background: "rgba(34,211,238,0.85)" }} />
      <span aria-hidden className="glitter-star" style={{ background: "rgba(255,122,90,0.70)", top: "60%", left: "75%" }} />

      <div className="relative">
        <div className="flex items-center gap-2 mb-4">
          <div
            className="p-1.5 rounded-lg"
            style={{ background: "var(--insight-bg)", border: "1px solid var(--insight-border)" }}
          >
            <Sparkles size={13} style={{ color: "var(--border-accent)" }} />
          </div>
          <p className="coral-card-title" style={{ color: "var(--heading-primary)" }}>
            Coral Insight
          </p>
        </div>

        {insights.length === 0 ? (
          <p className="coral-muted" style={{ color: "var(--text-muted)" }}>
            Upload investment statements to see portfolio insights.
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
    </div>
  );
}
