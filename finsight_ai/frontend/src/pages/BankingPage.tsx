import { useState } from "react";
import { motion } from "framer-motion";
import { contentPageVariants } from "../design/motion";
import { CoralMascot } from "../components/CoralMascot";
import { CoralLoadingState } from "../components/CoralLoadingState";
import { DashboardTabs } from "../components/dashboard/DashboardTabs";
import { BankingDataFreshness } from "../components/banking/BankingDataFreshness";
import { BankingOverviewTab } from "../components/banking/BankingOverviewTab";
import { BankingAccountsTab } from "../components/banking/BankingAccountsTab";
import { BankingRecurringTab } from "../components/banking/BankingRecurringTab";
import { BankingTransactionsTab } from "../components/banking/BankingTransactionsTab";
import { BankingStatementsTab } from "../components/banking/BankingStatementsTab";
import { useBankingData } from "../hooks/useBankingData";
import { useAppStore } from "../store/appStore";
import {
  buildBankingMetrics,
  buildBankingInsights,
  buildBankingFreshness,
  buildCreditCardRows,
  buildCheckingRows,
  buildSavingsRows,
  buildMonthlySpendChart,
  buildCashFlowChart,
  buildStatementCoverageGrid,
  getSubscriptions,
} from "../lib/bankingDashboard";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "accounts", label: "Accounts" },
  { key: "recurring", label: "Recurring" },
  { key: "transactions", label: "Transactions" },
  { key: "statements", label: "Statements" },
];

// ── Page header ───────────────────────────────────────────────────────────────

function PageHeader() {
  return (
    <div className="shrink-0 px-8 pt-10 pb-5">
      <div className="flex items-center gap-4">
        <CoralMascot variant="banking" size="sm" className="shrink-0" />
        <div>
          <h1
            className="text-2xl xl:text-3xl font-extrabold tracking-tight leading-none"
            style={{ color: "var(--text-primary)" }}
          >
            Banking
          </h1>
          <p className="coral-muted mt-1.5" style={{ color: "var(--text-secondary)" }}>
            Checking, savings, credit cards, and monthly cash flow.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function BankingPage() {
  const setActivePage = useAppStore((s) => s.setActivePage);
  const [activeTab, setActiveTab] = useState("overview");

  const { loading, raw } = useBankingData();

  if (loading) {
    return (
      <div className="flex flex-col min-h-full">
        <PageHeader />
        <div className="flex-1 flex items-center justify-center">
          <CoralLoadingState variant="banking" message="Loading banking data…" />
        </div>
      </div>
    );
  }

  // Compute dashboard data
  const metrics = buildBankingMetrics(raw);
  const insights = buildBankingInsights(raw);
  const freshnessItems = buildBankingFreshness(raw);
  const creditCardRows = buildCreditCardRows(raw);
  const checkingRows = buildCheckingRows(raw);
  const savingsRows = buildSavingsRows(raw);
  const spendChart = buildMonthlySpendChart(raw, 6);
  const cashFlowChart = buildCashFlowChart(raw, 6);
  const { months: coverageMonths, rows: coverageRows } = buildStatementCoverageGrid(raw, 12);
  const subscriptions = getSubscriptions(raw);

  const parsedCount = raw?.coverage?.reduce((s, c) => s + (c.doc_count ?? 0), 0) ?? 0;
  const accountsDetected = (raw?.card_summary?.length ?? 0);

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
        <BankingDataFreshness
          items={freshnessItems}
          parsedCount={parsedCount}
          accountsDetected={accountsDetected}
        />

        {/* Tabs */}
        <DashboardTabs tabs={TABS} active={activeTab} onChange={setActiveTab} />

        {/* Tab content */}
        {activeTab === "overview" && (
          <BankingOverviewTab
            metrics={metrics}
            insights={insights}
            spendChart={spendChart}
            cashFlowChart={cashFlowChart}
            creditCardRows={creditCardRows}
            checkingRows={checkingRows}
            savingsRows={savingsRows}
            onTabChange={setActiveTab}
            onDocuments={handleDocuments}
          />
        )}

        {activeTab === "accounts" && (
          <BankingAccountsTab
            creditCardRows={creditCardRows}
            checkingRows={checkingRows}
            savingsRows={savingsRows}
            onAskCoral={handleAskCoral}
            onViewDocuments={handleDocuments}
          />
        )}

        {activeTab === "recurring" && (
          <BankingRecurringTab
            subscriptions={subscriptions}
            onDocuments={handleDocuments}
          />
        )}

        {activeTab === "transactions" && (
          <BankingTransactionsTab
            raw={raw}
            onDocuments={handleDocuments}
          />
        )}

        {activeTab === "statements" && (
          <BankingStatementsTab
            months={coverageMonths}
            rows={coverageRows}
            onDocuments={handleDocuments}
          />
        )}

        <div className="h-4" />
      </motion.div>
    </div>
  );
}
