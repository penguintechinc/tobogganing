import { test, expect } from '@playwright/test'

test.describe('Smoke tests', () => {
  test('login page loads', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('form')).toBeVisible()
  })

  test('login page has required fields', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByLabel(/email/i)).toBeVisible()
    await expect(page.getByLabel(/password/i)).toBeVisible()
    await expect(page.getByRole('button', { name: /sign in|login/i })).toBeVisible()
  })

  test('invalid login shows error', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel(/email/i).fill('wrong@example.com')
    await page.getByLabel(/password/i).fill('wrongpass')
    await page.getByRole('button', { name: /sign in|login/i }).click()
    await expect(page.locator('[role="alert"], .error, [data-testid="error"]')).toBeVisible({ timeout: 5000 })
  })

  test('login page shows branding', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByText('Tobogganing')).toBeVisible()
    await expect(page.getByText('Hub Management Console')).toBeVisible()
  })

  test('unauthenticated access redirects to login', async ({ page }) => {
    await page.goto('/dashboard')
    // Should redirect to login
    await expect(page).toHaveURL(/login/)
  })
})
