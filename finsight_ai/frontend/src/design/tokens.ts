// Design tokens — Coral ocean theme
// Keep all visual constants here for maintainability

export const COLORS = {
  coral: {
    DEFAULT: "#FF7A5A",
    light: "#FFA38F",
    50: "#FFF5F2",
    100: "#FFE8E2",
  },
  ocean: {
    deep: "#0B3C5D",
    DEFAULT: "#1F6F8B",
    sea: "#5FA8D3",
    aqua: "#CDEDF6",
    50: "#F0F9FC",
  },
  sand: {
    DEFAULT: "#F5E6CA",
    50: "#FDF9F1",
  },
  pearl: "#FAFAFA",
  slate: "#2E2E2E",
  positive: "#4CAF93",
  negative: "#E45757",
  highlight: "#FFD166",
} as const;

export const GRADIENTS = {
  coral: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
  ocean: "linear-gradient(180deg, #0B3C5D, #1F6F8B)",
  light: "linear-gradient(180deg, #CDEDF6, #FAFAFA)",
  sidebar: "linear-gradient(180deg, #0B3C5D 0%, #1F6F8B 100%)",
} as const;

export const INSTITUTION_LABELS: Record<string, string> = {
  morgan_stanley: "Morgan Stanley",
  chase: "Chase",
  etrade: "E*TRADE",
  amex: "Amex",
  discover: "Discover",
  unknown: "Unknown",
};

export const INSTITUTION_COLORS: Record<string, string> = {
  morgan_stanley: "bg-ocean-50 text-ocean border-ocean-200",
  chase: "bg-ocean-50 text-ocean border-ocean-100",
  etrade: "bg-ocean-50 text-positive border-ocean-100",
  amex: "bg-sand-50 text-ocean border-sand-100",
  discover: "bg-coral-50 text-coral border-coral-100",
  unknown: "bg-ocean-50 text-ocean border-ocean-100",
};
