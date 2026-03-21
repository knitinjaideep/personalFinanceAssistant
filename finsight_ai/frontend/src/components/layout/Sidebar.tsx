import { useEffect, useState } from "react";
import { Home, MessageSquare, Lock, FolderOpen, FileText, Clock } from "lucide-react";
import { clsx } from "clsx";
import { motion } from "framer-motion";
import { useAppStore } from "../../store/appStore";
import { foldersApi } from "../../api/folders";
import type { FolderScanResult } from "../../api/folders";

type Page = "home" | "chat";

const NAV_ITEMS: { id: Page; label: string; icon: React.ReactNode }[] = [
  { id: "home", label: "Home",  icon: <Home size={16} /> },
  { id: "chat", label: "Chat",  icon: <MessageSquare size={16} /> },
];

// ── Brand block ───────────────────────────────────────────────────────────────

function SidebarBrand() {
  return (
    <div className="px-5 pt-6 pb-5">
      <motion.div
        className="flex items-center gap-3"
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.18, duration: 0.38 }}
      >
        {/* Mascot */}
        <motion.div
          animate={{ y: [0, -4, 0] }}
          transition={{ duration: 4.5, ease: "easeInOut", repeat: Infinity }}
          className="shrink-0"
        >
          <div
            className="w-10 h-10 rounded-xl overflow-hidden"
            style={{
              background: "rgba(255,255,255,0.10)",
              border: "1px solid rgba(255,255,255,0.16)",
              padding: "2px",
              boxShadow: "0 4px 16px rgba(4,14,26,0.35)",
            }}
          >
            <img
              src="/mascot.png"
              alt="Coral"
              className="w-full h-full object-contain rounded-lg"
              style={{ animation: "blink 5s ease-in-out infinite" }}
            />
          </div>
        </motion.div>

        {/* Name */}
        <div>
          <div className="font-bold text-[15px] text-white leading-none tracking-tight">
            Coral
          </div>
          <div className="text-[10px] text-white/35 mt-0.5 font-medium tracking-wide">
            Local financial intelligence
          </div>
        </div>
      </motion.div>
    </div>
  );
}

// ── Nav item ──────────────────────────────────────────────────────────────────

function NavItem({
  item,
  active,
  onClick,
  index,
}: {
  item: (typeof NAV_ITEMS)[number];
  active: boolean;
  onClick: () => void;
  index: number;
}) {
  return (
    <motion.button
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.22 + index * 0.06, duration: 0.32 }}
      onClick={onClick}
      whileHover={active ? undefined : { x: 3 }}
      className={clsx(
        "w-full flex items-center gap-3 px-3.5 py-2.5 rounded-2xl text-sm font-semibold",
        "relative transition-colors duration-200",
        active ? "text-white" : "text-white/40 hover:text-white/70"
      )}
    >
      {/* Active coral pill */}
      {active && (
        <motion.span
          layoutId="nav-active-pill"
          className="absolute inset-0 rounded-2xl"
          style={{
            background: "linear-gradient(135deg, #FF7A5A 0%, #FFA38F 100%)",
            boxShadow: "0 4px 16px rgba(255,122,90,0.40), inset 0 1px 0 rgba(255,255,255,0.20)",
          }}
          transition={{ type: "spring", stiffness: 380, damping: 30 }}
        />
      )}

      <span className="relative z-10 flex items-center">{item.icon}</span>
      <span className="relative z-10">{item.label}</span>
    </motion.button>
  );
}

// ── Status card ───────────────────────────────────────────────────────────────

function SidebarStatusCard({ scan }: { scan: FolderScanResult | null }) {
  const folders = scan?.folders.length ?? 0;
  const statements = (scan?.investments_total ?? 0) + (scan?.banking_total ?? 0);

  // Format "last sync" as relative time
  const lastSync = (() => {
    if (!scan) return "—";
    const now = new Date();
    const h = now.getHours().toString().padStart(2, "0");
    const m = now.getMinutes().toString().padStart(2, "0");
    return `${h}:${m}`;
  })();

  const rows: { icon: React.ReactNode; label: string; value: string | number }[] = [
    { icon: <FolderOpen size={11} />, label: "Folders",    value: folders },
    { icon: <FileText   size={11} />, label: "Statements", value: statements },
    { icon: <Clock      size={11} />, label: "Last sync",  value: lastSync },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.42, duration: 0.35 }}
      className="mx-3 mb-4 rounded-2xl overflow-hidden"
      style={{
        background: "rgba(255,255,255,0.05)",
        border: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      <div className="px-3.5 pt-3 pb-1">
        <p className="text-[9px] font-semibold text-white/25 uppercase tracking-widest mb-2.5">
          Status
        </p>
        <div className="space-y-2">
          {rows.map(({ icon, label, value }) => (
            <div key={label} className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-white/30">
                {icon}
                <span className="text-[11px] font-medium">{label}</span>
              </div>
              <span className="text-[11px] font-semibold text-white/55 tabular-nums">
                {value}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Privacy footer inside status card */}
      <div className="px-3.5 py-2.5 mt-2 border-t border-white/06 flex items-center justify-center gap-1.5">
        <Lock size={9} className="text-white/20" />
        <span className="text-[9px] text-white/20 font-medium tracking-wide">
          All data stays on device
        </span>
      </div>
    </motion.div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

export function Sidebar() {
  const { activePage, setActivePage } = useAppStore();
  const [scan, setScan] = useState<FolderScanResult | null>(null);

  useEffect(() => {
    foldersApi.scan(5).then(setScan).catch(() => {});
    const id = setInterval(() => {
      foldersApi.scan(5).then(setScan).catch(() => {});
    }, 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <motion.aside
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col shrink-0"
      style={{
        width: "260px",
        background: "linear-gradient(180deg, rgba(5,17,30,0.92) 0%, rgba(7,22,38,0.90) 100%)",
        borderRight: "1px solid rgba(255,255,255,0.06)",
        boxShadow: "4px 0 32px rgba(4,14,26,0.30)",
      }}
    >
      {/* Brand */}
      <SidebarBrand />

      {/* Hairline divider */}
      <div className="mx-5 h-px" style={{ background: "rgba(255,255,255,0.06)" }} />

      {/* Nav */}
      <nav className="flex-1 p-3 mt-2 space-y-0.5">
        {NAV_ITEMS.map((item, i) => (
          <NavItem
            key={item.id}
            item={item}
            active={activePage === item.id}
            onClick={() => setActivePage(item.id)}
            index={i}
          />
        ))}
      </nav>

      {/* Status card */}
      <SidebarStatusCard scan={scan} />
    </motion.aside>
  );
}
