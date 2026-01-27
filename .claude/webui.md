# WebUI Service Standards

## ⚠️ CRITICAL RULES

- **ALWAYS separate WebUI from API** - React runs in Node.js container, never with Flask
- **NEVER add curl/wget to Dockerfile** - Use native Node.js for health checks
- **ESLint + Prettier MANDATORY** - Run before every commit, no exceptions
- **Role-based UI required** - Admin, Maintainer, Viewer with conditional rendering
- **API auth interceptors required** - JWT tokens in Authorization header
- **Responsive design required** - Mobile-first, tested on multiple breakpoints
- **Keep file size under 5000 characters** - Split into modules/components

## Technology Stack

**Node.js 18+ with React**
- React 18.2+ for UI components
- React Router v6 for navigation
- Axios for HTTP client with interceptors
- @tanstack/react-query for data fetching
- Tailwind CSS v4 for styling
- lucide-react for icons
- Vite for build tooling

## Separate Container Requirements

WebUI runs in **separate Node.js container**, never bundled with Flask backend:
- Independent deployment and scaling
- Separate resource allocation
- Port 3000 (development) / 80 (production behind nginx)
- Express server proxies API calls to Flask backend (port 8080)

## Role-Based UI Implementation

**Three user roles control UI visibility:**

```javascript
// src/context/AuthContext.jsx
const { user } = useAuth();
const isAdmin = user?.role === 'Admin';
const isMaintainer = user?.role === 'Maintainer';
const isViewer = user?.role === 'Viewer';

// Conditional rendering
{isAdmin && <AdminSettings />}
{(isAdmin || isMaintainer) && <EditButton />}
{!isViewer && <DeleteButton />}
```

## API Client with Auth Interceptors

```javascript
// src/services/apiClient.js
const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8080'
});

// Request interceptor - add JWT token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('authToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor - handle 401 unauthorized
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('authToken');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

## Design Theme & Navigation

**Color Scheme:**
- Gold text default: `text-amber-400` (headings, primary text)
- Background: `bg-slate-900` (primary), `bg-slate-800` (secondary)
- Interactive elements: Sky blue `text-primary-500`

**Elder Sidebar Navigation Pattern:**
- Fixed left sidebar (w-64)
- Collapsible categories with state management
- Admin section with yellow accent for admin-only items
- Bottom user profile section with logout

**WaddlePerf Tab Navigation Pattern:**
- Horizontal tabs with underline indicators
- Active tab: blue underline, blue text
- Inactive: gold text on hover
- Tab content area below

## Linting & Code Quality

**MANDATORY - Run before every commit:**

```bash
npm run lint        # ESLint for code quality
npm run format      # Prettier for formatting
npm run type-check  # TypeScript type checking
```

**ESLint config:**
```json
{
  "extends": ["react-app", "react-app/jest"],
  "rules": {
    "no-unused-vars": "error",
    "no-console": "warn"
  }
}
```

## Responsive Design

- Mobile-first approach: `mobile → tablet → desktop`
- Grid layouts: `grid-cols-1 lg:grid-cols-2 xl:grid-cols-3`
- Test on: 320px (mobile), 768px (tablet), 1024px (desktop)
- No hardcoded widths: Use Tailwind breakpoints
- Sidebar hidden on mobile (`hidden lg:block`)

## Docker Health Check

```dockerfile
# ✅ Use Node.js built-in http module
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/healthz', \
    (r) => process.exit(r.statusCode === 200 ? 0 : 1)) \
    .on('error', () => process.exit(1))"
```

## Project Structure

```
services/webui/
├── src/
│   ├── components/       # Reusable UI components
│   ├── pages/            # Page-level components
│   ├── services/         # API client & services
│   ├── context/          # Auth, role context
│   ├── hooks/            # Custom React hooks
│   ├── App.jsx
│   └── index.jsx
├── public/
├── package.json
├── Dockerfile
└── .env
```
