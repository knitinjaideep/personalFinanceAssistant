import { motion } from "framer-motion";
import { MessageSquare, Upload, ArrowRight, Sparkles, CheckCircle2, AlertCircle, Clock } from "lucide-react";
import { staggerChild, staggerContainer, contentPageVariants } from "../design/motion";
import { CoralBubbleMascot } from "../components/CoralBubbleMascot";
import { OverviewImageFeatureCards } from "../components/dashboard/OverviewImageFeatureCards";
import { HomeImagePanel } from "../components/home/HomeImagePanel";
import { useAppStore } from "../store/appStore";
import { useBankingData } from "../hooks/useBankingData";
import { useInvestmentData } from "../hooks/useInvestmentData";
import { homeImages } from "../lib/homeImages";

// ── Open hero — no card, content floats over the page background ──────────────

function OpenHero() {
  const setActivePage = useAppStore((s) => s.setActivePage);

  return (
    <motion.div variants={staggerChild}>
      <section
        className="relative min-h-[520px] overflow-visible px-7 pt-10 pb-6"
        style={{ background: "transparent" }}
      >
        {/* Soft radial vignette — edge-less, not rectangular, improves text contrast */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse at 22% 48%, rgba(3,17,31,0.68) 0%, rgba(3,17,31,0.28) 42%, transparent 68%)",
          }}
        />

        {/* Content grid */}
        <div className="relative z-10 grid grid-cols-1 items-center gap-10 lg:grid-cols-2">
          {/* ── Left — text ──────────────────────────────────────────────── */}
          <div className="flex flex-col items-start">
            {/* Welcome badge */}
            <div
              className="mb-5 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-[11px] font-semibold tracking-wide"
              style={{
                background: "rgba(34,211,238,0.10)",
                border: "1px solid rgba(34,211,238,0.22)",
                color: "rgba(34,211,238,0.90)",
              }}
            >
              <Sparkles size={10} />
              Welcome to Coral
            </div>

            <h1 className="text-[44px] font-extrabold tracking-tight leading-[1.08] text-white drop-shadow-[0_2px_16px_rgba(3,17,31,0.80)]">
              Hi, I'm Coral 👋
            </h1>

            <p
              className="text-[15px] font-semibold mt-2"
              style={{ color: "rgba(34,211,238,0.75)" }}
            >
              Your local financial intelligence hub.
            </p>

            <p
              className="text-[13.5px] mt-4 max-w-[420px] leading-relaxed"
              style={{ color: "rgba(255,255,255,0.60)" }}
            >
              Everything you need to understand your finances, all in one place.
              100% private — no cloud, no sharing, ever.
            </p>

            {/* CTA buttons */}
            <div className="flex flex-wrap items-center gap-3 mt-7">
              <button
                onClick={() => setActivePage("chat")}
                className="flex items-center gap-2 px-6 py-3 rounded-2xl text-[13px] font-semibold text-white transition-all hover:scale-[1.03] active:scale-[0.97]"
                style={{
                  background: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
                  boxShadow: "0 6px 28px rgba(255,122,90,0.45)",
                }}
              >
                <MessageSquare size={14} />
                Ask Coral
              </button>
              <button
                onClick={() => setActivePage("documents")}
                className="flex items-center gap-2 px-6 py-3 rounded-2xl text-[13px] font-semibold transition-all hover:scale-[1.03] active:scale-[0.97]"
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

            {/* Privacy badge */}
            <div
              className="mt-6 inline-flex items-center gap-2 text-[11px] font-semibold tracking-wider"
              style={{ color: "rgba(76,175,147,0.85)" }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full bg-[#4CAF93] inline-block"
                style={{ boxShadow: "0 0 8px rgba(76,175,147,0.80)" }}
              />
              Private • Local • Secure
            </div>
          </div>

          {/* ── Right — mascot floats directly over background ───────────────── */}
          <div className="flex justify-center lg:justify-end">
            {/* Radial background glow so mascot doesn't feel pasted */}
            <div className="relative">
              <div
                aria-hidden
                className="pointer-events-none absolute"
                style={{
                  inset: "-30%",
                  borderRadius: "50%",
                  background:
                    "radial-gradient(circle, rgba(34,211,238,0.18) 0%, rgba(255,122,90,0.12) 40%, transparent 70%)",
                  filter: "blur(28px)",
                }}
              />
              <CoralBubbleMascot
                variant="main"
                size="hero"
                glow
                animated
                priority
                speech="Ask me anything about your spending, statements, fees, or investments!"
              />
            </div>
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
      <HomeImagePanel
        title={
          <>
            <Sparkles size={13} style={{ color: "rgba(255,122,90,0.85)" }} />
            ✦ Next best actions
          </>
        }
        backgroundSrc="/backgrounds/app-ocean-dark.png"
        overlay="left-heavy"
        imagePosition="center center"
        imageClassName="opacity-[0.88]"
        contentClassName="p-6 lg:p-7"
      >
        <div className="space-y-3">
          {NEXT_ACTIONS.map((action) => (
            <button
              key={action.title}
              type="button"
              onClick={() => setActivePage(action.page)}
              className="w-full flex items-center justify-between rounded-2xl text-left transition-all hover:scale-[1.01] group/row"
              style={{
                background: "rgba(3,17,31,0.45)",
                border: "1px solid rgba(34,211,238,0.12)",
                backdropFilter: "blur(12px)",
                WebkitBackdropFilter: "blur(12px)",
                padding: "14px 18px",
              }}
            >
              <div>
                <p className="text-[13px] font-semibold" style={{ color: "rgba(255,255,255,0.90)" }}>
                  {action.title}
                </p>
                <p className="text-[11px] mt-0.5" style={{ color: "rgba(186,230,255,0.55)" }}>
                  {action.description}
                </p>
              </div>
              <ArrowRight
                size={14}
                className="shrink-0 ml-3 transition-transform duration-200 group-hover/row:translate-x-1"
                style={{ color: "rgba(34,211,238,0.75)" }}
              />
            </button>
          ))}
        </div>
      </HomeImagePanel>
    </motion.div>
  );
}

// ── Data at a glance ──────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: "ok" | "missing" | "loading" }) {
  if (status === "loading") {
    return (
      <span className="flex items-center gap-1 text-[11px] font-semibold" style={{ color: "rgba(255,255,255,0.35)" }}>
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
      <HomeImagePanel
        title="Your data at a glance"
        backgroundSrc="/backgrounds/app-ocean-dark.png"
        overlay="balanced"
        imagePosition="center center"
        imageClassName="opacity-[0.82]"
        contentClassName="p-6 lg:p-7"
      >
        <div className="space-y-4">
          {rows.map((row) => (
            <div
              key={row.label}
              className="flex items-center justify-between rounded-2xl"
              style={{
                background: "rgba(3,17,31,0.42)",
                border: "1px solid rgba(34,211,238,0.12)",
                backdropFilter: "blur(12px)",
                WebkitBackdropFilter: "blur(12px)",
                padding: "14px 18px",
              }}
            >
              <span className="text-[13px] font-semibold" style={{ color: "rgba(255,255,255,0.85)" }}>
                {row.label}
              </span>
              <StatusBadge status={row.status} />
            </div>
          ))}
        </div>
      </HomeImagePanel>
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
        <motion.div variants={staggerChild} className="px-7 mt-2">
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
