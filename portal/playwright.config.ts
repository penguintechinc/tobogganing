import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
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
    url: 'http://localhost:3000/healthz',
    reuseExistingServer: !process.env.CI,
    env: {
      CORE_API_URL: 'http://localhost:3001',
      PORT: '3000',
    },
  },
});
