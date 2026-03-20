import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E config for card-web.
 *
 * Expects the Next.js dev server at http://localhost:3006
 * and the backend API at http://localhost:8001.
 */
export default defineConfig({
  testDir: './src/__tests__/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : 4,
  reporter: 'list',
  timeout: 30_000,
  use: {
    baseURL: 'http://localhost:3006',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
