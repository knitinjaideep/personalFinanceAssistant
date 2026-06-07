import { motion } from "framer-motion";
import { clsx } from "clsx";
import {
  Home, Landmark, TrendingUp,
  FileText, MessageSquare, Lock, Shield, ArrowRight, Sun, Moon,
} from "lucide-react";
import { useAppStore, type ActivePage } from "../../store/appStore";
import { CoralMascot } from "../CoralMascot";

// ── Nav config ────────────────────────────────────────────────────────────────

const NAV_ITEMS: { id: ActivePage; label: string; icon: React.ReactNode }[] = [
  { id: "overview",    label: "Home",        icon: <Home size={17} /> },
  { id: "banking",     label: "Banking",     icon: <Landmark size={17} /> },
  { id: "investments", label: "Investments", icon: <TrendingUp size={17} /> },
  { id: "documents",   label: "Documents",   icon: <FileText size={17} /> },
  { id: "chat",        label: "Chat",        icon: <MessageSquare size={17} /> },
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
          <div className="font-bold text-lg leading-none tracking-tight" style={{ color: "var(--text-primary)" }}>
            Coral
          </div>
          <div
            className="text-xs font-medium tracking-wide mt-0.5"
            style={{ color: "rgba(34,211,238,0.65)" }}
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
  const theme = useAppStore((s) => s.theme);
  const isLight = theme === "light";

  return (
    <motion.button
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay, duration: 0.26 }}
      onClick={onClick}
      whileHover={active ? undefined : { x: 3 }}
      className={clsx(
        "w-full flex items-center gap-3 px-3.5 py-3 rounded-2xl coral-nav-text font-medium",
        "relative transition-colors duration-150",
      )}
      style={{
        color: active
          ? "white"
          : isLight
            ? "rgba(11,40,65,0.55)"
            : "rgba(255,255,255,0.38)",
      }}
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

// ── Theme toggle ──────────────────────────────────────────────────────────────

function ThemeToggle() {
  const { theme, toggleTheme } = useAppStore();
  const isLight = theme === "light";

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.50, duration: 0.35 }}
      className="mx-3 mb-2"
    >
      <button
        type="button"
        onClick={toggleTheme}
        className="w-full flex items-center justify-between px-3.5 py-2.5 rounded-2xl transition-all duration-200"
        style={{
          background: "var(--privacy-bg)",
          border: "1px solid var(--privacy-border)",
        }}
      >
        <div className="flex items-center gap-2">
          {isLight
            ? <Sun size={13} style={{ color: "rgba(255,160,20,0.85)" }} />
            : <Moon size={13} style={{ color: "rgba(34,211,238,0.75)" }} />
          }
          <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
            {isLight ? "Light mode" : "Dark mode"}
          </span>
        </div>

        {/* Toggle pill */}
        <div
          className="relative flex items-center rounded-full transition-all duration-300"
          style={{
            width: 32,
            height: 18,
            background: isLight
              ? "rgba(255,160,20,0.25)"
              : "rgba(34,211,238,0.20)",
            border: `1px solid ${isLight ? "rgba(255,160,20,0.40)" : "rgba(34,211,238,0.35)"}`,
          }}
        >
          <motion.div
            layout
            transition={{ type: "spring", stiffness: 500, damping: 35 }}
            className="absolute rounded-full"
            style={{
              width: 12,
              height: 12,
              left: isLight ? 16 : 2,
              background: isLight ? "rgba(255,160,20,0.90)" : "rgba(34,211,238,0.85)",
              boxShadow: isLight
                ? "0 0 6px rgba(255,160,20,0.60)"
                : "0 0 6px rgba(34,211,238,0.55)",
            }}
          />
        </div>
      </button>
    </motion.div>
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
        background: "var(--privacy-bg)",
        border: "1px solid var(--privacy-border)",
      }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <Shield size={12} style={{ color: "rgba(34,211,238,0.70)" }} />
        <span className="text-xs font-bold" style={{ color: "var(--text-secondary)" }}>100% private</span>
      </div>
      <p className="text-xs leading-relaxed mb-2" style={{ color: "var(--text-muted)" }}>
        All data stays on your device.
      </p>
      <button
        type="button"
        className="flex items-center gap-1 text-xs font-semibold transition-opacity hover:opacity-80"
        style={{ color: "rgba(34,211,238,0.65)" }}
      >
        Learn more <ArrowRight size={10} />
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
        background: "var(--footer-bg)",
        border: "1px solid var(--footer-border)",
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full shrink-0"
        style={{ background: "#4CAF93", boxShadow: "0 0 6px rgba(76,175,147,0.70)" }}
      />
      <Lock size={10} style={{ color: "var(--text-dim)" }} />
      <span className="text-xs font-medium tracking-wide" style={{ color: "var(--text-dim)" }}>
        All data stays on device
      </span>
    </motion.div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

export function Sidebar() {
  const { activePage, setActivePage, theme } = useAppStore();
  const isLight = theme === "light";

  return (
    <motion.aside
      initial={{ x: -16, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.40, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col shrink-0"
      style={{
        width: "260px",
        background: isLight
          ? "linear-gradient(180deg, rgba(240,247,252,0.94) 0%, rgba(220,238,250,0.92) 100%)"
          : "linear-gradient(180deg, rgba(3,17,31,0.92) 0%, rgba(4,22,38,0.90) 100%)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderRight: `1px solid var(--border-subtle)`,
        boxShadow: isLight
          ? "4px 0 32px rgba(11,60,93,0.12)"
          : "4px 0 32px rgba(3,17,31,0.55)",
        minHeight: "100vh",
        transition: "background 0.3s ease, box-shadow 0.3s ease",
      }}
    >
      <SidebarBrand onClick={() => setActivePage("overview")} />

      {/* Hairline divider */}
      <div className="mx-4 h-px mb-4" style={{ background: "var(--border-subtle)" }} />

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

      {/* Theme toggle + privacy card + footer */}
      <div className="mt-auto">
        <ThemeToggle />
        <PrivacyCard />
        <SidebarFooter />
      </div>
    </motion.aside>
  );
}
