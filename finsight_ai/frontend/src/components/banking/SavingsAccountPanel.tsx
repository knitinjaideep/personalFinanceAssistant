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

  const totalInflow = cashFlow.reduce((s, m) => s + (m.inflow ?? 0), 0);
  const totalOutflow = cashFlow.reduce((s, m) => s + (m.outflow ?? 0), 0);
  const netSaved = totalInflow - totalOutflow;

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
          <p className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>High-yield savings</p>
        </div>
        {cardSummary && (
          <div className="text-right">
            <p className="text-[13px] font-bold" style={{ color: "#4CAF93" }}>
              {fmtUSD(cardSummary.total_spend)}
            </p>
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
              className="rounded-xl p-2 text-center"
              style={{ background: "var(--insight-bg)", border: "1px solid var(--panel-border)" }}
            >
              <p className="text-[10px] font-medium uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>{label}</p>
              <p className="text-[13px] font-bold mt-0.5 tabular" style={{ color }}>{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Cash flow chart */}
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--text-muted)" }}>
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
