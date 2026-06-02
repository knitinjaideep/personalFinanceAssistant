// Account normalization config for Coral's known financial accounts.
// Use fuzzy/alias matching against raw institution or account name strings.

export interface AccountConfig {
  key: string;
  displayName: string;
  institution: string;
  institutionKey: string;
  aliases: string[];
  bucket: "credit_card" | "checking" | "savings" | "investment";
}

export const CREDIT_CARD_ACCOUNTS: AccountConfig[] = [
  {
    key: "chase_freedom",
    displayName: "Chase Freedom",
    institution: "Chase",
    institutionKey: "chase",
    aliases: ["freedom", "chase freedom", "freedom unlimited", "chase freedom unlimited"],
    bucket: "credit_card",
  },
  {
    key: "chase_prime",
    displayName: "Chase Prime",
    institution: "Chase",
    institutionKey: "chase",
    aliases: ["prime", "amazon prime", "chase prime", "prime visa", "amazon prime visa"],
    bucket: "credit_card",
  },
  {
    key: "chase_sapphire",
    displayName: "Chase Sapphire Preferred",
    institution: "Chase",
    institutionKey: "chase",
    aliases: ["sapphire", "sapphire preferred", "csp", "chase sapphire", "chase sapphire preferred"],
    bucket: "credit_card",
  },
  {
    key: "amex_blue_cash",
    displayName: "Amex Blue Cash",
    institution: "American Express",
    institutionKey: "amex",
    aliases: ["blue cash", "amex blue cash", "american express blue cash", "blue cash everyday", "blue cash preferred"],
    bucket: "credit_card",
  },
  {
    key: "amex_gold",
    displayName: "Amex Gold",
    institution: "American Express",
    institutionKey: "amex",
    aliases: ["gold", "amex gold", "american express gold", "gold card"],
    bucket: "credit_card",
  },
  {
    key: "macys_credit",
    displayName: "Macy's Credit Card",
    institution: "Macy's",
    institutionKey: "macys",
    aliases: ["macys", "macy's", "macys credit card", "macy's credit card"],
    bucket: "credit_card",
  },
];

export const CHECKING_ACCOUNTS: AccountConfig[] = [
  {
    key: "chase_checking",
    displayName: "Chase Checking",
    institution: "Chase",
    institutionKey: "chase",
    aliases: ["chase checking", "chase total checking", "chase bank checking"],
    bucket: "checking",
  },
  {
    key: "bofa_checking",
    displayName: "Bank of America Checking",
    institution: "Bank of America",
    institutionKey: "bank_of_america",
    aliases: ["bofa", "bofa checking", "bank of america", "bank of america checking", "boa checking", "boa"],
    bucket: "checking",
  },
];

export const SAVINGS_ACCOUNTS: AccountConfig[] = [
  {
    key: "marcus_savings",
    displayName: "Marcus by Goldman Sachs",
    institution: "Goldman Sachs",
    institutionKey: "marcus",
    aliases: ["marcus", "goldman sachs", "marcus goldman sachs", "marcus by goldman sachs", "gs bank", "goldman"],
    bucket: "savings",
  },
];

export const INVESTMENT_ACCOUNTS: AccountConfig[] = [
  {
    key: "morgan_stanley",
    displayName: "Morgan Stanley",
    institution: "Morgan Stanley",
    institutionKey: "morgan_stanley",
    aliases: ["morgan stanley", "ms", "morgan_stanley"],
    bucket: "investment",
  },
  {
    key: "etrade",
    displayName: "E*TRADE",
    institution: "E*TRADE",
    institutionKey: "etrade",
    aliases: ["etrade", "e*trade", "e-trade", "e trade", "etrade financial"],
    bucket: "investment",
  },
];

export const ALL_ACCOUNTS: AccountConfig[] = [
  ...CREDIT_CARD_ACCOUNTS,
  ...CHECKING_ACCOUNTS,
  ...SAVINGS_ACCOUNTS,
  ...INVESTMENT_ACCOUNTS,
];

/** Normalize a raw name to lowercase trimmed for alias matching. */
export function normalizeName(name: string | null | undefined): string {
  return (name ?? "").toLowerCase().trim().replace(/[^a-z0-9\s]/g, "").replace(/\s+/g, " ");
}

/** Returns the AccountConfig that best matches the raw account/institution name, or null. */
export function matchAccount(
  rawName: string | null | undefined,
  pool: AccountConfig[] = ALL_ACCOUNTS,
): AccountConfig | null {
  const n = normalizeName(rawName);
  if (!n) return null;
  for (const acct of pool) {
    for (const alias of acct.aliases) {
      if (n.includes(normalizeName(alias)) || normalizeName(alias).includes(n)) {
        return acct;
      }
    }
  }
  return null;
}

/** Check if a raw institution name matches a given institution key. */
export function matchesInstitution(rawName: string | null | undefined, institutionKey: string): boolean {
  const n = normalizeName(rawName);
  const pool = ALL_ACCOUNTS.filter((a) => a.institutionKey === institutionKey);
  for (const acct of pool) {
    for (const alias of acct.aliases) {
      if (n.includes(normalizeName(alias)) || normalizeName(alias).includes(n)) return true;
    }
    if (n.includes(normalizeName(acct.institution))) return true;
  }
  return false;
}

/** IRA account type identifiers for investment account detection. */
export const IRA_KEYWORDS = ["ira", "roth", "rollover ira", "traditional ira", "individual retirement"];

export function isIRAAccount(name: string | null | undefined, accountType?: string | null): boolean {
  const n = normalizeName(name) + " " + normalizeName(accountType);
  return IRA_KEYWORDS.some((kw) => n.includes(kw));
}
