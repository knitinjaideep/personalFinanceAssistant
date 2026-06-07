// Flat ESLint config (ESLint 9). The installed toolchain ships ESLint 9 +
// @next/eslint-plugin-next 16, whose flat config we consume directly. Next 14's
// `next lint` wrapper passes legacy options ESLint 9 removed, so package.json's
// "lint" script invokes `eslint` directly against this config instead.
import next from "@next/eslint-plugin-next";
import tseslint from "typescript-eslint";

export default [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts", "tsconfig.tsbuildinfo"],
  },
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "@next/next": next },
    rules: {
      ...next.configs.recommended.rules,
      ...next.configs["core-web-vitals"].rules,
      // Allow intentional unused args prefixed with _.
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
];
