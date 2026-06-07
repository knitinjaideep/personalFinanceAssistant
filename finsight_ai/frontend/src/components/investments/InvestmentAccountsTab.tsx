import { useState } from "react";
import { DashboardEmptyState } from "../dashboard/DashboardEmptyState";
import { InvestmentAccountCardItem } from "./InvestmentAccountCard";
import { InvestmentAccountDetailDrawer } from "./InvestmentAccountDetailDrawer";
import type { InvestmentAccountCard } from "../../lib/investmentsDashboard";
import type { Holding } from "../../api/dashboard";

interface Props {
  accountCards: InvestmentAccountCard[];
  holdings: Holding[];
  onAskCoral?: () => void;
  onViewDocuments?: () => void;
}

export function InvestmentAccountsTab({ accountCards, holdings, onAskCoral, onViewDocuments }: Props) {
  const [selectedCard, setSelectedCard] = useState<InvestmentAccountCard | null>(null);

  if (accountCards.length === 0) {
    return (
      <DashboardEmptyState
        title="No investment accounts"
        description="Upload Morgan Stanley or E*TRADE statements to see your investment accounts."
        primaryAction={onViewDocuments ? { label: "Upload Statements", onClick: onViewDocuments } : undefined}
      />
    );
  }

  const iraCards = accountCards.filter((c) => c.isIRA);
  const brokerageCards = accountCards.filter((c) => !c.isIRA);

  return (
    <>
      <div className="space-y-6">
        {brokerageCards.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide mb-3" style={{ color: "var(--text-muted)" }}>
              Brokerage Accounts
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {brokerageCards.map((card, i) => (
                <InvestmentAccountCardItem
                  key={i}
                  card={card}
                  onClick={() => setSelectedCard(card)}
                />
              ))}
            </div>
          </div>
        )}

        {iraCards.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide mb-3" style={{ color: "var(--text-muted)" }}>
              IRA / Retirement Accounts
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {iraCards.map((card, i) => (
                <InvestmentAccountCardItem
                  key={i}
                  card={card}
                  onClick={() => setSelectedCard(card)}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      <InvestmentAccountDetailDrawer
        card={selectedCard}
        holdings={holdings}
        open={!!selectedCard}
        onClose={() => setSelectedCard(null)}
        onAskCoral={onAskCoral}
        onViewDocuments={onViewDocuments}
      />
    </>
  );
}
