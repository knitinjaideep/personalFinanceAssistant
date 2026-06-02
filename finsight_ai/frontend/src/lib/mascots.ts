/**
 * Central mascot registry.
 *
 * ── How to swap artwork ──────────────────────────────────────────────────────
 * Overwrite the PNG at the `src` path in `frontend/public/mascots/`.
 * No code change needed.
 *
 * ── How to remap a route ─────────────────────────────────────────────────────
 * Edit `getMascotForRoute` below. It accepts either a URL pathname
 * ("/banking") or a Zustand `activePage` id ("banking", "overview", …).
 *
 * ── Why "main" shows everywhere right now ────────────────────────────────────
 * The variant routing code is correct. The seeded PNG files in
 * public/mascots/ are all copies of coral-main.png (identical bytes).
 * Drop your real variant art into that folder and the correct image will
 * appear automatically — no code change needed.
 */

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

/**
 * Convenience helper — falls back to main if variant is unknown.
 */
export function getMascotAsset(variant: CoralMascotVariant) {
  return coralMascots[variant] ?? coralMascots.main;
}

/**
 * Resolve the mascot variant for a given page.
 *
 * Accepts either a URL pathname ("/banking") or a bare Zustand `activePage`
 * id ("banking", "overview", …). Substring matching handles both forms.
 *
 * To change a mapping, edit the table below.
 */
export function getMascotForRoute(pathname: string): CoralMascotVariant {
  const p = pathname.toLowerCase();
  const has = (...keys: string[]) => keys.some((k) => p.includes(k));

  if (has("documents"))                          return "documents";
  if (has("analytics", "insights", "overview")) return "analytics";
  if (has("banking", "accounts", "subscriptions", "fees", "credit-cards")) return "banking";
  if (has("investments", "portfolio"))           return "investments";
  if (has("settings", "privacy", "security"))    return "security";
  // chat + everything else → main
  return "main";
}
