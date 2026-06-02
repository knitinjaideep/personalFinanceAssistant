import { AlertCircle } from "lucide-react";
import { CashFlowChart } from "./CashFlowChart";
import type { SavingsAccountData } from "../../hooks/useBankingData";
import { fmtUSD } from "../../lib/financeDataAdapters";
import type { MonthLabel } from "../../lib/financeDataAdapters";

interface Props {
  data: SavingsAccountData;
  last6Months: MonthLabel[];
}

export function SavingsAccountPanel({ data, last6Months }: Props) {
  const { config, cardSummary, cashFlow, dataHealth } = data;
  const hasData = cashFlow.length > 0 && cashFlow.some((m) => m.inflow > 0 || m.outflow > 0);

  const chartData = last6Months.map((m) => {
    const row = cashFlow.find((c) => c.month.startsWith(m.key)) ?? { inflow: 0, outflow: 0 };
    return { month: m.label, inflow: row.inflow ?? 0, outflow: row.outflow ?? 0 };
  });

  // Compute summary from cash flow
  const totalInflow = cashFlow.reduce((s, m) => s + (m.inflow ?? 0), 0);
  const totalOutflow = cashFlow.reduce((s, m) => s + (m.outflow ?? 0), 0);
  const netSaved = totalInflow - totalOutflow;

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
          <p className="text-[11px] text-ocean/40 mt-0.5">High-yield savings</p>
        </div>
        {cardSummary && (
          <div className="text-right">
            <p className="text-[13px] font-bold" style={{ color: "#4CAF93" }}>
              {fmtUSD(cardSummary.total_spend)}
            </p>
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

      {/* Savings summary strip */}
      {(totalInflow > 0 || totalOutflow > 0) && (
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: "Deposited", value: fmtUSD(totalInflow), color: "#4CAF93" },
            { label: "Withdrawn", value: fmtUSD(totalOutflow), color: "#FF7A5A" },
            { label: "Net saved", value: fmtUSD(netSaved), color: netSaved >= 0 ? "#4CAF93" : "#E45757" },
          ].map(({ label, value, color }) => (
            <div
              key={label}
              className="rounded-lg p-2 text-center"
              style={{ background: "rgba(240,249,252,0.60)" }}
            >
              <p className="text-[10px] text-ocean/38 font-medium uppercase tracking-wide">{label}</p>
              <p className="text-[13px] font-bold mt-0.5 tabular" style={{ color }}>{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Cash flow chart */}
      <div>
        <p className="text-[11px] font-semibold text-ocean/50 uppercase tracking-wide mb-2">
          Deposits vs Withdrawals — Last 6 Months
        </p>
        <CashFlowChart
          data={chartData}
          height={150}
          emptyMessage="No Marcus savings data found yet. Upload Goldman Sachs statements."
        />
      </div>
    </div>
  );
}
