import { defineConfig, devices } from '@playwright/test';

/**
 * Dedicated Playwright config for marketing screenshot capture
 * (e2e/screenshots.spec.ts). Reuses the same globalSetup/globalTeardown
 * (mock API on :3001) and build+Express webServer wiring as the default
 * playwright.config.ts, but on port 4210 instead of 3000 to avoid
 * colliding with an unrelated dev server that may already occupy :3000
 * on a shared local machine.
 */
export default defineConfig({
  testDir: 'e2e',
  testMatch: 'screenshots.spec.ts',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:4210',
    trace: 'off',
  },
  outputDir: '/tmp/playwright-tobogganing',
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  globalSetup: 'e2e/global-setup.ts',
  globalTeardown: 'e2e/global-teardown.ts',
  webServer: {
    command: 'npm run build && node server.js',
    url: 'http://localhost:4210/healthz',
    reuseExistingServer: false,
    env: {
      CORE_API_URL: 'http://localhost:3001',
      PORT: '4210',
    },
  },
});
