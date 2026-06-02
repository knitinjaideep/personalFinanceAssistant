import { motion } from "framer-motion";
import { CoralImageFeatureCard } from "./CoralImageFeatureCard";
import { staggerContainer, staggerChild } from "../../design/motion";
import { useAppStore } from "../../store/appStore";

const CARDS = [
  {
    variant: "banking" as const,
    title: "Banking",
    description: "Credit cards, checking, savings, and cash flow.",
    actionLabel: "View banking",
    floatDelay: "0ms",
    page: "banking" as const,
  },
  {
    variant: "investments" as const,
    title: "Investments",
    description: "Portfolio value, holdings, and performance.",
    actionLabel: "View portfolio",
    floatDelay: "150ms",
    page: "investments" as const,
  },
  {
    variant: "documents" as const,
    title: "Documents",
    description: "Upload statements and track parsing.",
    actionLabel: "Manage documents",
    floatDelay: "300ms",
    page: "documents" as const,
  },
  {
    variant: "main" as const,
    title: "Chat",
    description: "Ask Coral about your finances in plain English.",
    actionLabel: "Open chat",
    floatDelay: "450ms",
    page: "chat" as const,
  },
] as const;

export function OverviewImageFeatureCards() {
  const setActivePage = useAppStore((s) => s.setActivePage);

  return (
    <motion.div
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
      className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4"
    >
      {CARDS.map((card) => (
        <motion.div key={card.variant} variants={staggerChild} className="flex">
          <CoralImageFeatureCard
            variant={card.variant}
            title={card.title}
            description={card.description}
            actionLabel={card.actionLabel}
            floatDelay={card.floatDelay}
            onAction={() => setActivePage(card.page)}
            className="flex-1"
          />
        </motion.div>
      ))}
    </motion.div>
  );
}
