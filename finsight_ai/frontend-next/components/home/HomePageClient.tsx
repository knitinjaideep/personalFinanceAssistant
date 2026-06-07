"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  MessageSquare, Upload, FileText, Landmark, TrendingUp,
  ArrowRight, Shield, RefreshCw, ChevronRight,
} from "lucide-react";
import { motion } from "framer-motion";
import MetricCard from "@/components/coral/MetricCard";
import GlassCard from "@/components/coral/GlassCard";
import SectionHeader from "@/components/coral/SectionHeader";
import { HomeHeroMascot } from "@/components/home/HomeHeroMascot";
import { documentsApi } from "@/features/documents/api";
import { useAppStore } from "@/store/appStore";
import type { DocumentStats, DocumentSummary } from "@/types/index";

const NEXT_TASKS = [
  {
    title: "Ask about last 6 months",
    description: "Get a summary of your spending patterns and biggest changes.",
    href: "/chat",
    icon: <MessageSquare size={18} />,
    accent: "rgba(255,122,90,0.25)",
  },
  {
    title: "Review unprocessed documents",
    description: "Check documents that failed parsing or need attention.",
    href: "/documents",
    icon: <FileText size={18} />,
    accent: "rgba(34,211,238,0.20)",
  },
  {
    title: "Check recurring transactions",
    description: "See your subscriptions and recurring charges across cards.",
    href: "/banking",
    icon: <Landmark size={18} />,
    accent: "rgba(95,168,211,0.22)",
  },
  {
    title: "Review investment changes",
    description: "Track portfolio movement from your latest statements.",
    href: "/investments",
    icon: <TrendingUp size={18} />,
    accent: "rgba(255,209,102,0.20)",
  },
  {
    title: "Upload missing statements",
    description: "Add statements from any institution to keep your data current.",
    href: null,
    icon: <Upload size={18} />,
    accent: "rgba(76,175,147,0.20)",
  },
];

const CONTAINER_ANIM = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};
const ITEM_ANIM = {
  hidden: { opacity: 0, y: 14 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.38, ease: "easeOut" as const } },
};

function RecentActivityRow({ doc }: { doc: DocumentSummary }) {
  const statusColor =
    doc.status === "parsed"      ? "#4CAF93"
    : doc.status === "processing" ? "rgba(34,211,238,0.85)"
    : doc.status === "failed"     ? "#E45757"
    : "var(--text-muted)";

  const statusLabel =
    doc.status === "parsed"      ? "Parsed"
    : doc.status === "processing" ? "Processing…"
    : doc.status === "failed"     ? "Failed"
    : "Uploaded";

  return (
    <div
      className="flex items-center gap-4 px-5 py-4 rounded-2xl transition-colors"
      style={{ background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" }}
    >
      <div
        className="w-9 h-9 rounded-2xl flex items-center justify-center shrink-0"
        style={{ background: "var(--glass-light-bg)", border: "1px solid var(--border-subtle)" }}
      >
        <FileText size={15} style={{ color: "var(--text-muted)" }} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="small-text font-semibold truncate" style={{ color: "var(--text-primary)" }}>
          {doc.filename}
        </p>
        <p className="micro-text mt-0.5 truncate" style={{ color: "var(--text-muted)" }}>
          {doc.institution} {doc.upload_time ? `· ${new Date(doc.upload_time).toLocaleDateString()}` : ""}
        </p>
      </div>
      <span
        className="status-badge shrink-0"
        style={{ color: statusColor, background: `${statusColor}18`, border: `1px solid ${statusColor}40` }}
      >
        {statusLabel}
      </span>
    </div>
  );
}

export default function HomePageClient() {
  const [stats, setStats]       = useState<DocumentStats | null>(null);
  const [recent, setRecent]     = useState<DocumentSummary[]>([]);
  const [loading, setLoading]   = useState(true);
  const openUploadModal         = useAppStore((s) => s.openUploadModal);

  useEffect(() => {
    Promise.all([
      documentsApi.stats().catch(() => null),
      documentsApi.list(5).catch(() => [] as DocumentSummary[]),
    ]).then(([s, docs]) => {
      setStats(s);
      const sorted = [...docs].sort(
        (a, b) => new Date(b.upload_time ?? 0).getTime() - new Date(a.upload_time ?? 0).getTime()
      );
      setRecent(sorted.slice(0, 5));
    }).finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-10">

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        className="pt-2"
      >
        <section className="grid items-center gap-0 lg:gap-4 lg:grid-cols-[1fr_1fr] max-w-[1200px]">
          {/* Left: text + CTA */}
          <div className="min-w-0">
            <p className="eyebrow-text mb-5" style={{ color: "var(--accent-strong)" }}>
              Your finance command center
            </p>
            <h1 className="page-hero-title mb-4 hero-shimmer-heading">
              Welcome back<br />to Coral
            </h1>
            <p className="body-text max-w-xl mb-8" style={{ color: "var(--text-secondary)" }}>
              Your financial documents, spending, investments, and insights are organized in one calm workspace.
              Everything stays on your device.
            </p>

            <div className="flex flex-wrap gap-3">
              <Link
                href="/chat"
                className="inline-flex items-center gap-2.5 px-7 py-3.5 rounded-2xl text-white font-semibold btn-coral transition-all"
                style={{ fontSize: "var(--font-body)" }}
              >
                <MessageSquare size={18} />
                Ask Coral
              </Link>
              <button
                type="button"
                onClick={openUploadModal}
                className="inline-flex items-center gap-2.5 px-7 py-3.5 rounded-2xl font-semibold btn-glass transition-all"
                style={{ fontSize: "var(--font-body)" }}
              >
                <Upload size={18} />
                Upload documents
              </button>
            </div>
          </div>

          {/* Right: hero mascot — hover reveals speech bubble, no card background */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
            className="hidden md:flex justify-center lg:justify-start"
          >
            <HomeHeroMascot />
          </motion.div>
        </section>
      </motion.div>

      {/* ── Data at a Glance ─────────────────────────────────────────────── */}
      <section>
        <SectionHeader
          eyebrow="Overview"
          title="Your Data at a Glance"
          description="A quick snapshot of what Coral has processed from your uploaded statements."
          className="mb-8"
        />

        <motion.div
          variants={CONTAINER_ANIM}
          initial="hidden"
          animate="show"
          className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4"
        >
          {[
            {
              title: "Total Documents",
              value: loading ? null : stats?.total ?? null,
              icon: <FileText size={16} style={{ color: "rgba(34,211,238,0.75)" }} />,
              accent: "rgba(34,211,238,0.14)",
            },
            {
              title: "Processed",
              value: loading ? null : stats?.parsed ?? null,
              icon: <FileText size={16} style={{ color: "#4CAF93" }} />,
              accent: "rgba(76,175,147,0.14)",
              status: "positive" as const,
            },
            {
              title: "Processing",
              value: loading ? null : stats?.processing ?? null,
              icon: <RefreshCw size={16} style={{ color: "rgba(255,209,102,0.85)" }} />,
              accent: "rgba(255,209,102,0.14)",
              status: "warning" as const,
            },
            {
              title: "Failed",
              value: loading ? null : stats?.failed ?? null,
              icon: <FileText size={16} style={{ color: "#E45757" }} />,
              accent: "rgba(228,87,87,0.14)",
              status: "negative" as const,
            },
            {
              title: "Banking Docs",
              value: loading ? null : null,
              icon: <Landmark size={16} style={{ color: "rgba(95,168,211,0.80)" }} />,
              accent: "rgba(95,168,211,0.14)",
              emptyText: "Upload to populate",
            },
            {
              title: "Investment Docs",
              value: loading ? null : null,
              icon: <TrendingUp size={16} style={{ color: "rgba(255,209,102,0.85)" }} />,
              accent: "rgba(255,209,102,0.14)",
              emptyText: "Upload to populate",
            },
          ].map((m, i) => (
            <motion.div key={m.title} variants={ITEM_ANIM}>
              <MetricCard
                title={m.title}
                value={m.value !== undefined ? (m.value !== null ? String(m.value) : null) : undefined}
                icon={m.icon}
                loading={loading && m.value === null}
                empty={!loading && m.value === null}
                emptyText={m.emptyText}
                status={m.status}
                accentColor={m.accent}
                size="sm"
              />
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ── Next Best Tasks + Recent Activity ───────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-8">

        {/* Next Best Tasks — 3 cols */}
        <section className="xl:col-span-3">
          <SectionHeader
            eyebrow="Recommended"
            title="Next Best Tasks"
            description="Smart suggestions based on your current data."
            className="mb-6"
          />

          <motion.div
            variants={CONTAINER_ANIM}
            initial="hidden"
            animate="show"
            className="space-y-3"
          >
            {NEXT_TASKS.map((task) => {
              const inner = (
                <>
                  <div
                    className="w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 transition-colors"
                    style={{
                      background: task.accent,
                      border: "1px solid var(--border-subtle)",
                      color: "var(--text-primary)",
                    }}
                  >
                    {task.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="small-text font-semibold" style={{ color: "var(--text-primary)" }}>{task.title}</p>
                    <p className="micro-text mt-0.5" style={{ color: "var(--text-muted)" }}>{task.description}</p>
                  </div>
                  <ChevronRight
                    size={16}
                    className="shrink-0 transition-transform group-hover:translate-x-1"
                    style={{ color: "var(--text-dim)" }}
                  />
                </>
              );
              const sharedClass = "flex items-center gap-4 px-5 py-4 rounded-2xl group transition-all duration-200 hover:-translate-y-0.5 w-full text-left";
              const sharedStyle = { background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" };

              return (
                <motion.div key={task.title} variants={ITEM_ANIM}>
                  {task.href === null ? (
                    <button type="button" onClick={openUploadModal} className={sharedClass} style={sharedStyle}>
                      {inner}
                    </button>
                  ) : (
                    <Link href={task.href} className={sharedClass} style={sharedStyle}>
                      {inner}
                    </Link>
                  )}
                </motion.div>
              );
            })}
          </motion.div>
        </section>

        {/* Recent Activity — 2 cols */}
        <section className="xl:col-span-2">
          <SectionHeader
            eyebrow="Activity"
            title="Recent Uploads"
            action={
              <Link href="/documents" className="flex items-center gap-1 text-sm font-semibold transition-opacity hover:opacity-70" style={{ color: "var(--accent-strong)" }}>
                View all <ArrowRight size={13} />
              </Link>
            }
            className="mb-6"
          />

          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="skeleton h-16 rounded-2xl" />
              ))}
            </div>
          ) : recent.length === 0 ? (
            <GlassCard variant="subtle" className="text-center py-10">
              <FileText size={28} className="mx-auto mb-3" style={{ color: "var(--empty-icon)" }} />
              <p className="small-text font-medium" style={{ color: "var(--text-secondary)" }}>No documents yet</p>
              <p className="micro-text mt-1" style={{ color: "var(--text-muted)" }}>Upload a statement to get started</p>
              <button type="button" onClick={openUploadModal} className="inline-flex items-center gap-1.5 mt-4 text-sm font-semibold" style={{ color: "rgba(255,122,90,0.85)" }}>
                Upload now <ArrowRight size={13} />
              </button>
            </GlassCard>
          ) : (
            <motion.div
              variants={CONTAINER_ANIM}
              initial="hidden"
              animate="show"
              className="space-y-3"
            >
              {recent.map((doc) => (
                <motion.div key={doc.id} variants={ITEM_ANIM}>
                  <RecentActivityRow doc={doc} />
                </motion.div>
              ))}
            </motion.div>
          )}
        </section>
      </div>

      {/* ── Privacy note ────────────────────────────────────────────────── */}
      <GlassCard variant="subtle" className="flex items-center gap-4 !py-4 !px-6">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0" style={{ background: "rgba(34,211,238,0.10)", border: "1px solid rgba(34,211,238,0.20)" }}>
          <Shield size={15} style={{ color: "rgba(34,211,238,0.75)" }} />
        </div>
        <p className="small-text" style={{ color: "var(--text-secondary)" }}>
          <strong style={{ color: "var(--text-primary)" }}>100% private.</strong>{" "}
          All data stays on your device. Coral uses Ollama locally — no cloud APIs, no data sharing.
        </p>
      </GlassCard>

    </div>
  );
}
