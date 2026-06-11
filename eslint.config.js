import globals from "globals";

export default [
  {
    ignores: [
      "node_modules/**",
      "public/imagenes/**",
      "**/*.min.js"
    ]
  },
  {
    files: ["public/**/*.js"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: { ...globals.browser, ...globals.node },
      sourceType: "module"
    },
    rules: {
      "no-unused-vars": "off",
      "no-undef": "error"
    }
  },
  {
    files: ["server.js"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: { ...globals.node },
      sourceType: "module"
    },
    rules: {
      "no-unused-vars": "warn",
      "no-undef": "error",
      "semi": ["error", "always"],
      "quotes": ["error", "single", { avoidEscape: true }],
      "indent": ["error", 2],
      "prefer-const": "warn",
      "no-var": "error",
      "object-shorthand": "warn",
      "arrow-spacing": ["error", { before: true, after: true }],
      "no-trailing-spaces": "error",
      "eol-last": "error",
      "comma-dangle": ["error", "never"],
      "keyword-spacing": "error",
      "space-before-blocks": "error",
      "no-multi-spaces": "off"
    }
  }
];