import { motion } from "framer-motion";
import { clsx } from "clsx";
import {
  LayoutDashboard, Landmark, TrendingUp, RefreshCw,
  Receipt, FileText, MessageSquare, Lock,
} from "lucide-react";
import { useAppStore, type ActivePage } from "../../store/appStore";
import { CoralMascot } from "../CoralMascot";

// ── Nav config ────────────────────────────────────────────────────────────────

const NAV_SECTIONS: { label: string; items: { id: ActivePage; label: string; icon: React.ReactNode }[] }[] = [
  {
    label: "Overview",
    items: [
      { id: "overview",      label: "Overview",      icon: <LayoutDashboard size={15} /> },
    ],
  },
  {
    label: "Money",
    items: [
      { id: "banking",       label: "Banking",       icon: <Landmark size={15} /> },
      { id: "investments",   label: "Investments",   icon: <TrendingUp size={15} /> },
      { id: "subscriptions", label: "Subscriptions", icon: <RefreshCw size={15} /> },
      { id: "fees",          label: "Fees",          icon: <Receipt size={15} /> },
    ],
  },
  {
    label: "Tools",
    items: [
      { id: "documents",     label: "Documents",     icon: <FileText size={15} /> },
      { id: "chat",          label: "Chat",          icon: <MessageSquare size={15} /> },
    ],
  },
];

// ── Brand ─────────────────────────────────────────────────────────────────────

function SidebarBrand({ onClick }: { onClick: () => void }) {
  return (
    <div className="px-5 pt-6 pb-5">
      <motion.button
        type="button"
        onClick={onClick}
        title="Coral AI"
        aria-label="Coral AI — go to overview"
        className="group flex items-center gap-3 text-left"
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.12, duration: 0.38 }}
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
      >
        <span className="relative shrink-0">
          <CoralMascot variant="main" size="sm" glow animated />
          {/* Mini tooltip / label on hover */}
          <span
            className="pointer-events-none absolute left-1/2 -translate-x-1/2 top-full mt-1.5 whitespace-nowrap rounded-md px-1.5 py-0.5 text-[9px] font-semibold tracking-wide opacity-0 transition-opacity duration-200 group-hover:opacity-100"
            style={{
              background: "rgba(255,255,255,0.10)",
              border: "1px solid rgba(255,255,255,0.16)",
              color: "rgba(255,255,255,0.70)",
            }}
          >
            Coral AI
          </span>
        </span>

        <div>
          <div className="font-bold text-[15px] text-white leading-none tracking-tight">
            Coral
          </div>
          <div className="text-[10px] font-medium tracking-wide mt-0.5" style={{ color: "rgba(255,255,255,0.28)" }}>
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
      transition={{ delay, duration: 0.28 }}
      onClick={onClick}
      whileHover={active ? undefined : { x: 2 }}
      className={clsx(
        "w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-[13px] font-medium",
        "relative transition-colors duration-150",
        active ? "text-white" : "hover:text-white/70",
      )}
      style={{ color: active ? undefined : "rgba(255,255,255,0.38)" }}
    >
      {active && (
        <motion.span
          layoutId="nav-pill"
          className="absolute inset-0 rounded-xl"
          style={{
            background: "linear-gradient(135deg, rgba(255,122,90,0.90) 0%, rgba(255,163,143,0.85) 100%)",
            boxShadow: "0 3px 14px rgba(255,122,90,0.38), inset 0 1px 0 rgba(255,255,255,0.18)",
          }}
          transition={{ type: "spring", stiffness: 380, damping: 32 }}
        />
      )}
      <span className="relative z-10 flex items-center shrink-0">{item.icon}</span>
      <span className="relative z-10">{item.label}</span>
    </motion.button>
  );
}

// ── Section group ─────────────────────────────────────────────────────────────

function NavGroup({
  section,
  activePage,
  onNavigate,
  delayBase,
}: {
  section: typeof NAV_SECTIONS[number];
  activePage: ActivePage;
  onNavigate: (page: ActivePage) => void;
  delayBase: number;
}) {
  return (
    <div className="mb-1">
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: delayBase, duration: 0.3 }}
        className="px-3 mb-1 text-[9px] font-semibold uppercase tracking-widest"
        style={{ color: "rgba(255,255,255,0.20)" }}
      >
        {section.label}
      </motion.p>
      <div className="space-y-0.5">
        {section.items.map((item, i) => (
          <NavItem
            key={item.id}
            item={item}
            active={activePage === item.id}
            onClick={() => onNavigate(item.id)}
            delay={delayBase + 0.04 + i * 0.04}
          />
        ))}
      </div>
    </div>
  );
}

// ── Privacy footer ────────────────────────────────────────────────────────────

function SidebarFooter() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.55, duration: 0.35 }}
      className="mx-3 mb-4 px-3 py-2.5 rounded-xl flex items-center justify-center gap-1.5"
      style={{
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.07)",
      }}
    >
      <Lock size={9} style={{ color: "rgba(255,255,255,0.18)" }} />
      <span className="text-[9px] font-medium tracking-wide" style={{ color: "rgba(255,255,255,0.18)" }}>
        All data stays on device
      </span>
    </motion.div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

export function Sidebar() {
  const { activePage, setActivePage } = useAppStore();

  let delayBase = 0.18;
  return (
    <motion.aside
      initial={{ x: -16, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.40, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col shrink-0"
      style={{
        width: "220px",
        background: "linear-gradient(180deg, rgba(4,14,26,0.96) 0%, rgba(6,18,32,0.94) 100%)",
        borderRight: "1px solid rgba(255,255,255,0.055)",
        boxShadow: "4px 0 28px rgba(2,8,18,0.35)",
      }}
    >
      <SidebarBrand onClick={() => setActivePage("overview")} />

      {/* Hairline */}
      <div className="mx-4 h-px mb-3" style={{ background: "rgba(255,255,255,0.055)" }} />

      {/* Nav */}
      <nav className="flex-1 px-2 space-y-3 overflow-y-auto">
        {NAV_SECTIONS.map((section) => {
          const base = delayBase;
          delayBase += 0.06 + section.items.length * 0.04;
          return (
            <NavGroup
              key={section.label}
              section={section}
              activePage={activePage}
              onNavigate={setActivePage}
              delayBase={base}
            />
          );
        })}
      </nav>

      <SidebarFooter />
    </motion.aside>
  );
}
