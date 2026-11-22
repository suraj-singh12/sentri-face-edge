import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

// Report-only for now: every rule is a warning, so only syntax errors fail.
const asWarnings = (rules) => Object.fromEntries(Object.keys(rules).map((name) => [name, "warn"]));

export default [
  { ignores: ["node_modules/**"] },
  {
    files: ["**/*.{js,jsx,mjs}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser, ...globals.node },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...asWarnings(js.configs.recommended.rules),
      ...asWarnings(reactHooks.configs.recommended.rules),
    },
  },
];
