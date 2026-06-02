import { AlertCircle } from "lucide-react";
import { CashFlowChart } from "./CashFlowChart";
import type { CheckingAccountData } from "../../hooks/useBankingData";
import { fmtUSD } from "../../lib/financeDataAdapters";
import type { MonthLabel } from "../../lib/financeDataAdapters";

interface Props {
  data: CheckingAccountData;
  last6Months: MonthLabel[];
}

export function CheckingAccountPanel({ data, last6Months }: Props) {
  const { config, cardSummary, cashFlow, dataHealth } = data;
  const hasData = cashFlow.length > 0 && cashFlow.some((m) => m.inflow > 0 || m.outflow > 0);

  // Build chart data from last 6 months of global cash flow
  const chartData = last6Months.map((m) => {
    const row = cashFlow.find((c) => c.month.startsWith(m.key)) ?? { inflow: 0, outflow: 0 };
    return { month: m.label, inflow: row.inflow ?? 0, outflow: row.outflow ?? 0 };
  });

  const total = cardSummary?.total_spend ?? 0;

  return (
    <div
      className="rounded-xl p-4 space-y-4"
      style={{
        background: "rgba(255,255,255,0.70)",
        border: "1px solid rgba(205,237,246,0.55)",
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[14px] font-bold text-ocean-deep">{config.displayName}</p>
          {cardSummary && (
            <p className="text-[11px] text-ocean/40 mt-0.5">
              {cardSummary.transaction_count} transactions
            </p>
          )}
        </div>
        {total > 0 && (
          <div className="text-right">
            <p className="text-[13px] font-bold text-coral">{fmtUSD(total)}</p>
            <p className="text-[10px] text-ocean/35">total activity</p>
          </div>
        )}
      </div>

      {!hasData && dataHealth.warning && (
        <div
          className="rounded-lg px-3 py-2 flex items-start gap-2"
          style={{ background: "rgba(255,209,102,0.10)", border: "1px solid rgba(255,209,102,0.25)" }}
        >
          <AlertCircle size={13} style={{ color: "#c89a00" }} className="shrink-0 mt-0.5" />
          <p className="text-[11px] leading-relaxed" style={{ color: "#a07800" }}>
            {dataHealth.warning}
          </p>
        </div>
      )}

      {/* Cash flow chart */}
      <div>
        <p className="text-[11px] font-semibold text-ocean/50 uppercase tracking-wide mb-2">
          Inflow vs Outflow — Last 6 Months
        </p>
        <CashFlowChart
          data={chartData}
          height={150}
          emptyMessage={`No cash flow data for ${config.displayName}. Upload checking statements.`}
        />
      </div>
    </div>
  );
}
