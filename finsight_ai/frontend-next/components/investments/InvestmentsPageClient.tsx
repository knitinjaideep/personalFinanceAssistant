"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  TrendingUp, TrendingDown, MessageSquare, Sparkles,
  Upload, BarChart2, Target,
} from "lucide-react";
import { motion } from "framer-motion";
import { investmentsApi, type InvestmentsDashboard } from "@/features/investments/api";
import { useAppStore } from "@/store/appStore";
import { formatCompactCurrency } from "@/lib/utils";
import MetricCard from "@/components/coral/MetricCard";
import GlassCard from "@/components/coral/GlassCard";
import SectionHeader from "@/components/coral/SectionHeader";
import EmptyState from "@/components/coral/EmptyState";
import LoadingState from "@/components/coral/LoadingState";
import ErrorState from "@/components/coral/ErrorState";

const INSIGHT_PROMPTS = [
  "How did my investments change this year?",
  "Summarize my Morgan Stanley statements.",
  "What is my down-payment savings progress?",
  "Compare my IRA balances over time.",
];

const KNOWN_ACCOUNTS = [
  { label: "Morgan Stanley Joint",   key: "morgan_stanley_joint",   icon: "MS" },
  { label: "Morgan Stanley Trad IRA",key: "morgan_stanley_trad_ira", icon: "IRA" },
  { label: "Morgan Stanley Roth IRA",key: "morgan_stanley_roth_ira", icon: "Roth" },
  { label: "E*TRADE",                key: "etrade",                  icon: "ET" },
  { label: "Empower 401k",           key: "empower",                 icon: "401k" },
  { label: "Down-Payment Savings",   key: "down_payment",            icon: "$" },
];

function AccountCard({
  label,
  icon,
  data,
}: {
  label: string;
  icon: string;
  data?: { total_value_fmt?: string; unrealized_gain_loss?: number; unrealized_gain_loss_fmt?: string; latest_statement_date?: string | null } | null;
}) {
  const hasData = !!data && !!data.total_value_fmt;
  const gainPositive = (data?.unrealized_gain_loss ?? 0) >= 0;

  return (
    <div
      className="flex items-center justify-between px-5 py-4 rounded-2xl transition-colors hover:bg-white/[0.02]"
      style={{ background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" }}
    >
      <div className="flex items-center gap-3">
        <div
          className="w-10 h-10 rounded-2xl flex items-center justify-center shrink-0"
          style={{
            background: "linear-gradient(135deg, rgba(34,211,238,0.12) 0%, rgba(31,111,139,0.08) 100%)",
            border: "1px solid rgba(34,211,238,0.15)",
            color: "rgba(34,211,238,0.85)",
            fontSize: "0.65rem",
            fontWeight: 700,
            letterSpacing: "0.02em",
          }}
        >
          {icon}
        </div>
        <div>
          <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>{label}</p>
          {data?.latest_statement_date && (
            <p className="micro-text mt-0.5" style={{ color: "var(--text-muted)" }}>
              {new Date(data.latest_statement_date).toLocaleDateString()}
            </p>
          )}
          {!hasData && (
            <p className="micro-text mt-0.5" style={{ color: "var(--text-dim)" }}>Waiting for data</p>
          )}
        </div>
      </div>

      {hasData ? (
        <div className="text-right">
          <p className="small-text font-bold tabular" style={{ color: "var(--text-primary)" }}>{data!.total_value_fmt}</p>
          {data?.unrealized_gain_loss_fmt && (
            <p className="micro-text tabular" style={{ color: gainPositive ? "#4CAF93" : "#E45757" }}>
              {gainPositive ? "↑" : "↓"} {data.unrealized_gain_loss_fmt}
            </p>
          )}
        </div>
      ) : (
        <span
          className="px-2.5 py-1 rounded-lg text-xs font-medium"
          style={{ background: "var(--empty-bg)", color: "var(--text-dim)", border: "1px solid var(--empty-border)" }}
        >
          No data
        </span>
      )}
    </div>
  );
}

export default function InvestmentsPageClient() {
  const [data, setData]     = useState<InvestmentsDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);
  const openUploadModal     = useAppStore((s) => s.openUploadModal);

  const load = () => {
    setLoading(true);
    setError(null);
    investmentsApi.investments()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  if (loading) return <LoadingState columns={4} rows={3} message="Loading your portfolio data…" />;
  if (error)   return <ErrorState message={error} onRetry={load} />;

  const { portfolio_summary, top_holdings, top_gainers, top_losers } = data!;
  const gainLossPositive = portfolio_summary.total_unrealized_gain_loss >= 0;
  const hasAnyData = portfolio_summary.accounts.length > 0 || top_holdings.length > 0;

  const accountMap: Record<string, typeof portfolio_summary.accounts[0]> = {};
  portfolio_summary.accounts.forEach((a) => {
    const key = (a.account_name ?? "").toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
    accountMap[key] = a;
  });

  const findAccount = (searchKeys: string[]) =>
    portfolio_summary.accounts.find((a) => {
      const name = (a.account_name ?? "").toLowerCase();
      return searchKeys.some((k) => name.includes(k));
    }) ?? null;

  return (
    <div className="space-y-8">

      {/* ── Header ──────────────────────────────────────────────────── */}
      <SectionHeader
        eyebrow="Portfolio"
        title="Investments"
        description="Review your long-term portfolio, retirement accounts, and down-payment savings from your statements."
        size="lg"
      />

      {/* ── Summary metrics ─────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.40, delay: 0.05 }}
        className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4"
      >
        {[
          {
            title: "Total Portfolio",
            value: portfolio_summary.total_portfolio_value > 0 ? formatCompactCurrency(portfolio_summary.total_portfolio_value) : null,
            fullValue: portfolio_summary.total_portfolio_value_fmt,
            icon: <BarChart2 size={16} style={{ color: "var(--accent-strong)" }} />,
            accent: "rgba(34,211,238,0.14)",
            emptyText: "Upload statements",
          },
          {
            title: "Unrealized G/L",
            value: portfolio_summary.total_unrealized_gain_loss !== 0 && portfolio_summary.total_portfolio_value > 0
              ? formatCompactCurrency(portfolio_summary.total_unrealized_gain_loss)
              : (portfolio_summary.total_portfolio_value > 0 ? portfolio_summary.total_unrealized_gain_loss_fmt : null),
            fullValue: portfolio_summary.total_unrealized_gain_loss_fmt,
            icon: gainLossPositive
              ? <TrendingUp size={16} style={{ color: "#4CAF93" }} />
              : <TrendingDown size={16} style={{ color: "#E45757" }} />,
            accent: gainLossPositive ? "rgba(76,175,147,0.14)" : "rgba(228,87,87,0.14)",
            status: gainLossPositive ? "positive" as const : "negative" as const,
            emptyText: "Upload statements",
          },
          {
            title: "Retirement",
            value: findAccount(["ira", "401k", "retirement"])?.total_value_fmt ?? null,
            icon: <Target size={16} style={{ color: "rgba(255,209,102,0.80)" }} />,
            accent: "rgba(255,209,102,0.14)",
            emptyText: "Upload IRA/401k statements",
          },
          {
            title: "Joint Investment",
            value: findAccount(["joint"])?.total_value_fmt ?? null,
            icon: <BarChart2 size={16} style={{ color: "rgba(95,168,211,0.80)" }} />,
            accent: "rgba(95,168,211,0.14)",
            emptyText: "Upload joint statements",
          },
          {
            title: "Accounts Tracked",
            value: portfolio_summary.accounts.length > 0 ? String(portfolio_summary.accounts.length) : null,
            icon: <TrendingUp size={16} style={{ color: "#4CAF93" }} />,
            accent: "rgba(76,175,147,0.14)",
            emptyText: "Upload statements",
          },
          {
            title: "Last Updated",
            value: portfolio_summary.last_updated
              ? new Date(portfolio_summary.last_updated).toLocaleDateString()
              : null,
            icon: <Target size={16} style={{ color: "var(--text-muted)" }} />,
            accent: "rgba(34,211,238,0.08)",
            emptyText: "Not yet",
          },
        ].map((m) => (
          <MetricCard key={m.title} {...m} size="sm" />
        ))}
      </motion.div>

      {/* ── Account sections ────────────────────────────────────────── */}
      {hasAnyData ? (
        <section>
          <SectionHeader eyebrow="Accounts" title="Investment Accounts" size="sm" className="mb-5" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[
              { label: "Morgan Stanley Joint",    icon: "MS",   keys: ["joint", "morgan"] },
              { label: "Traditional IRA",          icon: "IRA",  keys: ["traditional", "trad ira"] },
              { label: "Roth IRA",                icon: "Roth", keys: ["roth"] },
              { label: "E*TRADE",                 icon: "ET",   keys: ["etrade", "e*trade"] },
              { label: "Empower / 401k",          icon: "401k", keys: ["empower", "401k"] },
              { label: "Down-Payment Savings",    icon: "$",    keys: ["down", "savings", "529"] },
            ].map((acct) => (
              <AccountCard
                key={acct.label}
                label={acct.label}
                icon={acct.icon}
                data={findAccount(acct.keys)}
              />
            ))}
          </div>
        </section>
      ) : (
        <EmptyState
          icon={<TrendingUp size={28} />}
          title="No investment data yet"
          description="Upload statements from Morgan Stanley, E*TRADE, or other investment accounts to see your portfolio."
          action={
            <button type="button" onClick={openUploadModal} className="inline-flex items-center gap-2 px-6 py-3 rounded-2xl text-white font-semibold btn-coral">
              <Upload size={15} /> Upload statements
            </button>
          }
        />
      )}

      {/* ── Top holdings ────────────────────────────────────────────── */}
      {top_holdings.length > 0 && (
        <section>
          <SectionHeader eyebrow="Holdings" title="Top Holdings" size="sm" className="mb-5" />
          <GlassCard variant="default" className="!p-0 overflow-hidden">
            {top_holdings.slice(0, 10).map((h, i) => (
              <div
                key={i}
                className="flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-white/[0.02]"
                style={{ borderBottom: i < Math.min(top_holdings.length, 10) - 1 ? "1px solid var(--border-subtle)" : "none" }}
              >
                <span className="w-6 text-center micro-text font-bold" style={{ color: "var(--text-dim)" }}>{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <p className="small-text font-semibold truncate" style={{ color: "var(--text-primary)" }}>
                    {h.symbol || h.description.slice(0, 35)}
                  </p>
                  <p className="micro-text truncate" style={{ color: "var(--text-muted)" }}>{h.account_name}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className="small-text font-bold tabular" style={{ color: "var(--text-primary)" }}>{h.market_value_fmt}</p>
                  <p className="micro-text tabular" style={{ color: h.unrealized_gain_loss >= 0 ? "#4CAF93" : "#E45757" }}>
                    {h.unrealized_gain_loss >= 0 ? "↑" : "↓"} {h.unrealized_gain_loss_fmt}
                  </p>
                </div>
              </div>
            ))}
          </GlassCard>
        </section>
      )}

      {/* ── Gainers / Losers ────────────────────────────────────────── */}
      {(top_gainers.length > 0 || top_losers.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {top_gainers.length > 0 && (
            <section>
              <SectionHeader eyebrow="Performance" title="Top Gainers" size="sm" className="mb-4" />
              <div className="space-y-2">
                {top_gainers.slice(0, 5).map((h, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between px-4 py-3 rounded-2xl"
                    style={{ background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" }}
                  >
                    <p className="small-text font-medium truncate" style={{ color: "var(--text-primary)" }}>
                      {h.symbol || h.description.slice(0, 25)}
                    </p>
                    <p className="small-text font-bold tabular" style={{ color: "#4CAF93" }}>↑ {h.unrealized_gain_loss_fmt}</p>
                  </div>
                ))}
              </div>
            </section>
          )}
          {top_losers.length > 0 && (
            <section>
              <SectionHeader eyebrow="Performance" title="Needs Attention" size="sm" className="mb-4" />
              <div className="space-y-2">
                {top_losers.slice(0, 5).map((h, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between px-4 py-3 rounded-2xl"
                    style={{ background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" }}
                  >
                    <p className="small-text font-medium truncate" style={{ color: "var(--text-primary)" }}>
                      {h.symbol || h.description.slice(0, 25)}
                    </p>
                    <p className="small-text font-bold tabular" style={{ color: "#E45757" }}>↓ {h.unrealized_gain_loss_fmt}</p>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* ── Insight panel ───────────────────────────────────────────── */}
      <GlassCard variant="subtle" className="space-y-4">
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-2xl flex items-center justify-center"
            style={{ background: "rgba(255,122,90,0.15)", border: "1px solid rgba(255,122,90,0.25)" }}
          >
            <MessageSquare size={15} style={{ color: "#FF7A5A" }} />
          </div>
          <div>
            <p className="card-title-lg">Ask Coral about your investments</p>
            <p className="small-text mt-0.5" style={{ color: "var(--text-muted)" }}>Deep-dive into your portfolio</p>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {INSIGHT_PROMPTS.map((prompt) => (
            <Link
              key={prompt}
              href="/chat"
              className="flex items-center gap-2 px-4 py-3 rounded-2xl small-text font-medium transition-all hover:-translate-y-0.5"
              style={{
                background: "var(--insight-bg)",
                border: "1px solid var(--insight-border)",
                color: "var(--text-secondary)",
              }}
            >
              <Sparkles size={12} style={{ color: "rgba(255,122,90,0.70)" }} />
              {prompt}
            </Link>
          ))}
        </div>
      </GlassCard>

    </div>
  );
}
