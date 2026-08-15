import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * Vitest setup covering both pure-function/data-adapter unit tests (PR 07 —
 * see lib/bankingFlowTree.test.ts, scoped to `**\/*.test.ts`) and, since
 * PR 09 (docs/coral-redesign/pr-09-classification-review.md), component
 * tests for interactive review/correction UI (`**\/*.test.tsx`, jsdom +
 * Testing Library) — the classification review section's "Looks right"/
 * "Change"/error-path behavior genuinely needs to render and interact with
 * React components, not just exercise a pure data adapter.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "."),
    },
  },
  test: {
    environment: "jsdom",
    include: ["**/*.test.ts", "**/*.test.tsx"],
    exclude: ["node_modules/**", ".next/**"],
    setupFiles: ["./vitest.setup.ts"],
  },
});
