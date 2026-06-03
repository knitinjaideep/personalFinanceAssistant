import { motion } from "framer-motion";
import { clsx } from "clsx";
import {
  Home, Landmark, TrendingUp,
  FileText, MessageSquare, Lock, Shield, ArrowRight,
} from "lucide-react";
import { useAppStore, type ActivePage } from "../../store/appStore";
import { CoralMascot } from "../CoralMascot";

// ── Nav config ────────────────────────────────────────────────────────────────

const NAV_ITEMS: { id: ActivePage; label: string; icon: React.ReactNode }[] = [
  { id: "overview",    label: "Home",        icon: <Home size={15} /> },
  { id: "banking",     label: "Banking",     icon: <Landmark size={15} /> },
  { id: "investments", label: "Investments", icon: <TrendingUp size={15} /> },
  { id: "documents",   label: "Documents",   icon: <FileText size={15} /> },
  { id: "chat",        label: "Chat",        icon: <MessageSquare size={15} /> },
];

// ── Brand ─────────────────────────────────────────────────────────────────────

function SidebarBrand({ onClick }: { onClick: () => void }) {
  return (
    <div className="px-5 pt-6 pb-5">
      <motion.button
        type="button"
        onClick={onClick}
        title="Coral — Home"
        aria-label="Coral — go to home"
        className="group flex items-center gap-3 text-left w-full"
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.10, duration: 0.38 }}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.97 }}
      >
        <span className="relative shrink-0">
          <CoralMascot variant="main" size="sm" glow animated />
        </span>

        <div>
          <div className="font-bold text-[16px] text-white leading-none tracking-tight">
            Coral
          </div>
          <div
            className="text-[10px] font-medium tracking-wide mt-0.5"
            style={{ color: "rgba(34,211,238,0.55)" }}
          >
            Local financial intelligence
          </div>
        </div>
      </motion.button>
    </div>
  );
}

// ── Nav item ──────────────────────────────────────────────────────────────────

function NavItem({
  item,
  active,
  onClick,
  delay,
}: {
  item: { id: ActivePage; label: string; icon: React.ReactNode };
  active: boolean;
  onClick: () => void;
  delay: number;
}) {
  return (
    <motion.button
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay, duration: 0.26 }}
      onClick={onClick}
      whileHover={active ? undefined : { x: 3 }}
      className={clsx(
        "w-full flex items-center gap-3 px-3.5 py-2.5 rounded-2xl text-[13px] font-medium",
        "relative transition-colors duration-150",
        active ? "text-white" : "hover:text-white/80",
      )}
      style={{ color: active ? undefined : "rgba(255,255,255,0.38)" }}
    >
      {active && (
        <motion.span
          layoutId="nav-pill"
          className="absolute inset-0 rounded-2xl"
          style={{
            background: "linear-gradient(135deg, rgba(255,122,90,0.88) 0%, rgba(255,163,143,0.80) 100%)",
            boxShadow:
              "0 4px 20px rgba(255,122,90,0.35), 0 0 0 1px rgba(255,255,255,0.10), inset 0 1px 0 rgba(255,255,255,0.18)",
          }}
          transition={{ type: "spring", stiffness: 380, damping: 32 }}
        />
      )}
      <span className="relative z-10 flex items-center shrink-0">{item.icon}</span>
      <span className="relative z-10">{item.label}</span>
    </motion.button>
  );
}

// ── Privacy card ──────────────────────────────────────────────────────────────

function PrivacyCard() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.55, duration: 0.35 }}
      className="mx-3 mb-3 rounded-2xl px-3.5 py-3"
      style={{
        background: "rgba(34,211,238,0.06)",
        border: "1px solid rgba(34,211,238,0.14)",
      }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <Shield size={11} style={{ color: "rgba(34,211,238,0.70)" }} />
        <span className="text-[11px] font-bold text-white/80">100% private</span>
      </div>
      <p className="text-[10px] leading-relaxed mb-2" style={{ color: "rgba(255,255,255,0.35)" }}>
        All data stays on your device.
      </p>
      <button
        type="button"
        className="flex items-center gap-1 text-[10px] font-semibold transition-opacity hover:opacity-80"
        style={{ color: "rgba(34,211,238,0.65)" }}
      >
        Learn more <ArrowRight size={9} />
      </button>
    </motion.div>
  );
}

// ── Bottom status ─────────────────────────────────────────────────────────────

function SidebarFooter() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.65, duration: 0.35 }}
      className="mx-3 mb-4 px-3 py-2 rounded-xl flex items-center justify-center gap-1.5"
      style={{
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full shrink-0"
        style={{ background: "#4CAF93", boxShadow: "0 0 6px rgba(76,175,147,0.70)" }}
      />
      <Lock size={8} style={{ color: "rgba(255,255,255,0.18)" }} />
      <span className="text-[9px] font-medium tracking-wide" style={{ color: "rgba(255,255,255,0.22)" }}>
        All data stays on device
      </span>
    </motion.div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

export function Sidebar() {
  const { activePage, setActivePage } = useAppStore();

  return (
    <motion.aside
      initial={{ x: -16, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.40, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col shrink-0"
      style={{
        width: "260px",
        background: "linear-gradient(180deg, rgba(3,17,31,0.92) 0%, rgba(4,22,38,0.90) 100%)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderRight: "1px solid rgba(34,211,238,0.08)",
        boxShadow: "4px 0 32px rgba(3,17,31,0.55)",
        minHeight: "100vh",
      }}
    >
      <SidebarBrand onClick={() => setActivePage("overview")} />

      {/* Hairline divider */}
      <div className="mx-4 h-px mb-4" style={{ background: "rgba(34,211,238,0.08)" }} />

      {/* Nav */}
      <nav className="flex-1 px-2 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item, i) => (
          <NavItem
            key={item.id}
            item={item}
            active={activePage === item.id}
            onClick={() => setActivePage(item.id)}
            delay={0.16 + i * 0.05}
          />
        ))}
      </nav>

      {/* Privacy card + footer */}
      <div className="mt-auto">
        <PrivacyCard />
        <SidebarFooter />
      </div>
    </motion.aside>
  );
}
