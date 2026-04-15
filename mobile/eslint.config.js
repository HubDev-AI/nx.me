// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require("eslint/config");
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*"],
  },
  // Jest test files — `require()` is used for `jest.mock()` factories
  // and hoisted mock references, which cannot be expressed with `import`.
  {
    files: ["**/*.test.{ts,tsx}", "**/__tests__/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-require-imports": "off",
    },
  },
  // Runtime-conditional require: native modules that are unavailable on web
  // or in Expo Go need lazy `require()` to avoid crashing on import.
  {
    files: ["lib/haptics.ts", "lib/social-auth.ts"],
    rules: {
      "@typescript-eslint/no-require-imports": "off",
    },
  },
]);
