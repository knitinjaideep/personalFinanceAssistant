import React from "react";
import { Toaster } from "react-hot-toast";
import { Sidebar } from "./components/layout/Sidebar";
import { DocumentUpload } from "./components/upload/DocumentUpload";
import { ChatInterface } from "./components/chat/ChatInterface";
import { MetricsPage } from "./pages/MetricsPage";
import { StatementList } from "./components/statements/StatementList";
import { FeeChart } from "./components/analytics/FeeChart";
import { BalanceTimeline } from "./components/analytics/BalanceTimeline";
import { useAppStore } from "./store/appStore";

function AnalyticsDashboard() {
  return (
    <div className="p-6 space-y-8 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold text-gray-900">Analytics</h1>

      <section>
        <h2 className="text-sm font-medium text-gray-700 mb-3">Fee Analysis (Last 6 Months)</h2>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <FeeChart />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-medium text-gray-700 mb-3">Balance History</h2>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <BalanceTimeline />
        </div>
      </section>
    </div>
  );
}

function StatementsPage() {
  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold text-gray-900 mb-4">Statements</h1>
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <StatementList />
      </div>
    </div>
  );
}

function PageContent() {
  const { activePage } = useAppStore();
  switch (activePage) {
    case "upload":
      return <DocumentUpload />;
    case "statements":
      return <StatementsPage />;
    case "chat":
      return <ChatInterface />;
    case "analytics":
      return <AnalyticsDashboard />;
    case "metrics":
      return <MetricsPage />;
    default:
      return <DocumentUpload />;
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
