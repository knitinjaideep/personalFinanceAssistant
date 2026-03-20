import { Home, MessageSquare, Lock } from "lucide-react";
import { clsx } from "clsx";
import { motion } from "framer-motion";
import { useAppStore } from "../../store/appStore";

type Page = "home" | "chat";

const NAV_ITEMS: { id: Page; label: string; icon: React.ReactNode }[] = [
  { id: "home", label: "Home",  icon: <Home size={17} /> },
  { id: "chat", label: "Chat",  icon: <MessageSquare size={17} /> },
];

export function Sidebar() {
  const { activePage, setActivePage } = useAppStore();

  return (
    <motion.aside
      initial={{ x: -16, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
      className="w-56 flex flex-col min-h-screen shrink-0"
      style={{
        background: "linear-gradient(180deg, #0a3352 0%, #1a5e7a 65%, #337fa0 100%)",
        borderRight: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      {/* Brand */}
      <div className="px-4 py-5">
        <motion.div
          className="flex items-center gap-3"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.35 }}
        >
          {/* Mascot with subtle float */}
          <motion.div
            animate={{ y: [0, -4, 0] }}
            transition={{ duration: 4, ease: "easeInOut", repeat: Infinity }}
            className="shrink-0"
          >
            <div
              className="w-10 h-10 rounded-xl overflow-hidden"
              style={{
                background: "rgba(255,255,255,0.12)",
                border: "1px solid rgba(255,255,255,0.20)",
                padding: "2px",
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

          <div>
            <div className="font-bold text-[15px] text-white leading-none tracking-tight">
              Coral
            </div>
            <div className="text-[10px] text-white/40 mt-0.5 font-medium tracking-wide">
              Local · Private
            </div>
          </div>
        </motion.div>
      </div>

      {/* Divider */}
      <div className="mx-4 h-px" style={{ background: "rgba(255,255,255,0.08)" }} />

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-1 mt-2">
        {NAV_ITEMS.map(({ id, label, icon }) => {
          const active = activePage === id;
          return (
            <button
              key={id}
              onClick={() => setActivePage(id)}
              className={clsx(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-2xl text-sm font-semibold",
                "transition-colors duration-200 relative",
                active
                  ? "text-white"
                  : "text-white/45 hover:text-white/75"
              )}
            >
              {/* Active background — sliding pill */}
              {active && (
                <motion.span
                  layoutId="nav-active"
                  className="absolute inset-0 rounded-2xl"
                  style={{
                    background: "rgba(255,255,255,0.13)",
                    border: "1px solid rgba(255,255,255,0.12)",
                  }}
                  transition={{ type: "spring", stiffness: 380, damping: 30 }}
                />
              )}

              <span className="relative z-10 flex items-center">{icon}</span>
              <span className="relative z-10">{label}</span>
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4" style={{ borderTop: "1px solid rgba(255,255,255,0.07)" }}>
        <div className="flex items-center justify-center gap-1.5">
          <Lock size={9} className="text-white/25" />
          <span className="text-[10px] text-white/25 font-medium tracking-wide">
            All data stays on device
          </span>
        </div>
      </div>
    </motion.aside>
  );
}
