import { Toaster } from "react-hot-toast";
import { motion, AnimatePresence } from "framer-motion";
import { useAppStore } from "./store/appStore";
import { Sidebar } from "./components/layout/Sidebar";
import { OverviewPage } from "./pages/OverviewPage";
import { BankingPage } from "./pages/BankingPage";
import { InvestmentsPage } from "./pages/InvestmentsPage";
import { SubscriptionsPage } from "./pages/SubscriptionsPage";
import { FeesPage } from "./pages/FeesPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ChatPage } from "./pages/ChatPage";
import { CoralFloatingButton } from "./components/CoralFloatingButton";
import { CoralAppBackground } from "./components/CoralAppBackground";

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
        {activePage === "overview"       && <OverviewPage />}
        {activePage === "banking"        && <BankingPage />}
        {activePage === "investments"    && <InvestmentsPage />}
        {activePage === "subscriptions"  && <SubscriptionsPage />}
        {activePage === "fees"           && <FeesPage />}
        {activePage === "documents"      && <DocumentsPage />}
        {activePage === "chat"           && <ChatPage />}
      </motion.div>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <div
      className="relative min-h-screen w-full flex items-center justify-center overflow-hidden"
      style={{
        background: "radial-gradient(ellipse at 40% 20%, #0f3d55 0%, #071826 55%, #040e18 100%)",
        padding: "20px",
      }}
    >
      {/* Global full-viewport watermark — outside the clipped shell so it spans
          the entire screen. Uses position:fixed internally and sits at z-0
          behind everything. pointer-events-none so it never blocks clicks. */}
      <CoralAppBackground />

      {/* Outer shell — fills viewport with slight margin */}
      <motion.div
        initial={{ opacity: 0, scale: 0.985, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        className="w-full flex"
        style={{
          position: "relative",
          zIndex: 10,
          height: "calc(100vh - 40px)",
          maxWidth: "1400px",
          borderRadius: "20px",
          overflow: "hidden",
          boxShadow:
            "0 48px 140px rgba(2,8,18,0.75), 0 8px 32px rgba(2,8,18,0.50), 0 0 0 1px rgba(255,255,255,0.05)",
        }}
      >
        {/* Left sidebar — dark navy panel */}
        <Sidebar />

        {/* Right content — light glass panel */}
        <div
          className="relative flex-1 flex flex-col min-w-0"
          style={{
            background: "linear-gradient(160deg, rgba(240,249,252,0.97) 0%, rgba(248,253,255,0.99) 100%)",
            borderLeft: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          {/* Page content */}
          <div className="relative z-10 flex-1 flex flex-col min-h-0">
            <PageContent />
          </div>
        </div>
      </motion.div>

      {/* Floating "Ask Coral" launcher (hidden on chat page) */}
      <CoralFloatingButton />

      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            borderRadius: "14px",
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
