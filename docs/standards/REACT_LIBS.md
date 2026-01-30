# 📦 Shared React Libraries

Part of [Development Standards](../STANDARDS.md)

The `@penguintechinc/react-libs` package provides shared React components that **MUST** be used across all Penguin Tech applications. This ensures consistency, reduces code duplication, and centralizes security-critical functionality.

## Installation

```bash
npm install @penguintechinc/react-libs
# or
yarn add @penguintechinc/react-libs
```

## Required Components

| Component | Purpose | Mandatory? |
|-----------|---------|------------|
| `AppConsoleVersion` | Console version logging | **YES** - Every app |
| `LoginPageBuilder` | Login/authentication page | **YES** - Apps with auth |
| `SidebarMenu` | Navigation sidebar | When app has sidebar |
| `FormModalBuilder` | Modal dialogs with forms | When using modal forms |

---

## LoginPageBuilder

A comprehensive login page component with built-in security features.

### Features

- **Elder-style dark theme** with gold/amber accents
- **ALTCHA CAPTCHA** - Proof-of-work verification after failed attempts
- **MFA/2FA support** - 6-digit TOTP input (Google Authenticator style)
- **Social login** - OAuth2, OIDC, and SAML providers
- **GDPR compliance** - Cookie consent banner with preferences
- **Full theming** - Customize all colors

### Basic Usage

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

### Props Reference

#### Required Props

| Prop | Type | Description |
|------|------|-------------|
| `api` | `LoginApiConfig` | API endpoint configuration |
| `branding` | `BrandingConfig` | Logo, app name, tagline |
| `onSuccess` | `(response: LoginResponse) => void` | Success callback |

#### API Configuration

```typescript
interface LoginApiConfig {
  loginUrl: string;           // e.g., '/api/v1/auth/login'
  method?: 'POST' | 'PUT';    // Default: 'POST'
  headers?: Record<string, string>;  // Additional headers
}
```

#### Branding Configuration

```typescript
interface BrandingConfig {
  appName: string;            // Displayed as page title
  logo?: ReactNode | string;  // Image URL or React component
  logoWidth?: number;         // Default: 300px
  tagline?: string;           // Subtitle below app name
  githubRepo?: string;        // For LICENSE link (e.g., 'penguintechinc/app')
}
```

### CAPTCHA Configuration

CAPTCHA appears automatically after failed login attempts.

```tsx
<LoginPageBuilder
  // ...required props
  captcha={{
    enabled: true,
    provider: 'altcha',
    challengeUrl: '/api/v1/captcha/challenge',
    failedAttemptsThreshold: 3,  // Show after 3 failures
    resetTimeoutMs: 900000,      // Reset after 15 minutes
  }}
/>
```

**Backend requirement**: Expose `/api/v1/captcha/challenge` endpoint returning ALTCHA challenge format.

### MFA Configuration

MFA modal appears when API returns `mfaRequired: true`.

```tsx
<LoginPageBuilder
  // ...required props
  mfa={{
    enabled: true,
    codeLength: 6,              // TOTP code length
    allowRememberDevice: true,  // "Remember this device" option
  }}
/>
```

**API Response for MFA**:
```json
{
  "success": true,
  "mfaRequired": true
}
```

### Social Login Providers

#### Built-in OAuth2 Providers

```tsx
<LoginPageBuilder
  // ...required props
  socialLogins={[
    {
      provider: 'google',
      clientId: 'your-google-client-id',
      redirectUri: `${window.location.origin}/auth/callback/google`,
    },
    {
      provider: 'github',
      clientId: 'your-github-client-id',
      scopes: ['user:email', 'read:user'],
    },
    {
      provider: 'microsoft',
      clientId: 'your-microsoft-client-id',
    },
  ]}
/>
```

Supported providers: `google`, `github`, `microsoft`, `apple`, `twitch`, `discord`

#### Custom OAuth2 Provider

```tsx
{
  provider: 'oauth2',
  clientId: 'your-client-id',
  authUrl: 'https://auth.example.com/oauth/authorize',
  label: 'Continue with Example',
  scopes: ['openid', 'email'],
  buttonColor: '#4A90D9',
  textColor: '#ffffff',
}
```

#### OIDC Provider (OpenID Connect)

```tsx
{
  provider: 'oidc',
  issuerUrl: 'https://auth.company.com',  // Auto-discovers endpoints
  clientId: 'your-oidc-client-id',
  scopes: ['openid', 'email', 'profile'],
  label: 'Company SSO',
}
```

#### SAML Provider (Enterprise SSO)

```tsx
{
  provider: 'saml',
  idpSsoUrl: 'https://idp.enterprise.com/saml/sso',
  entityId: 'https://your-app.com/saml/metadata',
  acsUrl: `${window.location.origin}/auth/saml/acs`,
  label: 'Enterprise SSO',
}
```

### GDPR Cookie Consent

```tsx
<LoginPageBuilder
  // ...required props
  gdpr={{
    enabled: true,
    privacyPolicyUrl: '/legal/privacy',
    cookiePolicyUrl: '/legal/cookies',
    consentText: 'We use cookies to enhance your experience.',
    showPreferences: true,  // Show "Manage Preferences" button
  }}
/>
```

The consent banner appears on first visit. Users must accept before the login form becomes interactive.

### Custom Theming

Override the default Elder theme:

```tsx
<LoginPageBuilder
  // ...required props
  colors={{
    pageBackground: 'bg-gray-900',
    cardBackground: 'bg-gray-800',
    titleText: 'text-purple-400',
    primaryButton: 'bg-purple-500',
    primaryButtonHover: 'hover:bg-purple-600',
    // ...see LoginColorConfig for all options
  }}
/>
```

### UI Options

```tsx
<LoginPageBuilder
  // ...required props
  showForgotPassword={true}
  forgotPasswordUrl="/auth/forgot-password"
  onForgotPassword={() => navigate('/forgot-password')}
  showSignUp={true}
  signUpUrl="/auth/register"
  onSignUp={() => navigate('/register')}
  showRememberMe={true}
/>
```

### Error Handling

```tsx
<LoginPageBuilder
  // ...required props
  onError={(error, errorCode) => {
    // Log to error tracking service
    console.error('Login failed:', errorCode);
  }}
  transformErrorMessage={(error, code) => {
    const messages = {
      INVALID_CREDENTIALS: 'Invalid email or password.',
      ACCOUNT_LOCKED: 'Account locked. Contact support.',
    };
    return messages[code] || error;
  }}
/>
```

### Logging

LoginPageBuilder includes comprehensive logging for troubleshooting. All sensitive data is automatically sanitized:

- Passwords, tokens, MFA codes: **Never logged**
- Email addresses: Only domain portion logged (e.g., `example.com`)
- CAPTCHA thresholds: **Not logged** (security)

Console output example:
```
[LoginPage] LoginPage mounted { appName: 'MyApp', captchaEnabled: true }
[LoginPage] Login attempt started { emailDomain: 'example.com', rememberMe: true }
[LoginPage:CAPTCHA] Failed login attempt recorded { attemptNumber: 1 }
[LoginPage:MFA] MFA verification started { rememberDevice: false }
```

---

## FormModalBuilder

A flexible modal form builder with validation, tabs, and file uploads.

### Basic Usage

```tsx
import { FormModalBuilder } from '@penguintechinc/react-libs';

<FormModalBuilder
  title="Create User"
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  onSubmit={async (data) => {
    await api.createUser(data);
  }}
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

### Field Types

| Type | Description | Returns |
|------|-------------|---------|
| `text` | Standard text input | `string` |
| `email` | Email with validation | `string` |
| `password` | Hidden characters | `string` |
| `password_generate` | With generate button | `string` |
| `number` | Numeric with min/max | `number` |
| `textarea` | Multi-line text | `string` |
| `multiline` | Multi-line, splits by newline | `string[]` |
| `select` | Dropdown | `string` |
| `checkbox` | Boolean toggle | `boolean` |
| `checkbox_multi` | Multiple selection | `string[]` |
| `radio` | Radio button group | `string` |
| `date` | Date picker | `string` (YYYY-MM-DD) |
| `time` | Time picker | `string` (HH:MM) |
| `datetime-local` | Date and time | `string` |
| `file` | Single file upload | `File` |
| `file_multiple` | Multiple files | `File[]` |

### Field Configuration

```typescript
interface FormField {
  name: string;
  type: FieldType;
  label: string;
  description?: string;
  helpText?: string;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  hidden?: boolean;
  defaultValue?: any;
  options?: Array<{ value: string; label: string }>;
  min?: number;
  max?: number;
  pattern?: string;
  accept?: string;        // File type filter
  maxFileSize?: number;   // Bytes
  maxFiles?: number;      // For file_multiple
  schema?: ZodType;       // Custom Zod validation
  tab?: string;           // Tab assignment
  triggerField?: string;  // Show when field is truthy
  showWhen?: (values) => boolean;  // Conditional visibility
}
```

### Tabs

```tsx
<FormModalBuilder
  title="User Settings"
  tabs={[
    {
      id: 'profile',
      label: 'Profile',
      fields: [
        { name: 'name', type: 'text', label: 'Name' },
        { name: 'email', type: 'email', label: 'Email' },
      ],
    },
    {
      id: 'security',
      label: 'Security',
      fields: [
        { name: 'password', type: 'password', label: 'Password' },
        { name: 'mfa', type: 'checkbox', label: 'Enable 2FA' },
      ],
    },
  ]}
  // ...other props
/>
```

### Conditional Fields

```tsx
fields={[
  { name: 'enableNotifications', type: 'checkbox', label: 'Enable Notifications' },
  {
    name: 'notificationEmail',
    type: 'email',
    label: 'Notification Email',
    triggerField: 'enableNotifications',  // Only shows when checkbox is checked
  },
]}
```

---

## SidebarMenu

A collapsible navigation sidebar with role-based visibility.

### Basic Usage

```tsx
import { SidebarMenu } from '@penguintechinc/react-libs';
import { Home, Users, Settings } from 'lucide-react';

<SidebarMenu
  logo={<img src="/logo.png" alt="Logo" className="h-8" />}
  categories={[
    {
      header: 'Main',
      items: [
        { name: 'Dashboard', href: '/dashboard', icon: Home },
        { name: 'Users', href: '/users', icon: Users, roles: ['admin'] },
      ],
    },
    {
      header: 'Settings',
      collapsible: true,
      items: [
        { name: 'General', href: '/settings', icon: Settings },
      ],
    },
  ]}
  currentPath={location.pathname}
  onNavigate={(href) => navigate(href)}
  userRole={user?.role}
/>
```

### Props Reference

```typescript
interface SidebarMenuProps {
  logo?: ReactNode;
  categories: MenuCategory[];
  currentPath: string;
  onNavigate?: (href: string) => void;
  footerItems?: MenuItem[];
  userRole?: string;
  width?: string;          // Default: 'w-64'
  colors?: SidebarColorConfig;
}

interface MenuCategory {
  header?: string;
  collapsible?: boolean;
  items: MenuItem[];
}

interface MenuItem {
  name: string;
  href: string;
  icon?: React.ComponentType<{ className?: string }>;
  roles?: string[];  // Only show if user has one of these roles
}
```

---

## AppConsoleVersion

Logs version info to the browser console on app startup.

### Usage

```tsx
import { AppConsoleVersion } from '@penguintechinc/react-libs';

function App() {
  return (
    <>
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

### Vite Configuration

```typescript
// vite.config.ts
export default defineConfig({
  define: {
    'import.meta.env.VITE_BUILD_TIME': JSON.stringify(Math.floor(Date.now() / 1000)),
    'import.meta.env.VITE_VERSION': JSON.stringify(process.env.npm_package_version || '0.0.0'),
  },
});
```

### Console Output

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

---

## Utility Exports

### OAuth2/OIDC Utilities

```typescript
import {
  buildOAuth2Url,
  buildCustomOAuth2Url,
  buildOIDCUrl,
  generateState,
  validateState,
  getProviderLabel,
  getProviderColors,
} from '@penguintechinc/react-libs';
```

### SAML Utilities

```typescript
import {
  buildSAMLRequest,
  buildSAMLRedirectUrl,
  initiateSAMLLogin,
  validateRelayState,
} from '@penguintechinc/react-libs';
```

### Hooks

```typescript
import { useCaptcha, useCookieConsent } from '@penguintechinc/react-libs';

// CAPTCHA state management
const { showCaptcha, incrementFailedAttempts, resetFailedAttempts } = useCaptcha(config);

// GDPR consent management
const { consent, showBanner, acceptAll, acceptEssential } = useCookieConsent(gdprConfig);
```

### Theme

```typescript
import { ELDER_LOGIN_THEME, mergeWithElderTheme } from '@penguintechinc/react-libs';

// Use default theme
const theme = ELDER_LOGIN_THEME;

// Merge custom colors with defaults
const customTheme = mergeWithElderTheme({
  primaryButton: 'bg-purple-500',
});
```

---

## Do NOT Implement Custom Versions

To maintain consistency and security, **never** implement custom versions of:

- ❌ Login pages - use `LoginPageBuilder`
- ❌ Navigation sidebars - use `SidebarMenu`
- ❌ Modal forms - use `FormModalBuilder`
- ❌ Console version logging - use `AppConsoleVersion`
- ❌ Cookie consent banners - use GDPR config in `LoginPageBuilder`
- ❌ Social login buttons - use `socialLogins` prop

**Why?**
1. **Security**: Centralized CAPTCHA, MFA, CSRF protection
2. **Consistency**: Uniform look across all apps
3. **Maintenance**: Bug fixes benefit all apps
4. **Compliance**: GDPR handled consistently
5. **Efficiency**: No duplicating complex auth logic

---

## Examples

See the [penguin-libs repository](https://github.com/penguintechinc/penguin-libs/tree/main/packages/react-libs/examples) for complete usage examples:

- `LoginPageExample.tsx` - 8 different login configurations
- `SidebarMenuExample.tsx` - Navigation patterns
- `UserFormExample.tsx` - Form modal usage
- `TabbedFormExample.tsx` - Multi-tab forms
- `ThemedFormExample.tsx` - Custom theming

---

**Package Version**: 1.1.0 | **Last Updated**: 2026-01-28 | **Maintained by**: Penguin Tech Inc
