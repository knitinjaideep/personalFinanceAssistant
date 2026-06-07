import { useState } from "react";
import { motion } from "framer-motion";
import { contentPageVariants } from "../design/motion";
import { CoralMascot } from "../components/CoralMascot";
import { CoralLoadingState } from "../components/CoralLoadingState";
import { DashboardTabs } from "../components/dashboard/DashboardTabs";
import { InvestmentDataFreshness } from "../components/investments/InvestmentDataFreshness";
import { InvestmentsOverviewTab } from "../components/investments/InvestmentsOverviewTab";
import { InvestmentAccountsTab } from "../components/investments/InvestmentAccountsTab";
import { InvestmentHoldingsTab } from "../components/investments/InvestmentHoldingsTab";
import { InvestmentActivityTab } from "../components/investments/InvestmentActivityTab";
import { InvestmentStatementsTab } from "../components/investments/InvestmentStatementsTab";
import { useInvestmentData } from "../hooks/useInvestmentData";
import { useAppStore } from "../store/appStore";
import {
  buildInvestmentMetrics,
  buildInvestmentInsights,
  buildInvestmentFreshness,
  buildInvestmentAccountCards,
  buildPortfolioAllocation,
  buildPortfolioTrend,
  buildTopHoldings,
  buildInvestmentActivity,
  buildInvestmentCoverageRows,
} from "../lib/investmentsDashboard";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "accounts", label: "Accounts" },
  { key: "holdings", label: "Holdings" },
  { key: "activity", label: "Activity" },
  { key: "statements", label: "Statements" },
];

// ── Page header ───────────────────────────────────────────────────────────────

function PageHeader() {
  return (
    <div className="shrink-0 px-8 pt-10 pb-5 relative">
      <span aria-hidden className="glitter-star" style={{ background: "rgba(34,211,238,0.85)", top: "22%", left: "55%" }} />
      <span aria-hidden className="glitter-star" style={{ background: "rgba(255,122,90,0.75)", top: "70%", left: "80%" }} />
      <div className="flex items-center gap-4">
        <CoralMascot variant="investments" size="sm" className="shrink-0" />
        <div>
          <h1 className="text-2xl xl:text-3xl font-extrabold tracking-tight leading-none aurora-heading">
            Investments
          </h1>
          <p className="coral-muted mt-1.5" style={{ color: "var(--text-secondary)" }}>
            Portfolio value, retirement accounts, and long-term savings.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function InvestmentsPage() {
  const setActivePage = useAppStore((s) => s.setActivePage);
  const [activeTab, setActiveTab] = useState("overview");

  const { loading, raw } = useInvestmentData();

  if (loading) {
    return (
      <div className="flex flex-col min-h-full">
        <PageHeader />
        <div className="flex-1 flex items-center justify-center">
          <CoralLoadingState variant="investments" message="Loading portfolio data…" />
        </div>
      </div>
    );
  }

  // Compute dashboard data
  const metrics = buildInvestmentMetrics(raw);
  const insights = buildInvestmentInsights(raw);
  const freshnessItems = buildInvestmentFreshness(raw);
  const accountCards = buildInvestmentAccountCards(raw);
  const allocation = buildPortfolioAllocation(raw);
  const trendData = buildPortfolioTrend(raw, 12);
  const holdings = buildTopHoldings(raw, 50);
  const activity = buildInvestmentActivity(raw);
  const coverageRows = buildInvestmentCoverageRows(raw);

  const accountsDetected = accountCards.length;

  const handleAskCoral = () => setActivePage("chat");
  const handleDocuments = () => setActivePage("documents");

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader />

      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 pb-8 space-y-4"
      >
        {/* Data freshness strip */}
        <InvestmentDataFreshness
          items={freshnessItems}
          accountsDetected={accountsDetected}
        />

        {/* Tabs */}
        <DashboardTabs tabs={TABS} active={activeTab} onChange={setActiveTab} />

        {/* Tab content */}
        {activeTab === "overview" && (
          <InvestmentsOverviewTab
            metrics={metrics}
            insights={insights}
            accountCards={accountCards}
            allocation={allocation}
            trendData={trendData}
            holdings={holdings}
            onDocuments={handleDocuments}
            onAskCoral={handleAskCoral}
          />
        )}

        {activeTab === "accounts" && (
          <InvestmentAccountsTab
            accountCards={accountCards}
            holdings={holdings}
            onAskCoral={handleAskCoral}
            onViewDocuments={handleDocuments}
          />
        )}

        {activeTab === "holdings" && (
          <InvestmentHoldingsTab
            holdings={holdings}
            onDocuments={handleDocuments}
          />
        )}

        {activeTab === "activity" && (
          <InvestmentActivityTab
            activity={activity}
            onDocuments={handleDocuments}
          />
        )}

        {activeTab === "statements" && (
          <InvestmentStatementsTab
            rows={coverageRows}
            onDocuments={handleDocuments}
          />
        )}

        <div className="h-4" />
      </motion.div>
    </div>
  );
}
