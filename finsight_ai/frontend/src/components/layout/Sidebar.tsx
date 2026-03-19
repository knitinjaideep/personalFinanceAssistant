import { Home, MessageSquare } from "lucide-react";
import { clsx } from "clsx";
import { useAppStore } from "../../store/appStore";

type Page = "home" | "chat";

const NAV_ITEMS: { id: Page; label: string; icon: React.ReactNode }[] = [
  { id: "home", label: "Home", icon: <Home size={18} /> },
  { id: "chat", label: "Chat", icon: <MessageSquare size={18} /> },
];

export function Sidebar() {
  const { activePage, setActivePage } = useAppStore();

  return (
    <aside
      className="w-56 flex flex-col min-h-screen shrink-0"
      style={{ background: "linear-gradient(180deg, #0B3C5D 0%, #1F6F8B 100%)" }}
    >
      {/* Brand */}
      <div className="px-4 py-5 flex items-center gap-3">
        <img
          src="/mascot.png"
          alt="Coral"
          className="w-9 h-9 object-contain rounded-xl bg-white/10 p-0.5"
        />
        <div>
          <div className="font-bold text-base text-white leading-none">Coral</div>
          <div className="text-xs text-white/40 mt-0.5">Local · Private</div>
        </div>
      </div>

      {/* Divider */}
      <div className="mx-4 h-px bg-white/10" />

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-1 mt-2">
        {NAV_ITEMS.map(({ id, label, icon }) => (
          <button
            key={id}
            onClick={() => setActivePage(id)}
            className={clsx(
              "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150",
              activePage === id
                ? "bg-white/15 text-white shadow-soft"
                : "text-white/50 hover:text-white hover:bg-white/8"
            )}
          >
            {icon}
            {label}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-white/10">
        <div className="text-xs text-white/30 text-center leading-relaxed">
          All data stays on device
        </div>
      </div>
    </aside>
  );
}
