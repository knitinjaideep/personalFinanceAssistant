import { motion } from "framer-motion";
import { MessageSquare, Upload, ArrowRight, Sparkles, CheckCircle2, AlertCircle, Clock } from "lucide-react";
import { staggerChild, staggerContainer, contentPageVariants } from "../design/motion";
import { OverviewImageFeatureCards } from "../components/dashboard/OverviewImageFeatureCards";
import { HomeHeroMascot } from "../components/home/HomeHeroMascot";
import { useAppStore } from "../store/appStore";
import { useBankingData } from "../hooks/useBankingData";
import { useInvestmentData } from "../hooks/useInvestmentData";

// ── Open hero — no card, content floats over the page background ──────────────

function OpenHero() {
  const setActivePage = useAppStore((s) => s.setActivePage);

  return (
    <motion.div variants={staggerChild}>
      <section
        className="relative overflow-visible"
        style={{ background: "transparent" }}
      >
        {/* Left-side text vignette — improves readability without boxing the hero */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse at 18% 50%, rgba(3,17,31,0.72) 0%, rgba(3,17,31,0.32) 44%, transparent 70%)",
          }}
        />
        {/* No bottom-fade overlay here — avoids a hard seam against the feature cards */}

        {/* Content grid */}
        <div className="relative z-10 mx-auto grid min-h-[560px] max-w-7xl grid-cols-1 items-center gap-8 px-6 pt-12 pb-4 lg:grid-cols-[0.46fr_0.54fr] lg:gap-4 lg:px-10 xl:min-h-[620px]">

          {/* ── Left — text ──────────────────────────────────────────────── */}
          <div className="relative z-20 flex max-w-xl flex-col items-start">

            {/* Welcome pill */}
            <div
              className="mb-6 inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold"
              style={{
                background: "rgba(34,211,238,0.10)",
                border: "1px solid rgba(34,211,238,0.25)",
                color: "rgba(186,230,255,0.90)",
                backdropFilter: "blur(12px)",
                WebkitBackdropFilter: "blur(12px)",
                boxShadow: "0 0 30px rgba(34,211,238,0.08)",
              }}
            >
              <Sparkles size={12} style={{ color: "rgba(34,211,238,0.90)" }} />
              Welcome to Coral
            </div>

            <h1
              className="text-5xl font-bold tracking-tight text-white xl:text-6xl"
              style={{
                lineHeight: 1.08,
                textShadow: "0 2px 20px rgba(3,17,31,0.80)",
              }}
            >
              Hi, I'm Coral <span className="inline-block">👋</span>
            </h1>

            <p
              className="mt-5 text-xl font-semibold"
              style={{ color: "rgba(34,211,238,0.85)" }}
            >
              Your local financial intelligence hub.
            </p>

            <p
              className="mt-5 max-w-lg text-[15px] leading-relaxed"
              style={{ color: "rgba(255,255,255,0.62)" }}
            >
              Everything you need to understand your finances, all in one place.
              100% private — no cloud, no sharing, ever.
            </p>

            {/* CTA buttons */}
            <div className="mt-9 flex flex-col gap-4 sm:flex-row">
              <button
                type="button"
                onClick={() => setActivePage("chat")}
                className="flex items-center gap-2 rounded-2xl px-6 py-3 text-[13px] font-semibold text-white transition-all hover:scale-[1.03] active:scale-[0.97]"
                style={{
                  background: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
                  boxShadow: "0 6px 28px rgba(255,122,90,0.45)",
                }}
              >
                <MessageSquare size={14} />
                Ask Coral
              </button>
              <button
                type="button"
                onClick={() => setActivePage("documents")}
                className="flex items-center gap-2 rounded-2xl px-6 py-3 text-[13px] font-semibold transition-all hover:scale-[1.03] active:scale-[0.97]"
                style={{
                  background: "rgba(255,255,255,0.08)",
                  backdropFilter: "blur(8px)",
                  WebkitBackdropFilter: "blur(8px)",
                  border: "1px solid rgba(255,255,255,0.18)",
                  color: "rgba(255,255,255,0.85)",
                }}
              >
                <Upload size={14} />
                Upload Documents
              </button>
            </div>

            {/* Privacy line */}
            <div
              className="mt-7 flex items-center gap-2 text-[12px] font-semibold tracking-wide"
              style={{ color: "rgba(110,231,183,0.80)" }}
            >
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{
                  background: "#6ee7b7",
                  boxShadow: "0 0 18px rgba(110,231,183,0.80)",
                }}
              />
              Private • Local • Secure
            </div>
          </div>

          {/* ── Right — glass bubble mascot ──────────────────────────────── */}
          <div className="relative z-10 flex items-center justify-center lg:-ml-8 xl:-ml-14">
            <HomeHeroMascot />
          </div>
        </div>
      </section>
    </motion.div>
  );
}

// ── Next best actions ─────────────────────────────────────────────────────────

const NEXT_ACTIONS = [
  {
    title: "Upload or reprocess recent statements",
    description: "Keep your data up to date",
    page: "documents" as const,
  },
  {
    title: "Review your latest spending insights",
    description: "See where your money goes",
    page: "banking" as const,
  },
  {
    title: "Ask Coral a question",
    description: "Get clarity on anything",
    page: "chat" as const,
  },
];

function NextBestActions() {
  const setActivePage = useAppStore((s) => s.setActivePage);

  return (
    <motion.div variants={staggerChild} className="h-full">
      <motion.div
        className="group relative h-full min-h-[280px] rounded-[28px] p-6 lg:p-7"
        style={{
          background: "var(--panel-bg)",
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          border: "1px solid var(--panel-border-accent)",
          boxShadow: "var(--panel-shadow)",
          animation: "coralFeatureFloat 5.2s ease-in-out infinite",
          animationDelay: "0ms",
        }}
        whileHover={{ scale: 1.025, y: -5, transition: { type: "spring", stiffness: 280, damping: 22 } }}
        whileTap={{ scale: 0.98, transition: { duration: 0.12 } }}
      >
        {/* Hover glow ring */}
        <div
          className="absolute inset-0 rounded-[28px] pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-300"
          style={{ boxShadow: "inset 0 0 0 1.5px rgba(255,255,255,0.12), 0 0 50px rgba(95,168,211,0.15)" }}
        />

        <h2 className="relative flex items-center gap-1.5 text-[13px] font-bold mb-4" style={{ color: "var(--text-primary)" }}>
          <Sparkles size={13} style={{ color: "rgba(255,122,90,0.85)" }} />
          ✦ Next best actions
        </h2>
        <div className="relative space-y-3">
          {NEXT_ACTIONS.map((action) => (
            <button
              key={action.title}
              type="button"
              onClick={() => setActivePage(action.page)}
              className="w-full flex items-center justify-between rounded-2xl text-left transition-all hover:scale-[1.01] group/row"
              style={{
                background: "var(--row-bg)",
                border: "1px solid var(--row-border-strong)",
                backdropFilter: "blur(2px)",
                WebkitBackdropFilter: "blur(2px)",
                padding: "13px 16px",
              }}
            >
              <div>
                <p className="text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>
                  {action.title}
                </p>
                <p className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {action.description}
                </p>
              </div>
              <ArrowRight
                size={14}
                className="shrink-0 ml-3 transition-transform duration-200 group-hover/row:translate-x-1"
                style={{ color: "rgba(34,211,238,0.70)" }}
              />
            </button>
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Data at a glance ──────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: "ok" | "missing" | "loading" }) {
  if (status === "loading") {
    return (
      <span className="flex items-center gap-1 text-[11px] font-semibold" style={{ color: "var(--text-muted)" }}>
        <Clock size={10} />
        Loading…
      </span>
    );
  }
  if (status === "ok") {
    return (
      <span className="flex items-center gap-1.5 text-[11px] font-semibold" style={{ color: "#4CAF93" }}>
        <CheckCircle2 size={10} />
        Up to date
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-[11px] font-semibold" style={{ color: "rgba(255,122,90,0.80)" }}>
      <AlertCircle size={10} />
      Needs data
    </span>
  );
}

function DataAtAGlance() {
  const { loading: bankLoading, raw: bankRaw } = useBankingData();
  const { loading: invLoading, hasData: invHasData } = useInvestmentData();

  const bankStatus = bankLoading ? "loading" : bankRaw ? "ok" : "missing";
  const invStatus = invLoading ? "loading" : invHasData ? "ok" : "missing";

  const rows = [
    { label: "Banking", status: bankStatus as "ok" | "missing" | "loading" },
    { label: "Investments", status: invStatus as "ok" | "missing" | "loading" },
    { label: "Documents", status: (bankRaw || invHasData) ? "ok" as const : "missing" as const },
  ];

  return (
    <motion.div variants={staggerChild} className="h-full">
      <motion.div
        className="group relative h-full min-h-[280px] rounded-[28px] p-6 lg:p-7"
        style={{
          background: "var(--panel-bg)",
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          border: "1px solid var(--panel-border-accent)",
          boxShadow: "var(--panel-shadow)",
          animation: "coralFeatureFloat 5.2s ease-in-out infinite",
          animationDelay: "400ms",
        }}
        whileHover={{ scale: 1.025, y: -5, transition: { type: "spring", stiffness: 280, damping: 22 } }}
        whileTap={{ scale: 0.98, transition: { duration: 0.12 } }}
      >
        {/* Hover glow ring */}
        <div
          className="absolute inset-0 rounded-[28px] pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-300"
          style={{ boxShadow: "inset 0 0 0 1.5px rgba(255,255,255,0.12), 0 0 50px rgba(95,168,211,0.15)" }}
        />

        <h2 className="relative text-[13px] font-bold mb-4" style={{ color: "var(--text-primary)" }}>Your data at a glance</h2>
        <div className="relative space-y-4">
          {rows.map((row) => (
            <div
              key={row.label}
              className="flex items-center justify-between rounded-2xl"
              style={{
                background: "var(--row-bg)",
                border: "1px solid var(--row-border-strong)",
                backdropFilter: "blur(2px)",
                WebkitBackdropFilter: "blur(2px)",
                padding: "13px 16px",
              }}
            >
              <span className="text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>
                {row.label}
              </span>
              <StatusBadge status={row.status} />
            </div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function OverviewPage() {
  return (
    <div className="relative flex flex-col min-h-full" style={{ background: "transparent" }}>
      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto"
        style={{ background: "transparent" }}
      >
        {/* Open hero — no wrapper div, section has its own px */}
        <OpenHero />

        {/* Four feature cards */}
        <motion.div variants={staggerChild} className="px-7">
          <OverviewImageFeatureCards />
        </motion.div>

        {/* Bottom row: next actions + data glance — each panel is fully independent */}
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-1 lg:grid-cols-2 gap-6 px-7 mt-6 pb-28 lg:pb-16 items-stretch"
        >
          <NextBestActions />
          <DataAtAGlance />
        </motion.div>
      </motion.div>
    </div>
  );
}
