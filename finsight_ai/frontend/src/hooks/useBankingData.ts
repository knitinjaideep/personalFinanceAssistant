import { useEffect, useState, useCallback } from "react";
import { dashboardApi } from "../api/dashboard";
import type { BankingDashboard, CardSpend, Subscription, CashFlowMonth } from "../api/dashboard";
import {
  getLastNMonths,
  detectRecurringTransactions,
  type RawTransaction,
  type RecurringTransaction,
} from "../lib/financeDataAdapters";
import {
  matchAccount,
  CREDIT_CARD_ACCOUNTS,
  CHECKING_ACCOUNTS,
  SAVINGS_ACCOUNTS,
  type AccountConfig,
} from "../lib/accountMapping";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AccountDataHealth {
  hasTransactions: boolean;
  hasStatements: boolean;
  latestStatementDate: string | null;
  warning: string | null;
}

export interface CreditCardData {
  config: AccountConfig;
  cardSummary: CardSpend | null;
  transactions: RawTransaction[];
  recurringTransactions: RecurringTransaction[];
  dataHealth: AccountDataHealth;
}

export interface CheckingAccountData {
  config: AccountConfig;
  cardSummary: CardSpend | null;
  cashFlow: CashFlowMonth[];
  transactions: RawTransaction[];
  dataHealth: AccountDataHealth;
}

export interface SavingsAccountData {
  config: AccountConfig;
  cardSummary: CardSpend | null;
  cashFlow: CashFlowMonth[];
  transactions: RawTransaction[];
  dataHealth: AccountDataHealth;
}

export interface BankingDataResult {
  loading: boolean;
  error: string | null;
  raw: BankingDashboard | null;
  creditCards: CreditCardData[];
  checkingAccounts: CheckingAccountData[];
  savingsAccounts: SavingsAccountData[];
  subscriptions: Subscription[];
  globalCashFlow: CashFlowMonth[];
  last6Months: ReturnType<typeof getLastNMonths>;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeHealth(
  cardSummary: CardSpend | null,
  transactions: RawTransaction[],
): AccountDataHealth {
  const hasStatements = !!cardSummary?.latest_statement;
  const hasTransactions = transactions.length > 0;
  let warning: string | null = null;
  if (!hasStatements && !hasTransactions) {
    warning = "No data found. Upload or reprocess statements for this account.";
  } else if (hasStatements && !hasTransactions) {
    warning = "Statement found but no transactions were extracted. Try reprocessing.";
  }
  return {
    hasTransactions,
    hasStatements,
    latestStatementDate: cardSummary?.latest_statement ?? null,
    warning,
  };
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useBankingData(): BankingDataResult {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [raw, setRaw] = useState<BankingDashboard | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await dashboardApi.banking(12);
      setRaw(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load banking data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const last6Months = getLastNMonths(6);

  if (!raw) {
    const emptyHealth: AccountDataHealth = {
      hasTransactions: false,
      hasStatements: false,
      latestStatementDate: null,
      warning: "No data loaded yet.",
    };

    return {
      loading,
      error,
      raw: null,
      creditCards: CREDIT_CARD_ACCOUNTS.map((config) => ({
        config,
        cardSummary: null,
        transactions: [],
        recurringTransactions: [],
        dataHealth: emptyHealth,
      })),
      checkingAccounts: CHECKING_ACCOUNTS.map((config) => ({
        config,
        cardSummary: null,
        cashFlow: [],
        transactions: [],
        dataHealth: emptyHealth,
      })),
      savingsAccounts: SAVINGS_ACCOUNTS.map((config) => ({
        config,
        cardSummary: null,
        cashFlow: [],
        transactions: [],
        dataHealth: emptyHealth,
      })),
      subscriptions: [],
      globalCashFlow: [],
      last6Months,
    };
  }

  // Map card_summary entries to each known credit card config
  const creditCards: CreditCardData[] = CREDIT_CARD_ACCOUNTS.map((config) => {
    const cardSummary =
      raw.card_summary.find((cs) => {
        const matched = matchAccount(cs.product_label ?? cs.account_name, CREDIT_CARD_ACCOUNTS);
        return matched?.key === config.key;
      }) ?? null;

    return {
      config,
      cardSummary,
      transactions: [],
      recurringTransactions: detectRecurringTransactions(
        raw.card_summary
          .filter((cs) => {
            const matched = matchAccount(cs.product_label ?? cs.account_name, CREDIT_CARD_ACCOUNTS);
            return matched?.key === config.key;
          })
          .flatMap(() => []),
      ),
      dataHealth: makeHealth(cardSummary, []),
    };
  });

  const checkingAccounts: CheckingAccountData[] = CHECKING_ACCOUNTS.map((config) => {
    const cardSummary =
      raw.card_summary.find((cs) => {
        const matched = matchAccount(cs.product_label ?? cs.account_name, CHECKING_ACCOUNTS);
        return matched?.key === config.key;
      }) ?? null;

    const hasCashFlow = raw.cash_flow.some((m) => m.inflow > 0 || m.outflow > 0);
    const checkingHealth: AccountDataHealth = {
      hasTransactions: hasCashFlow,
      hasStatements: hasCashFlow,
      latestStatementDate: null,
      warning: hasCashFlow ? null : "No data found. Upload or reprocess statements for this account.",
    };

    return {
      config,
      cardSummary,
      cashFlow: raw.cash_flow,
      transactions: [],
      dataHealth: checkingHealth,
    };
  });

  const savingsAccounts: SavingsAccountData[] = SAVINGS_ACCOUNTS.map((config) => {
    const cardSummary =
      raw.card_summary.find((cs) => {
        const matched = matchAccount(cs.product_label ?? cs.account_name, SAVINGS_ACCOUNTS);
        return matched?.key === config.key;
      }) ?? null;

    return {
      config,
      cardSummary,
      cashFlow: raw.cash_flow,
      transactions: [],
      dataHealth: makeHealth(cardSummary, []),
    };
  });

  return {
    loading,
    error,
    raw,
    creditCards,
    checkingAccounts,
    savingsAccounts,
    subscriptions: raw.subscriptions ?? [],
    globalCashFlow: raw.cash_flow ?? [],
    last6Months,
  };
}
