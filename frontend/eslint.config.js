// Flat config (ESLint 9+). The `lint` script has existed since the Wave 01
// scaffold and never ran: `eslint` was not in devDependencies and no config
// file existed, so `npm run lint` failed with "command not found" rather
// than reporting anything about the code.
//
// Scope is deliberately the application source. `dist/` is build output and
// the root config files are plain Node scripts, not part of the app.
import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "*.config.js", "*.config.ts"] },
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // AGENTS.md forbids `any` as a way to silence the type checker, and
      // the project rule is that a problem is fixed, not hidden. An error,
      // not a warning: `--max-warnings 0` would fail on it either way, and
      // the severity should say what the project means.
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
);
