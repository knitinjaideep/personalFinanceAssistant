import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { RefreshCw, CheckCircle2 } from "lucide-react";
import { dashboardApi } from "../api/dashboard";
import type { BankingDashboard, Subscription } from "../api/dashboard";
import { staggerContainer, staggerChild, contentPageVariants } from "../design/motion";

function PageHeader() {
  return (
    <div
      className="shrink-0 px-7 py-5"
      style={{
        borderBottom: "1px solid rgba(205,237,246,0.50)",
        background: "rgba(255,255,255,0.55)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      <h1 className="text-[18px] font-bold text-ocean-deep tracking-tight">Subscriptions</h1>
      <p className="text-[12px] text-ocean/40 mt-0.5 font-medium">Recurring charges detected across your statements</p>
    </div>
  );
}

function SubCard({ sub, index }: { sub: Subscription; index: number }) {
  const isHigh = sub.confidence === "high";
  return (
    <motion.div
      variants={staggerChild}
      className="flex items-center justify-between p-4 rounded-2xl"
      style={{
        background: "rgba(255,255,255,0.88)",
        border: "1px solid rgba(205,237,246,0.60)",
        boxShadow: "0 2px 12px rgba(11,60,93,0.05)",
      }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div
          className="w-8 h-8 rounded-xl flex items-center justify-center text-[12px] font-bold shrink-0"
          style={{ background: "rgba(255,122,90,0.10)", color: "#FF7A5A" }}
        >
          {index + 1}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <p className="text-[13px] font-semibold text-ocean-deep truncate">{sub.merchant}</p>
            {isHigh && (
              <span className="flex items-center gap-0.5 text-[9px] font-semibold px-1.5 py-0.5 rounded-full shrink-0"
                style={{ background: "rgba(76,175,147,0.12)", color: "#3a9c7a" }}>
                <CheckCircle2 size={8} />
                confirmed
              </span>
            )}
          </div>
          <p className="text-[10px] text-ocean/38 mt-0.5">
            {sub.category ? `${sub.category} · ` : ""}{sub.occurrences} months detected
            {sub.last_seen ? ` · last: ${sub.last_seen}` : ""}
          </p>
        </div>
      </div>
      <div className="text-right shrink-0 ml-4">
        <p className="text-[15px] font-bold text-coral">${sub.avg_monthly_amount_fmt}</p>
        <p className="text-[10px] text-ocean/35">per month</p>
      </div>
    </motion.div>
  );
}

export function SubscriptionsPage() {
  const [loading, setLoading] = useState(true);
  const [data, setData]       = useState<BankingDashboard | null>(null);

  const fetch = useCallback(async () => {
    try { setData(await dashboardApi.banking()); }
    catch { /* backend not ready */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  const subs = data?.subscriptions ?? [];
  const highConfidence = subs.filter(s => s.confidence === "high");
  const monthlyTotal = subs.reduce((t, s) => t + s.avg_monthly_amount, 0);

  return (
    <div className="flex flex-col h-full">
      <PageHeader />
      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-5"
      >

        {/* Summary strip */}
        {!loading && subs.length > 0 && (
          <motion.div variants={staggerChild}>
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: "Monthly Total", value: `$${monthlyTotal.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, color: "#CC5A40" },
                { label: "Annual Estimate", value: `$${(monthlyTotal * 12).toLocaleString("en-US", { maximumFractionDigits: 0 })}`, color: "#0B3C5D" },
                { label: "Confirmed", value: `${highConfidence.length} of ${subs.length}`, color: "#3a9c7a" },
              ].map(({ label, value, color }) => (
                <div key={label} className="rounded-2xl p-4 text-center"
                  style={{ background: "rgba(255,255,255,0.88)", border: "1px solid rgba(205,237,246,0.65)" }}>
                  <p className="text-[10px] font-semibold text-ocean/38 uppercase tracking-widest mb-1.5">{label}</p>
                  <p className="text-[17px] font-bold tracking-tight tabular" style={{ color }}>{value}</p>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="rounded-2xl h-16 animate-pulse"
                style={{ background: "rgba(205,237,246,0.20)" }} />
            ))}
          </div>
        ) : subs.length === 0 ? (
          <motion.div variants={staggerChild}>
            <div className="rounded-2xl px-6 py-12 text-center"
              style={{ background: "rgba(255,255,255,0.65)", border: "1px dashed rgba(205,237,246,0.70)" }}>
              <motion.div
                animate={{ rotate: [0, 360] }}
                transition={{ duration: 8, ease: "linear", repeat: Infinity }}
                className="inline-block mb-4"
              >
                <RefreshCw size={28} style={{ color: "rgba(11,60,93,0.18)" }} />
              </motion.div>
              <p className="text-[14px] font-semibold text-ocean-deep mb-1.5">No subscriptions detected yet</p>
              <p className="text-[12px] text-ocean/40 max-w-xs mx-auto leading-relaxed">
                Upload 2+ months of credit card statements. Coral detects merchants that charge you repeatedly at a consistent amount.
              </p>
            </div>
          </motion.div>
        ) : (
          <motion.div
            variants={staggerContainer}
            initial="hidden"
            animate="visible"
            className="space-y-2.5"
          >
            {/* Confirmed high-confidence first */}
            {highConfidence.length > 0 && (
              <>
                <p className="text-[10px] font-semibold text-ocean/35 uppercase tracking-widest px-1">
                  Confirmed recurring
                </p>
                {highConfidence.map((s, i) => (
                  <SubCard key={s.merchant} sub={s} index={i} />
                ))}
              </>
            )}

            {/* Medium confidence */}
            {subs.filter(s => s.confidence === "medium").length > 0 && (
              <>
                <p className="text-[10px] font-semibold text-ocean/35 uppercase tracking-widest px-1 mt-4">
                  Likely recurring
                </p>
                {subs.filter(s => s.confidence === "medium").map((s, i) => (
                  <SubCard key={s.merchant} sub={s} index={highConfidence.length + i} />
                ))}
              </>
            )}
          </motion.div>
        )}

        <div className="h-3" />
      </motion.div>
    </div>
  );
}
