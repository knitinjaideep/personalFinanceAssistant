import { Toaster } from "react-hot-toast";
import { motion } from "framer-motion";
import { Sidebar } from "./components/layout/Sidebar";
import { HomePage } from "./pages/HomePage";
import { ChatPage } from "./pages/ChatPage";
import { useAppStore } from "./store/appStore";

function PageContent() {
  const { activePage } = useAppStore();
  switch (activePage) {
    case "chat":
      return <ChatPage />;
    default:
      return <HomePage />;
  }
}

export default function App() {
  return (
    // ── Layer 1: full-viewport deep ocean radial background ───────────────────
    <div
      className="min-h-screen w-full flex items-center justify-center p-4 lg:p-6 overflow-hidden"
      style={{
        background: "radial-gradient(ellipse at 50% 30%, #1a5e7a 0%, #0B3C5D 45%, #061e2f 100%)",
      }}
    >
      {/* ── Layer 2: centered app shell ──────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, scale: 0.985, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        className="w-full flex"
        style={{
          maxWidth: "1440px",
          minHeight: "calc(100vh - 48px)",
          maxHeight: "calc(100vh - 48px)",
          borderRadius: "28px",
          overflow: "hidden",
          background: "linear-gradient(160deg, rgba(10,32,52,0.82) 0%, rgba(6,18,34,0.92) 100%)",
          border: "1px solid rgba(255,255,255,0.07)",
          boxShadow:
            "0 40px 120px rgba(4,14,26,0.65), 0 8px 32px rgba(4,14,26,0.40), 0 0 0 1px rgba(255,255,255,0.04)",
        }}
      >
        {/* ── Layer 3a: sidebar ─────────────────────────────────────────────── */}
        <Sidebar />

        {/* ── Layer 3b: main content ────────────────────────────────────────── */}
        <main
          className="flex-1 overflow-hidden flex flex-col"
          style={{
            background: "linear-gradient(160deg, rgba(240,249,252,0.97) 0%, rgba(248,253,255,0.99) 100%)",
            borderRadius: "0 27px 27px 0",
            boxShadow: "inset 0 1px 0 rgba(255,255,255,0.9), -1px 0 0 rgba(11,60,93,0.08)",
          }}
        >
          <PageContent />
        </main>
      </motion.div>

      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            borderRadius: "16px",
            background: "rgba(255,255,255,0.96)",
            backdropFilter: "blur(16px)",
            color: "#0B3C5D",
            border: "1px solid rgba(205,237,246,0.8)",
            boxShadow: "0 8px 32px rgba(11,60,93,0.14)",
            fontSize: "13px",
            fontWeight: "500",
          },
          success: { iconTheme: { primary: "#4CAF93", secondary: "white" } },
          error:   { iconTheme: { primary: "#E45757", secondary: "white" } },
        }}
      />
    </div>
  );
}
