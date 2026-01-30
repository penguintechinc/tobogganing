# ⚛️ Frontend Guide - Making Things Pretty

Part of [Development Standards](../STANDARDS.md)

Welcome to the frontend! This is where React magic happens. We build fast, beautiful UIs that users love.

**Foundation**: ALL frontend applications MUST use ReactJS with Vite, TypeScript, and modern practices.

## 🏗️ Project Structure

```
services/webui/
├── public/                    # Static assets served as-is
│   ├── index.html            # Entry HTML file
│   └── favicon.ico           # App icon
├── src/
│   ├── components/           # Reusable UI pieces (buttons, cards, etc)
│   ├── pages/                # Full page components (Dashboard, Settings)
│   ├── services/             # API communication helpers
│   ├── hooks/                # Custom React hooks (useUsers, usePosts)
│   ├── context/              # Global state (AuthContext, ThemeContext)
│   ├── utils/                # Helper functions (formatters, validators)
│   ├── App.jsx               # Root component, route definitions
│   └── index.jsx             # React DOM bootstrap
├── package.json              # Dependencies and scripts
├── vite.config.js            # Build configuration
├── Dockerfile                # Container definition
└── .env                       # Environment variables (GITIGNORED!)
```

Each folder has a clear job - components are UI building blocks, pages use them to create screens, hooks handle data logic, and context manages global state like "who's logged in."

## 🎨 Your First Component

Here's a real component you'd write:

```javascript
// src/components/UserCard.jsx
import React from 'react';
import './UserCard.css';

export const UserCard = ({ user, onEdit, onDelete }) => {
  return (
    <div className="user-card">
      <div className="user-header">
        <h3>{user.name}</h3>
        <span className="user-role">{user.role}</span>
      </div>
      <p className="user-email">{user.email}</p>
      <div className="card-actions">
        <button onClick={() => onEdit(user.id)} className="btn-primary">
          Edit
        </button>
        <button onClick={() => onDelete(user.id)} className="btn-danger">
          Delete
        </button>
      </div>
    </div>
  );
};
```

**Why this works**: It's a pure function that returns JSX. Pass in data (user, callbacks), get back UI. Simple!

## 🔌 Connecting to the Backend

Your React app talks to Flask via REST APIs. Here's how:

```javascript
// src/services/apiClient.js
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true, // Keeps session cookies
});

// Attach auth token to every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('authToken');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Handle 401 errors (expired login)
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

**Now fetch data** with React Query (automatic caching, refetching, loading states):

```javascript
// src/hooks/useUsers.js
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../services/apiClient';

export const useUsers = () => {
  return useQuery({
    queryKey: ['users'],
    queryFn: () => apiClient.get('/api/v1/users').then(r => r.data),
  });
};

export const useCreateUser = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userData) => apiClient.post('/api/v1/users', userData),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  });
};
```

Usage in a component:

```javascript
const { data: users, isLoading, error } = useUsers();
const createMutation = useCreateUser();

if (isLoading) return <div>Loading users...</div>;
if (error) return <div>Failed to load: {error.message}</div>;

return (
  <>
    {users.map(u => <UserCard key={u.id} user={u} />)}
    <button onClick={() => createMutation.mutate({ name: 'New User' })}>
      Add User
    </button>
  </>
);
```

## 💾 State Management

Think of state like your app's memory:

- **Local state** (useState): Component-specific data (form input, toggle)
- **Global state** (Context): Shared across app (current user, theme, permissions)
- **Server state** (React Query): Data from API (users list, posts) - Query handles caching/sync

**Authentication with Context**:

```javascript
// src/context/AuthContext.jsx
import { createContext, useContext, useState, useEffect } from 'react';
import { apiClient } from '../services/apiClient';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient.get('/auth/me')
      .then(r => setUser(r.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = async (email, password) => {
    const res = await apiClient.post('/auth/login', { email, password });
    setUser(res.data.user);
    localStorage.setItem('authToken', res.data.token);
  };

  const logout = async () => {
    await apiClient.post('/auth/logout');
    setUser(null);
    localStorage.removeItem('authToken');
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
```

**Protected Routes** stay simple:

```javascript
// src/components/ProtectedRoute.jsx
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return <div>Loading...</div>;
  return user ? children : <Navigate to="/login" />;
};
```

## 🎨 Styling Guide

Use CSS modules or Tailwind for component styles:

```css
/* src/components/UserCard.css */
.user-card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.user-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.user-role {
  background: #dbeafe;
  color: #1e40af;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.card-actions button {
  margin-right: 8px;
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.btn-primary {
  background: #3b82f6;
  color: white;
}

.btn-danger {
  background: #ef4444;
  color: white;
}
```

**Color palette**: Blues (#3b82f6), Reds (#ef4444), Grays (#6b7280), Greens (#10b981).

## 📦 Common Patterns

**Pagination with React Query**:
```javascript
const [page, setPage] = useState(1);
const { data, isLoading } = useQuery({
  queryKey: ['users', page],
  queryFn: () => apiClient.get(`/api/v1/users?page=${page}`),
});
```

**Form handling with validation**:
```javascript
const [form, setForm] = useState({ name: '', email: '' });
const [errors, setErrors] = useState({});

const handleSubmit = (e) => {
  e.preventDefault();
  const newErrors = {};
  if (!form.name) newErrors.name = 'Name required';
  if (!form.email.includes('@')) newErrors.email = 'Invalid email';
  if (Object.keys(newErrors).length) return setErrors(newErrors);

  createMutation.mutate(form);
};
```

**Conditional rendering**:
```javascript
{user?.role === 'admin' && <AdminPanel />}
{isLoading ? <Spinner /> : error ? <Error /> : <Content />}
```

## 🐛 Debugging Tips

**Browser DevTools**:
- React DevTools extension: Inspect component tree, state, props in real-time
- Network tab: Watch API calls, check response status/data
- Console: Watch for errors, add console.log for tracing

**Common issues**:
- **"Cannot read property of undefined"**: Check null/undefined values with `?.` operator
- **API calls hang**: Check network tab for CORS errors, ensure backend is running
- **State doesn't update**: React needs immutable updates - don't mutate directly
- **Component renders twice**: Normal in dev mode (React.StrictMode), only happens in dev
- **Stale cache**: React Query handles this, but manually trigger with `queryClient.invalidateQueries()`

**Test in browser**: `npm run dev` opens dev server with hot-reload. Edit code, see changes instantly!

## 📚 Essentials

**Required dependencies**:
- `react` 18.2+, `react-dom` - Core framework
- `react-router-dom` 6.20+ - Page routing
- `axios` 1.6+ - HTTP requests
- `@tanstack/react-query` 5.0+ - Server state management
- `vite` 5.0+ - Build tool (faster than Create React App)
- `eslint`, `prettier` - Code quality

**Scripts in package.json**:
```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "lint": "eslint src/",
    "format": "prettier --write src/"
  }
}
```

**Docker (multi-stage build)**:
```dockerfile
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

Build locally with `npm run build`, Docker serves the static files with nginx. Fast and lightweight!

## 📦 Shared React Libraries (MANDATORY)

All React applications **MUST** use `@penguintechinc/react-libs` for common components. See the [React Libraries Standards](REACT_LIBS.md) for complete documentation.

**Required components:**

| Component | Purpose | When to Use |
|-----------|---------|-------------|
| `AppConsoleVersion` | Console version logging | **Every app** |
| `LoginPageBuilder` | Login/auth page | Apps with authentication |
| `SidebarMenu` | Navigation sidebar | Apps with sidebar navigation |
| `FormModalBuilder` | Modal forms | All modal dialogs with forms |

**Quick example:**

```tsx
import { LoginPageBuilder, AppConsoleVersion, SidebarMenu } from '@penguintechinc/react-libs';

// In App.tsx
function App() {
  return (
    <>
      <AppConsoleVersion appName="MyApp" webuiVersion="1.0.0" />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/*" element={<MainLayout />} />
      </Routes>
    </>
  );
}
```

**Do NOT implement custom versions of:**
- ❌ Login pages → use `LoginPageBuilder`
- ❌ Navigation sidebars → use `SidebarMenu`
- ❌ Modal forms → use `FormModalBuilder`
- ❌ Version logging → use `AppConsoleVersion`

📚 **Full documentation**: [React Libraries Standards](REACT_LIBS.md)
