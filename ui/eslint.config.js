// @ts-check
const eslint = require("@eslint/js");
const { defineConfig } = require("eslint/config");
const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');
module.exports = defineConfig(
  // TypeScript files
  {
    files: ["**/*.ts"],
    extends: [
      // Apply the recommended core rules
      eslint.configs.recommended,
      // Apply the recommended TypeScript rules
      ...tseslint.configs.recommended,
      // Optionally apply stylistic rules from typescript-eslint that improve code consistency
      ...tseslint.configs.stylistic,
      // Apply the recommended Angular rules
      ...angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,
    rules: {
      "@angular-eslint/component-selector": [
        "error",
        {
          prefix: "app",
          style: "kebab-case",
          type: "element",
        },
      ],
      "@angular-eslint/directive-selector": [
        "error",
        {
          prefix: "app",
          style: "camelCase",
          type: "attribute",
        },
      ],
      "@typescript-eslint/no-empty-function": "off",
    },
  },
  // HTML template files
  {
    files: ["**/*.html"],
    extends: [
      // Apply the recommended Angular template rules
      ...angular.configs.templateRecommended,
      // Apply the Angular template rules which focus on accessibility of our apps
      ...angular.configs.templateAccessibility,
    ],
    rules: {},
  },
);
