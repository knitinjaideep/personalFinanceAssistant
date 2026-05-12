import { Toaster } from "react-hot-toast";
import { motion } from "framer-motion";
import { ChatPage } from "./pages/ChatPage";

export default function App() {
  return (
    <div
      className="min-h-screen w-full flex items-center justify-center p-4 lg:p-6 overflow-hidden"
      style={{
        background: "radial-gradient(ellipse at 50% 30%, #1a5e7a 0%, #0B3C5D 45%, #061e2f 100%)",
      }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.985, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        className="w-full flex flex-col"
        style={{
          maxWidth: "860px",
          height: "calc(100vh - 48px)",
          borderRadius: "28px",
          overflow: "hidden",
          background: "linear-gradient(160deg, rgba(240,249,252,0.97) 0%, rgba(248,253,255,0.99) 100%)",
          border: "1px solid rgba(255,255,255,0.07)",
          boxShadow:
            "0 40px 120px rgba(4,14,26,0.65), 0 8px 32px rgba(4,14,26,0.40), 0 0 0 1px rgba(255,255,255,0.04)",
        }}
      >
        <ChatPage />
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
