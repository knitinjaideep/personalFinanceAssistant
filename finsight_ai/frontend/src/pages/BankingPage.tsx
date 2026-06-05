import { motion } from "framer-motion";
import { CreditCard, Landmark, PiggyBank } from "lucide-react";
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

// ── Underwater page header ────────────────────────────────────────────────────

function PageHeader() {
  return (
    <div className="shrink-0 px-8 pt-10 pb-4">
      <div className="flex items-center gap-4">
        <CoralMascot variant="banking" size="sm" className="shrink-0" />
        <div>
          <h1 className="text-[22px] font-extrabold tracking-tight leading-none" style={{ color: "var(--text-primary)" }}>
            Banking
          </h1>
          <p className="text-[12px] mt-1 font-medium" style={{ color: "var(--text-secondary)" }}>
            Credit cards, checking, savings, and cash flow.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Accordion wrapper ─────────────────────────────────────────────────────────

function AccordionWrapper({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="rounded-3xl overflow-hidden"
      style={{
        background: "var(--panel-bg)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: "1px solid var(--panel-border)",
      }}
    >
      {children}
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
      <div className="flex flex-col min-h-full">
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
    <div className="flex flex-col min-h-full">
      <PageHeader />

      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-4"
      >
        {!hasAnyData && (
          <motion.div variants={staggerChild}>
            <div
              className="rounded-3xl"
              style={{
                background: "var(--panel-bg)",
                backdropFilter: "blur(16px)",
                WebkitBackdropFilter: "blur(16px)",
                border: "1px dashed var(--empty-border)",
              }}
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
          <AccordionWrapper>
            <BankingAccordion
              title="Credit Cards"
              subtitle="Chase, Amex, and Macy's credit cards"
              badge={ccHasData ? `${creditCards.filter((c) => c.cardSummary).length} active` : "No data"}
              defaultOpen={ccHasData}
              accentColor="#FF7A5A"
            >
              <div className="flex items-center gap-1.5 mb-3 mt-1">
                <CreditCard size={12} style={{ color: "#FF7A5A" }} />
                <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
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
          </AccordionWrapper>
        </motion.div>

        {/* ── Checking accordion ─────────────────────────────────────────── */}
        <motion.div variants={staggerChild}>
          <AccordionWrapper>
            <BankingAccordion
              title="Checking"
              subtitle="Chase and Bank of America checking accounts"
              badge={checkingHasData ? "Active" : "No data"}
              defaultOpen={checkingHasData}
              accentColor="#22d3ee"
            >
              <div className="flex items-center gap-1.5 mb-3 mt-1">
                <Landmark size={12} style={{ color: "#22d3ee" }} />
                <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
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
          </AccordionWrapper>
        </motion.div>

        {/* ── Savings accordion ──────────────────────────────────────────── */}
        <motion.div variants={staggerChild}>
          <AccordionWrapper>
            <BankingAccordion
              title="Savings"
              subtitle="Marcus by Goldman Sachs high-yield savings"
              badge={savingsHasData ? "Active" : "No data"}
              defaultOpen={savingsHasData}
              accentColor="#4CAF93"
            >
              <div className="flex items-center gap-1.5 mb-3 mt-1">
                <PiggyBank size={12} style={{ color: "#4CAF93" }} />
                <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
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
          </AccordionWrapper>
        </motion.div>

        <div className="h-3" />
      </motion.div>
    </div>
  );
}
