import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, Calendar, AlertCircle, CheckCircle } from "lucide-react";
import { MonthlySpendChart } from "./MonthlySpendChart";
import { RecurringTransactionsTable } from "./RecurringTransactionsTable";
import type { CreditCardData } from "../../hooks/useBankingData";
import type { Subscription } from "../../api/dashboard";
import { calculateMonthlySpend } from "../../lib/financeDataAdapters";
import type { MonthLabel } from "../../lib/financeDataAdapters";

interface Props {
  data: CreditCardData;
  subscriptions: Subscription[];
  last6Months: MonthLabel[];
}

function DataHealthBadge({ warning, latestDate }: { warning: string | null; latestDate: string | null }) {
  if (warning) {
    return (
      <div className="flex items-center gap-1.5 text-[10px]" style={{ color: "#c89a00" }}>
        <AlertCircle size={11} />
        <span className="hidden sm:inline">{latestDate ? `Latest: ${latestDate}` : "No data"}</span>
      </div>
    );
  }
  if (latestDate) {
    return (
      <div className="flex items-center gap-1.5 text-[10px]" style={{ color: "#4CAF93" }}>
        <CheckCircle size={11} />
        <span className="hidden sm:inline">Latest: {latestDate}</span>
      </div>
    );
  }
  return null;
}

export function CreditCardAccountPanel({ data, subscriptions, last6Months }: Props) {
  const [expanded, setExpanded] = useState(false);

  const { config, cardSummary, dataHealth } = data;

  // Build 6-month spend from the card summary total (backend doesn't return per-month per-card)
  // We use the aggregated total as a single last-month placeholder, or zero-fill
  const monthlySpend = calculateMonthlySpend([], last6Months);

  // If we have card-level total, put it in the most recent month as an approximation
  if (cardSummary?.total_spend && monthlySpend.length > 0) {
    monthlySpend[monthlySpend.length - 1].spend = Math.round(cardSummary.total_spend);
  }

  const hasAnyData = !!cardSummary;

  const institutionColors: Record<string, string> = {
    chase: "#1F6F8B",
    amex: "#0B3C5D",
    macys: "#FF7A5A",
  };
  const accentColor = institutionColors[config.institutionKey] ?? "#5FA8D3";

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{
        background: "rgba(3,17,31,0.50)",
        border: "1px solid rgba(34,211,238,0.10)",
      }}
    >
      {/* Card header */}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
        aria-expanded={expanded}
      >
        {/* Institution badge */}
        <div
          className="shrink-0 px-2 py-1 rounded-lg text-[9px] font-bold uppercase tracking-wide text-white"
          style={{ background: accentColor }}
        >
          {config.institution.split(" ")[0]}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-semibold text-white leading-tight truncate">
            {config.displayName}
          </p>
          {cardSummary && (
            <p className="text-[10px] mt-0.5" style={{ color: "rgba(255,255,255,0.38)" }}>
              {cardSummary.transaction_count} transactions · ${cardSummary.total_spend_fmt}
            </p>
          )}
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <DataHealthBadge warning={dataHealth.warning} latestDate={dataHealth.latestStatementDate} />
          <motion.div
            animate={{ rotate: expanded ? 0 : -90 }}
            transition={{ duration: 0.2 }}
          >
            <ChevronDown size={14} style={{ color: "rgba(255,255,255,0.35)" }} />
          </motion.div>
        </div>
      </button>

      {/* Expanded content */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: [0.4, 0, 0.2, 1] }}
            style={{ overflow: "hidden" }}
          >
            <div
              className="px-4 pb-4 space-y-4"
              style={{ borderTop: "1px solid rgba(34,211,238,0.10)" }}
            >
              {/* Payment due date */}
              <div className="flex items-center gap-1.5 pt-3">
                <Calendar size={11} style={{ color: "rgba(255,255,255,0.28)" }} />
                <span className="text-[11px]" style={{ color: "rgba(255,255,255,0.40)" }}>
                  Payment due:{" "}
                  <span className="font-medium text-white/70">
                    {cardSummary?.latest_statement ?? "Not available"}
                  </span>
                </span>
              </div>

              {!hasAnyData && (
                <div
                  className="rounded-xl px-3 py-3 flex items-start gap-2"
                  style={{ background: "rgba(255,209,102,0.08)", border: "1px solid rgba(255,209,102,0.20)" }}
                >
                  <AlertCircle size={13} style={{ color: "#FFD166" }} className="shrink-0 mt-0.5" />
                  <p className="text-[11px] leading-relaxed" style={{ color: "rgba(255,209,102,0.80)" }}>
                    {dataHealth.warning ?? "No data found for this card. Upload or reprocess statements."}
                  </p>
                </div>
              )}

              {/* 6-month spend chart */}
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide mb-2" style={{ color: "rgba(255,255,255,0.38)" }}>
                  6-Month Spend
                </p>
                <MonthlySpendChart
                  data={monthlySpend}
                  height={140}
                  emptyMessage={`No spending data yet for ${config.displayName}. Reprocess statements.`}
                />
              </div>

              {/* Recurring subscriptions */}
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide mb-2" style={{ color: "rgba(255,255,255,0.38)" }}>
                  Recurring Charges
                </p>
                <RecurringTransactionsTable
                  apiSubscriptions={subscriptions}
                  detected={data.recurringTransactions}
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
