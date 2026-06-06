/**
 * Coral color palette — single source of truth for all color values.
 *
 * Structure:
 *   RAW        — base hex values, no opacity
 *   OPACITY    — pre-computed rgba helpers keyed by alpha
 *   DARK/LIGHT — semantic tokens that map to CSS variables in index.css
 *   CHARTS     — ordered palettes for data visualizations
 *   TAILWIND   — Tailwind class strings for institution/status badges
 */

// ── Raw base colors ────────────────────────────────────────────────────────────

export const RAW = {
  // Brand
  coral:      "#FF7A5A",
  coralLight: "#FFA38F",
  coralDeep:  "#E8522E",

  // Ocean scale (dark → light)
  oceanDeep: "#0B3C5D",
  ocean:     "#1F6F8B",
  oceanSea:  "#5FA8D3",
  oceanAqua: "#CDEDF6",

  // Teal accent (CSS `rgba(34,211,238,...)`)
  teal:      "#22d3ee",
  tealLight: "#67e8f9",
  tealDeep:  "#0891b2",

  // Neutrals
  sand:  "#F5E6CA",
  pearl: "#FAFAFA",
  slate: "#2E2E2E",

  // Dark base (CSS `rgba(3,17,31,...)`)
  navyBase:    "#03111f",
  navyMid:     "#05182e",
  navyDeep:    "#020d18",

  // Semantic
  positive:  "#3db886",
  negative:  "#E45757",
  highlight: "#FFD166",

  // Light mode base
  lightBase: "#F4FBFF",
  lightText: "#071F33",
} as const;

// ── Opacity helpers ────────────────────────────────────────────────────────────

const tealOpacity    = (a: number) => `rgba(34,211,238,${a})`;
const navyOpacity    = (a: number) => `rgba(3,17,31,${a})`;
const whiteOpacity   = (a: number) => `rgba(255,255,255,${a})`;
const coralOpacity   = (a: number) => `rgba(255,122,90,${a})`;
const oceanOpacity   = (a: number) => `rgba(31,111,139,${a})`;
const lightTextOpacity = (a: number) => `rgba(7,31,51,${a})`;
const iceOpacity     = (a: number) => `rgba(248,252,255,${a})`;

export const OPACITY = {
  teal:      tealOpacity,
  navy:      navyOpacity,
  white:     whiteOpacity,
  coral:     coralOpacity,
  ocean:     oceanOpacity,
  lightText: lightTextOpacity,
  ice:       iceOpacity,
} as const;

// ── Semantic tokens — dark mode (matches :root / [data-theme="dark"] in index.css) ──

export const DARK = {
  // Backgrounds
  bgBase:    RAW.navyBase,
  bgSidebar: "linear-gradient(180deg, rgba(3,17,31,0.94) 0%, rgba(4,22,40,0.92) 100%)",

  // Text — improved contrast
  textPrimary:   iceOpacity(0.96),
  textSecondary: "rgba(220,242,250,0.78)",
  textMuted:     "rgba(190,220,232,0.62)",
  textDim:       "rgba(160,190,205,0.48)",
  headingPrimary:   iceOpacity(0.98),
  headingSecondary: "rgba(220,242,250,0.88)",
  textStrong:    iceOpacity(1.0),
  textOnAccent:  RAW.navyBase,

  // Glow accents
  coralGlow:  "rgba(255,122,90,0.30)",
  aquaGlow:   "rgba(34,211,238,0.28)",

  // Borders
  borderSubtle: tealOpacity(0.12),
  borderAccent: tealOpacity(0.24),

  // Glass surfaces
  glassBg:       navyOpacity(0.60),
  glassDarkBg:   navyOpacity(0.78),
  glassLightBg:  whiteOpacity(0.06),
  glassHighlight: whiteOpacity(0.04),
  cardInnerGlow:  tealOpacity(0.04),

  // Cards
  cardBg:         "rgba(5,24,42,0.72)",
  cardShadow:     navyOpacity(0.55),
  cardHoverShadow: navyOpacity(0.70),

  // Focus
  focusRing: tealOpacity(0.55),

  // Overlays
  overlayDark:  navyOpacity(0.30),
  overlayMid:   navyOpacity(0.15),
  overlayHeavy: navyOpacity(0.80),
  accentRay:    tealOpacity(0.16),
  vignette:     navyOpacity(0.60),

  // Buttons
  btnGlassBg:      whiteOpacity(0.09),
  btnGlassBorder:  whiteOpacity(0.16),
  btnGlassColor:   iceOpacity(0.85),
  btnGlassHoverBg: whiteOpacity(0.14),

  // Panels
  panelBg:           "rgba(6,28,48,0.68)",
  panelBgAlt:        "rgba(8,35,58,0.74)",
  panelBorder:       tealOpacity(0.10),
  panelBorderAccent: tealOpacity(0.16),

  // Rows
  rowBg:           whiteOpacity(0.055),
  rowBorder:       tealOpacity(0.12),
  rowBorderStrong: tealOpacity(0.18),

  // Accordion
  accordionOpenBg: tealOpacity(0.06),

  // Charts / tables
  chartAxis:   "rgba(220,242,250,0.55)",
  chartGrid:   tealOpacity(0.08),
  tableHead:   "rgba(220,242,250,0.70)",
  tableRowAlt: tealOpacity(0.06),

  // Empty / skeleton
  emptyBg:     tealOpacity(0.04),
  emptyBorder: tealOpacity(0.20),
  emptyIcon:   whiteOpacity(0.22),
  emptyText:   "rgba(220,242,250,0.60)",

  // Status softened
  successSoft:  "rgba(61,184,134,0.12)",
  warningSoft:  "rgba(255,209,102,0.10)",
  dangerSoft:   "rgba(228,87,87,0.10)",

  // Insight strip
  insightBg:     tealOpacity(0.07),
  insightBorder: tealOpacity(0.18),

  // Warning strip
  warnBg:     "rgba(255,209,102,0.09)",
  warnBorder: "rgba(255,209,102,0.24)",
  warnText:   "rgba(255,224,130,0.88)",

  // Chat answer card
  answerBg:             "rgba(5,20,36,0.75)",
  answerBorder:         tealOpacity(0.20),
  answerDivider:        tealOpacity(0.12),
  answerMetricBg:       tealOpacity(0.05),
  answerSqlBg:          navyOpacity(0.65),
  answerFollowupBg:     tealOpacity(0.09),
  answerFollowupBorder: tealOpacity(0.22),
  answerFollowupColor:  tealOpacity(0.82),

  // Modals
  modalOverlay: navyOpacity(0.80),
  modalBg:      "rgba(5,20,36,0.94)",
  modalBorder:  tealOpacity(0.20),

  // Misc
  privacyBg:      tealOpacity(0.07),
  privacyBorder:  tealOpacity(0.16),
  uploadBg:       navyOpacity(0.58),
  scrollbarThumb: tealOpacity(0.28),
  scrollbarHover: tealOpacity(0.48),
  toastBg:        "rgba(4,18,34,0.94)",
  toastBorder:    tealOpacity(0.22),
  footerBg:       whiteOpacity(0.03),
  footerBorder:   whiteOpacity(0.06),
} as const;

// ── Semantic tokens — light mode (matches [data-theme="light"] in index.css) ──

export const LIGHT = {
  // Backgrounds
  bgBase:    RAW.lightBase,
  bgSidebar: "linear-gradient(180deg, rgba(244,251,255,0.97) 0%, rgba(220,242,252,0.95) 100%)",

  // Text — strong readable navy
  textPrimary:   lightTextOpacity(0.96),
  textSecondary: "rgba(14,55,82,0.78)",
  textMuted:     "rgba(29,78,105,0.62)",
  textDim:       "rgba(50,95,120,0.48)",
  headingPrimary:   lightTextOpacity(0.98),
  headingSecondary: "rgba(14,55,82,0.90)",
  textStrong:    lightTextOpacity(1.0),
  textOnAccent:  "#FFFFFF",

  // Glow accents
  coralGlow: "rgba(255,122,90,0.22)",
  aquaGlow:  "rgba(31,111,139,0.18)",

  // Borders
  borderSubtle: oceanOpacity(0.16),
  borderAccent: oceanOpacity(0.28),

  // Glass surfaces
  glassBg:        "rgba(255,255,255,0.76)",
  glassDarkBg:    "rgba(255,255,255,0.88)",
  glassLightBg:   oceanOpacity(0.06),
  glassHighlight: whiteOpacity(0.60),
  cardInnerGlow:  oceanOpacity(0.04),

  // Cards
  cardBg:         "rgba(255,255,255,0.86)",
  cardShadow:     "rgba(11,60,93,0.14)",
  cardHoverShadow: "rgba(11,60,93,0.26)",

  // Focus
  focusRing: oceanOpacity(0.50),

  // Overlays
  overlayDark:  "rgba(240,247,252,0.50)",
  overlayMid:   "rgba(240,247,252,0.25)",
  overlayHeavy: "rgba(240,247,252,0.88)",
  accentRay:    tealOpacity(0.10),
  vignette:     "rgba(180,215,232,0.30)",

  // Buttons
  btnGlassBg:      oceanOpacity(0.09),
  btnGlassBorder:  oceanOpacity(0.22),
  btnGlassColor:   lightTextOpacity(0.80),
  btnGlassHoverBg: oceanOpacity(0.16),

  // Panels
  panelBg:           "rgba(255,255,255,0.84)",
  panelBgAlt:        "rgba(244,251,255,0.92)",
  panelBorder:       oceanOpacity(0.16),
  panelBorderAccent: oceanOpacity(0.22),

  // Rows
  rowBg:           "rgba(31,111,139,0.07)",
  rowBorder:       oceanOpacity(0.14),
  rowBorderStrong: oceanOpacity(0.22),

  // Accordion
  accordionOpenBg: oceanOpacity(0.06),

  // Charts / tables
  chartAxis:   "rgba(7,31,51,0.60)",
  chartGrid:   oceanOpacity(0.12),
  tableHead:   "rgba(7,31,51,0.72)",
  tableRowAlt: oceanOpacity(0.05),

  // Empty / skeleton
  emptyBg:     oceanOpacity(0.05),
  emptyBorder: oceanOpacity(0.22),
  emptyIcon:   lightTextOpacity(0.22),
  emptyText:   "rgba(14,55,82,0.62)",

  // Status softened
  successSoft:  "rgba(61,184,134,0.10)",
  warningSoft:  "rgba(255,209,102,0.10)",
  dangerSoft:   "rgba(228,87,87,0.08)",

  // Insight strip
  insightBg:     oceanOpacity(0.08),
  insightBorder: oceanOpacity(0.20),

  // Warning strip
  warnBg:     "rgba(160,100,0,0.07)",
  warnBorder: "rgba(160,100,0,0.22)",
  warnText:   "rgba(120,75,0,0.90)",

  // Chat answer card
  answerBg:             "rgba(255,255,255,0.90)",
  answerBorder:         oceanOpacity(0.22),
  answerDivider:        oceanOpacity(0.12),
  answerMetricBg:       oceanOpacity(0.06),
  answerSqlBg:          "rgba(240,248,255,0.92)",
  answerFollowupBg:     oceanOpacity(0.09),
  answerFollowupBorder: oceanOpacity(0.25),
  answerFollowupColor:  "rgba(10,75,105,0.85)",

  // Modals
  modalOverlay: lightTextOpacity(0.45),
  modalBg:      "rgba(255,255,255,0.98)",
  modalBorder:  oceanOpacity(0.22),

  // Misc
  privacyBg:      oceanOpacity(0.07),
  privacyBorder:  oceanOpacity(0.18),
  uploadBg:       "rgba(255,255,255,0.70)",
  scrollbarThumb: oceanOpacity(0.28),
  scrollbarHover: oceanOpacity(0.48),
  toastBg:        "rgba(255,255,255,0.97)",
  toastBorder:    oceanOpacity(0.22),
  footerBg:       oceanOpacity(0.04),
  footerBorder:   oceanOpacity(0.12),
} as const;

// ── Chart color palettes ───────────────────────────────────────────────────────

/** General-purpose ordered palette for pie/bar/line series */
export const CHART_COLORS = [
  RAW.teal,       // cyan
  RAW.coral,      // coral
  RAW.positive,   // green
  RAW.highlight,  // yellow
  "#9B59B6",      // purple
  "#E67E22",      // orange
  "#2ECC71",      // emerald
  "#E74C3C",      // red
  "#3498DB",      // blue
  "#1ABC9C",      // teal-green
] as const;

/** Semantic fills for banking flow charts */
export const FLOW_COLORS = {
  deposits:    "#10b981", // emerald
  withdrawals: "#f59e0b", // amber
  fees:        "#ef4444", // red
  dividends:   "#6366f1", // indigo
} as const;

/** Spending category colors (extend as categories grow) */
export const CATEGORY_COLORS: Record<string, string> = {
  dining:        RAW.coral,
  travel:        RAW.oceanSea,
  groceries:     RAW.positive,
  shopping:      RAW.highlight,
  utilities:     "#9B59B6",
  entertainment: "#E67E22",
  health:        "#2ECC71",
  other:         "#94a3b8",
};

// ── Gradients ─────────────────────────────────────────────────────────────────

export const GRADIENTS = {
  coral:      "linear-gradient(135deg, #FF7A5A, #FFA38F)",
  coralDeep:  "linear-gradient(135deg, #E8522E, #FF7A5A)",
  coralSoft:  "linear-gradient(135deg, #FF8C73, #FFB5A0)",
  ocean:      "linear-gradient(180deg, #0B3C5D, #1F6F8B, #5FA8D3)",
  aqua:       "linear-gradient(135deg, #22d3ee, #5FA8D3)",
  oceanPage: {
    dark:  "linear-gradient(180deg, #03111f 0%, #06263a 40%, #0b3c5d 100%)",
    light: "linear-gradient(180deg, #e8f4fb 0%, #cde9f6 40%, #a3dae9 100%)",
  },
  textCoral: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
  textOcean: "linear-gradient(135deg, #22d3ee, #5FA8D3)",
  sidebar:   "linear-gradient(180deg, #0B3C5D 0%, #1F6F8B 60%, #3D8FB5 100%)",
} as const;

// ── Tailwind badge/chip classes ────────────────────────────────────────────────

/** Institution badge classes — use as `className={INSTITUTION_BADGE[institution]}` */
export const INSTITUTION_BADGE: Record<string, string> = {
  morgan_stanley: "bg-ocean-50 text-ocean border-ocean-200",
  chase:          "bg-ocean-50 text-ocean border-ocean-100",
  etrade:         "bg-ocean-50 text-positive border-ocean-100",
  amex:           "bg-sand-50 text-ocean border-sand-100",
  discover:       "bg-coral-50 text-coral border-coral-100",
  bofa:           "bg-ocean-50 text-ocean-deep border-ocean-200",
  marcus:         "bg-positive/10 text-positive border-positive/20",
  unknown:        "bg-ocean-50 text-ocean border-ocean-100",
};

/** Status badge classes */
export const STATUS_BADGE = {
  success:  "bg-positive/10 text-positive border-positive/20",
  error:    "bg-negative/10 text-negative border-negative/20",
  warning:  "bg-highlight/10 text-highlight border-highlight/20",
  pending:  "bg-ocean-50 text-ocean border-ocean-100",
  info:     "bg-ocean-50 text-ocean border-ocean-200",
} as const;
