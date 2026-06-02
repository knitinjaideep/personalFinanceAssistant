import { motion } from "framer-motion";
import { CreditCard, Landmark, PiggyBank, Lightbulb } from "lucide-react";
import { staggerContainer, staggerChild, contentPageVariants } from "../design/motion";
import { CoralMascot } from "../components/CoralMascot";
import { CoralEmptyState } from "../components/CoralEmptyState";
import { CoralLoadingState } from "../components/CoralLoadingState";
import { BankingAccordion } from "../components/banking/BankingAccordion";
import { CreditCardAccountPanel } from "../components/banking/CreditCardAccountPanel";
import { CheckingAccountPanel } from "../components/banking/CheckingAccountPanel";
import { SavingsAccountPanel } from "../components/banking/SavingsAccountPanel";
import { useBankingData } from "../hooks/useBankingData";
import { useAppStore } from "../store/appStore";

// ── Page header ───────────────────────────────────────────────────────────────

function PageHeader() {
  return (
    <div
      className="shrink-0 px-7 py-5"
      style={{
        borderBottom: "1px solid rgba(205,237,246,0.50)",
        background: "rgba(255,255,255,0.55)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      <div className="flex items-center gap-3">
        <CoralMascot variant="banking" size="sm" className="shrink-0" />
        <div>
          <h1 className="text-[18px] font-bold text-ocean-deep tracking-tight">Banking</h1>
          <p className="text-[12px] text-ocean/40 mt-0.5 font-medium">
            Cash flow, cards, payments, and recurring transactions
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Coral tip ─────────────────────────────────────────────────────────────────

function CoralTip({ message }: { message: string }) {
  return (
    <div
      className="flex items-start gap-2.5 rounded-xl px-4 py-3"
      style={{
        background: "rgba(95,168,211,0.08)",
        border: "1px solid rgba(95,168,211,0.22)",
      }}
    >
      <Lightbulb size={13} style={{ color: "#1F6F8B" }} className="shrink-0 mt-0.5" />
      <p className="text-[11.5px] text-ocean/60 leading-relaxed">{message}</p>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function BankingPage() {
  const setActivePage = useAppStore((s) => s.setActivePage);
  const {
    loading,
    creditCards,
    checkingAccounts,
    savingsAccounts,
    subscriptions,
    last6Months,
    raw,
  } = useBankingData();

  if (loading) {
    return (
      <div className="flex flex-col h-full">
        <PageHeader />
        <div className="flex-1 flex items-center justify-center">
          <CoralLoadingState variant="banking" message="Loading banking data…" />
        </div>
      </div>
    );
  }

  const hasAnyData = !!raw;

  const ccHasData = creditCards.some((c) => !!c.cardSummary);
  const checkingHasData = checkingAccounts.some((c) => !!c.cardSummary || c.cashFlow.length > 0);
  const savingsHasData = savingsAccounts.some((s) => !!s.cardSummary || s.cashFlow.length > 0);

  return (
    <div className="flex flex-col h-full">
      <PageHeader />

      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-4"
      >
        {/* Coral tip */}
        <motion.div variants={staggerChild}>
          <CoralTip message="Credit cards, checking, and savings are organized here. Expand each section to see spending trends, top transactions, and recurring charges." />
        </motion.div>

        {!hasAnyData && (
          <motion.div variants={staggerChild}>
            <div
              className="rounded-2xl"
              style={{ background: "rgba(255,255,255,0.65)", border: "1px dashed rgba(205,237,246,0.70)" }}
            >
              <CoralEmptyState
                variant="banking"
                title="No banking data yet"
                description="Upload Chase, Amex, Discover, or Bank of America statements to see spending trends and card activity."
                actionLabel="Upload documents"
                onAction={() => setActivePage("documents")}
              />
            </div>
          </motion.div>
        )}

        {/* ── Credit Cards accordion ─────────────────────────────────────── */}
        <motion.div variants={staggerChild}>
          <BankingAccordion
            title="Credit Cards"
            subtitle="Chase, Amex, and Macy's credit cards"
            badge={ccHasData ? `${creditCards.filter((c) => c.cardSummary).length} active` : "No data"}
            defaultOpen={ccHasData}
            accentColor="#FF7A5A"
          >
            <div className="flex items-center gap-1.5 mb-3 mt-1">
              <CreditCard size={12} style={{ color: "#FF7A5A" }} />
              <span className="text-[11px] font-semibold text-ocean/40 uppercase tracking-wide">
                {creditCards.length} accounts configured
              </span>
            </div>

            <motion.div
              variants={staggerContainer}
              initial="hidden"
              animate="visible"
              className="space-y-3"
            >
              {creditCards.map((card) => (
                <motion.div key={card.config.key} variants={staggerChild}>
                  <CreditCardAccountPanel
                    data={card}
                    subscriptions={subscriptions}
                    last6Months={last6Months}
                  />
                </motion.div>
              ))}
            </motion.div>
          </BankingAccordion>
        </motion.div>

        {/* ── Checking accordion ─────────────────────────────────────────── */}
        <motion.div variants={staggerChild}>
          <BankingAccordion
            title="Checking"
            subtitle="Chase and Bank of America checking accounts"
            badge={checkingHasData ? "Active" : "No data"}
            defaultOpen={checkingHasData}
            accentColor="#1F6F8B"
          >
            <div className="flex items-center gap-1.5 mb-3 mt-1">
              <Landmark size={12} style={{ color: "#1F6F8B" }} />
              <span className="text-[11px] font-semibold text-ocean/40 uppercase tracking-wide">
                {checkingAccounts.length} accounts configured
              </span>
            </div>

            <motion.div
              variants={staggerContainer}
              initial="hidden"
              animate="visible"
              className="grid grid-cols-1 lg:grid-cols-2 gap-3"
            >
              {checkingAccounts.map((acct) => (
                <motion.div key={acct.config.key} variants={staggerChild}>
                  <CheckingAccountPanel data={acct} last6Months={last6Months} />
                </motion.div>
              ))}
            </motion.div>
          </BankingAccordion>
        </motion.div>

        {/* ── Savings accordion ──────────────────────────────────────────── */}
        <motion.div variants={staggerChild}>
          <BankingAccordion
            title="Savings"
            subtitle="Marcus by Goldman Sachs high-yield savings"
            badge={savingsHasData ? "Active" : "No data"}
            defaultOpen={savingsHasData}
            accentColor="#4CAF93"
          >
            <div className="flex items-center gap-1.5 mb-3 mt-1">
              <PiggyBank size={12} style={{ color: "#4CAF93" }} />
              <span className="text-[11px] font-semibold text-ocean/40 uppercase tracking-wide">
                Marcus Goldman Sachs
              </span>
            </div>

            <motion.div
              variants={staggerContainer}
              initial="hidden"
              animate="visible"
              className="space-y-3"
            >
              {savingsAccounts.map((acct) => (
                <motion.div key={acct.config.key} variants={staggerChild}>
                  <SavingsAccountPanel data={acct} last6Months={last6Months} />
                </motion.div>
              ))}
            </motion.div>
          </BankingAccordion>
        </motion.div>

        <div className="h-3" />
      </motion.div>
    </div>
  );
}
