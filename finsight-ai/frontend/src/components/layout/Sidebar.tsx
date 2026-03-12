import React from "react";
import { UploadCloud, MessageSquare, BarChart2, FileText, TrendingUp } from "lucide-react";
import { clsx } from "clsx";
import { useAppStore } from "../../store/appStore";

type Page = "upload" | "statements" | "chat" | "analytics";

const NAV_ITEMS: { id: Page; label: string; icon: React.ReactNode }[] = [
  { id: "upload", label: "Upload", icon: <UploadCloud size={18} /> },
  { id: "statements", label: "Statements", icon: <FileText size={18} /> },
  { id: "chat", label: "Chat", icon: <MessageSquare size={18} /> },
  { id: "analytics", label: "Analytics", icon: <BarChart2 size={18} /> },
];

export function Sidebar() {
  const { activePage, setActivePage } = useAppStore();

  return (
    <aside className="w-56 bg-gray-900 text-white flex flex-col min-h-screen">
      {/* Logo */}
      <div className="p-4 border-b border-gray-700 flex items-center gap-2">
        <TrendingUp size={22} className="text-blue-400" />
        <div>
          <div className="font-bold text-sm">FinSight AI</div>
          <div className="text-xs text-gray-400">Local · Private</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-1">
        {NAV_ITEMS.map(({ id, label, icon }) => (
          <button
            key={id}
            onClick={() => setActivePage(id)}
            className={clsx(
              "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
              activePage === id
                ? "bg-blue-600 text-white"
                : "text-gray-300 hover:bg-gray-800"
            )}
          >
            {icon}
            {label}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-gray-700">
        <div className="text-xs text-gray-500 text-center">
          All data stays local
        </div>
      </div>
    </aside>
  );
}
