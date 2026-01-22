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

FROM nginx:alpine
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
