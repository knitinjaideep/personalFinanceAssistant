import { motion } from "framer-motion";
import { MessageSquare, Upload } from "lucide-react";
import { staggerChild, contentPageVariants } from "../design/motion";
import { CoralMascot } from "../components/CoralMascot";
import { CoralBubbleMascot } from "../components/CoralBubbleMascot";
import { OverviewImageFeatureCards } from "../components/dashboard/OverviewImageFeatureCards";
import { useAppStore } from "../store/appStore";

// ── Page header ───────────────────────────────────────────────────────────────

function PageHeader() {
  return (
    <div
      className="shrink-0 px-7 py-5 flex items-center justify-between"
      style={{
        borderBottom: "1px solid rgba(205,237,246,0.50)",
        background: "rgba(255,255,255,0.55)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      <div className="flex items-center gap-3">
        <CoralMascot variant="analytics" size="sm" className="shrink-0" />
        <div>
          <h1 className="text-[18px] font-bold text-ocean-deep tracking-tight leading-none">
            Overview
          </h1>
          <p className="text-[12px] text-ocean/40 mt-1 font-medium">
            Your financial command center
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Hero card ─────────────────────────────────────────────────────────────────

function HeroCard() {
  const setActivePage = useAppStore((s) => s.setActivePage);
  const ctaBase = "flex items-center gap-2 px-4 py-2.5 rounded-xl text-[13px] font-semibold transition-all";

  return (
    <motion.div variants={staggerChild}>
      <div
        className="relative overflow-hidden rounded-3xl"
        style={{
          background:
            "linear-gradient(135deg, rgba(7,24,38,0.97) 0%, rgba(11,45,70,0.96) 55%, rgba(15,61,85,0.95) 100%)",
          border: "1px solid rgba(95,168,211,0.18)",
          boxShadow: "0 18px 60px rgba(4,14,26,0.45), inset 0 1px 0 rgba(255,255,255,0.06)",
        }}
      >
        <div
          aria-hidden
          className="pointer-events-none absolute -top-24 -right-16 w-72 h-72 rounded-full"
          style={{
            background: "radial-gradient(circle, rgba(95,168,211,0.28) 0%, transparent 70%)",
            filter: "blur(8px)",
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-20 right-32 w-56 h-56 rounded-full"
          style={{
            background: "radial-gradient(circle, rgba(255,122,90,0.22) 0%, transparent 70%)",
            filter: "blur(8px)",
          }}
        />
        <div className="relative flex flex-col md:flex-row items-center gap-6 px-7 py-8 md:py-9">
          <div className="flex-1 text-center md:text-left order-2 md:order-1">
            <h2 className="text-[26px] font-extrabold tracking-tight leading-none">
              <span className="text-gradient-coral">Coral</span>
            </h2>
            <p className="text-[13px] font-semibold text-ocean-aqua/80 mt-1.5">
              Local financial intelligence
            </p>
            <p className="text-[13px] text-white/55 mt-3 max-w-md leading-relaxed mx-auto md:mx-0">
              Your local AI analyst. Ask questions about spending, investments,
              and statements — everything stays private on your device.
            </p>
            <div className="flex flex-wrap items-center justify-center md:justify-start gap-2.5 mt-5">
              <button
                onClick={() => setActivePage("chat")}
                className={ctaBase + " text-white"}
                style={{
                  background: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
                  boxShadow: "0 6px 20px rgba(255,122,90,0.38)",
                }}
              >
                <MessageSquare size={14} />
                Ask Coral
              </button>
              <button
                onClick={() => setActivePage("documents")}
                className={ctaBase + " text-white/85"}
                style={{
                  background: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.16)",
                }}
              >
                <Upload size={14} />
                Upload Documents
              </button>
            </div>
          </div>
          <div className="order-1 md:order-2 shrink-0 pt-2">
            <CoralBubbleMascot
              variant="main"
              size="hero"
              glow
              animated
              priority
              speech="Ask me about your spending, investments, and statements."
            />
          </div>
        </div>
      </div>
    </motion.div>
  );
}


// ── Privacy callout ───────────────────────────────────────────────────────────

function PrivacyCallout() {
  return (
    <motion.div variants={staggerChild}>
      <div
        className="flex items-center gap-4 rounded-2xl px-5 py-4"
        style={{
          background: "rgba(76,175,147,0.07)",
          border: "1px solid rgba(76,175,147,0.22)",
        }}
      >
        <CoralMascot variant="security" size="sm" className="shrink-0" />
        <div>
          <p className="text-[13px] font-semibold text-ocean-deep">
            All analysis stays local on your device.
          </p>
          <p className="text-[11.5px] text-ocean/45 mt-0.5">
            Coral uses Ollama to run AI models locally — no cloud APIs, no data sharing, ever.
          </p>
        </div>
      </div>
    </motion.div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function OverviewPage() {
  return (
    <div className="flex flex-col h-full">
      <PageHeader />
      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-5"
      >
        <HeroCard />

        {/* ── Full-image feature cards ──────────────────────────────────── */}
        <motion.div variants={staggerChild}>
          <OverviewImageFeatureCards />
        </motion.div>

        <PrivacyCallout />
        <div className="h-3" />
      </motion.div>
    </div>
  );
}
