import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import { dashboardApi } from "../api/dashboard";
import type { InvestmentsDashboard } from "../api/dashboard";
import { staggerChild, contentPageVariants } from "../design/motion";
import { CoralMascot } from "../components/CoralMascot";
import { CoralEmptyState } from "../components/CoralEmptyState";

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
      <div className="flex items-center gap-3">
        <CoralMascot variant="investments" size="sm" className="shrink-0" />
        <div>
          <h1 className="text-[18px] font-bold text-ocean-deep tracking-tight">Fees</h1>
          <p className="text-[12px] text-ocean/40 mt-0.5 font-medium">Investment management & advisory fees</p>
        </div>
      </div>
    </div>
  );
}

function GlassCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl p-5"
      style={{
        background: "rgba(255,255,255,0.82)",
        border: "1px solid rgba(205,237,246,0.65)",
        boxShadow: "0 4px 24px rgba(11,60,93,0.07), inset 0 1px 0 rgba(255,255,255,0.90)",
      }}>
      {children}
    </div>
  );
}

const tooltipStyle = {
  borderRadius: 10, fontSize: 12,
  background: "rgba(255,255,255,0.96)",
  border: "1px solid rgba(205,237,246,0.8)",
  boxShadow: "0 4px 16px rgba(11,60,93,0.10)",
};

export function FeesPage() {
  const [loading, setLoading] = useState(true);
  const [data, setData]       = useState<InvestmentsDashboard | null>(null);

  const fetch = useCallback(async () => {
    try { setData(await dashboardApi.investments()); }
    catch { /* backend not ready */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  const fees = data?.fees;
  const hasFees = !!fees && fees.by_category.length > 0;

  return (
    <div className="flex flex-col h-full">
      <PageHeader />
      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-5"
      >

        {loading ? (
          <div className="space-y-4">
            <div className="rounded-2xl h-24 animate-pulse" style={{ background: "rgba(205,237,246,0.20)" }} />
            <div className="rounded-2xl h-48 animate-pulse" style={{ background: "rgba(205,237,246,0.20)" }} />
          </div>
        ) : !hasFees ? (
          <motion.div variants={staggerChild}>
            <div className="rounded-2xl"
              style={{ background: "rgba(255,255,255,0.65)", border: "1px dashed rgba(205,237,246,0.70)" }}>
              <CoralEmptyState
                variant="investments"
                title="No fees found"
                description="Upload Morgan Stanley or E*TRADE statements. Fees are extracted from advisory fee, management fee, and expense ratio line items."
              />
            </div>
          </motion.div>
        ) : (
          <>
            {/* Total */}
            <motion.div variants={staggerChild}>
              <div className="rounded-2xl p-5 flex items-center justify-between"
                style={{ background: "rgba(255,122,90,0.07)", border: "1px solid rgba(255,122,90,0.18)" }}>
                <div>
                  <p className="text-[10px] font-semibold text-coral/60 uppercase tracking-widest">Total Fees</p>
                  <p className="text-[28px] font-bold text-coral tracking-tight mt-1">${fees!.total_fees_fmt}</p>
                </div>
                <p className="text-[11px] text-ocean/35 text-right">
                  {fees!.by_category.length} categor{fees!.by_category.length !== 1 ? "ies" : "y"}
                </p>
              </div>
            </motion.div>

            {/* Fee trend */}
            {fees!.recent_trend.length > 1 && (
              <motion.div variants={staggerChild}>
                <GlassCard>
                  <p className="text-[13px] font-semibold text-ocean-deep mb-1">Fee Trend</p>
                  <p className="text-[11px] text-ocean/40 mb-4">Last 6 months</p>
                  <ResponsiveContainer width="100%" height={120}>
                    <BarChart data={fees!.recent_trend} barSize={14}>
                      <XAxis dataKey="month" tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }} tickLine={false} axisLine={false} />
                      <YAxis tick={{ fontSize: 10, fill: "rgba(11,60,93,0.38)" }} tickLine={false} axisLine={false}
                        tickFormatter={(v) => `$${v.toFixed(0)}`} width={36} />
                      <Tooltip formatter={(v: number) => [`$${v.toLocaleString()}`, "Fees"]} contentStyle={tooltipStyle} />
                      <Bar dataKey="total" fill="#FF7A5A" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </GlassCard>
              </motion.div>
            )}

            {/* By category */}
            <motion.div variants={staggerChild}>
              <GlassCard>
                <p className="text-[13px] font-semibold text-ocean-deep mb-4">By Category</p>
                <div className="space-y-3">
                  {fees!.by_category.map((f, i) => {
                    const maxTotal = Math.max(...fees!.by_category.map(x => x.total));
                    const pct = maxTotal > 0 ? (f.total / maxTotal) * 100 : 0;
                    return (
                      <div key={i}>
                        <div className="flex items-center justify-between text-xs mb-1.5">
                          <span className="capitalize text-ocean-deep font-medium">{f.category}</span>
                          <div className="flex items-center gap-2">
                            <span className="text-ocean/38">×{f.count}</span>
                            <span className="font-semibold text-coral">${f.total_fmt}</span>
                          </div>
                        </div>
                        <div className="h-1.5 rounded-full overflow-hidden"
                          style={{ background: "rgba(205,237,246,0.50)" }}>
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${pct}%` }}
                            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: i * 0.06 }}
                            className="h-full rounded-full"
                            style={{ background: "linear-gradient(90deg, #FF7A5A, #FFA38F)" }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </GlassCard>
            </motion.div>
          </>
        )}

        <div className="h-3" />
      </motion.div>
    </div>
  );
}
