import { Activity, TrendingUp, TrendingDown } from "lucide-react";
import { SectionCard } from "../dashboard/SectionCard";
import { DashboardEmptyState } from "../dashboard/DashboardEmptyState";
import type { InvestmentActivityItem } from "../../lib/investmentsDashboard";
import { safeArray, formatCurrency } from "../../lib/dashboardData";

interface Props {
  activity: InvestmentActivityItem[];
  onDocuments?: () => void;
}

export function InvestmentActivityTab({ activity, onDocuments }: Props) {
  const items = safeArray(activity);

  if (items.length === 0) {
    return (
      <DashboardEmptyState
        icon={<Activity size={22} />}
        title="No activity data"
        description="Investment activity will appear after Coral extracts transactions from statements."
        primaryAction={onDocuments ? { label: "View Documents", onClick: onDocuments } : undefined}
      />
    );
  }

  const gainers = items.filter((i) => i.isPositive);
  const losers = items.filter((i) => !i.isPositive);

  return (
    <div className="space-y-4">
      {gainers.length > 0 && (
        <SectionCard title="Top Gainers" subtitle="Unrealized gains by position">
          <div className="space-y-2">
            {gainers.map((item, i) => (
              <div key={i} className="flex items-center justify-between py-1.5">
                <div className="flex items-center gap-2.5 min-w-0">
                  <TrendingUp size={13} color="#4CAF93" className="shrink-0" />
                  <div className="min-w-0">
                    <p className="text-[13px] font-semibold truncate" style={{ color: "var(--text-primary)" }}>
                      {item.description}
                    </p>
                    <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>{item.account}</p>
                  </div>
                </div>
                <span className="text-[13px] font-semibold ml-3 shrink-0" style={{ color: "#4CAF93" }}>
                  +{formatCurrency(item.amount)}
                </span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {losers.length > 0 && (
        <SectionCard title="Top Losers" subtitle="Unrealized losses by position">
          <div className="space-y-2">
            {losers.map((item, i) => (
              <div key={i} className="flex items-center justify-between py-1.5">
                <div className="flex items-center gap-2.5 min-w-0">
                  <TrendingDown size={13} color="#E45757" className="shrink-0" />
                  <div className="min-w-0">
                    <p className="text-[13px] font-semibold truncate" style={{ color: "var(--text-primary)" }}>
                      {item.description}
                    </p>
                    <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>{item.account}</p>
                  </div>
                </div>
                <span className="text-[13px] font-semibold ml-3 shrink-0" style={{ color: "#E45757" }}>
                  {formatCurrency(item.amount)}
                </span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  );
}
