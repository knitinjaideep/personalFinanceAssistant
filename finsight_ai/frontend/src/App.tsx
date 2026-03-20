import { Toaster } from "react-hot-toast";
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
    <div className="flex h-screen text-slate overflow-hidden" style={{ background: "#0B3C5D" }}>
      <Sidebar />
      <main className="flex-1 overflow-hidden flex flex-col">
        <PageContent />
      </main>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            borderRadius: "16px",
            background: "rgba(255,255,255,0.92)",
            backdropFilter: "blur(12px)",
            color: "#0B3C5D",
            border: "1px solid rgba(205,237,246,0.7)",
            boxShadow: "0 8px 32px rgba(11,60,93,0.12)",
            fontSize: "13px",
            fontWeight: "500",
          },
          success: {
            iconTheme: { primary: "#4CAF93", secondary: "white" },
          },
          error: {
            iconTheme: { primary: "#E45757", secondary: "white" },
          },
        }}
      />
    </div>
  );
}
