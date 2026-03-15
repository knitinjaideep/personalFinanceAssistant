import { Toaster } from "react-hot-toast";
import { Sidebar } from "./components/layout/Sidebar";
import { ChatInterface } from "./components/chat/ChatInterface";
import { HomePage } from "./pages/HomePage";
import { useAppStore } from "./store/appStore";

function PageContent() {
  const { activePage } = useAppStore();
  switch (activePage) {
    case "home":
      return <HomePage />;
    case "chat":
      return <ChatInterface />;
    default:
      return <HomePage />;
  }
}

export default function App() {
  return (
    <div className="flex h-screen bg-gray-50 text-gray-900 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <PageContent />
      </main>
      <Toaster position="top-right" />
    </div>
  );
}
