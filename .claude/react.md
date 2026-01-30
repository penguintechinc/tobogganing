# React / Frontend Standards

## ⚠️ CRITICAL RULES

- **ReactJS MANDATORY** for all frontend applications - no exceptions
- **Node.js 18+** required for build tooling
- **ES2022+ standards** mandatory (modern JS syntax, async/await, arrow functions, destructuring)
- **Functional components with hooks only** - no class components
- **Centralized API client** with auth interceptors - all API calls through `apiClient`
- **Protected routes** required - use AuthContext with authentication state
- **ESLint + Prettier required** - all code must pass linting before commit
- **Dark theme default** - gold text (amber-400) with slate backgrounds
- **TailwindCSS v4** for styling - use CSS variables for design system
- **Responsive design** - mobile-first approach, all layouts must be responsive
- **ConsoleVersion MANDATORY** - Every React app MUST include ConsoleVersion component (see below)
- **Shared Library Components MANDATORY** - Use `@penguintechinc/react-libs` components by default (see below)
- **Console Logging REQUIRED** - All components must include sanitized console logging for troubleshooting

## Technology Stack

**Required Dependencies:**
- `react@^18.2.0`, `react-dom@^18.2.0`
- `react-router-dom@^6.20.0` - page routing
- `axios@^1.6.0` - HTTP client
- `@tanstack/react-query@^5.0.0` - data fetching & caching
- `zustand@^4.4.0` - state management (optional)
- `lucide-react@^0.453.0` - icons
- `tailwindcss@^4.0.0` - styling

**DevDependencies:**
- `vite@^5.0.0` - build tool
- `@vitejs/plugin-react@^4.2.0` - React plugin
- `eslint@^8.55.0` - code linting
- `prettier@^3.1.0` - code formatting

## Project Structure

```
services/webui/
├── src/
│   ├── components/      # Reusable UI components
│   ├── pages/           # Page components
│   ├── services/        # API client & integrations
│   ├── hooks/           # Custom React hooks
│   ├── context/         # React context (auth, etc)
│   ├── utils/           # Utility functions
│   ├── App.jsx
│   └── index.jsx
├── package.json
├── Dockerfile
└── .env
```

## ConsoleVersion Component (MANDATORY)

**Every React application MUST include the `AppConsoleVersion` component** from `@penguintechinc/react-libs` to log build version and epoch information to the browser console on startup.

**Required Information:**
- WebUI version and build epoch (from Vite build-time env vars)
- API version and build epoch (fetched from `/api/v1/status` endpoint)

**Implementation in App.tsx (RECOMMENDED - Single Component):**

```tsx
import { AppConsoleVersion } from '@penguintechinc/react-libs';

function App() {
  return (
    <>
      {/* Logs both WebUI and API versions automatically */}
      <AppConsoleVersion
        appName="MyApp"
        webuiVersion={import.meta.env.VITE_VERSION || '0.0.0'}
        webuiBuildEpoch={Number(import.meta.env.VITE_BUILD_TIME) || 0}
        environment={import.meta.env.MODE}
        apiStatusUrl="/api/v1/status"
        metadata={{
          'API URL': import.meta.env.VITE_API_URL || '(relative)',
        }}
      />

      {/* Rest of app */}
    </>
  );
}
```

**Vite Configuration (vite.config.ts):**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_BUILD_TIME': JSON.stringify(
      Math.floor(Date.now() / 1000)
    ),
    'import.meta.env.VITE_VERSION': JSON.stringify(
      process.env.npm_package_version || '0.0.0'
    ),
  },
});
```

**API Status Endpoint Requirements:**

The API must expose a `/api/v1/status` endpoint returning:

```json
{
  "version": "1.2.3.1737720000",
  "build_epoch": 1737720000
}
```

**Expected Console Output:**
```
🖥️ MyApp - WebUI
Version: 1.2.3
Build Epoch: 1737727200
Build Date: 2025-01-24 12:00:00 UTC
Environment: development
API URL: http://localhost:5000
⚙️ MyApp - API
Version: 1.2.3
Build Epoch: 1737720000
Build Date: 2025-01-24 10:00:00 UTC
```

**Why This Is Required:**
- Debugging: Quickly verify deployed versions match expectations
- Support: Users can report exact versions when filing issues
- Audit: Track which versions are running in production
- CI/CD: Verify deployments completed successfully

## Console Logging Standards (MANDATORY)

**All shared library components and React applications MUST include sanitized console logging** for troubleshooting. This allows debugging without exposing sensitive information.

### Logging Principles

1. **Log lifecycle events**: Component mount, unmount, state changes
2. **Log user actions**: Form submissions, button clicks, navigation
3. **Log errors**: API failures, validation errors, exceptions
4. **NEVER log sensitive data**: Passwords, tokens, full emails, MFA codes, security thresholds

### Sanitization Rules

```typescript
// NEVER log these values directly
const SENSITIVE_KEYS = [
  'password', 'token', 'secret', 'credential', 'mfaCode',
  'captchaToken', 'apiKey', 'authToken', 'refreshToken'
];

// Sanitize emails - only log domain
const sanitizeEmail = (email: string) => {
  const parts = email.split('@');
  return parts.length === 2 ? parts[1] : '[invalid]';
};

// Example sanitized log
console.log('[LoginPage] Login attempt', { emailDomain: 'example.com' });
// NOT: console.log('[LoginPage] Login attempt', { email: 'user@example.com', password: 'secret' });
```

### Standard Log Format

All shared components use prefixed logging:

```
[ComponentName] Action description { sanitizedData }
[ComponentName:SubFeature] Specific action { data }
```

**Examples:**
```
[LoginPage] LoginPage mounted { appName: 'MyApp', captchaEnabled: true }
[LoginPage] Login attempt started { emailDomain: 'example.com', rememberMe: true }
[LoginPage:CAPTCHA] Failed login attempt recorded { attemptNumber: 2 }
[LoginPage:MFA] MFA verification started { rememberDevice: false }
[FormModal] Modal opened { title: 'Create User', fieldCount: 3 }
[FormModal] Form submitted successfully { tabCount: 1 }
```

### Security Logging Rules

**NEVER log:**
- ❌ Passwords or password hints
- ❌ Authentication tokens (JWT, refresh tokens, API keys)
- ❌ Full email addresses (only log domain)
- ❌ MFA/TOTP codes
- ❌ CAPTCHA tokens or solutions
- ❌ Security thresholds (e.g., "CAPTCHA triggers after 3 attempts" - tells attackers limits)
- ❌ Session IDs or cookies
- ❌ Form field values that might contain sensitive data

**Safe to log:**
- ✅ Component lifecycle events (mount, unmount)
- ✅ User action types (not content)
- ✅ Email domains (not full addresses)
- ✅ Attempt counts (but not thresholds)
- ✅ Error codes and types
- ✅ Validation failure field names (not values)
- ✅ Navigation events
- ✅ Feature flags and configuration (non-sensitive)

## API Client Integration

**Centralized axios client with auth interceptors:**

```javascript
// src/services/apiClient.js
import axios from 'axios';

const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:5000',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

// Request: Add auth token to headers
apiClient.interceptors.request.use(config => {
  const token = localStorage.getItem('authToken');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Response: Handle 401 (redirect to login)
apiClient.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.removeItem('authToken');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

## Component Patterns

**Functional components with hooks:**
- Use `useState` for local state, `useEffect` for side effects
- Custom hooks for shared logic (e.g., `useUsers`, `useFetch`)
- React Query for data fetching with caching (`useQuery`, `useMutation`)

**Authentication Context:**
- Centralize auth state in `AuthProvider`
- Export `useAuth` hook for accessing user, login, logout
- Validate token on app mount, refresh on 401 responses

**Protected Routes:**
- Create `ProtectedRoute` component checking `useAuth()` state
- Redirect unauthenticated users to `/login`
- Show loading state while checking auth status

**Data Fetching:**
- Use React Query for server state management
- Custom hooks wrapping `useQuery`/`useMutation` for API calls
- Automatic caching, refetching, and error handling

## Design System

**Color Palette (CSS Variables):**
```css
--bg-primary: #0f172a;      /* slate-900 - main background */
--bg-secondary: #1e293b;    /* slate-800 - sidebar/cards */
--text-primary: #fbbf24;    /* amber-400 - headings */
--text-secondary: #f59e0b;  /* amber-500 - body text */
--primary-500: #0ea5e9;     /* sky-blue - interactive elements */
--border-color: #334155;    /* slate-700 */
```

**Navigation Patterns:**
1. **Sidebar (Elder style)**: Fixed left sidebar with collapsible categories
2. **Tabs (WaddlePerf style)**: Horizontal tabs with active underline
3. **Combined**: Sidebar + tabs for complex layouts

**Required Components:**
- `Card` - bordered container with optional title
- `Button` - variants: primary, secondary, danger, ghost
- `ProtectedRoute` - authentication guard
- `Sidebar` - main navigation with collapsible groups

## Styling Standards

- **TailwindCSS v4** for all styling (no inline styles)
- **Dark theme default**: slate backgrounds + gold/amber text
- **Responsive**: Use Tailwind breakpoints (sm, md, lg, xl)
- **Transitions**: `transition-colors` or `transition-all 0.2s` for state changes
- **Consistent spacing**: Use Tailwind spacing scale (4, 6, 8 px increments)
- **Gradient accents**: Subtle, sparing usage for visual interest

## Quality Standards

**Linting & Formatting:**
- **ESLint** required - extends React best practices
- **Prettier** required - enforces code style
- Run before every commit: `npm run lint && npm run format`

**Code Quality:**
- All code must pass ESLint without errors/warnings
- Type checking with PropTypes or TypeScript (if using TS)
- Meaningful variable/component names
- Props validation for all components

**Testing:**
- Smoke tests: Build, run, API health, page loads, tab loads
- Unit tests for custom hooks and utilities
- Integration tests for component interactions
- Shared component validation (see Smoke Tests section below)

## Smoke Tests for Shared Components (MANDATORY)

**All React applications using shared library components MUST include smoke tests** to validate:
1. Page loads correctly (including auth-protected pages)
2. Tab navigation works
3. Forms render and submit properly
4. Shared components initialize without errors

### Page Load Smoke Tests

Test that all pages load without JavaScript errors:

```typescript
// tests/smoke/pageLoads.spec.ts
import { test, expect } from '@playwright/test';

const PAGES = [
  { path: '/login', name: 'Login Page', requiresAuth: false },
  { path: '/dashboard', name: 'Dashboard', requiresAuth: true },
  { path: '/users', name: 'Users List', requiresAuth: true },
  { path: '/settings', name: 'Settings', requiresAuth: true },
];

test.describe('Page Load Smoke Tests', () => {
  for (const page of PAGES) {
    test(`${page.name} loads without errors`, async ({ page: browserPage }) => {
      const errors: string[] = [];
      browserPage.on('pageerror', (err) => errors.push(err.message));

      if (page.requiresAuth) {
        // Login first for protected pages
        await browserPage.goto('/login');
        await browserPage.fill('input[name="email"]', 'admin@localhost.local');
        await browserPage.fill('input[name="password"]', 'admin123');
        await browserPage.click('button[type="submit"]');
        await browserPage.waitForURL('/dashboard');
      }

      await browserPage.goto(page.path);
      await browserPage.waitForLoadState('networkidle');

      expect(errors).toEqual([]);
    });
  }
});
```

### Tab Load Smoke Tests

Test tab navigation on pages with multiple tabs:

```typescript
// tests/smoke/tabLoads.spec.ts
import { test, expect } from '@playwright/test';

const TABBED_PAGES = [
  {
    path: '/settings',
    tabs: ['General', 'Security', 'Notifications'],
  },
  {
    path: '/users/1',
    tabs: ['Profile', 'Permissions', 'Activity'],
  },
];

test.describe('Tab Load Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login for protected pages
    await page.goto('/login');
    await page.fill('input[name="email"]', 'admin@localhost.local');
    await page.fill('input[name="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForURL('/dashboard');
  });

  for (const tabPage of TABBED_PAGES) {
    for (const tab of tabPage.tabs) {
      test(`${tabPage.path} - ${tab} tab loads`, async ({ page }) => {
        const errors: string[] = [];
        page.on('pageerror', (err) => errors.push(err.message));

        await page.goto(tabPage.path);
        await page.click(`[data-testid="tab-${tab.toLowerCase()}"]`);
        await page.waitForLoadState('networkidle');

        expect(errors).toEqual([]);
      });
    }
  }
});
```

### Form Component Smoke Tests

Test that FormModalBuilder forms render and validate:

```typescript
// tests/smoke/formModals.spec.ts
import { test, expect } from '@playwright/test';

const FORMS = [
  { trigger: '[data-testid="create-user-btn"]', title: 'Create User' },
  { trigger: '[data-testid="edit-settings-btn"]', title: 'Edit Settings' },
];

test.describe('Form Modal Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[name="email"]', 'admin@localhost.local');
    await page.fill('input[name="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForURL('/dashboard');
  });

  for (const form of FORMS) {
    test(`${form.title} form opens and closes`, async ({ page }) => {
      await page.goto('/users'); // Navigate to page with form
      await page.click(form.trigger);

      // Verify modal opened
      await expect(page.locator('[role="dialog"]')).toBeVisible();
      await expect(page.locator('h2')).toContainText(form.title);

      // Close modal
      await page.click('[data-testid="modal-close"]');
      await expect(page.locator('[role="dialog"]')).not.toBeVisible();
    });

    test(`${form.title} form shows validation errors`, async ({ page }) => {
      await page.goto('/users');
      await page.click(form.trigger);

      // Submit empty form
      await page.click('button[type="submit"]');

      // Should show validation errors (not submit)
      await expect(page.locator('[role="dialog"]')).toBeVisible();
      await expect(page.locator('.text-red-400')).toBeVisible();
    });
  }
});
```

### LoginPageBuilder Smoke Tests

Test the login page shared component:

```typescript
// tests/smoke/loginPage.spec.ts
import { test, expect } from '@playwright/test';

test.describe('LoginPageBuilder Smoke Tests', () => {
  test('login page renders correctly', async ({ page }) => {
    await page.goto('/login');

    // Verify LoginPageBuilder components rendered
    await expect(page.locator('input[name="email"]')).toBeVisible();
    await expect(page.locator('input[name="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('login page shows validation errors for empty form', async ({ page }) => {
    await page.goto('/login');
    await page.click('button[type="submit"]');

    // Should show validation error
    await expect(page.locator('.text-red-400')).toBeVisible();
  });

  test('login page shows error for invalid credentials', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[name="email"]', 'wrong@example.com');
    await page.fill('input[name="password"]', 'wrongpassword');
    await page.click('button[type="submit"]');

    // Should show error message
    await expect(page.locator('[data-testid="login-error"]')).toBeVisible();
  });

  test('successful login redirects to dashboard', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[name="email"]', 'admin@localhost.local');
    await page.fill('input[name="password"]', 'admin123');
    await page.click('button[type="submit"]');

    await page.waitForURL('/dashboard');
    expect(page.url()).toContain('/dashboard');
  });

  test('GDPR consent banner appears on first visit', async ({ page, context }) => {
    // Clear cookies/storage for fresh visit
    await context.clearCookies();

    await page.goto('/login');

    // GDPR banner should be visible
    await expect(page.locator('[data-testid="cookie-consent"]')).toBeVisible();
  });
});
```

### Running Smoke Tests

```bash
# Install Playwright
npm install -D @playwright/test

# Run all smoke tests
npx playwright test tests/smoke/

# Run specific smoke test category
npx playwright test tests/smoke/pageLoads.spec.ts
npx playwright test tests/smoke/loginPage.spec.ts

# Run with UI for debugging
npx playwright test --ui
```

### Test Data Attributes

Add these data-testid attributes to your components for reliable testing:

```tsx
// In LoginPageBuilder usage
<LoginPageBuilder
  data-testid="login-form"
  // ... other props
/>

// In FormModalBuilder usage
<FormModalBuilder
  data-testid="user-form-modal"
  // ... other props
/>

// Tab buttons
<button data-testid="tab-general">General</button>
<button data-testid="tab-security">Security</button>
```

## Docker Configuration

```dockerfile
# services/webui/Dockerfile - Multi-stage build
FROM node:18-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:stable-bookworm-slim
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

## Accessibility Requirements

- Keyboard navigation for all interactive elements
- Focus states: `focus:ring-2 focus:ring-primary-500`
- ARIA labels for screen readers
- Color contrast minimum 4.5:1
- Respect `prefers-reduced-motion` preference

## Shared React Libraries (MANDATORY - DEFAULT BEHAVIOR)

**All React applications MUST use `@penguintechinc/react-libs` shared components BY DEFAULT** unless explicitly told otherwise. This is the default behavior - do not implement custom versions.

**IMPORTANT:** When building any React application:
1. **Always start with shared components** from `@penguintechinc/react-libs`
2. **Only deviate if explicitly instructed** by the user/requirements
3. **Document any exceptions** in the project's APP_STANDARDS.md

This ensures consistency, security, and maintainability across all Penguin Tech applications.

### Required Components

| Component | Purpose | When to Use |
|-----------|---------|-------------|
| `AppConsoleVersion` | Console version logging | **REQUIRED** - Every React app |
| `SidebarMenu` | Navigation sidebar | Apps with sidebar navigation |
| `FormModalBuilder` | Modal forms | All modal dialogs with forms |
| `LoginPageBuilder` | Login page | **REQUIRED** - All apps with authentication |

### Installation

**Step 1: Configure npm for GitHub Packages**

```bash
# Add to ~/.npmrc (one-time setup)
echo "@penguintechinc:registry=https://npm.pkg.github.com" >> ~/.npmrc
```

**Step 2: Install the package**

```bash
npm install @penguintechinc/react-libs
# or
yarn add @penguintechinc/react-libs
```

**For CI/CD (GitHub Actions)**:

```yaml
- name: Configure npm for GitHub Packages
  run: echo "@penguintechinc:registry=https://npm.pkg.github.com" >> ~/.npmrc
  env:
    NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

- name: Install dependencies
  run: npm ci
```

### LoginPageBuilder (MANDATORY for Auth)

**Every application with authentication MUST use `LoginPageBuilder`** from `@penguintechinc/react-libs`.

**Features included:**
- Elder-style dark theme (gold/amber accents)
- ALTCHA proof-of-work CAPTCHA (after failed attempts)
- MFA/2FA support with 6-digit TOTP input
- Social login (OAuth2, OIDC, SAML)
- GDPR cookie consent banner
- Full theming customization

**Basic Implementation:**

```tsx
import { LoginPageBuilder, LoginResponse } from '@penguintechinc/react-libs';

function LoginPage() {
  const handleSuccess = (response: LoginResponse) => {
    if (response.token) {
      localStorage.setItem('authToken', response.token);
    }
    window.location.href = '/dashboard';
  };

  return (
    <LoginPageBuilder
      api={{ loginUrl: '/api/v1/auth/login' }}
      branding={{
        appName: 'My Application',
        logo: '/images/logo.png',
        tagline: 'Welcome back!',
        githubRepo: 'penguintechinc/my-app',
      }}
      onSuccess={handleSuccess}
      gdpr={{
        enabled: true,
        privacyPolicyUrl: '/privacy',
      }}
    />
  );
}
```

**With MFA and CAPTCHA:**

```tsx
<LoginPageBuilder
  api={{ loginUrl: '/api/v1/auth/login' }}
  branding={{
    appName: 'Secure App',
    githubRepo: 'penguintechinc/secure-app',
  }}
  onSuccess={handleSuccess}
  gdpr={{
    enabled: true,
    privacyPolicyUrl: '/privacy',
  }}
  captcha={{
    enabled: true,
    provider: 'altcha',
    challengeUrl: '/api/v1/captcha/challenge',
    failedAttemptsThreshold: 3,
  }}
  mfa={{
    enabled: true,
    codeLength: 6,
    allowRememberDevice: true,
  }}
/>
```

**With Social Login:**

```tsx
<LoginPageBuilder
  api={{ loginUrl: '/api/v1/auth/login' }}
  branding={{ appName: 'Community App' }}
  onSuccess={handleSuccess}
  gdpr={{ enabled: true, privacyPolicyUrl: '/privacy' }}
  socialLogins={[
    { provider: 'google', clientId: 'your-google-client-id' },
    { provider: 'github', clientId: 'your-github-client-id' },
    { provider: 'oidc', issuerUrl: 'https://auth.company.com', clientId: 'app-id', label: 'Company SSO' },
  ]}
/>
```

### SidebarMenu Usage

```tsx
import { SidebarMenu } from '@penguintechinc/react-libs';

<SidebarMenu
  logo={<img src="/logo.png" alt="Logo" />}
  categories={[
    {
      header: 'Main',
      items: [
        { name: 'Dashboard', href: '/dashboard', icon: HomeIcon },
        { name: 'Users', href: '/users', icon: UsersIcon },
      ],
    },
  ]}
  currentPath={location.pathname}
  onNavigate={(href) => navigate(href)}
/>
```

### FormModalBuilder Usage

```tsx
import { FormModalBuilder } from '@penguintechinc/react-libs';

<FormModalBuilder
  title="Create User"
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  onSubmit={handleSubmit}
  fields={[
    { name: 'email', type: 'email', label: 'Email', required: true },
    { name: 'name', type: 'text', label: 'Name', required: true },
    { name: 'role', type: 'select', label: 'Role', options: [
      { value: 'admin', label: 'Admin' },
      { value: 'user', label: 'User' },
    ]},
  ]}
/>
```

### Why Shared Libraries?

1. **Consistency**: Uniform look and feel across all applications
2. **Security**: Centralized security features (CAPTCHA, MFA, CSRF protection)
3. **Maintenance**: Bug fixes and improvements benefit all apps
4. **Compliance**: GDPR consent handled consistently
5. **Efficiency**: No duplicating complex authentication logic

### Do NOT Implement Custom Versions Of:

- ❌ Login pages/forms - use `LoginPageBuilder`
- ❌ Navigation sidebars - use `SidebarMenu`
- ❌ Modal forms - use `FormModalBuilder`
- ❌ Console version logging - use `AppConsoleVersion`
- ❌ Cookie consent banners - use `LoginPageBuilder` with GDPR config
- ❌ Social login buttons - use `LoginPageBuilder` with socialLogins config
