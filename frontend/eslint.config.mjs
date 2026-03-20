import js from "@eslint/js";
import globals from "globals";
import nextPlugin from "@next/eslint-plugin-next";
import reactPlugin from "eslint-plugin-react";
import reactHooksPlugin from "eslint-plugin-react-hooks";
import jsxA11yPlugin from "eslint-plugin-jsx-a11y";
import importPlugin from "eslint-plugin-import";

export default [
  {
    ignores: [".next/**", "out/**", "node_modules/**"],
  },
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      "@next/next": nextPlugin,
      react: reactPlugin,
      "react-hooks": reactHooksPlugin,
      "jsx-a11y": jsxA11yPlugin,
      import: importPlugin,
    },
    settings: {
      react: {
        version: "detect",
      },
    },
    rules: {
      ...(nextPlugin.configs?.recommended?.rules ?? {}),
      ...(nextPlugin.configs?.["core-web-vitals"]?.rules ?? {}),
      ...(reactPlugin.configs?.recommended?.rules ?? {}),
      ...(reactHooksPlugin.configs?.recommended?.rules ?? {}),
      ...(jsxA11yPlugin.configs?.recommended?.rules ?? {}),
    },
  },
];

