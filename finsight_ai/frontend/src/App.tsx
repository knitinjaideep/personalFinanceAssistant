import { Toaster } from "react-hot-toast";
import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "./store/appStore";
import { Sidebar } from "./components/layout/Sidebar";
import { OverviewPage } from "./pages/OverviewPage";
import { BankingPage } from "./pages/BankingPage";
import { InvestmentsPage } from "./pages/InvestmentsPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ChatPage } from "./pages/ChatPage";
import { CoralFloatingButton } from "./components/CoralFloatingButton";
import { CoralPageBackground } from "./components/CoralPageBackground";

const pageVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.28, ease: "easeOut" as const } },
  exit:   { opacity: 0, y: -4, transition: { duration: 0.18, ease: "easeIn" as const } },
};

function PageContent() {
  const { activePage } = useAppStore();
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={activePage}
        variants={pageVariants}
        initial="hidden"
        animate="visible"
        exit="exit"
        className="flex-1 min-h-0 flex flex-col"
      >
        {activePage === "overview"    && <OverviewPage />}
        {activePage === "banking"     && <BankingPage />}
        {activePage === "investments" && <InvestmentsPage />}
        {activePage === "documents"   && <DocumentsPage />}
        {activePage === "chat"        && <ChatPage />}
      </motion.div>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <div
      className="relative min-h-screen w-full overflow-hidden"
      style={{ background: "#03111f" }}
    >
      {/* Full-viewport underwater photo background — fixed, z-0, never blocks clicks */}
      <CoralPageBackground />

      {/* App shell — full screen, sits above background */}
      <div
        className="relative flex min-h-screen"
        style={{ zIndex: 10 }}
      >
        {/* Left sidebar */}
        <Sidebar />

        {/* Main content area — transparent so the full-viewport background shows through */}
        <main
          className="relative flex-1 flex flex-col min-w-0 min-h-screen"
          style={{
            background: "transparent",
            borderLeft: "1px solid rgba(34,211,238,0.08)",
          }}
        >
          <div className="relative z-10 flex-1 flex flex-col min-h-0" style={{ background: "transparent" }}>
            <PageContent />
          </div>
        </main>
      </div>

      {/* Floating "Ask Coral" launcher (hidden on chat page) */}
      <CoralFloatingButton />

      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            borderRadius: "14px",
            background: "rgba(6,26,42,0.92)",
            backdropFilter: "blur(16px)",
            color: "rgba(255,255,255,0.90)",
            border: "1px solid rgba(34,211,238,0.20)",
            boxShadow: "0 8px 32px rgba(3,17,31,0.50)",
            fontSize: "13px",
            fontWeight: "500",
          },
          success: { iconTheme: { primary: "#4CAF93", secondary: "rgba(6,26,42,0.92)" } },
          error:   { iconTheme: { primary: "#E45757", secondary: "rgba(6,26,42,0.92)" } },
        }}
      />
    </div>
  );
}
