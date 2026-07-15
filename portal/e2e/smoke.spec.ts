import { test, expect } from '@playwright/test';

test.describe('Portal Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Ensure we start from a clean state
    await page.context().clearCookies();
    await page.goto('/login');
  });

  test('login page renders with email and password fields, no prefilled creds', async ({ page }) => {
    // Check that the login page is displayed
    await expect(page).toHaveURL('/login');

    // Check for email input field
    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toBeVisible();
    await expect(emailInput).toHaveValue('');

    // Check for password input field
    const passwordInput = page.locator('input[type="password"]');
    await expect(passwordInput).toBeVisible();
    await expect(passwordInput).toHaveValue('');

    // Check for submit button
    const submitButton = page.locator('button[type="submit"]');
    await expect(submitButton).toBeVisible();
  });

  test('bad credentials shows error and stays on /login', async ({ page }) => {
    const emailInput = page.locator('input[type="email"]');
    const passwordInput = page.locator('input[type="password"]');
    const submitButton = page.locator('button[type="submit"]');

    // Enter invalid credentials
    await emailInput.fill('invalid@example.com');
    await passwordInput.fill('wrongpassword');
    await submitButton.click();

    // Verify we stay on login page
    await expect(page).toHaveURL('/login');

    // Verify error message appears
    const errorMessage = page.locator('text=Invalid credentials');
    await expect(errorMessage).toBeVisible();
  });

  test('good credentials redirects to dashboard and sidebar shows module nav', async ({ page }) => {
    const emailInput = page.locator('input[type="email"]');
    const passwordInput = page.locator('input[type="password"]');
    const submitButton = page.locator('button[type="submit"]');

    // Enter valid credentials
    await emailInput.fill('test@example.com');
    await passwordInput.fill('testpass');
    await submitButton.click();

    // Verify redirect to dashboard
    await expect(page).toHaveURL('/', { timeout: 5000 });

    // Verify sidebar is visible with module navigation
    const sidebar = page.locator('nav');
    await expect(sidebar).toBeVisible();

    // Verify waddleperf_cluster module entries are in nav (scope to links —
    // the labels also appear on dashboard module cards)
    await expect(page.getByRole('link', { name: 'Devices' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Tests' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Stats' })).toBeVisible();
  });

  test('direct navigation to protected route while logged out redirects to /login', async ({ page }) => {
    // Try to navigate to a real protected route
    await page.goto('/m/waddleperf_cluster/devices');

    // Verify redirect to login page
    await expect(page).toHaveURL('/login');
  });

  test('healthz endpoint returns 200', async ({ page }) => {
    const response = await page.request.get('/healthz');
    expect(response.status()).toBe(200);
    const json = await response.json();
    expect(json.status).toBe('ok');
  });
});

  test('module views render across all three modules', async ({ page }) => {
    await page.goto('/login');
    const emailInput = page.locator('input[type="email"]');
    const passwordInput = page.locator('input[type="password"]');
    await emailInput.fill('test@example.com');
    await passwordInput.fill('testpass');
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL('/', { timeout: 5000 });

    // waddleperf_cluster devices: two mocked rows
    await page.goto('/m/waddleperf_cluster/devices');
    await expect(page.getByText('edge-nyc-1')).toBeVisible();
    await expect(page.getByText('edge-lon-1')).toBeVisible();

    // sase clusters: empty state renders (no crash)
    await page.goto('/m/sase/clusters');
    await expect(page.getByText(/no .*found|no data|empty/i).first()).toBeVisible({
      timeout: 5000,
    });

    // c2c nodes: one mocked row
    await page.goto('/m/waddleperf_c2c/c2c-nodes');
    await expect(page.getByText('us-east-node')).toBeVisible();
  });
