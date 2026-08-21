import { test, expect } from '@playwright/test';
import { mkdirSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS_DIR = join(__dirname, '..', '..', 'docs', 'screenshots');

/**
 * Marketing screenshot capture for the netsvcs (DNS) and threat-intel web UI.
 * Boots against the same mock API + built portal wiring as smoke.spec.ts
 * (globalSetup/globalTeardown + webServer in playwright.config.ts) and walks
 * every new module view with seeded data visible, writing PNGs to
 * docs/screenshots/. Not an assertion-heavy test — each `expect` below only
 * gates that real content rendered before the screenshot is taken.
 */
test.describe('Marketing screenshots: netsvcs + threatintel', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('capture login + netsvcs + threatintel pages', async ({ page }) => {
    mkdirSync(SCREENSHOTS_DIR, { recursive: true });

    // Unauthenticated first impression: the login page, no prefilled creds.
    await page.context().clearCookies();
    await page.goto('/login');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="email"]')).toHaveValue('');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: join(SCREENSHOTS_DIR, 'login.png') });

    // Authenticate via the mock API's seeded test user.
    await page.locator('input[type="email"]').fill('test@example.com');
    await page.locator('input[type="password"]').fill('testpass');
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL('/', { timeout: 5000 });

    // netsvcs: Zones — populated zones list
    await page.goto('/m/netsvcs/zones');
    await expect(page.getByRole('heading', { name: 'Zones' })).toBeVisible();
    await expect(page.locator('[data-testid="datatable-row"]').first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: join(SCREENSHOTS_DIR, 'dns-zones.png') });

    // netsvcs: DNS Servers — resolver fleet list
    await page.goto('/m/netsvcs/dns-servers');
    await expect(page.getByRole('heading', { name: 'DNS Servers' })).toBeVisible();
    await expect(page.locator('[data-testid="datatable-row"]').first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: join(SCREENSHOTS_DIR, 'dns-servers.png') });

    // netsvcs: Analytics — recharts dashboards with seeded summary/timeline data
    await page.goto('/m/netsvcs/analytics');
    await expect(page.getByRole('heading', { name: 'Analytics' })).toBeVisible();
    await expect(page.locator('.recharts-wrapper').first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: join(SCREENSHOTS_DIR, 'dns-analytics.png') });

    // threatintel: IOC Check — a real lookup verdict (matches mocked blocklist entry b1)
    await page.goto('/m/threatintel/ioc-check');
    await expect(page.getByRole('heading', { name: 'IOC Check' })).toBeVisible();
    await page.locator('#ioc-type').selectOption('domain');
    await page.locator('#ioc-value').fill('malicious-example.com');
    await page.getByRole('button', { name: 'Check indicator against blocklist' }).click();
    await expect(page.locator('[data-testid="ioc-verdict-blocked"]')).toBeVisible();
    await page.screenshot({ path: join(SCREENSHOTS_DIR, 'threatintel-ioc.png') });

    // threatintel: Feeds — feed source list
    await page.goto('/m/threatintel/feeds');
    await expect(page.getByRole('heading', { name: 'Feeds' })).toBeVisible();
    await expect(page.locator('[data-testid="datatable-row"]').first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: join(SCREENSHOTS_DIR, 'threatintel-feeds.png') });

    // threatintel: Blocklist — manual entries list
    await page.goto('/m/threatintel/blocklist');
    await expect(page.getByRole('heading', { name: 'Blocklist' })).toBeVisible();
    await expect(page.locator('[data-testid="datatable-row"]').first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: join(SCREENSHOTS_DIR, 'threatintel-blocklist.png') });
  });
});
