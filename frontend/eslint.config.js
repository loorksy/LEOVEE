import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    // Third-party code we ship but did not write. Linting the vendored
    // TradingView type definitions produces ~70 errors about `any` and empty
    // object types in someone else's declarations — noise that would drown the
    // findings in our own code, and that we cannot act on without editing a
    // library whose files are replaced wholesale on every update.
    //
    // Excluded rather than silenced with rule overrides: turning off
    // `no-explicit-any` to accommodate a vendored file would turn it off for
    // ours too, which is the opposite of the trade.
    ignores: [
      "dist",
      "public/charting_library/**",
      "vendor/tradingview/**",
    ],
  },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
);
