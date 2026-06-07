export type CoralMascotVariant =
  | "main"
  | "banking"
  | "investments"
  | "documents"
  | "analytics"
  | "security";

export const coralMascots = {
  main: {
    src: "/mascots/coral-main.png",
    alt: "Coral mascot",
  },
  banking: {
    src: "/mascots/coral-banking.png",
    alt: "Coral banking mascot",
  },
  investments: {
    src: "/mascots/coral-investments.png",
    alt: "Coral investment mascot",
  },
  documents: {
    src: "/mascots/coral-documents.png",
    alt: "Coral documents mascot",
  },
  analytics: {
    src: "/mascots/coral-analytics.png",
    alt: "Coral analytics mascot",
  },
  security: {
    src: "/mascots/coral-security.png",
    alt: "Coral security mascot",
  },
} as const satisfies Record<CoralMascotVariant, { src: string; alt: string }>;

export function getMascotAsset(variant: CoralMascotVariant) {
  return coralMascots[variant] ?? coralMascots.main;
}

export function getMascotForRoute(pathname: string): CoralMascotVariant {
  const p = pathname.toLowerCase();
  const has = (...keys: string[]) => keys.some((k) => p.includes(k));

  if (has("documents"))                                                     return "documents";
  if (has("analytics", "insights", "overview"))                            return "analytics";
  if (has("banking", "accounts", "subscriptions", "fees", "credit-cards")) return "banking";
  if (has("investments", "portfolio"))                                      return "investments";
  if (has("settings", "privacy", "security"))                              return "security";
  return "main";
}
