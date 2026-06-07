/**
 * Coral UI scale constants.
 *
 * To make the entire app LARGER: increase the max values in index.css:
 *   --font-size-app: clamp(16px, 0.38vw + 14.5px, 20px)  ← raise 18 → 20
 *
 * To make the entire app SMALLER: lower the min value:
 *   --font-size-app: clamp(14px, 0.38vw + 14.5px, 18px)  ← lower 16 → 14
 *
 * The `density` and `maxContentWidth` values below are informational — they
 * document the intent but are not consumed programmatically yet.
 */
export const uiScale = {
  /** "comfortable" = current default spacing/padding rhythm */
  density: "comfortable" as const,

  /** Maximum content column width — prevents sprawl on ultra-wide monitors */
  maxContentWidth: "1500px",
} as const;
