import { BankingAccountGroup } from "./BankingAccountGroup";
import type { BankingAccountRow } from "../../lib/bankingDashboard";

interface Props {
  creditCardRows: BankingAccountRow[];
  checkingRows: BankingAccountRow[];
  savingsRows: BankingAccountRow[];
  onAskCoral?: () => void;
  onViewDocuments?: () => void;
}

export function BankingAccountsTab({
  creditCardRows,
  checkingRows,
  savingsRows,
  onAskCoral,
  onViewDocuments,
}: Props) {
  return (
    <div className="space-y-3">
      <BankingAccountGroup
        title="Credit Cards"
        subtitle="Chase, American Express, and Macy's credit cards"
        rows={creditCardRows}
        accentColor="#FF7A5A"
        defaultOpen={true}
        onAskCoral={onAskCoral}
        onViewDocuments={onViewDocuments}
      />
      <BankingAccountGroup
        title="Checking"
        subtitle="Chase and Bank of America checking accounts"
        rows={checkingRows}
        accentColor="#22d3ee"
        defaultOpen={false}
        showCashFlow={true}
        onAskCoral={onAskCoral}
        onViewDocuments={onViewDocuments}
      />
      <BankingAccountGroup
        title="Savings"
        subtitle="Marcus by Goldman Sachs high-yield savings"
        rows={savingsRows}
        accentColor="#4CAF93"
        defaultOpen={false}
        showCashFlow={true}
        onAskCoral={onAskCoral}
        onViewDocuments={onViewDocuments}
      />
    </div>
  );
}
