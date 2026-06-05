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

  const chartData = last6Months.map((m) => {
    const row = cashFlow.find((c) => c.month.startsWith(m.key)) ?? { inflow: 0, outflow: 0 };
    return { month: m.label, inflow: row.inflow ?? 0, outflow: row.outflow ?? 0 };
  });

  const total = cardSummary?.total_spend ?? 0;

  return (
    <div
      className="rounded-2xl p-4 space-y-4"
      style={{
        background: "var(--row-bg)",
        border: "1px solid var(--row-border)",
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[14px] font-bold" style={{ color: "var(--text-primary)" }}>{config.displayName}</p>
          {cardSummary && (
            <p className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>
              {cardSummary.transaction_count} transactions
            </p>
          )}
        </div>
        {total > 0 && (
          <div className="text-right">
            <p className="text-[13px] font-bold" style={{ color: "#FF7A5A" }}>{fmtUSD(total)}</p>
            <p className="text-[10px]" style={{ color: "var(--text-dim)" }}>total activity</p>
          </div>
        )}
      </div>

      {!hasData && dataHealth.warning && (
        <div
          className="rounded-xl px-3 py-2 flex items-start gap-2"
          style={{ background: "var(--warn-bg)", border: "1px solid var(--warn-border)" }}
        >
          <AlertCircle size={13} style={{ color: "#FFD166" }} className="shrink-0 mt-0.5" />
          <p className="text-[11px] leading-relaxed" style={{ color: "var(--warn-text)" }}>
            {dataHealth.warning}
          </p>
        </div>
      )}

      {/* Cash flow chart */}
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--text-muted)" }}>
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
