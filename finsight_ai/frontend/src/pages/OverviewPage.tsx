import { motion } from "framer-motion";
import {
  MessageSquare, Upload, ArrowRight, Sparkles,
  CheckCircle2, AlertCircle, Clock, Database, TrendingUp, FileText,
} from "lucide-react";
import { staggerChild, staggerContainer, contentPageVariants } from "../design/motion";
import { OverviewImageFeatureCards } from "../components/dashboard/OverviewImageFeatureCards";
import { HomeHeroMascot } from "../components/home/HomeHeroMascot";
import { useAppStore } from "../store/appStore";
import { useBankingData } from "../hooks/useBankingData";
import { useInvestmentData } from "../hooks/useInvestmentData";

// Theme-aware helper — hero text sits over the background photo so we
// use a vignette overlay in dark mode. In light mode the background is
// bright so we flip all hard-coded rgba(255,255,255,…) to navy values.
function useHeroColors() {
  const theme = useAppStore((s) => s.theme);
  const dark = theme !== "light";
  return {
    dark,
    heading:    dark ? "rgba(248,252,255,0.97)" : "rgba(7,31,51,0.97)",
    tagline:    dark ? "rgba(34,211,238,0.90)"  : "rgba(14,90,120,0.92)",
    body:       dark ? "rgba(220,242,250,0.80)" : "rgba(14,55,82,0.82)",
    pillBg:     dark ? "rgba(34,211,238,0.10)"  : "rgba(31,111,139,0.12)",
    pillBorder: dark ? "rgba(34,211,238,0.28)"  : "rgba(31,111,139,0.32)",
    pillText:   dark ? "rgba(186,230,255,0.92)" : "rgba(7,50,80,0.90)",
    pillIcon:   dark ? "rgba(34,211,238,0.92)"  : "rgba(31,111,139,0.85)",
    glassBtn:   dark ? "rgba(255,255,255,0.08)" : "rgba(255,255,255,0.78)",
    glassBtnBorder: dark ? "rgba(255,255,255,0.18)" : "rgba(31,111,139,0.28)",
    glassBtnText:   dark ? "rgba(255,255,255,0.88)" : "rgba(7,31,51,0.88)",
    privacy:    dark ? "rgba(110,231,183,0.85)"  : "rgba(14,110,75,0.88)",
    vignette:   dark
      ? "radial-gradient(ellipse at 18% 50%, rgba(3,17,31,0.75) 0%, rgba(3,17,31,0.30) 44%, transparent 70%)"
      : "radial-gradient(ellipse at 18% 50%, rgba(244,251,255,0.65) 0%, rgba(244,251,255,0.25) 44%, transparent 70%)",
  };
}

// ── Open hero — no card, content floats over the page background ──────────────

function OpenHero() {
  const setActivePage = useAppStore((s) => s.setActivePage);
  const c = useHeroColors();

  return (
    <motion.div variants={staggerChild}>
      <section className="relative overflow-visible" style={{ background: "transparent" }}>
        {/* Readability vignette — adapts to dark/light */}
        <div aria-hidden className="pointer-events-none absolute inset-0" style={{ background: c.vignette }} />

        {/* Content grid */}
        <div className="relative z-10 mx-auto grid min-h-[580px] max-w-7xl grid-cols-1 items-center gap-8 px-6 pt-12 pb-4 lg:grid-cols-[0.46fr_0.54fr] lg:gap-4 lg:px-10 xl:min-h-[640px]">

          {/* ── Left — text ──────────────────────────────────────────────── */}
          <div className="relative z-20 flex max-w-xl flex-col items-start">

            {/* Welcome pill — metallic shimmer */}
            <div
              className="mb-7 shimmer-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold"
              style={{
                background: c.pillBg,
                border: `1px solid ${c.pillBorder}`,
                color: c.pillText,
                backdropFilter: "blur(12px)",
                WebkitBackdropFilter: "blur(12px)",
              }}
            >
              <Sparkles size={13} style={{ color: c.pillIcon }} aria-hidden />
              Welcome to Coral
            </div>

            {/* Main heading — shimmer class applied */}
            <h1
              className="heading-coral text-5xl xl:text-6xl hero-shimmer-heading"
              style={{ color: c.heading, textShadow: c.dark ? "0 2px 24px rgba(3,17,31,0.80)" : "0 1px 12px rgba(244,251,255,0.60)" }}
            >
              Hi, I'm Coral <span className="inline-block">👋</span>
            </h1>

            <p className="mt-5 text-xl font-semibold tracking-tight" style={{ color: c.tagline }}>
              Your local financial intelligence hub.
            </p>

            <p className="mt-4 max-w-lg text-[15px] leading-relaxed" style={{ color: c.body }}>
              Everything you need to understand your finances, all in one place.
              100% private — no cloud, no sharing, ever.
            </p>

            {/* CTA buttons */}
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                onClick={() => setActivePage("chat")}
                aria-label="Open Coral chat"
                className="btn-coral btn-coral-breathe flex items-center gap-2.5 rounded-2xl px-6 py-3.5 text-sm font-semibold text-white"
              >
                <MessageSquare size={15} aria-hidden />
                Ask Coral
              </button>
              <button
                type="button"
                onClick={() => setActivePage("documents")}
                aria-label="Upload financial documents"
                className="flex items-center gap-2.5 rounded-2xl px-6 py-3.5 text-sm font-semibold transition-all hover:scale-[1.03] active:scale-[0.97]"
                style={{
                  background: c.glassBtn,
                  backdropFilter: "blur(10px)",
                  WebkitBackdropFilter: "blur(10px)",
                  border: `1px solid ${c.glassBtnBorder}`,
                  color: c.glassBtnText,
                }}
              >
                <Upload size={15} aria-hidden />
                Upload Documents
              </button>
            </div>

            {/* Privacy line */}
            <div
              className="mt-7 flex items-center gap-2 text-[12px] font-semibold tracking-widest uppercase"
              style={{ color: c.privacy }}
            >
              <span aria-hidden className="inline-block h-2 w-2 rounded-full"
                style={{ background: "currentColor", boxShadow: "0 0 10px currentColor" }} />
              Private · Local · Secure
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
    description: "Keep your data fresh and up to date",
    page: "documents" as const,
    icon: FileText,
    accent: "rgba(34,211,238,0.85)",
    iconBg: "rgba(34,211,238,0.10)",
    iconBorder: "rgba(34,211,238,0.20)",
  },
  {
    title: "Review your latest spending insights",
    description: "See exactly where your money goes",
    page: "banking" as const,
    icon: TrendingUp,
    accent: "rgba(255,122,90,0.90)",
    iconBg: "rgba(255,122,90,0.10)",
    iconBorder: "rgba(255,122,90,0.20)",
  },
  {
    title: "Ask Coral a question",
    description: "Get instant clarity on any financial topic",
    page: "chat" as const,
    icon: MessageSquare,
    accent: "rgba(61,184,134,0.90)",
    iconBg: "rgba(61,184,134,0.10)",
    iconBorder: "rgba(61,184,134,0.20)",
  },
];

function NextBestActions() {
  const setActivePage = useAppStore((s) => s.setActivePage);

  return (
    <motion.div variants={staggerChild} className="h-full">
      <motion.div
        className="group relative h-full min-h-[300px] rounded-[28px] p-7 lg:p-8 card-shimmer-hover caustic-overlay gradient-border-hover glitter-container"
        style={{
          background: "var(--panel-bg)",
          backdropFilter: "blur(18px)",
          WebkitBackdropFilter: "blur(18px)",
          border: "1px solid var(--panel-border-accent)",
          boxShadow: "var(--panel-shadow), var(--panel-inset)",
        }}
        whileHover={{
          scale: 1.018,
          y: -4,
          transition: { type: "spring", stiffness: 300, damping: 24 },
        }}
        whileTap={{ scale: 0.99, transition: { duration: 0.12 } }}
      >
        {/* Glitter stars */}
        <span aria-hidden className="glitter-star" style={{ background: "rgba(34,211,238,0.85)" }} />
        <span aria-hidden className="glitter-star" style={{ background: "rgba(255,122,90,0.75)" }} />
        <span aria-hidden className="glitter-star" style={{ background: "rgba(255,255,255,0.90)" }} />
        <span aria-hidden className="glitter-star" style={{ background: "rgba(34,211,238,0.70)" }} />
        <span aria-hidden className="glitter-star" style={{ background: "rgba(255,209,102,0.80)" }} />
        <span aria-hidden className="glitter-star" style={{ background: "rgba(255,255,255,0.80)" }} />

        {/* Hover glow ring */}
        <div
          aria-hidden
          className="absolute inset-0 rounded-[28px] pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-300"
          style={{ boxShadow: "inset 0 0 0 1.5px rgba(255,255,255,0.10), 0 0 60px rgba(95,168,211,0.12)" }}
        />

        {/* Header */}
        <div className="relative flex items-center gap-2.5 mb-6">
          <Sparkles size={15} aria-hidden style={{ color: "rgba(255,122,90,0.88)" }} />
          <h2 className="section-heading aurora-heading">Next best actions</h2>
        </div>

        {/* Action rows */}
        <div className="relative space-y-3">
          {NEXT_ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <button
                key={action.title}
                type="button"
                onClick={() => setActivePage(action.page)}
                aria-label={action.title}
                className="w-full flex items-center justify-between rounded-2xl text-left transition-all duration-200 hover:scale-[1.012] group/row"
                style={{
                  background: "var(--row-bg)",
                  border: "1px solid var(--row-border-strong)",
                  backdropFilter: "blur(4px)",
                  WebkitBackdropFilter: "blur(4px)",
                  padding: "14px 16px",
                }}
              >
                <div className="flex items-center gap-3.5 min-w-0">
                  {/* Icon bubble */}
                  <div
                    aria-hidden
                    className="shrink-0 flex items-center justify-center rounded-xl"
                    style={{
                      width: 36,
                      height: 36,
                      background: action.iconBg,
                      border: `1px solid ${action.iconBorder}`,
                    }}
                  >
                    <Icon size={16} style={{ color: action.accent }} />
                  </div>
                  <div className="min-w-0">
                    <p className="card-heading leading-snug truncate" style={{ fontSize: "0.9375rem" }}>
                      {action.title}
                    </p>
                    <p className="readable-caption mt-0.5">
                      {action.description}
                    </p>
                  </div>
                </div>
                <ArrowRight
                  size={15}
                  aria-hidden
                  className="shrink-0 ml-3 transition-transform duration-200 group-hover/row:translate-x-1.5"
                  style={{ color: "rgba(34,211,238,0.65)" }}
                />
              </button>
            );
          })}
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Data at a glance ──────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: "ok" | "missing" | "loading" }) {
  if (status === "loading") {
    return (
      <span
        className="flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-semibold"
        style={{
          background: "rgba(160,190,205,0.12)",
          color: "var(--text-muted)",
          border: "1px solid rgba(160,190,205,0.18)",
        }}
      >
        <Clock size={10} aria-hidden />
        Loading…
      </span>
    );
  }
  if (status === "ok") {
    return (
      <span
        className="flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-semibold"
        style={{
          background: "var(--success-soft)",
          color: "#3db886",
          border: "1px solid rgba(61,184,134,0.22)",
        }}
      >
        <CheckCircle2 size={10} aria-hidden />
        Up to date
      </span>
    );
  }
  return (
    <span
      className="flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-semibold"
      style={{
        background: "var(--danger-soft)",
        color: "rgba(255,122,90,0.90)",
        border: "1px solid rgba(255,122,90,0.22)",
      }}
    >
      <AlertCircle size={10} aria-hidden />
      Needs data
    </span>
  );
}

const DATA_ROW_ICONS = {
  Banking:     Database,
  Investments: TrendingUp,
  Documents:   FileText,
};

function DataAtAGlance() {
  const { loading: bankLoading, raw: bankRaw } = useBankingData();
  const { loading: invLoading, hasData: invHasData } = useInvestmentData();

  const bankStatus = bankLoading ? "loading" : bankRaw ? "ok" : "missing";
  const invStatus  = invLoading  ? "loading" : invHasData ? "ok" : "missing";

  const rows = [
    { label: "Banking",     status: bankStatus as "ok" | "missing" | "loading" },
    { label: "Investments", status: invStatus  as "ok" | "missing" | "loading" },
    { label: "Documents",   status: (bankRaw || invHasData) ? "ok" as const : "missing" as const },
  ];

  return (
    <motion.div variants={staggerChild} className="h-full">
      <motion.div
        className="group relative h-full min-h-[300px] rounded-[28px] p-7 lg:p-8 card-shimmer-hover caustic-overlay gradient-border-hover"
        style={{
          background: "var(--panel-bg)",
          backdropFilter: "blur(18px)",
          WebkitBackdropFilter: "blur(18px)",
          border: "1px solid var(--panel-border-accent)",
          boxShadow: "var(--panel-shadow), var(--panel-inset)",
        }}
        whileHover={{
          scale: 1.018,
          y: -4,
          transition: { type: "spring", stiffness: 300, damping: 24 },
        }}
        whileTap={{ scale: 0.99, transition: { duration: 0.12 } }}
      >
        {/* Hover glow ring */}
        <div
          aria-hidden
          className="absolute inset-0 rounded-[28px] pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-300"
          style={{ boxShadow: "inset 0 0 0 1.5px rgba(255,255,255,0.10), 0 0 60px rgba(95,168,211,0.12)" }}
        />

        {/* Header with accent line */}
        <div className="relative mb-6">
          <div className="flex items-center gap-2.5">
            {/* Aqua accent dot with sparkle */}
            <span
              aria-hidden
              className="sparkle-dot inline-block w-2 h-2 rounded-full"
              style={{
                background: "rgba(34,211,238,0.90)",
                boxShadow: "0 0 12px rgba(34,211,238,0.60)",
              }}
            />
            <h2 className="section-heading aurora-heading">Your data at a glance</h2>
          </div>
          {/* Subtle underline accent */}
          <div
            aria-hidden
            className="mt-2 rounded-full"
            style={{
              height: 2,
              width: 48,
              marginLeft: 20,
              background: "linear-gradient(90deg, rgba(34,211,238,0.55), transparent)",
            }}
          />
        </div>

        <div className="relative space-y-3">
          {rows.map((row) => {
            const Icon = DATA_ROW_ICONS[row.label as keyof typeof DATA_ROW_ICONS];
            return (
              <div
                key={row.label}
                className="flex items-center justify-between rounded-2xl"
                style={{
                  background: "var(--row-bg)",
                  border: "1px solid var(--row-border-strong)",
                  backdropFilter: "blur(4px)",
                  WebkitBackdropFilter: "blur(4px)",
                  padding: "14px 16px",
                }}
              >
                <div className="flex items-center gap-3">
                  <div
                    aria-hidden
                    className="flex items-center justify-center rounded-xl"
                    style={{
                      width: 32,
                      height: 32,
                      background: "rgba(34,211,238,0.08)",
                      border: "1px solid rgba(34,211,238,0.15)",
                    }}
                  >
                    <Icon size={14} style={{ color: "rgba(34,211,238,0.75)" }} />
                  </div>
                  <span className="card-heading" style={{ fontSize: "0.9375rem" }}>
                    {row.label}
                  </span>
                </div>
                <StatusBadge status={row.status} />
              </div>
            );
          })}
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
        {/* Open hero */}
        <OpenHero />

        {/* Four feature cards */}
        <motion.div variants={staggerChild} className="px-7">
          <OverviewImageFeatureCards />
        </motion.div>

        {/* Bottom row: next actions + data glance */}
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
