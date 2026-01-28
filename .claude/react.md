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

**Every React application MUST include the `AppConsoleVersion` component** from `@penguin/react_libs` to log build version and epoch information to the browser console on startup.

**Required Information:**
- WebUI version and build epoch (from Vite build-time env vars)
- API version and build epoch (fetched from `/api/v1/status` endpoint)

**Implementation in App.tsx (RECOMMENDED - Single Component):**

```tsx
import { AppConsoleVersion } from '@penguin/react_libs';

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
- Smoke tests: Build, run, API health, page loads
- Unit tests for custom hooks and utilities
- Integration tests for component interactions

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

## Shared React Libraries (MANDATORY)

**All React applications MUST use `@penguin/react_libs` shared components** instead of implementing custom versions. This ensures consistency across all Penguin Tech applications.

### Required Components

| Component | Purpose | When to Use |
|-----------|---------|-------------|
| `AppConsoleVersion` | Console version logging | **REQUIRED** - Every React app |
| `SidebarMenu` | Navigation sidebar | Apps with sidebar navigation |
| `FormModalBuilder` | Modal forms | All modal dialogs with forms |
| `LoginPageBuilder` | Login page | **REQUIRED** - All apps with authentication |

### Installation

```bash
# In your React application
npm install @penguin/react_libs
# or
yarn add @penguin/react_libs
```

### LoginPageBuilder (MANDATORY for Auth)

**Every application with authentication MUST use `LoginPageBuilder`** from `@penguin/react_libs`.

**Features included:**
- Elder-style dark theme (gold/amber accents)
- ALTCHA proof-of-work CAPTCHA (after failed attempts)
- MFA/2FA support with 6-digit TOTP input
- Social login (OAuth2, OIDC, SAML)
- GDPR cookie consent banner
- Full theming customization

**Basic Implementation:**

```tsx
import { LoginPageBuilder, LoginResponse } from '@penguin/react_libs';

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
import { SidebarMenu } from '@penguin/react_libs';

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
import { FormModalBuilder } from '@penguin/react_libs';

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
