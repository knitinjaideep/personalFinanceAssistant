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
    <div className="flex h-screen bg-pearl text-slate overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <PageContent />
      </main>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            borderRadius: "14px",
            background: "#FAFAFA",
            color: "#2E2E2E",
            border: "1px solid #CDEDF6",
            boxShadow: "0 4px 24px rgba(11,60,93,0.08)",
            fontSize: "13px",
          },
          success: {
            iconTheme: { primary: "#4CAF93", secondary: "#FAFAFA" },
          },
          error: {
            iconTheme: { primary: "#E45757", secondary: "#FAFAFA" },
          },
        }}
      />
    </div>
  );
}
