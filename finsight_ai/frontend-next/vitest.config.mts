import path from "node:path";
import { defineConfig } from "vitest/config";

/**
 * Minimal vitest setup for pure-function/data-adapter unit tests (PR 07 —
 * see lib/bankingFlowTree.test.ts). Deliberately scoped to `lib/**` +
 * `features/**` style pure modules, not a full component-testing setup
 * (jsdom/RTL) — the coral-redesign work orders explicitly ask for robust
 * tests on deterministic data adapters, not exhaustive SVG/component
 * coverage. Add a jsdom environment + Testing Library later if a future PR
 * needs to render components in tests.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "."),
    },
  },
  test: {
    environment: "node",
    include: ["**/*.test.ts"],
    exclude: ["node_modules/**", ".next/**"],
  },
});
