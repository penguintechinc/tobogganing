# Development Standards

This document consolidates all development standards, patterns, and requirements for projects using this template.

## Table of Contents

1. [Language Selection Criteria](#language-selection-criteria)
2. [Flask-Security-Too Integration](#flask-security-too-integration)
3. [ReactJS Frontend Standards](#reactjs-frontend-standards)
4. [Database Standards](#database-standards)
5. [Protocol Support](#protocol-support)
6. [API Versioning](#api-versioning)
7. [Performance Best Practices](#performance-best-practices)
8. [High-Performance Networking](#high-performance-networking)
9. [Microservices Architecture](#microservices-architecture)
10. [Docker Standards](#docker-standards)
11. [Testing Requirements](#testing-requirements)
12. [Security Standards](#security-standards)
13. [Documentation Standards](#documentation-standards)
14. [Web UI Design Standards](#web-ui-design-standards)
15. [WaddleAI Integration](#waddleai-integration)

---

## Language Selection Criteria

**Evaluate on a case-by-case basis which language to use for each project or service:**

### Python 3.13 (Default Choice)
**Use Python for most applications:**
- Web applications and REST APIs
- Business logic and data processing
- Integration services and connectors
- CRUD applications
- Admin panels and internal tools
- Low to moderate traffic applications (<10K req/sec)

**Advantages:**
- Rapid development and iteration
- Rich ecosystem of libraries
- Excellent for prototyping and MVPs
- Strong support for data processing
- Easy maintenance and debugging

### Go 1.24.x (Performance-Critical Only)
**Use Go ONLY for high-traffic, performance-critical applications:**
- Applications handling >10K requests/second
- Network-intensive services requiring low latency
- Services with latency requirements <10ms
- CPU-bound operations requiring maximum throughput
- Systems requiring minimal memory footprint
- Real-time processing pipelines

**Traffic Threshold Decision Matrix:**
| Requests/Second | Language Choice | Rationale |
|-----------------|-----------------|-----------|
| < 1K req/sec    | Python 3.13     | Development speed priority |
| 1K - 10K req/sec| Python 3.13     | Python can handle with optimization |
| 10K - 50K req/sec| Evaluate both  | Consider complexity vs performance needs |
| > 50K req/sec   | Go 1.24.x       | Performance becomes critical |

**Important Considerations:**
- Start with Python for faster iteration
- Profile and measure actual performance before switching
- Consider operational complexity of multi-language stack
- Go adds development overhead - only use when necessary

---

## Flask-Security-Too Integration

**MANDATORY for ALL Flask applications - provides comprehensive security framework**

### Core Features
- User authentication and session management
- Role-based access control (RBAC)
- Password hashing with bcrypt
- Email confirmation and password reset
- Two-factor authentication (2FA)
- Token-based authentication for APIs
- Login tracking and session management

### Integration with PyDAL

Flask-Security-Too integrates with PyDAL for database operations:

```python
from flask import Flask
from flask_security import Security, auth_required, hash_password
from flask_security.datastore import DataStore, UserDataMixin, RoleDataMixin
from pydal import DAL, Field
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'super-secret')
app.config['SECURITY_PASSWORD_SALT'] = os.getenv('SECURITY_PASSWORD_SALT', 'salt')
app.config['SECURITY_REGISTERABLE'] = True
app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
app.config['SECURITY_PASSWORD_HASH'] = 'bcrypt'

# PyDAL database setup
db = DAL(
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@"
    f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}",
    pool_size=10,
    migrate=True
)

# Define user and role tables
db.define_table('auth_user',
    Field('email', 'string', requires=IS_EMAIL(), unique=True),
    Field('username', 'string', unique=True),
    Field('password', 'string'),
    Field('active', 'boolean', default=True),
    Field('fs_uniquifier', 'string', unique=True),
    Field('confirmed_at', 'datetime'),
    migrate=True
)

db.define_table('auth_role',
    Field('name', 'string', unique=True),
    Field('description', 'text'),
    migrate=True
)

db.define_table('auth_user_roles',
    Field('user_id', 'reference auth_user'),
    Field('role_id', 'reference auth_role'),
    migrate=True
)

# Custom PyDAL datastore for Flask-Security-Too
class PyDALUserDatastore(DataStore):
    def __init__(self, db, user_model, role_model):
        self.db = db
        self.user_model = user_model
        self.role_model = role_model

    def put(self, model):
        self.db.commit()
        return model

    def delete(self, model):
        self.db(self.user_model.id == model.id).delete()
        self.db.commit()

    def find_user(self, **kwargs):
        query = self.db(self.user_model)
        for key, value in kwargs.items():
            if hasattr(self.user_model, key):
                query = query(self.user_model[key] == value)
        row = query.select().first()
        return row

# Initialize Flask-Security-Too
user_datastore = PyDALUserDatastore(db, db.auth_user, db.auth_role)
security = Security(app, user_datastore)

# Protected route example
@app.route('/api/protected')
@auth_required()
def protected_endpoint():
    return {'message': 'Access granted', 'user': current_user.email}

# Admin-only route example
@app.route('/api/admin')
@auth_required()
@roles_required('admin')
def admin_endpoint():
    return {'message': 'Admin access granted'}
```

### SSO Integration (Enterprise Feature)

**ALWAYS license-gate SSO as an enterprise-only feature:**

```python
from shared.licensing import requires_feature
from flask_security import auth_required

@app.route('/auth/saml/login')
@requires_feature('sso_saml')
def saml_login():
    """SAML SSO login - enterprise feature"""
    # SAML authentication logic
    pass

@app.route('/auth/oauth/login')
@requires_feature('sso_oauth')
def oauth_login():
    """OAuth SSO login - enterprise feature"""
    # OAuth authentication logic
    pass
```

**SSO Configuration:**
```python
# Enterprise SSO features (license-gated)
if license_client.has_feature('sso_saml'):
    app.config['SECURITY_SAML_ENABLED'] = True
    app.config['SECURITY_SAML_IDP_METADATA_URL'] = os.getenv('SAML_IDP_METADATA_URL')

if license_client.has_feature('sso_oauth'):
    app.config['SECURITY_OAUTH_ENABLED'] = True
    app.config['SECURITY_OAUTH_PROVIDERS'] = {
        'google': {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
        },
        'azure': {
            'client_id': os.getenv('AZURE_CLIENT_ID'),
            'client_secret': os.getenv('AZURE_CLIENT_SECRET'),
        }
    }
```

### Environment Variables

Required environment variables for Flask-Security-Too:

```bash
# Flask-Security-Too core
SECRET_KEY=your-secret-key-here
SECURITY_PASSWORD_SALT=your-password-salt
SECURITY_REGISTERABLE=true
SECURITY_SEND_REGISTER_EMAIL=false

# SSO (Enterprise only - license-gated)
SAML_IDP_METADATA_URL=https://idp.example.com/metadata
GOOGLE_CLIENT_ID=google-oauth-client-id
GOOGLE_CLIENT_SECRET=google-oauth-client-secret
AZURE_CLIENT_ID=azure-oauth-client-id
AZURE_CLIENT_SECRET=azure-oauth-client-secret
```

### Default Admin User Creation

**ALL Flask applications MUST create a default admin user on startup if it doesn't exist:**

```python
from flask_security import hash_password
from datetime import datetime

def create_default_admin_if_not_exists():
    """Create default admin user on application startup"""
    # Default credentials (should be changed in production)
    default_email = 'admin@localhost.local'
    default_password = 'admin123'

    # Check if admin already exists
    admin = user_datastore.find_user(email=default_email)
    if admin:
        return  # Admin already exists

    # Create admin role if it doesn't exist
    admin_role = user_datastore.find_role('admin')
    if not admin_role:
        admin_role = user_datastore.create_role(
            name='admin',
            description='Administrator with full system access'
        )

    # Create default admin user
    admin_user = user_datastore.create_user(
        email=default_email,
        password=hash_password(default_password),
        active=True,
        confirmed_at=datetime.utcnow()
    )

    # Assign admin role
    user_datastore.add_role_to_user(admin_user, admin_role)
    db.commit()

    print(f"✓ Default admin created: {default_email} / {default_password}")

# Call during application startup (before running server)
@app.before_first_request
def initialize_app():
    """Initialize application on first request"""
    with app.app_context():
        db.create_all()  # Create tables if they don't exist
        create_default_admin_if_not_exists()
```

**Alternative: Run during Docker container startup:**

```bash
# In your Docker entrypoint or Dockerfile CMD
python -c "from app import app, create_default_admin_if_not_exists; \
           create_default_admin_if_not_exists()"

python app.py  # Then start the Flask server
```

### Login Page UI Standards

**Login pages MUST follow these standards:**

1. **Logo Display**:
   - Logo placed ABOVE login form fields
   - Height: 300px (fixed)
   - Image file naming: `[project-name]-logo.png` or `[project-name]-logo.svg`
   - Location: `services/webui/public/images/logo.[png|svg]`
   - Also used as favicon in `public/favicon.ico`
   - Responsive: Scale down on mobile (<768px width)

2. **Default Login Credentials NOT Displayed**:
   - NEVER display default credentials on login page
   - NEVER pre-fill email/password fields
   - Default credentials only documented in README.md Quick Start section
   - Credentials must be changed in production

3. **Login Form Elements**:
   - Email field (required)
   - Password field (required, masked)
   - "Remember me" checkbox (optional)
   - Login button
   - "Forgot password?" link
   - Optional: SSO buttons (if enterprise features enabled)

**Example React Login Component:**

```jsx
// services/webui/src/pages/Login.jsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../services/apiClient';

export function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await apiClient.post('/api/v1/auth/login', {
        email,
        password,
      });

      // Store token and redirect
      localStorage.setItem('access_token', response.data.access_token);
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      {/* Logo: 300px height */}
      <img
        src="/images/logo.png"
        alt="Logo"
        className="login-logo"
        style={{ height: '300px' }}
      />

      <form onSubmit={handleLogin} className="login-form">
        {error && <div className="error-message">{error}</div>}

        <div className="form-group">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Enter your email"
            required
          />
        </div>

        <div className="form-group">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter your password"
            required
          />
        </div>

        <button type="submit" disabled={loading}>
          {loading ? 'Logging in...' : 'Login'}
        </button>

        <a href="/forgot-password" className="forgot-password">
          Forgot password?
        </a>
      </form>
    </div>
  );
}
```

**CSS Styling (300px logo, responsive):**

```css
.login-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.login-logo {
  height: 300px;
  width: auto;
  margin-bottom: 40px;
  max-width: 90vw;
}

.login-form {
  background: white;
  padding: 40px;
  border-radius: 8px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
  width: 100%;
  max-width: 400px;
}

@media (max-width: 768px) {
  .login-logo {
    height: 200px;
  }

  .login-form {
    padding: 20px;
  }
}
```

---

## ReactJS Frontend Standards

**ALL frontend applications MUST use ReactJS**

### Project Structure

```
services/webui/
├── public/
│   ├── index.html
│   └── favicon.ico
├── src/
│   ├── components/      # Reusable components
│   ├── pages/           # Page components
│   ├── services/        # API client services
│   ├── hooks/           # Custom React hooks
│   ├── context/         # React context providers
│   ├── utils/           # Utility functions
│   ├── App.jsx
│   └── index.jsx
├── package.json
├── Dockerfile
└── .env
```

### Required Dependencies

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "axios": "^1.6.0",
    "@tanstack/react-query": "^5.0.0",
    "zustand": "^4.4.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.0",
    "vite": "^5.0.0",
    "eslint": "^8.55.0",
    "prettier": "^3.1.0"
  }
}
```

### API Client Integration

**Create centralized API client for Flask backend:**

```javascript
// src/services/apiClient.js
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Important for session cookies
});

// Request interceptor for auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('authToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Redirect to login on unauthorized
      localStorage.removeItem('authToken');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

### Authentication Context

```javascript
// src/context/AuthContext.jsx
import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiClient } from '../services/apiClient';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is authenticated on mount
    const checkAuth = async () => {
      try {
        const response = await apiClient.get('/auth/user');
        setUser(response.data);
      } catch (error) {
        console.error('Not authenticated:', error);
      } finally {
        setLoading(false);
      }
    };
    checkAuth();
  }, []);

  const login = async (email, password) => {
    const response = await apiClient.post('/auth/login', { email, password });
    setUser(response.data.user);
    localStorage.setItem('authToken', response.data.token);
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

### Protected Routes

```javascript
// src/components/ProtectedRoute.jsx
import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return <div>Loading...</div>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
};
```

### React Query for Data Fetching

```javascript
// src/hooks/useUsers.js
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../services/apiClient';

export const useUsers = () => {
  return useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const response = await apiClient.get('/api/users');
      return response.data;
    },
  });
};

export const useCreateUser = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (userData) => {
      const response = await apiClient.post('/api/users', userData);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['users']);
    },
  });
};
```

### Component Standards

**Use functional components with hooks:**

```javascript
import React, { useState, useEffect } from 'react';
import { useUsers, useCreateUser } from '../hooks/useUsers';

export const UserList = () => {
  const { data: users, isLoading, error } = useUsers();
  const createUser = useCreateUser();

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;

  return (
    <div>
      <h2>Users</h2>
      <ul>
        {users.map(user => (
          <li key={user.id}>{user.name} - {user.email}</li>
        ))}
      </ul>
    </div>
  );
};
```

### Docker Configuration for React

```dockerfile
# services/webui/Dockerfile
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

---

## Database Standards

### Supported Databases

ALL applications MUST support the following databases by default:

| Database | DB_TYPE Value | Use Case | Notes |
|----------|---------------|----------|-------|
| **PostgreSQL** | `postgresql` | Production (default) | Primary database for all deployments |
| **MySQL** | `mysql` | Production alternative | Full support for MySQL 8.0+ |
| **MariaDB Galera** | `mysql` | High-availability clusters | Requires special handling (see below) |
| **SQLite** | `sqlite` | Development/lightweight | File-based, no server required |

### Dual-Library Architecture (Python) - MANDATORY

ALL Python applications MUST use a dual-library approach for database access:

1. **SQLAlchemy** - Database Initialization ONLY
   - Create database schemas and initial structure
   - One-time setup operations
   - NOT used for runtime queries or migrations

2. **PyDAL** - Runtime Operations and Migrations
   - ALL runtime database queries and operations
   - Schema migrations via `migrate=True`
   - Connection pooling and thread-safe access

**Why This Approach:**
- SQLAlchemy provides robust schema creation and DDL generation
- PyDAL offers simpler runtime query syntax and automatic migrations
- Separation of concerns between initialization and runtime
- Better compatibility with MariaDB Galera cluster requirements

#### SQLAlchemy Initialization Example

```python
"""Database initialization using SQLAlchemy - RUN ONCE during setup"""
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.schema import CreateTable
import os

def get_sqlalchemy_engine():
    """Create SQLAlchemy engine for initialization only"""
    db_type = os.getenv('DB_TYPE', 'postgresql')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'app_db')
    db_user = os.getenv('DB_USER', 'app_user')
    db_pass = os.getenv('DB_PASS', 'app_pass')

    # Map DB_TYPE to SQLAlchemy dialect
    dialect_map = {
        'postgresql': 'postgresql',
        'mysql': 'mysql+pymysql',
        'sqlite': 'sqlite',
    }
    dialect = dialect_map.get(db_type, 'postgresql')

    if db_type == 'sqlite':
        db_url = f"sqlite:///{db_name}.db"
    else:
        db_url = f"{dialect}://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    return create_engine(db_url)

def initialize_database():
    """One-time database schema initialization"""
    engine = get_sqlalchemy_engine()
    metadata = MetaData()

    # Define tables for initial schema creation
    users = Table('auth_user', metadata,
        Column('id', Integer, primary_key=True),
        Column('email', String(255), unique=True, nullable=False),
        Column('password', String(255)),
        Column('active', Boolean, default=True),
        Column('fs_uniquifier', String(64), unique=True),
        Column('confirmed_at', DateTime),
    )

    roles = Table('auth_role', metadata,
        Column('id', Integer, primary_key=True),
        Column('name', String(80), unique=True),
        Column('description', String(255)),
    )

    # Create all tables
    metadata.create_all(engine)
    print("Database schema initialized via SQLAlchemy")

# Run during application first-time setup ONLY
if __name__ == '__main__':
    initialize_database()
```

#### PyDAL Runtime Example

```python
"""Runtime database operations using PyDAL"""
from pydal import DAL, Field
import os

def get_pydal_connection():
    """Get PyDAL connection for runtime operations"""
    db_type = os.getenv('DB_TYPE', 'postgresql')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'app_db')
    db_user = os.getenv('DB_USER', 'app_user')
    db_pass = os.getenv('DB_PASS', 'app_pass')
    pool_size = int(os.getenv('DB_POOL_SIZE', '10'))

    if db_type == 'sqlite':
        db_uri = f"sqlite://{db_name}.db"
    else:
        db_uri = f"{db_type}://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    db = DAL(
        db_uri,
        pool_size=pool_size,
        migrate=True,  # PyDAL handles all migrations
        check_reserved=['all'],
        lazy_tables=True
    )

    # Define tables for PyDAL (mirrors SQLAlchemy schema)
    db.define_table('auth_user',
        Field('email', 'string', unique=True, notnull=True),
        Field('password', 'password'),
        Field('active', 'boolean', default=True),
        Field('fs_uniquifier', 'string', unique=True),
        Field('confirmed_at', 'datetime'),
        migrate=True
    )

    return db

# Runtime usage
db = get_pydal_connection()
# Query example: db(db.auth_user.active == True).select()
```

### MariaDB Galera Cluster Support

MariaDB Galera requires special handling for cluster-aware operations:

```python
"""MariaDB Galera-specific configuration"""
import os

def get_galera_pydal_connection():
    """PyDAL connection with Galera-specific settings"""
    db_uri = f"mysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

    db = DAL(
        db_uri,
        pool_size=int(os.getenv('DB_POOL_SIZE', '10')),
        migrate=True,
        check_reserved=['all'],
        lazy_tables=True,
        # Galera-specific: Use ROW format for binary logging
        driver_args={'charset': 'utf8mb4'}
    )

    return db

# Galera-specific considerations:
# 1. AUTO_INCREMENT: Use larger increment steps for multi-node writes
# 2. WSREP: Check wsrep_ready before critical operations
# 3. Transactions: Avoid long-running transactions (certification conflicts)
# 4. DDL: Schema changes replicate as TOI (Total Order Isolation)
```

**Galera Requirements:**
- Use `innodb_autoinc_lock_mode=2` for interleaved auto-increment
- Check `wsrep_ready` status before writes
- Keep transactions short to avoid certification failures
- Plan DDL operations during low-traffic periods

### Async and Multi-Threading Requirements

Database operations MUST use appropriate concurrency patterns based on workload characteristics:

#### Decision Matrix

| Workload Type | Recommended Approach | Libraries | Use Case |
|---------------|---------------------|-----------|----------|
| **I/O-bound (network, disk)** | Async/await | `asyncio`, `aiohttp`, `databases` | Web APIs, external service calls |
| **CPU-bound** | Multi-processing | `multiprocessing`, `concurrent.futures` | Data processing, calculations |
| **Mixed I/O with blocking** | Multi-threading | `threading`, `concurrent.futures` | Legacy integrations, file I/O |
| **High-concurrency web** | Async + thread pool | `asyncio` + `ThreadPoolExecutor` | Flask/async hybrid patterns |

#### Async Database Operations (Recommended for Web APIs)

```python
"""Async database operations for high-concurrency scenarios"""
import asyncio
from databases import Database
import os

# Async database connection (use alongside PyDAL for specific async needs)
async def get_async_db():
    """Get async database connection for I/O-bound operations"""
    db_type = os.getenv('DB_TYPE', 'postgresql')
    db_url = f"{db_type}://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

    database = Database(db_url)
    await database.connect()
    return database

async def fetch_users_async(database: Database):
    """Example async query - better for high-concurrency web requests"""
    query = "SELECT * FROM auth_user WHERE active = :active"
    return await database.fetch_all(query=query, values={"active": True})

# Usage in async context
async def main():
    db = await get_async_db()
    users = await fetch_users_async(db)
    await db.disconnect()
```

#### Multi-Threading for Blocking Operations

```python
"""Thread-safe database operations for blocking I/O"""
import threading
from concurrent.futures import ThreadPoolExecutor
from pydal import DAL, Field

# Thread-local storage for DAL instances
thread_local = threading.local()

def get_thread_db():
    """Get thread-local PyDAL connection"""
    if not hasattr(thread_local, 'db'):
        db_uri = f"{os.getenv('DB_TYPE')}://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        thread_local.db = DAL(db_uri, pool_size=5, migrate=False)
    return thread_local.db

def process_user(user_id: int):
    """Process user in separate thread"""
    db = get_thread_db()
    user = db(db.auth_user.id == user_id).select().first()
    # Process user...
    return user

# Parallel processing with thread pool
def process_users_parallel(user_ids: list[int], max_workers: int = 10):
    """Process multiple users in parallel threads"""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_user, user_ids))
    return results
```

#### Flask Async Hybrid Pattern

```python
"""Flask with async database operations"""
from flask import Flask, g
import asyncio
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=20)

def run_async(coro):
    """Run async coroutine in thread pool for Flask compatibility"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route('/users')
def get_users():
    """Endpoint using async database operations"""
    async def fetch():
        db = await get_async_db()
        users = await fetch_users_async(db)
        await db.disconnect()
        return users

    # Run async operation in thread pool
    future = executor.submit(run_async, fetch())
    users = future.result(timeout=30)
    return {"users": users}
```

#### Performance Guidelines

1. **Choose async when:**
   - Handling >100 concurrent requests
   - Operations are primarily network I/O (database, HTTP calls)
   - Low latency is critical (<100ms response time)

2. **Choose multi-threading when:**
   - Integrating with blocking libraries (legacy code)
   - File system operations
   - Moderate concurrency needs (10-100 concurrent operations)

3. **Choose multi-processing when:**
   - CPU-intensive calculations
   - Data transformation pipelines
   - Batch processing jobs

4. **Connection Pool Sizing:**
   - Async: Pool size = expected concurrent requests / 2
   - Threading: Pool size = number of worker threads + buffer
   - Rule of thumb: `pool_size = (2 * CPU_cores) + disk_spindles`

### Go Database Requirements

When using Go for high-performance applications, MUST use a DAL supporting PostgreSQL and MySQL:

**Recommended Options:**
1. **GORM** (Preferred)
   - Full-featured ORM
   - Supports PostgreSQL, MySQL, SQLite, SQL Server
   - Active maintenance and large community
   - Auto migrations and associations

2. **sqlx** (Alternative)
   - Lightweight extension of database/sql
   - Supports PostgreSQL, MySQL, SQLite
   - More control, less abstraction
   - Good for performance-critical scenarios

**Example GORM Implementation:**
```go
package main

import (
    "os"
    "gorm.io/driver/postgres"
    "gorm.io/driver/mysql"
    "gorm.io/gorm"
)

func initDB() (*gorm.DB, error) {
    dbType := os.Getenv("DB_TYPE") // "postgres" or "mysql"
    dsn := os.Getenv("DATABASE_URL")

    var dialector gorm.Dialector
    switch dbType {
    case "mysql":
        dialector = mysql.Open(dsn)
    default: // postgres
        dialector = postgres.Open(dsn)
    }

    db, err := gorm.Open(dialector, &gorm.Config{})
    return db, err
}
```

#### Environment Variables

Applications MUST accept these Docker environment variables:
- `DB_TYPE`: Database type (postgresql, mysql, sqlite, mssql, oracle, etc.)
- `DB_HOST`: Database host/IP address
- `DB_PORT`: Database port (default depends on DB_TYPE)
- `DB_NAME`: Database name
- `DB_USER`: Database username
- `DB_PASS`: Database password
- `DB_POOL_SIZE`: Connection pool size (default: 10)
- `DB_MAX_RETRIES`: Maximum connection retry attempts (default: 5)
- `DB_RETRY_DELAY`: Delay between retry attempts in seconds (default: 5)

#### Database Connection Requirements

1. **Wait for Database Initialization**: Application MUST wait for database to be ready
   - Implement retry logic with exponential backoff
   - Maximum retry attempts configurable via `DB_MAX_RETRIES`
   - Log each connection attempt for debugging
   - Fail gracefully with clear error messages

2. **Connection Pooling**: MUST use PyDAL's built-in connection pooling
   - Configure pool size via `DB_POOL_SIZE` environment variable
   - Implement proper connection lifecycle management
   - Handle connection timeouts and stale connections
   - Monitor pool utilization via metrics

3. **Database URI Construction**: Build connection string from environment variables
   ```python
   db_uri = f"{DB_TYPE}://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
   ```

#### Implementation Pattern

```python
import os
import time
from pydal import DAL, Field

def wait_for_database(max_retries=5, retry_delay=5):
    """Wait for database to be available with retry logic"""
    retries = 0
    while retries < max_retries:
        try:
            db = get_db_connection(test=True)
            db.close()
            print(f"Database connection successful")
            return True
        except Exception as e:
            retries += 1
            print(f"Database connection attempt {retries}/{max_retries} failed: {e}")
            if retries < max_retries:
                time.sleep(retry_delay)
    return False

def get_db_connection():
    """Initialize PyDAL database connection with pooling"""
    db_type = os.getenv('DB_TYPE', 'postgresql')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'app_db')
    db_user = os.getenv('DB_USER', 'app_user')
    db_pass = os.getenv('DB_PASS', 'app_pass')
    pool_size = int(os.getenv('DB_POOL_SIZE', '10'))

    db_uri = f"{db_type}://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    db = DAL(
        db_uri,
        pool_size=pool_size,
        migrate_enabled=True,
        check_reserved=['all'],
        lazy_tables=True
    )

    return db

# Application startup
if __name__ == '__main__':
    max_retries = int(os.getenv('DB_MAX_RETRIES', '5'))
    retry_delay = int(os.getenv('DB_RETRY_DELAY', '5'))

    if not wait_for_database(max_retries, retry_delay):
        print("Failed to connect to database after maximum retries")
        sys.exit(1)

    db = get_db_connection()
    # Continue with application initialization...
```

#### Thread Safety Requirements

**PyDAL MUST be used in a thread-safe manner:**

1. **Thread-local connections**: Each thread MUST have its own DAL instance
   - NEVER share a single DAL instance across multiple threads
   - Use thread-local storage (threading.local()) for per-thread DAL instances
   - Connection pooling handles multi-threaded access automatically

2. **Implementation Pattern for Threading:**
   ```python
   import threading
   from pydal import DAL

   # Thread-local storage for DAL instances
   thread_local = threading.local()

   def get_thread_db():
       """Get thread-local database connection"""
       if not hasattr(thread_local, 'db'):
           thread_local.db = DAL(
               db_uri,
               pool_size=10,
               migrate_enabled=True,
               check_reserved=['all'],
               lazy_tables=True
           )
       return thread_local.db

   # Usage in threaded context
   def worker_function():
       db = get_thread_db()  # Each thread gets its own connection
       # Perform database operations...
   ```

3. **Flask/WSGI Applications**: Flask already handles thread-local contexts
   ```python
   from flask import Flask, g

   app = Flask(__name__)

   def get_db():
       """Get database connection for current request context"""
       if 'db' not in g:
           g.db = DAL(db_uri, pool_size=10)
       return g.db

   @app.teardown_appcontext
   def close_db(error):
       """Close database connection after request"""
       db = g.pop('db', None)
       if db is not None:
           db.close()
   ```

4. **Async/Threading Considerations**:
   - When using threading.Thread, ensure each thread creates its own DAL instance
   - When using asyncio, use async-compatible database drivers if available
   - Connection pooling is thread-safe and manages concurrent access automatically
   - NEVER pass DAL instances between threads

5. **Multi-process Safety**:
   - Each process MUST create its own DAL instance
   - Connection pool is per-process, not shared across processes

---

## API Design Best Practices

**All APIs MUST follow these core design principles:**

### 1. Keep APIs Simple and Focused

- Single responsibility: One endpoint per logical action
- Consistent naming conventions across all endpoints
- Predictable URL structure
- Clear parameter names without abbreviations
- Minimize endpoint complexity with nested resources

**Good:**
```
GET /api/v1/users/{id}
POST /api/v1/users
PUT /api/v1/users/{id}
DELETE /api/v1/users/{id}
GET /api/v1/users/{id}/orders
```

**Avoid:**
```
GET /api/v1/get_user_info?uid=123
POST /api/v1/create_new_usr
GET /api/v1/usr/123/ord/get_all
```

### 2. Build Extensible and Backward-Compatible APIs

**Input Flexibility:**
- Accept additional fields in request bodies without breaking
- Use optional parameters with sensible defaults
- Implement request filtering via query parameters (e.g., `?status=active&limit=10`)
- Support different content types (JSON, form-data)

**Response Compatibility:**
- Add new fields to responses without breaking existing clients
- Use consistent response envelope structure
- Never remove fields, only deprecate them
- Include metadata (version, timestamp, links) in responses

**Example:**
```python
@app.route('/api/v2/users', methods=['POST'])
def create_user():
    data = request.get_json()
    # Accept new fields without breaking
    user = {
        'id': generate_id(),
        'name': data.get('name'),
        'email': data.get('email'),
        'phone': data.get('phone'),  # New field, optional
        'preferences': data.get('preferences', {}),  # New field, optional
    }
    return jsonify({
        'status': 'success',
        'data': user,
        'meta': {'version': 2, 'timestamp': datetime.utcnow().isoformat()}
    }), 201
```

### 3. Reuse and Leverage Existing APIs

- Search for existing endpoints before creating new ones
- Create single endpoint for multiple use cases when possible
- Use query parameters for filtering instead of separate endpoints
- Document common API patterns and encourage reuse

**Instead of multiple endpoints:**
```
GET /api/v1/active-users
GET /api/v1/inactive-users
GET /api/v1/admin-users
```

**Use single versioned endpoint with filtering:**
```
GET /api/v1/users?status=active
GET /api/v1/users?status=inactive
GET /api/v1/users?role=admin
GET /api/v1/users?status=active&role=admin
```

### 4. Consistent Versioning Strategy

- Use path-based versioning: `/api/v1/`, `/api/v2/`
- Version at major version level only (breaking changes)
- Maintain N-2 versions minimum (current + 2 previous)
- Never increment patch/minor versions in API URLs
- Include version in response metadata for clarity

---

## Protocol Support

**ALL applications MUST use appropriate protocols for inter-service and external communication:**

### API Design Principles

**Keep APIs Simple, Extensible, and Versioned:**
1. **Simple**: Minimize endpoint complexity, use clear resource-based design
2. **Extensible**: Support flexible input structures and backward-compatible responses for easy future expansion
3. **Reuse**: Leverage existing APIs where possible - avoid creating duplicate endpoints
4. **Versioned**: All APIs must support multiple versions with clear deprecation paths

### Communication Protocol Selection

**External Communication** (clients, third-party integrations):
- **REST API over HTTPS**: Client-facing and external APIs
  - RESTful HTTP endpoints (GET, POST, PUT, DELETE, PATCH)
  - JSON request/response format
  - Proper HTTP status codes (200, 201, 400, 404, 500, etc.)
  - Resource-based URL design with version prefix: `/api/v{major}/resource`
  - Support HTTP/1.1 minimum, HTTP/2 preferred
  - Fully documented with OpenAPI/Swagger specs

**Inter-Container Communication** (within Kubernetes namespace/cluster):
- **gRPC**: High-performance service-to-service calls (PREFERRED)
  - Protocol Buffers for message serialization
  - Binary protocol for lower latency and bandwidth
  - Bi-directional streaming support
  - Service definitions in .proto files
  - Health checking via gRPC health protocol
  - Use for internal APIs between microservices
  - Fallback to REST over HTTP/2 only if gRPC unavailable

**HTTP Protocol Support:**
- **HTTP/1.1**: Standard HTTP protocol (minimum requirement)
  - Keep-alive connections
  - Chunked transfer encoding
  - Compression (gzip, deflate)

- **HTTP/2**: Modern HTTP protocol (recommended)
  - Multiplexing multiple requests over single connection
  - Header compression (HPACK)
  - Stream prioritization
  - Better performance than HTTP/1.1

- **HTTP/3 (QUIC)**: Next-generation protocol (optional for high-performance scenarios)
  - UDP-based transport with TLS 1.3
  - Zero round-trip time (0-RTT) connection establishment
  - Built-in encryption
  - Consider for inter-container scenarios >10K req/sec

### Protocol Configuration via Environment Variables

Applications must accept these environment variables:
- `HTTP1_ENABLED`: Enable HTTP/1.1 (default: true)
- `HTTP2_ENABLED`: Enable HTTP/2 (default: true)
- `HTTP3_ENABLED`: Enable HTTP/3/QUIC (default: false)
- `GRPC_ENABLED`: Enable gRPC (default: true)
- `HTTP_PORT`: HTTP/REST API port (default: 8080)
- `GRPC_PORT`: gRPC port (default: 50051)
- `METRICS_PORT`: Prometheus metrics port (default: 9090)

### Implementation Example

```python
from flask import Flask, jsonify, request
import grpc
from concurrent import futures

app = Flask(__name__)

@app.route('/api/v1/resource', methods=['GET', 'POST'])
def rest_resource():
    if request.method == 'GET':
        return jsonify({'status': 'success', 'data': []})
    elif request.method == 'POST':
        return jsonify({'status': 'created'}), 201

# gRPC Server (run alongside Flask)
def serve_grpc():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()
```

### Required Dependencies

**Python:**
```
flask>=3.0.0
grpcio>=1.60.0
grpcio-tools>=1.60.0
hypercorn>=0.16.0  # For HTTP/2 and HTTP/3 support
aioquic>=0.9.0     # For QUIC/HTTP3
protobuf>=4.25.0
```

**Go:**
- `google.golang.org/grpc` for gRPC
- `golang.org/x/net/http2` for HTTP/2
- `github.com/quic-go/quic-go` for HTTP/3/QUIC

---

## API Versioning

**ALL REST APIs MUST use versioning in the URL path**

### URL Structure

**Required Format:** `/api/v{major}/endpoint`

**Examples:**
- `/api/v1/users` - User management
- `/api/v1/auth/login` - Authentication
- `/api/v1/organizations` - Organizations
- `/api/v2/analytics` - Version 2 of analytics endpoint

**Key Rules:**
1. **Always include version prefix** in URL path - NEVER use query parameters for versioning
2. **Semantic versioning** for API versions: `v1`, `v2`, `v3`, etc.
3. **Major version only** in URL - minor/patch versions are NOT in the URL
4. **Consistent prefix** across all endpoints in a service
5. **Version-specific** sub-resources: `/api/v1/users/{id}/profile` not `/api/v1/users/profile/{id}`

### Version Lifecycle

**Version Strategy (N-2 Support Model):**
- **Current Version**: Active development and fully supported
- **Previous Version (N-1)**: Supported with bug fixes and security patches
- **Two Versions Back (N-2)**: Supported with critical security patches only
- **Older Versions (N-3+)**: Deprecated with deprecation warning headers, no support

**Deprecation Process:**
1. Release new major version with improvements/breaking changes
2. Support current and 2 previous versions (N-2 minimum)
3. Communicate deprecation timeline 6 months in advance
4. Add deprecation header to N-3+ versions: `Deprecation: true`
5. Include sunset date header: `Sunset: <ISO 8601 date>`
6. Return `Link` header pointing to new version documentation
7. Provide migration guide for all deprecated versions

**Example Deprecation Headers:**
```python
@app.route('/api/v1/users', methods=['GET'])
def get_users_v1():
    """Deprecated - use /api/v2/users instead"""
    response = make_response(jsonify(users))
    response.headers['Deprecation'] = 'true'
    response.headers['Sunset'] = 'Sun, 01 Jan 2026 00:00:00 GMT'
    response.headers['Link'] = '</api/v2/users>; rel="successor-version"'
    return response
```

### Implementation Examples

**Python (Flask):**

```python
from flask import Flask, jsonify, request, make_response
from datetime import datetime

app = Flask(__name__)

# API v1 endpoints
@app.route('/api/v1/users', methods=['GET', 'POST'])
def users_v1():
    """User management - v1"""
    if request.method == 'GET':
        users = get_all_users()
        return jsonify({'data': users, 'version': 1})
    elif request.method == 'POST':
        new_user = create_user(request.json)
        return jsonify({'data': new_user, 'version': 1}), 201

@app.route('/api/v1/users/<int:user_id>', methods=['GET', 'PUT', 'DELETE'])
def user_detail_v1(user_id):
    """Single user detail - v1"""
    if request.method == 'GET':
        user = get_user(user_id)
        return jsonify({'data': user, 'version': 1})
    elif request.method == 'PUT':
        updated_user = update_user(user_id, request.json)
        return jsonify({'data': updated_user, 'version': 1})
    elif request.method == 'DELETE':
        delete_user(user_id)
        return '', 204

# API v2 endpoints (newer version with improved structure)
@app.route('/api/v2/users', methods=['GET', 'POST'])
def users_v2():
    """User management - v2 (improved response format)"""
    if request.method == 'GET':
        users = get_all_users()
        return jsonify({
            'status': 'success',
            'data': users,
            'meta': {
                'version': 2,
                'timestamp': datetime.utcnow().isoformat(),
                'total': len(users)
            }
        })
    elif request.method == 'POST':
        new_user = create_user(request.json)
        return jsonify({
            'status': 'created',
            'data': new_user,
            'meta': {'version': 2}
        }), 201

@app.route('/api/v2/users/<int:user_id>', methods=['GET', 'PUT', 'DELETE'])
def user_detail_v2(user_id):
    """Single user detail - v2 (improved response format)"""
    if request.method == 'GET':
        user = get_user(user_id)
        if not user:
            return jsonify({
                'status': 'error',
                'error': 'User not found',
                'meta': {'version': 2}
            }), 404
        return jsonify({
            'status': 'success',
            'data': user,
            'meta': {'version': 2}
        })
    elif request.method == 'PUT':
        updated_user = update_user(user_id, request.json)
        return jsonify({
            'status': 'success',
            'data': updated_user,
            'meta': {'version': 2}
        })
    elif request.method == 'DELETE':
        delete_user(user_id)
        return jsonify({
            'status': 'success',
            'meta': {'version': 2}
        }), 204

# Deprecated v1 with warnings
@app.before_request
def add_deprecation_headers_v1():
    """Add deprecation headers for v1 endpoints"""
    if request.path.startswith('/api/v1/'):
        @app.after_request
        def add_headers(response):
            response.headers['Deprecation'] = 'true'
            response.headers['Sunset'] = 'Sun, 01 Jan 2026 00:00:00 GMT'
            response.headers['Link'] = '</api/v2' + request.path[7:] + '>; rel="successor-version"'
            response.headers['Warning'] = '299 - "v1 API is deprecated, use v2 instead"'
            return response
        return None
```

**Go:**

```go
package main

import (
    "fmt"
    "net/http"
    "time"
)

type APIResponse struct {
    Status string      `json:"status"`
    Data   interface{} `json:"data"`
    Meta   APIMeta     `json:"meta"`
}

type APIMeta struct {
    Version   int       `json:"version"`
    Timestamp time.Time `json:"timestamp,omitempty"`
}

// API v1 endpoints
func getUsersV1(w http.ResponseWriter, r *http.Request) {
    users := getAllUsers()
    response := map[string]interface{}{
        "data":    users,
        "version": 1,
    }
    writeJSON(w, http.StatusOK, response)
}

func getUserDetailV1(w http.ResponseWriter, r *http.Request) {
    // Handle GET, PUT, DELETE for /api/v1/users/{id}
}

// API v2 endpoints (improved)
func getUsersV2(w http.ResponseWriter, r *http.Request) {
    users := getAllUsers()
    response := APIResponse{
        Status: "success",
        Data:   users,
        Meta: APIMeta{
            Version:   2,
            Timestamp: time.Now().UTC(),
        },
    }
    writeJSON(w, http.StatusOK, response)
}

func getUserDetailV2(w http.ResponseWriter, r *http.Request) {
    // Handle GET, PUT, DELETE for /api/v2/users/{id}
}

// Router setup
func setupRoutes() {
    // v1 endpoints
    http.HandleFunc("/api/v1/users", getUsersV1)
    http.HandleFunc("/api/v1/users/", getUserDetailV1)

    // v2 endpoints
    http.HandleFunc("/api/v2/users", getUsersV2)
    http.HandleFunc("/api/v2/users/", getUserDetailV2)
}

// Middleware for deprecation headers
func deprecationMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if strings.HasPrefix(r.URL.Path, "/api/v1/") {
            w.Header().Set("Deprecation", "true")
            w.Header().Set("Sunset", "Sun, 01 Jan 2026 00:00:00 GMT")
            w.Header().Set("Link", fmt.Sprintf("</api/v2%s>; rel=\"successor-version\"", strings.TrimPrefix(r.URL.Path, "/api/v1")))
            w.Header().Set("Warning", "299 - \"v1 API is deprecated, use v2 instead\"")
        }
        next.ServeHTTP(w, r)
    })
}
```

### Client Migration Guide

**For Frontend Clients:**

```javascript
// src/services/apiClient.js
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

// Use v2 by default
const API_VERSION = process.env.REACT_APP_API_VERSION || 'v2';

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/${API_VERSION}`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Response interceptor to handle deprecation warnings
apiClient.interceptors.response.use(
  (response) => {
    // Check for deprecation header
    if (response.headers.deprecation === 'true') {
      console.warn('API endpoint is deprecated:', {
        sunset: response.headers.sunset,
        successor: response.headers.link,
      });
      // Optionally migrate to new version
    }
    return response;
  },
  (error) => Promise.reject(error)
);

// Usage
export const getUsers = () => apiClient.get('/users');
export const createUser = (userData) => apiClient.post('/users', userData);
export const updateUser = (id, userData) => apiClient.put(`/users/${id}`, userData);
export const deleteUser = (id) => apiClient.delete(`/users/${id}`);
```

**Environment Variables:**
```bash
# Default to latest stable version
REACT_APP_API_VERSION=v2

# Can override in .env files
REACT_APP_API_VERSION=v1  # For backwards compatibility during migration
```

### Backwards Compatibility

**When introducing breaking changes:**

1. **Add new version** with breaking changes
2. **Maintain previous version** for minimum 12 months
3. **Document migration path** for users
4. **Provide migration tools** or helper functions
5. **Communicate deprecation timeline** to users

**Example Migration Timeline:**
- **Month 0**: Release v2 alongside v1
- **Month 1-12**: Both versions fully supported
- **Month 12**: v1 enters sunset period
- **Month 13**: v1 endpoints return errors

### API Documentation

**ALWAYS document API versions in README and API docs:**

```markdown
## API Versions

### Current Version: v2
- Latest features and improvements
- Recommended for all new integrations
- Supported indefinitely while v2 is current

### Previous Version: v1
- Deprecated as of 2024-01-01
- Supported until 2026-01-01
- [Migration guide](docs/migration-v1-to-v2.md)

### Version Comparison

| Feature | v1 | v2 |
|---------|----|----|
| User Management | ✓ | ✓ |
| Response Format | Simple | Enhanced metadata |
| Error Handling | Basic | Detailed error codes |
| Pagination | Query params | Header-based |
```

---

## Performance Best Practices

**ALWAYS prioritize performance and stability through modern concurrency patterns**

### Python Performance Requirements

#### Concurrency Patterns - Choose Based on Use Case

1. **asyncio** - For I/O-bound operations:
   - Database queries and connections
   - HTTP/REST API calls
   - File I/O operations
   - Network communication
   - Best for operations that wait on external resources

2. **threading.Thread** - For I/O-bound operations with blocking libraries:
   - Legacy libraries without async support
   - Blocking I/O operations
   - Moderate parallelism (10-100 threads)
   - Use ThreadPoolExecutor for managed thread pools

3. **multiprocessing** - For CPU-bound operations:
   - Data processing and transformations
   - Cryptographic operations
   - Image/video processing
   - Heavy computational tasks
   - Bypasses GIL for true parallelism

**Decision Matrix:**
```python
# I/O-bound + async library available → asyncio
async def fetch_data():
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# I/O-bound + blocking library → threading
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=10) as executor:
    results = executor.map(blocking_function, data)

# CPU-bound → multiprocessing
from multiprocessing import Pool
with Pool(processes=8) as pool:
    results = pool.map(cpu_intensive_function, data)
```

#### Dataclasses with Slots - MANDATORY

**ALL data structures MUST use dataclasses with slots for memory efficiency:**

```python
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass(slots=True, frozen=True)
class User:
    """User model with slots for 30-50% memory reduction"""
    id: int
    name: str
    email: str
    created_at: str
    metadata: dict = field(default_factory=dict)
```

**Benefits of Slots:**
- 30-50% less memory per instance
- Faster attribute access
- Better type safety with type hints
- Immutability with `frozen=True`

#### Type Hints - MANDATORY

**Comprehensive type hints are REQUIRED for all Python code:**

```python
from typing import Optional, List, Dict
from collections.abc import AsyncIterator

async def process_users(
    user_ids: List[int],
    batch_size: int = 100,
    callback: Optional[Callable[[User], None]] = None
) -> Dict[int, User]:
    """Process users with full type hints"""
    results: Dict[int, User] = {}
    for user_id in user_ids:
        user = await fetch_user(user_id)
        results[user_id] = user
        if callback:
            callback(user)
    return results
```

### Go Performance Requirements
- **Goroutines**: Leverage goroutines and channels for concurrent operations
- **Sync primitives**: Use sync.Pool, sync.Map for concurrent data structures
- **Context**: Proper context propagation for cancellation and timeouts

---

## High-Performance Networking

**Evaluate on a case-by-case basis for network-intensive applications**

### When to Consider XDP/AF_XDP

Only evaluate XDP (eXpress Data Path) and AF_XDP for applications with extreme network requirements:

**Traffic Thresholds:**
- Standard applications: Regular socket programming (most cases)
- High traffic (>100K packets/sec): Consider XDP/AF_XDP
- Extreme traffic (>1M packets/sec): XDP/AF_XDP strongly recommended

### XDP (eXpress Data Path)

**Kernel-level packet processing:**
- Processes packets at the earliest point in networking stack
- Bypass most of kernel networking code
- Can drop, redirect, or pass packets
- Ideal for DDoS mitigation, load balancing, packet filtering

**Use Cases:**
- Network firewalls and packet filters
- Load balancers
- DDoS protection
- High-frequency trading systems
- Real-time packet inspection

**Language Considerations:**
- Typically implemented in C with BPF bytecode
- Can be triggered from Go or Python applications
- Requires kernel support (Linux 4.8+)

### AF_XDP (Address Family XDP)

**Zero-copy socket for user-space packet processing:**
- Bypass kernel networking stack entirely
- Direct packet access from NIC to user-space
- Lowest latency possible for packet processing
- More flexible than kernel XDP

**Use Cases:**
- Custom network protocols
- Ultra-low latency applications
- Network monitoring and analytics
- Packet capture at high speeds

**Implementation Notes:**
```python
# Python with pyxdp (if available)
# Generally prefer Go for AF_XDP implementations
```

```go
// Go with AF_XDP libraries
import (
    "github.com/asavie/xdp"
)

// AF_XDP socket setup for high-performance packet processing
func setupAFXDP(ifname string, queueID int) (*xdp.Socket, error) {
    program := &xdp.SocketOptions{
        NumFrames:      4096,
        FrameSize:      2048,
        FillRingSize:   2048,
        CompletionRingSize: 2048,
        RxRingSize:     2048,
        TxRingSize:     2048,
    }

    return xdp.NewSocket(ifname, queueID, program)
}
```

### Decision Matrix: Networking Implementation

| Packets/Sec | Technology | Language | Justification |
|-------------|------------|----------|---------------|
| < 10K       | Standard sockets | Python 3.13 | Regular networking sufficient |
| 10K - 100K  | Optimized sockets | Python/Go | Standard with optimization |
| 100K - 500K | Consider XDP | Go + XDP | High performance needed |
| > 500K      | XDP/AF_XDP required | Go + AF_XDP | Extreme performance critical |

**Important:**
- Start with standard networking
- Profile actual performance before optimization
- XDP/AF_XDP adds significant complexity
- Requires specialized knowledge and maintenance

---

## Microservices Architecture

**ALWAYS use microservices architecture for application development**

### Three-Container Architecture

This template provides three base containers representing the core footprints:

| Container | Technology | Purpose | When to Use |
|-----------|------------|---------|-------------|
| **flask-backend** | Flask + PyDAL | Standard APIs, auth, CRUD | <10K req/sec, business logic |
| **go-backend** | Go + XDP/AF_XDP | High-performance networking | >10K req/sec, <10ms latency |
| **webui** | Node.js + React | Frontend shell | All frontend applications |

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              NGINX (optional)                               │
└─────────────────────────────────────────────────────────────────────────────┘
          │                        │                          │
┌─────────┴─────────┐   ┌─────────┴─────────┐   ┌────────────┴────────────┐
│  WebUI Container  │   │  Flask Backend    │   │    Go Backend           │
│  (Node.js/React)  │   │  (Flask/PyDAL)    │   │    (XDP/AF_XDP)         │
│                   │   │                   │   │                         │
│ - React SPA       │   │ - /api/v1/auth/*  │   │ - High-perf networking  │
│ - Proxies to APIs │   │ - /api/v1/users/* │   │ - XDP packet processing │
│ - Static assets   │   │ - /api/v1/hello   │   │ - AF_XDP zero-copy      │
│ - Port 3000       │   │ - Port 5000       │   │ - NUMA-aware memory     │
└───────────────────┘   └───────────────────┘   │ - Port 8080             │
                                 │              └─────────────────────────┘
                        ┌────────┴────────┐
                        │   PostgreSQL    │
                        └─────────────────┘
```

### Container Details

1. **WebUI Container** (Node.js + React)
   - Express server proxies API calls to backends
   - React SPA with role-based navigation
   - Elder-style collapsible sidebar
   - WaddlePerf-style tab navigation
   - Gold (amber-400) text theme

2. **Flask Backend** (Flask + PyDAL)
   - JWT authentication with bcrypt
   - User management CRUD (Admin only)
   - Role-based access: Admin, Maintainer, Viewer
   - PyDAL for multi-database support
   - Health check endpoints

3. **Go Backend** (Go + XDP/AF_XDP)
   - XDP for kernel-level packet processing
   - AF_XDP for zero-copy user-space I/O
   - NUMA-aware memory allocation
   - Memory slot pools for packet buffers
   - Prometheus metrics

4. **Connector Container** (placeholder)
   - External system integration
   - Background job processing

### Default Roles

| Role | Permissions |
|------|-------------|
| **Admin** | Full access: user CRUD, settings, all features |
| **Maintainer** | Read/write access to resources, no user management |
| **Viewer** | Read-only access to resources |

### Design Principles

- **Single Responsibility**: Each container has one clear purpose
- **Independent Deployment**: Services can be updated independently
- **API-First Design**: All inter-service communication via well-defined APIs
- **Data Isolation**: Each service owns its data
- **Fault Isolation**: Failure in one service doesn't cascade
- **Scalability**: Scale individual services based on demand

### Service Communication Patterns

#### Inter-Container Communication (Within Cluster)

**MUST use gRPC or HTTP/3 (QUIC) for all container-to-container communication:**

| Protocol | Use Case | Benefits |
|----------|----------|----------|
| **gRPC** | Service-to-service RPC calls | Binary protocol, streaming, code generation |
| **HTTP/3 (QUIC)** | High-throughput data transfer | 0-RTT, multiplexing, built-in encryption |

```python
# Example: Flask backend calling Go backend via gRPC
import grpc
from generated import backend_pb2, backend_pb2_grpc

def call_go_backend(request_data):
    """Internal service call using gRPC"""
    channel = grpc.insecure_channel('go-backend:50051')  # Docker network
    stub = backend_pb2_grpc.BackendServiceStub(channel)
    response = stub.ProcessData(backend_pb2.DataRequest(data=request_data))
    return response
```

**Why NOT REST for internal communication:**
- Higher latency due to text-based JSON serialization
- No streaming support
- More overhead for frequent service-to-service calls

#### External Communication (Clients, Integrations)

**MUST use REST API over HTTPS for all external-facing endpoints:**

| Protocol | Use Case | Benefits |
|----------|----------|----------|
| **REST/HTTPS** | Client apps, third-party integrations | Universal compatibility, human-readable, well-documented |

```python
# Example: Flask REST endpoint for external clients
@app.route('/api/v1/users', methods=['GET'])
def get_users():
    """External API endpoint - REST over HTTPS"""
    users = db(db.auth_user.active == True).select()
    return jsonify({'users': [u.as_dict() for u in users]})
```

**When to use REST externally:**
- Client-facing APIs (web, mobile apps)
- Third-party integrations and webhooks
- Public API access
- Documentation and developer experience priority

#### Communication Summary

| Direction | Protocol | Port | Example |
|-----------|----------|------|---------|
| WebUI → Flask Backend | REST/HTTPS | 8080 | External client requests |
| Flask → Go Backend | gRPC | 50051 | Internal high-perf operations |
| Go → Flask | gRPC or HTTP/3 | 50051/443 | Internal callbacks |
| External Client → WebUI | HTTPS | 443 | Browser/mobile access |
| External API → Flask | REST/HTTPS | 8080 | Third-party integrations |

#### Asynchronous Communication

- **Message Queues**: Kafka, RabbitMQ for event-driven architecture
- **Use for**: Background jobs, event sourcing, decoupled processing

#### Infrastructure

- **Service Discovery**: Docker networking or service mesh
- **Circuit Breakers**: Fallback mechanisms for failures
- **API Gateway**: MarchProxy for routing external traffic (see below)

### MarchProxy API Gateway Integration

Applications are expected to run behind **MarchProxy** (`~/code/MarchProxy`) for API gateway and load balancing functionality.

**IMPORTANT:** Do NOT include MarchProxy in the application's `docker-compose.yml` - it's external infrastructure managed separately.

#### Configuration Export

Generate MarchProxy-compatible import configuration files in `config/marchproxy/`:

```
config/
└── marchproxy/
    ├── services.json          # Service definitions
    ├── mappings.json          # Route mappings
    └── import-config.json     # Combined import file
```

#### Service Definition Format

```json
{
  "services": [
    {
      "name": "myapp-flask-api",
      "ip_fqdn": "flask-backend",
      "port": 8080,
      "protocol": "http",
      "collection": "myapp",
      "auth_type": "jwt",
      "tls_enabled": false,
      "health_check_enabled": true,
      "health_check_path": "/healthz",
      "health_check_interval": 30
    },
    {
      "name": "myapp-go-backend",
      "ip_fqdn": "go-backend",
      "port": 50051,
      "protocol": "grpc",
      "collection": "myapp",
      "auth_type": "none",
      "tls_enabled": false,
      "health_check_enabled": true,
      "health_check_path": "/grpc.health.v1.Health/Check",
      "health_check_interval": 10
    },
    {
      "name": "myapp-webui",
      "ip_fqdn": "webui",
      "port": 80,
      "protocol": "http",
      "collection": "myapp",
      "auth_type": "none",
      "tls_enabled": false,
      "health_check_enabled": true,
      "health_check_path": "/",
      "health_check_interval": 30
    }
  ]
}
```

#### Mapping Definition Format

```json
{
  "mappings": [
    {
      "name": "myapp-external-api",
      "description": "External REST API access",
      "source_services": ["external"],
      "dest_services": ["myapp-flask-api"],
      "listen_port": 443,
      "protocol": "https",
      "path_prefix": "/api/v1"
    },
    {
      "name": "myapp-webui-access",
      "description": "WebUI frontend access",
      "source_services": ["external"],
      "dest_services": ["myapp-webui"],
      "listen_port": 443,
      "protocol": "https",
      "path_prefix": "/"
    }
  ]
}
```

#### Import Script

Create `scripts/marchproxy-import.sh`:

```bash
#!/bin/bash
# Import service configuration into MarchProxy

MARCHPROXY_API="${MARCHPROXY_API:-http://localhost:8000}"
CLUSTER_API_KEY="${CLUSTER_API_KEY:-}"

if [ -z "$CLUSTER_API_KEY" ]; then
    echo "Error: CLUSTER_API_KEY environment variable required"
    exit 1
fi

# Import services
curl -X POST "$MARCHPROXY_API/api/v1/services/import" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $CLUSTER_API_KEY" \
    -d @config/marchproxy/import-config.json

echo "MarchProxy configuration imported"
```

#### Python Configuration Generator

```python
"""Generate MarchProxy import configuration from application settings"""
import json
import os
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class MarchProxyService:
    name: str
    ip_fqdn: str
    port: int
    protocol: str = "http"
    collection: Optional[str] = None
    auth_type: str = "none"
    tls_enabled: bool = False
    health_check_enabled: bool = True
    health_check_path: str = "/healthz"
    health_check_interval: int = 30

def generate_marchproxy_config(app_name: str, services: list[MarchProxyService]) -> dict:
    """Generate MarchProxy-compatible import configuration"""
    return {
        "services": [asdict(s) for s in services],
        "metadata": {
            "app_name": app_name,
            "generated_by": "project-template",
            "version": os.getenv("APP_VERSION", "0.0.0")
        }
    }

def write_marchproxy_config(config: dict, output_dir: str = "config/marchproxy"):
    """Write configuration files for MarchProxy import"""
    os.makedirs(output_dir, exist_ok=True)

    with open(f"{output_dir}/import-config.json", "w") as f:
        json.dump(config, f, indent=2)

# Example usage
if __name__ == "__main__":
    services = [
        MarchProxyService(
            name="myapp-flask-api",
            ip_fqdn="flask-backend",
            port=8080,
            protocol="http",
            collection="myapp",
            auth_type="jwt"
        ),
        MarchProxyService(
            name="myapp-go-backend",
            ip_fqdn="go-backend",
            port=50051,
            protocol="grpc",
            collection="myapp"
        ),
    ]

    config = generate_marchproxy_config("myapp", services)
    write_marchproxy_config(config)
```

#### Integration Notes

1. **Service Names**: Use `{app_name}-{service}` naming convention for easy filtering
2. **Collection**: Group all app services under same collection for bulk operations
3. **Protocol Selection**:
   - `http`/`https`: REST API endpoints (Flask)
   - `grpc`: Internal high-performance services (Go backend)
   - `tcp`: Raw TCP connections
4. **Health Checks**: Always enable for production services
5. **Auth Type**: Use `jwt` for external-facing APIs, `none` for internal gRPC

#### MarchProxy API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/services` | POST | Create service |
| `/api/v1/services/import` | POST | Bulk import services |
| `/api/v1/services` | GET | List services |
| `/api/v1/services/{id}` | PUT | Update service |
| `/api/v1/services/{id}` | DELETE | Delete service |
| `/api/v1/config/{cluster_id}` | GET | Get cluster config |

📚 **Full MarchProxy Documentation**: See `~/code/MarchProxy/api-server/README.md`

### Container Organization

```
project-name/
├── services/
│   ├── flask-backend/      # Flask + PyDAL backend (auth, users, APIs)
│   ├── go-backend/         # Go high-performance backend (XDP, NUMA)
│   ├── webui/              # Node.js + React frontend shell
│   └── connector/          # Integration services (placeholder)
```

---

## Docker Standards

### Build Standards

**All builds MUST be executed within Docker containers:**

```bash
# Go builds (using debian-slim)
docker run --rm -v $(pwd):/app -w /app golang:1.24-slim go build -o bin/app

# Python builds (using debian-slim)
docker run --rm -v $(pwd):/app -w /app python:3.13-slim pip install -r requirements.txt
```

**Use multi-stage builds with debian-slim:**
```dockerfile
FROM golang:1.24-slim AS builder
FROM debian:stable-slim AS runtime

FROM python:3.13-slim AS builder
FROM debian:stable-slim AS runtime
```

### Docker Compose Standards

**ALWAYS create docker-compose.dev.yml for local development**

**Prefer Docker networks over host ports:**
- Minimize host port exposure
- Only expose ports for developer access
- Use named Docker networks for service-to-service communication

```yaml
# docker-compose.dev.yml
version: '3.8'

networks:
  app-network:
    driver: bridge
  db-network:
    driver: bridge

services:
  app:
    build: ./apps/app
    networks:
      - app-network
      - db-network
    ports:
      - "8080:8080"  # Only expose for developer access
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/appdb

  postgres:
    image: postgres:16-alpine
    networks:
      - db-network
    # NO ports exposed to host - only accessible via Docker network
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=appdb
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  postgres-data:
```

### Multi-Arch Build Strategy

GitHub Actions should use multi-arch builds:
```yaml
- uses: docker/build-push-action@v4
  with:
    platforms: linux/amd64,linux/arm64
    context: ./apps/app
    file: ./apps/app/Dockerfile
```

---

## Testing Requirements

### Unit Testing

**All applications MUST have comprehensive unit tests:**

- **Network isolation**: Unit tests must NOT require external network connections
- **No external dependencies**: Cannot reach databases, APIs, or external services
- **Use mocks/stubs**: Mock all external dependencies and I/O operations
- **KISS principle**: Keep unit tests simple, focused, and fast
- **Test isolation**: Each test should be independent and repeatable
- **Fast execution**: Unit tests should complete in milliseconds

### Integration Testing

- Test component interactions
- Use test databases and services
- Verify API contracts
- Test authentication and authorization

### End-to-End Testing

- Test critical user workflows
- Use staging environment
- Verify full system integration

### Performance Testing

- Benchmark critical operations
- Load testing for scalability
- Regression testing for performance

---

## Security Standards

### Input Validation

- ALL inputs MUST have appropriate validators
- Use framework-native validation (PyDAL validators, Go libraries)
- Implement XSS and SQL injection prevention
- Server-side validation for all client input
- CSRF protection using framework native features

### Authentication & Authorization

**Core Requirements:**
- Multi-factor authentication support
- Role-based access control (RBAC) with OAuth2-style scopes
- API key management with rotation
- JWT token validation with proper expiration
- Session management with secure cookies

**OAuth2-Style Scopes Model:**
- All APIs and user permissions MUST be scopable similar to OAuth2 scopes
- Scopes define granular permissions (e.g., `users:read`, `users:write`, `reports:read`, `analytics:admin`)
- Users and API clients receive tokens with specific scope sets
- Endpoints check requested operation against available scopes
- Scopes are hierarchical and composable

**Role-Based Access Control with Scopes:**

Implement three-tier role system at multiple levels:

1. **Global Level** - Organization-wide roles:
   - **Admin**: Full system access, user management, all scopes
   - **Maintainer**: Read/write access to resources, no user management, limited scopes
   - **Viewer**: Read-only access, minimal scopes (e.g., `:read` only)
   - **Custom Roles**: User-defined with selected scopes

2. **Container/Team Level** - Per service/team access:
   - **Team Admin**: Full access within container/team
   - **Team Maintainer**: Read/write within container/team
   - **Team Viewer**: Read-only within container/team
   - **Custom Roles**: Selected scopes for container context

3. **Resource Level** - Per-resource permissions:
   - **Owner**: Full control over specific resource
   - **Editor**: Read/write on specific resource
   - **Viewer**: Read-only on specific resource
   - **Custom Roles**: Specific scopes for resource

**Implementation Pattern:**

```python
# Define scopes for API endpoints
SCOPES = {
    'users:read': 'Read user data',
    'users:write': 'Create/update users',
    'users:admin': 'Delete users, manage roles',
    'reports:read': 'Read reports',
    'reports:write': 'Create/update reports',
    'analytics:read': 'Read analytics',
    'analytics:admin': 'Configure analytics',
}

# Role definitions with scope mappings
ROLE_SCOPES = {
    'global': {
        'admin': ['users:read', 'users:write', 'users:admin', 'reports:read', 'reports:write', 'analytics:read', 'analytics:admin'],
        'maintainer': ['users:read', 'users:write', 'reports:read', 'reports:write', 'analytics:read'],
        'viewer': ['users:read', 'reports:read', 'analytics:read'],
    },
    'container': {
        'admin': ['users:read', 'users:write', 'reports:read', 'reports:write'],
        'maintainer': ['users:read', 'reports:read', 'reports:write'],
        'viewer': ['users:read', 'reports:read'],
    },
}

from flask import Flask, request
from functools import wraps

app = Flask(__name__)

def require_scope(*required_scopes):
    """Decorator to check if user has required scopes"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get user from request context (from JWT token)
            user = request.user  # Set by authentication middleware
            user_scopes = user.get_scopes()

            # Check if user has at least one of required scopes
            has_scope = any(scope in user_scopes for scope in required_scopes)
            if not has_scope:
                return {'error': 'Insufficient permissions', 'required_scopes': required_scopes}, 403

            return func(*args, **kwargs)
        return wrapper
    return decorator

@app.route('/api/v1/users', methods=['GET'])
@require_scope('users:read')
def list_users():
    """List users - requires users:read scope"""
    users = db.users.select().fetchall()
    return jsonify({'data': users})

@app.route('/api/v1/users', methods=['POST'])
@require_scope('users:write')
def create_user():
    """Create user - requires users:write scope"""
    data = request.get_json()
    user = db.users.insert(**data)
    return jsonify({'data': user}), 201

@app.route('/api/v1/users/<int:user_id>', methods=['DELETE'])
@require_scope('users:admin')
def delete_user(user_id):
    """Delete user - requires users:admin scope"""
    db.users.delete(db.users.id == user_id)
    return '', 204
```

**Custom Roles with Scope Selection:**

```python
# Allow users to create custom roles
@app.route('/api/v1/roles/custom', methods=['POST'])
@require_scope('users:admin')
def create_custom_role():
    """Create custom role with selected scopes"""
    data = request.get_json()
    role_name = data.get('name')
    selected_scopes = data.get('scopes', [])

    # Validate requested scopes
    available_scopes = set(SCOPES.keys())
    if not set(selected_scopes).issubset(available_scopes):
        return {'error': 'Invalid scopes requested'}, 400

    # Create custom role
    custom_role = {
        'name': role_name,
        'scopes': selected_scopes,
        'level': data.get('level', 'container'),  # global, container, or resource
        'created_by': request.user.id,
    }
    db.custom_roles.insert(**custom_role)
    return jsonify({'data': custom_role}), 201

# Assign custom role to user
@app.route('/api/v1/users/<int:user_id>/roles', methods=['POST'])
@require_scope('users:admin')
def assign_role_to_user(user_id):
    """Assign role (standard or custom) to user"""
    data = request.get_json()
    role_id = data.get('role_id')
    scope = data.get('scope', 'global')  # global, container_id, or resource_id

    assignment = {
        'user_id': user_id,
        'role_id': role_id,
        'scope': scope,
    }
    db.role_assignments.insert(**assignment)
    return jsonify({'data': assignment}), 201
```

**JWT Token with Scopes:**

```python
import jwt
from datetime import datetime, timedelta

def create_access_token(user, scopes, expires_in=3600):
    """Create JWT token with scopes"""
    payload = {
        'sub': user.id,
        'user_email': user.email,
        'scopes': scopes,  # Include scopes in token
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
    return token

def verify_token(token):
    """Verify token and extract scopes"""
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.InvalidTokenError:
        return None
```

**API Client Scopes:**

API clients (service accounts, third-party integrations) should also have scope-based permissions:

```python
# Create API client with specific scopes
@app.route('/api/v1/clients', methods=['POST'])
@require_scope('users:admin')
def create_api_client():
    """Create API client with selected scopes"""
    data = request.get_json()
    client_name = data.get('name')
    client_scopes = data.get('scopes', [])

    # Generate API key
    api_key = generate_secure_key()

    client = {
        'name': client_name,
        'api_key': hash_api_key(api_key),
        'scopes': client_scopes,
        'created_by': request.user.id,
        'created_at': datetime.utcnow(),
    }
    db.api_clients.insert(**client)

    # Return plaintext API key only once
    return jsonify({
        'data': client,
        'api_key': api_key,  # Only shown once
    }), 201
```

### TLS/Encryption

- **TLS enforcement**: TLS 1.2 minimum, prefer TLS 1.3
- **Connection security**: Use HTTPS where possible
- **Modern protocols**: HTTP3/QUIC for high-performance
- **Standard security**: JWT, MFA, mTLS where applicable
- **Enterprise SSO**: SAML/OAuth2 as enterprise features

### Dependency Security

- **ALWAYS check Dependabot alerts** before commits
- **Monitor vulnerabilities** via Socket.dev
- **Mandatory security scanning** before dependency changes
- **Fix all security alerts immediately**
- **Version pinning**: Exact versions for security-critical dependencies

### Vulnerability Response Process

1. Identify affected packages and severity
2. Update to patched versions immediately
3. Test updated dependencies thoroughly
4. Document security fixes in commit messages
5. Verify no new vulnerabilities introduced

---

## Documentation Standards

### README.md Standards

**ALWAYS include build status badges:**
- CI/CD pipeline status (GitHub Actions)
- Test coverage status (Codecov)
- Go Report Card (for Go projects)
- Version badge
- License badge (Limited AGPL3)

**ALWAYS include catchy ASCII art** below badges

**Company homepage**: Point to **www.penguintech.io**

**Quick Start Section - DEFAULT CREDENTIALS DOCUMENTATION:**

The README.md MUST include a Quick Start section documenting default credentials for development:

```markdown
## Quick Start

### Prerequisites
- Docker & Docker Compose
- Git

### Development Environment

Start all services:
```bash
make dev
```

Access the application at `http://localhost:3000`

**Default Development Credentials:**
- **Email**: `admin@localhost.local`
- **Password**: `admin123`

⚠️ **IMPORTANT**: Change these credentials in production. The default admin user is automatically created on first startup.

### Login
1. Navigate to `http://localhost:3000`
2. Enter default email: `admin@localhost.local`
3. Enter default password: `admin123`
4. Click Login

### Change Default Password
After first login, immediately change the admin password in Settings → Security.

### Production Deployment
See [Deployment Guide](docs/DEPLOYMENT.md) for production setup without default credentials.
```

**Key Points:**
- Default credentials MUST be documented in README Quick Start
- Default credentials MUST NOT be displayed on the login page itself
- Clearly mark credentials as for development only
- Warn about changing passwords in production
- Link to production deployment guide

### CLAUDE.md File Management

- **Maximum**: 35,000 characters
- **High-level approach**: Reference detailed docs
- **Documentation strategy**: Create detailed docs in `docs/` folder
- **Keep focused**: Critical context and workflow instructions only

### API Documentation

- Comprehensive endpoint documentation
- Request/response examples
- Error codes and handling
- Authentication requirements
- Rate limiting information

### Architecture Documentation

- System architecture diagrams
- Component interaction patterns
- Data flow documentation
- Decision records (ADRs)

---

## Logging & Monitoring

### Logging Standards

- **Console logging**: Always implement console output
- **Multi-destination logging**:
  - UDP syslog (legacy)
  - HTTP3/QUIC to Kafka
  - Cloud-native services (AWS/GCP)
- **Logging levels**:
  - `-v`: Warnings and criticals only
  - `-vv`: Info level (default)
  - `-vvv`: Debug logging

### Monitoring Requirements

- **Health endpoints**: ALL applications implement `/healthz`
- **Metrics endpoints**: Prometheus metrics endpoint required
- **Structured logging**: Use correlation IDs
- **Distributed tracing**: Support for complex flows
- **Alerting**: Critical failure notifications

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, generate_latest

REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration')

@app.route('/metrics')
def metrics():
    return generate_latest(), {'Content-Type': 'text/plain'}
```

---

## Web Framework Standards

- **Flask primary**: Use Flask for ALL Python web applications
- **PyDAL mandatory**: ALL Python applications use PyDAL
- **Health endpoints**: `/healthz` required for all applications
- **Metrics endpoints**: Prometheus metrics required

---

## Web UI Design Standards

**ALL ReactJS frontend applications MUST follow these design patterns:**

### Design Philosophy

- **Dark Theme Default**: Use dark backgrounds with light text for reduced eye strain
- **Consistent Spacing**: Use standardized spacing scale (Tailwind's spacing utilities)
- **Smooth Transitions**: Apply `transition-colors` or `transition-all 0.2s` for state changes
- **Subtle Gradients**: Use gradient accents sparingly for modern aesthetic
- **Responsive Design**: Mobile-first approach with breakpoint-based layouts

### Color Palette (Dark Theme)

**CSS Variables (Required):**
```css
:root {
  /* Background colors */
  --bg-primary: #0f172a;      /* slate-900 - main background */
  --bg-secondary: #1e293b;    /* slate-800 - sidebar/cards */
  --bg-tertiary: #334155;     /* slate-700 - hover states */

  /* Text colors - Gold default */
  --text-primary: #fbbf24;    /* amber-400 - headings, primary text */
  --text-secondary: #f59e0b;  /* amber-500 - body text */
  --text-muted: #d97706;      /* amber-600 - secondary/muted text */
  --text-light: #fef3c7;      /* amber-100 - high contrast text */

  /* Accent colors (sky-blue for interactive elements) */
  --primary-400: #38bdf8;
  --primary-500: #0ea5e9;
  --primary-600: #0284c7;
  --primary-700: #0369a1;

  /* Border colors */
  --border-color: #334155;    /* slate-700 */

  /* Admin/Warning accent */
  --warning-color: #eab308;   /* yellow-500 */
}
```

**Gold Text Usage:**
- Default body text: `text-amber-400` or `var(--text-primary)`
- Headings: `text-amber-400` with `font-semibold`
- Muted/secondary text: `text-amber-600` or `var(--text-muted)`
- High contrast when needed: `text-amber-100` or `var(--text-light)`
- Interactive elements (links, buttons): Use primary blue accent for distinction

### Sidebar Navigation Pattern (Elder Style)

**Required for applications with complex navigation:**

**Structure:**
```
┌─────────────────────────────────────────────────────────────┐
│  Logo Section (h-16, centered)                              │
├─────────────────────────────────────────────────────────────┤
│  Primary Navigation (always visible)                        │
│    ├── Dashboard                                            │
│    ├── Search                                               │
│    └── Overview                                             │
├─────────────────────────────────────────────────────────────┤
│  Category: Assets (collapsible)           [▼]               │
│    ├── Entities                                             │
│    ├── Organizations                                        │
│    └── Services                                             │
├─────────────────────────────────────────────────────────────┤
│  Category: Settings (collapsible)         [▶]               │
│    └── (collapsed)                                          │
├─────────────────────────────────────────────────────────────┤
│  Admin Section (role-based, yellow accent)                  │
│    └── System Settings                                      │
├─────────────────────────────────────────────────────────────┤
│  User Section (bottom, border-top)                          │
│    ├── Profile                                              │
│    └── Logout                                               │
└─────────────────────────────────────────────────────────────┘
```

**Implementation Requirements:**

1. **Fixed Positioning**: Sidebar fixed to left edge, full height
   ```jsx
   <div className="fixed inset-y-0 left-0 w-64 bg-slate-800 border-r border-slate-700">
   ```

2. **Collapsible Categories**: State-managed category groups
   ```typescript
   const [collapsedCategories, setCollapsedCategories] = useState<Record<string, boolean>>({})

   const toggleCategory = (header: string) => {
     setCollapsedCategories(prev => ({
       ...prev,
       [header]: !prev[header]
     }))
   }
   ```

3. **Navigation Item Styling**:
   ```jsx
   <Link
     to={item.href}
     className={`flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors ${
       isActive
         ? 'bg-primary-600 text-white'
         : 'text-amber-400 hover:bg-slate-700 hover:text-amber-200'
     }`}
   >
     <Icon className="w-5 h-5 mr-3" />
     {item.name}
   </Link>
   ```

4. **Active Route Detection**:
   ```typescript
   const isActive = location.pathname === item.href ||
                    location.pathname.startsWith(item.href + '/')
   ```

5. **Admin Items** (role-based with yellow accent):
   ```jsx
   className={isActive
     ? 'bg-yellow-600/20 text-yellow-500 border border-yellow-600/30'
     : 'text-amber-400 hover:bg-slate-700 hover:text-amber-200'}
   ```

6. **Main Content Offset**: Match sidebar width
   ```jsx
   <div className="pl-64">
     <main className="min-h-screen">
       <Outlet />
     </main>
   </div>
   ```

7. **Icons**: Use `lucide-react` with consistent sizing (`w-5 h-5`)

### Tab Navigation Pattern (WaddlePerf Style)

**Required for applications with content sections:**

**Structure:**
```
┌─────────────────────────────────────────────────────────────┐
│  [Speed Test]  [Network Tests]  [Trace Tests]  [Download]   │
│  ━━━━━━━━━━━━                                               │
│  (active tab has colored underline)                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    Tab Content Area                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Implementation Requirements:**

1. **Tab Container Styling**:
   ```css
   .tab-navigation {
     display: flex;
     gap: 1rem;
     margin-bottom: 2rem;
     border-bottom: 2px solid var(--border-color);
   }
   ```

2. **Tab Button Styling**:
   ```css
   .tab-button {
     padding: 0.75rem 1.5rem;
     background: transparent;
     border: none;
     border-bottom: 3px solid transparent;
     color: var(--text-secondary);    /* amber-500 - gold default */
     font-size: 1rem;
     font-weight: 500;
     cursor: pointer;
     transition: all 0.2s;
     margin-bottom: -2px;  /* Overlap container border */
   }

   .tab-button:hover {
     color: var(--text-light);        /* amber-100 - lighter gold on hover */
   }

   .tab-button.active {
     color: var(--primary-500);       /* sky-blue for active distinction */
     border-bottom-color: var(--primary-500);
     font-weight: 600;
   }
   ```

3. **React Implementation**:
   ```typescript
   type TabKey = 'overview' | 'details' | 'settings' | 'logs'
   const [activeTab, setActiveTab] = useState<TabKey>('overview')

   // Tab navigation
   <div className="tab-navigation">
     {tabs.map(tab => (
       <button
         key={tab.key}
         className={`tab-button ${activeTab === tab.key ? 'active' : ''}`}
         onClick={() => setActiveTab(tab.key)}
       >
         {tab.label}
       </button>
     ))}
   </div>

   // Tab content (conditional rendering)
   {activeTab === 'overview' && <OverviewPanel />}
   {activeTab === 'details' && <DetailsPanel />}
   {activeTab === 'settings' && <SettingsPanel />}
   {activeTab === 'logs' && <LogsPanel />}
   ```

4. **Transition Details**:
   - Duration: 200ms (0.2s)
   - Properties: color, border-bottom-color
   - Easing: linear (default)

5. **Dark Mode Support**: Use CSS variables for all colors

### Combined Layout Pattern

**For applications requiring both sidebar and tabs:**

```
┌──────────────┬──────────────────────────────────────────────┐
│              │  Page Header                                 │
│   SIDEBAR    ├──────────────────────────────────────────────┤
│              │  [Tab 1]  [Tab 2]  [Tab 3]  [Tab 4]          │
│  - Primary   │  ━━━━━━━                                     │
│  - Assets    ├──────────────────────────────────────────────┤
│  - Settings  │                                              │
│  - Admin     │           Tab Content Area                   │
│              │                                              │
│  ──────────  │                                              │
│  Profile     │                                              │
│  Logout      │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

**Layout Structure:**
```jsx
<div className="flex min-h-screen">
  {/* Sidebar - fixed left */}
  <aside className="fixed inset-y-0 left-0 w-64 bg-slate-800 border-r border-slate-700">
    <Sidebar />
  </aside>

  {/* Main content - offset for sidebar */}
  <main className="flex-1 pl-64">
    <div className="p-6">
      {/* Page header - gold text */}
      <h1 className="text-2xl font-semibold text-amber-400 mb-6">Page Title</h1>

      {/* Tab navigation */}
      <TabNavigation activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Tab content */}
      <div className="mt-6">
        {renderTabContent()}
      </div>
    </div>
  </main>
</div>
```

### Right Sidebar Pattern (Detail Pages)

**For detail pages with metadata panels:**

```jsx
<div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
  {/* Main content */}
  <div className="lg:col-span-2">
    <MainContent />
  </div>

  {/* Right sidebar */}
  <div className="lg:col-span-1 space-y-6">
    <Card title="Related Items">
      <RelatedItemsList />
    </Card>
    <Card title="Metadata">
      <MetadataPanel />
    </Card>
  </div>
</div>
```

### Required Dependencies

```json
{
  "dependencies": {
    "lucide-react": "^0.453.0",
    "react-router-dom": "^6.20.0",
    "@tanstack/react-query": "^5.0.0"
  },
  "devDependencies": {
    "tailwindcss": "^4.0.0",
    "@tailwindcss/postcss": "^4.0.0"
  }
}
```

### Tailwind CSS v4 Theme Configuration

```css
/* index.css */
@import "tailwindcss";

@theme {
  --color-primary-50: #f0f9ff;
  --color-primary-100: #e0f2fe;
  --color-primary-200: #bae6fd;
  --color-primary-300: #7dd3fc;
  --color-primary-400: #38bdf8;
  --color-primary-500: #0ea5e9;
  --color-primary-600: #0284c7;
  --color-primary-700: #0369a1;
  --color-primary-800: #075985;
  --color-primary-900: #0c4a6e;
}
```

### Component Library Standards

**Card Component:**
```jsx
export const Card = ({ title, children, className = '' }) => (
  <div className={`bg-slate-800 border border-slate-700 rounded-lg shadow-lg ${className}`}>
    {title && (
      <div className="px-4 py-3 border-b border-slate-700">
        <h3 className="text-sm font-semibold text-amber-400">{title}</h3>
      </div>
    )}
    <div className="p-4 text-amber-400">{children}</div>
  </div>
)
```

**Button Component:**
```jsx
const variants = {
  primary: 'bg-primary-600 hover:bg-primary-700 text-white',
  secondary: 'bg-slate-700 hover:bg-slate-600 text-amber-400',
  danger: 'bg-red-600 hover:bg-red-700 text-white',
  ghost: 'bg-transparent hover:bg-slate-700 text-amber-400 hover:text-amber-200'
}

export const Button = ({ variant = 'primary', size = 'md', children, ...props }) => (
  <button
    className={`rounded-lg font-medium transition-colors ${variants[variant]} ${sizes[size]}`}
    {...props}
  >
    {children}
  </button>
)
```

### Accessibility Requirements

1. **Keyboard Navigation**: All interactive elements must be keyboard accessible
2. **Focus States**: Visible focus indicators using `focus:ring-2 focus:ring-primary-500`
3. **ARIA Labels**: Proper labeling for screen readers
4. **Color Contrast**: Minimum 4.5:1 contrast ratio for text
5. **Reduced Motion**: Respect `prefers-reduced-motion` preference

---

## Ansible Integration

- **Documentation Research**: ALWAYS research modules on https://docs.ansible.com
- **Module verification**: Check official docs for syntax and parameters
- **Best practices**: Follow community standards and idempotency
- **Testing**: Ensure playbooks are idempotent

---

## Git Workflow

- **NEVER commit automatically** unless explicitly requested
- **NEVER push to remote repositories** under any circumstances
- **ONLY commit when explicitly asked**
- Always use feature branches
- Require pull request reviews for main branch
- Automated testing must pass before merge

---

## WaddleAI Integration

**Optional AI capabilities - integrate only when AI features are required**

### When to Use WaddleAI

Consider WaddleAI integration for projects requiring:
- Natural language processing (NLP)
- Machine learning model inference
- AI-powered features and automation
- Intelligent data analysis
- Chatbots and conversational interfaces
- Document understanding and extraction
- Predictive analytics

### Architecture Pattern

**WaddleAI runs as a separate microservice:**

```
project-name/
├── services/
│   ├── api/           # Flask backend API
│   ├── webui/         # ReactJS frontend
│   ├── connector/     # Integration services
│   └── ai/            # WaddleAI service (optional)
```

### Integration Setup

**1. Reference WaddleAI from ~/code/WaddleAI:**

```bash
# Add as git submodule or copy required components
git submodule add ~/code/WaddleAI services/ai/waddleai
```

**2. Docker Compose Integration:**

```yaml
# docker-compose.dev.yml
version: '3.8'

services:
  api:
    build: ./services/api
    environment:
      - WADDLEAI_URL=http://waddleai:8000
    depends_on:
      - waddleai

  waddleai:
    build: ./services/ai/waddleai
    environment:
      - MODEL_PATH=/models
      - MAX_WORKERS=4
    volumes:
      - ai-models:/models
    # Not exposed to host - internal network only

volumes:
  ai-models:
```

### API Client for WaddleAI

**Python integration in Flask backend:**

```python
import os
import httpx
from typing import Dict, Any, Optional

class WaddleAIClient:
    """Client for WaddleAI service"""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.getenv('WADDLEAI_URL', 'http://localhost:8000')
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def analyze_text(self, text: str, task: str = "sentiment") -> Dict[str, Any]:
        """Analyze text with AI model"""
        response = await self.client.post(
            "/api/v1/analyze",
            json={"text": text, "task": task}
        )
        response.raise_for_status()
        return response.json()

    async def generate_response(self, prompt: str, context: Optional[str] = None) -> str:
        """Generate AI response"""
        response = await self.client.post(
            "/api/v1/generate",
            json={"prompt": prompt, "context": context}
        )
        response.raise_for_status()
        return response.json()["response"]

    async def close(self):
        await self.client.aclose()

# Flask integration
from flask import Flask, request, jsonify
from shared.licensing import requires_feature

app = Flask(__name__)
ai_client = WaddleAIClient()

@app.route('/api/ai/analyze', methods=['POST'])
@auth_required()
@requires_feature('ai_analysis')  # License-gate AI features
async def ai_analyze():
    """AI-powered analysis - enterprise feature"""
    data = request.get_json()
    result = await ai_client.analyze_text(data['text'], data.get('task', 'sentiment'))
    return jsonify(result)
```

**ReactJS integration:**

```javascript
// src/services/aiClient.js
import { apiClient } from './apiClient';

export const aiService = {
  async analyzeText(text, task = 'sentiment') {
    const response = await apiClient.post('/api/ai/analyze', { text, task });
    return response.data;
  },

  async generateResponse(prompt, context = null) {
    const response = await apiClient.post('/api/ai/generate', { prompt, context });
    return response.data;
  }
};

// React component
import { useState } from 'react';
import { aiService } from '../services/aiClient';

export const AIAnalyzer = () => {
  const [text, setText] = useState('');
  const [result, setResult] = useState(null);

  const handleAnalyze = async () => {
    const analysis = await aiService.analyzeText(text);
    setResult(analysis);
  };

  return (
    <div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} />
      <button onClick={handleAnalyze}>Analyze</button>
      {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    </div>
  );
};
```

### License-Gating AI Features

**ALWAYS make AI features enterprise-only:**

```python
# License configuration
AI_FEATURES = {
    'ai_analysis': 'professional',      # Professional tier+
    'ai_generation': 'professional',    # Professional tier+
    'ai_training': 'enterprise',        # Enterprise tier only
    'ai_custom_models': 'enterprise'    # Enterprise tier only
}

# Feature checking
from shared.licensing import license_client

def check_ai_features():
    """Check available AI features based on license"""
    features = {}
    for feature, required_tier in AI_FEATURES.items():
        features[feature] = license_client.has_feature(feature)
    return features
```

### Environment Variables

```bash
# WaddleAI service configuration
WADDLEAI_URL=http://waddleai:8000
WADDLEAI_API_KEY=optional-api-key
WADDLEAI_MODEL_PATH=/models
WADDLEAI_MAX_WORKERS=4
WADDLEAI_TIMEOUT=30

# License-gated AI features
AI_FEATURES_ENABLED=true
```

### Important Notes

1. **Optional Integration**: Only add WaddleAI when AI features are needed
2. **License Gating**: AI features are typically enterprise/professional tier
3. **Performance**: AI inference can be resource-intensive - monitor usage
4. **Isolation**: Run WaddleAI as separate service for resource isolation
5. **Documentation**: Refer to WaddleAI documentation at `~/code/WaddleAI`

---

## CI/CD Standards

### Overview

This section documents comprehensive CI/CD standards and requirements for all projects. These standards ensure consistent, secure, and efficient build pipelines across the organization while maintaining compliance with `.WORKFLOW` specifications.

**Key Principles:**
- Efficient execution with parallel builds where possible
- Mandatory security scanning for all code
- Consistent naming conventions across all projects
- Version management integration in all workflows
- Comprehensive documentation requirements

---

### Workflow Architecture

#### Build Package Definition

A **build package** is a single service or application that may target multiple architectures or operating systems:

**Examples:**
- Docker container: Builds for both AMD64 and ARM64 architectures
- Go binary: Builds for Windows ARM64, Windows AMD64, Linux ARM64, Linux AMD64, macOS ARM64
- Node.js application: Containerized builds for multiple platforms

#### Pipeline Principles

**All CI/CD pipelines MUST:**
- Be 1 per build package
- Optimize for maximum efficiency
- Include only unit tests (no integration/resource-intensive tests requiring external mocks)
- Trigger on either:
  - Changes to files in the build package's folder structure
  - Changes to the `.version` file
- Utilize parallel builds and forks where possible for timely execution

**Testing Scope:**
- Unit tests with mocked dependencies
- Network-isolated testing
- Container or application internal testing only
- No external resource dependencies (APIs, databases, etc.)

### Naming Conventions

Version placeholder: `vX.X.X` represents the build package's semantic version from `.version` file.

#### Docker Container Naming

**Pattern 1: Regular Builds (No Version Change)**

When build package folder changes but `.version` file is unchanged:

**Main branch:**
```
<build-package-name>:beta-<epoch64>
```

**Other branches (develop, feature, etc.):**
```
<build-package-name>:alpha-<epoch64>
```

**Example:**
- Flask backend on main: `api-server:beta-1702000000`
- Flask backend on feature: `api-server:alpha-1702000000`

**Pattern 2: Version Release Builds (.version Changed)**

When `.version` file changes (regardless of other file changes):

**Main branch:**
```
<build-package-name>:vX.X.X-beta
```

**Other branches:**
```
<build-package-name>:vX.X.X-alpha
```

**Release tags (from GitHub release):**
```
<build-package-name>:vX.X.X
<build-package-name>:latest
```

**Example:**
- Flask backend on main (version 1.2.3): `api-server:v1.2.3-beta`
- Flask backend on feature (version 1.2.3): `api-server:v1.2.3-alpha`
- Flask backend release: `api-server:v1.2.3` and `api-server:latest`

#### Compiled Binary Naming

**Pattern 1: Regular Builds (No Version Change)**

When build package folder changes but `.version` file is unchanged:

**Main branch:**
```
<build-package-name>-beta-<epoch64><file-extension>
```

**Other branches:**
```
<build-package-name>-alpha-<epoch64><file-extension>
```

**Example:**
- Go proxy on main: `proxy-beta-1702000000`
- Go proxy on feature: `proxy-alpha-1702000000`
- Go Windows binary: `proxy-alpha-1702000000.exe`

**Pattern 2: Version Release Builds (.version Changed)**

When `.version` file changes:

**Main branch:**
```
<build-package-name>-vX.X.X-beta<file-extension>
```

**Other branches:**
```
<build-package-name>-vX.X.X-alpha<file-extension>
```

**Release artifacts:**
```
<build-package-name>-vX.X.X<file-extension>
```

**Example:**
- Go proxy on main (v1.2.3): `proxy-v1.2.3-beta`
- Go proxy on feature (v1.2.3): `proxy-v1.2.3-alpha`
- Go proxy release (v1.2.3): `proxy-v1.2.3`

#### Auto Pre-Release Creation

**Important**: When `.version` file changes on the **main branch**, GitHub Actions MUST automatically:
1. Detect the version change
2. Read the semantic version from `.version`
3. Check if a release already exists for that version
4. If not exists, create a GitHub pre-release:
   - Pre-release flag set to true
   - Release notes auto-generated
   - Triggered by `.version` file change only on main branch

**Note**: Skips creation if:
- Version is `0.0.0` (development version)
- Release already exists for that version

### Required Workflows Checklist

Every project MUST have the following workflows configured in `.github/workflows/`:

#### Essential Workflows

- [ ] **Build workflows**: 1 per build package (Docker, Go binary, etc.)
  - Must monitor `.version` in path filters
  - Must implement epoch64 and version detection steps
  - Must include proper tag generation logic

- [ ] **version-release.yml**: Automatic version release creation
  - Triggers on `.version` changes in main branch
  - Creates GitHub pre-releases automatically
  - Must be present in every project

- [ ] **Security scanning workflows**: Per technology stack
  - Go projects: gosec scanning required
  - Node.js projects: npm audit required
  - Python projects: bandit verification required
  - All projects: Trivy container scanning (if Docker)
  - All projects: CodeQL security analysis

#### Optional Workflows (Technology-Specific)

- [ ] **Integration testing** (if applicable)
- [ ] **Performance testing** (for high-traffic services)
- [ ] **Release deployment** (production automation)
- [ ] **Documentation generation** (if auto-generated)
- [ ] **Dependency updates** (Dependabot or similar)

### Path Filter Requirements

#### Critical: .version File Monitoring

**EVERY build workflow MUST include `.version` in its path filter:**

```yaml
on:
  push:
    branches: [main, develop]
    paths:
      - '.version'                              # MANDATORY
      - 'services/flask-backend/**'             # Existing path
      - '.github/workflows/build-flask-backend.yml'  # Existing path
```

#### Why .version is Critical

The `.version` file is the **trigger for version release builds**. Without `.version` in path filters:

1. ❌ Version changes don't trigger rebuilds
2. ❌ Pre-release creation doesn't occur
3. ❌ Builds won't include version-based tags
4. ❌ Release tracking fails

#### Path Filter Examples

**Single-service project:**
```yaml
paths:
  - '.version'
  - 'services/api/**'
  - '.github/workflows/build-api.yml'
```

**Multi-service project (all services rebuild on .version change):**
```yaml
# Flask backend workflow
paths:
  - '.version'
  - 'services/flask-backend/**'
  - '.github/workflows/build-flask-backend.yml'

# Go backend workflow
paths:
  - '.version'
  - 'services/go-backend/**'
  - '.github/workflows/build-go-backend.yml'

# WebUI workflow
paths:
  - '.version'
  - 'services/webui/**'
  - '.github/workflows/build-webui.yml'
```

**Rationale for including .version in all workflows:**
- Ensures all build packages version-lock together
- Prevents partial version releases
- Maintains consistency across multi-container deployments

### Security Scanning Standards

#### Mandatory Security Checks

**ALL workflows must include security scanning and fail on HIGH/CRITICAL findings.**

#### Go Projects: gosec Scanning

**Required in all Go build workflows:**

```yaml
- name: Run gosec security scanner
  uses: securecodewarrior/github-action-gosec@master
  with:
    args: '-severity high -confidence medium ./...'
  continue-on-error: false

- name: Upload gosec results
  uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: 'results.sarif'
```

**Configuration:**
- Severity threshold: `high` (includes HIGH and CRITICAL)
- Confidence: `medium` (balance between false positives and coverage)
- Continue on error: `false` (fail the workflow on findings)
- Result upload: Always upload to GitHub security tab

**Failure Criteria:**
- Any HIGH severity findings: Build fails
- Any CRITICAL severity findings: Build fails
- MEDIUM and LOW findings: Build continues (logged for review)

#### Node.js Projects: npm audit

**Required in all Node.js build workflows:**

```yaml
- name: Run npm audit
  working-directory: services/webui
  run: |
    npm audit --audit-level=high
  continue-on-error: false
```

**Configuration:**
- Audit level: `high` (includes HIGH and CRITICAL)
- Continue on error: `false` (fail on findings)

**Dependency Update Process:**
1. Review npm audit findings
2. Run `npm audit fix` to auto-fix compatible updates
3. Manually update remaining vulnerable dependencies
4. Test thoroughly before committing
5. Update package-lock.json

#### Python Projects: bandit Verification

**Required in all Python build workflows:**

```yaml
- name: Run bandit security scanner
  run: |
    pip install bandit
    bandit -r services/flask-backend -f json -o bandit-report.json
    bandit -r services/flask-backend -f txt

- name: Check bandit results
  run: |
    if grep -q '"severity": "HIGH"' bandit-report.json; then
      echo "HIGH severity issues found"
      exit 1
    fi
    if grep -q '"severity": "CRITICAL"' bandit-report.json; then
      echo "CRITICAL severity issues found"
      exit 1
    fi
```

**Configuration:**
- Output formats: JSON (machine-readable) and text (human-readable)
- Failure criteria: HIGH or CRITICAL findings
- Scope: All Python code in the build package directory

#### All Projects: Trivy Container Scanning

**Required for all Docker build workflows:**

```yaml
- name: Run Trivy vulnerability scanner
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ${{ steps.meta.outputs.tags }}
    format: 'sarif'
    output: 'trivy-results.sarif'
    severity: 'HIGH,CRITICAL'

- name: Upload Trivy results
  uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: 'trivy-results.sarif'
```

**Configuration:**
- Severity filter: HIGH and CRITICAL
- Format: SARIF for GitHub integration
- Always upload results for tracking

#### All Projects: CodeQL Analysis

**Required for all projects with code:**

```yaml
- name: Initialize CodeQL
  uses: github/codeql-action/init@v2
  with:
    languages: 'python,go,javascript'

# Build step here

- name: Perform CodeQL Analysis
  uses: github/codeql-action/analyze@v2
```

**Supported Languages:**
- `python` - Python 3.x
- `go` - Go 1.x
- `javascript` - JavaScript/TypeScript
- `java` - Java/Kotlin

**Requirements:**
- Analysis must complete successfully
- Security alerts reviewed and addressed
- No critical alerts allowed in main branch

#### Vulnerability Severity Thresholds

| Severity | Build Outcome | Action Required |
|----------|---------------|-----------------|
| CRITICAL | ❌ FAIL | Fix immediately before merge |
| HIGH | ❌ FAIL | Fix before merge to main |
| MEDIUM | ⚠️ WARN | Review, fix or document |
| LOW | ⚠️ WARN | Document in comments |
| INFO | ✅ PASS | Optional fix |

### Version Management

#### Version Format: vMajor.Minor.Patch.build

The `.version` file maintains semantic versioning with an optional build component:

```
vMajor.Minor.Patch
```

Or with build epoch64 timestamp:

```
vMajor.Minor.Patch.epoch64
```

#### Version Components

**Major** (breaking changes):
- Incompatible API changes
- Removed features
- Major refactoring
- Database schema changes (breaking)

**Minor** (new features):
- New functionality added
- New API endpoints
- New features enabled
- Database schema changes (backward compatible)

**Patch** (bug fixes):
- Bug fixes
- Security patches
- Performance improvements
- Documentation updates

**Build** (optional epoch64):
- Unix timestamp of build time
- Format: 10-digit epoch seconds
- Example: `1.2.3.1702000000`
- Used for automated builds without explicit version bumps

#### .version File Format

**Location:** Project root directory

**Content:** Plain text, single version line

```
# Valid versions
1.0.0
1.2.3
2.1.0.1702000000
0.0.0
```

**Important:**
- No `v` prefix in file (prefix added by workflow)
- No trailing newline (trimmed by workflow)
- Whitespace trimmed automatically
- One version per line

#### Version Detection in Workflows

**Epoch64 timestamp generation step:**

```yaml
- name: Generate epoch64 timestamp
  id: timestamp
  run: |
    EPOCH64=$(date +%s)
    echo "epoch64=$EPOCH64" >> $GITHUB_OUTPUT
```

**Version file detection step:**

```yaml
- name: Check version file
  id: version
  run: |
    if [ -f .version ]; then
      VERSION=$(cat .version | tr -d '[:space:]')
      SEMVER=$(echo "$VERSION" | cut -d'.' -f1-3)
      echo "semver=$SEMVER" >> $GITHUB_OUTPUT

      if git diff --name-only HEAD^ HEAD | grep -q "^.version$"; then
        echo "changed=true" >> $GITHUB_OUTPUT
      else
        echo "changed=false" >> $GITHUB_OUTPUT
      fi
    else
      echo "semver=0.0.0" >> $GITHUB_OUTPUT
      echo "changed=false" >> $GITHUB_OUTPUT
    fi
```

**Output variables:**
- `steps.version.outputs.semver` - Semantic version (vX.X.X)
- `steps.version.outputs.changed` - Boolean: true if .version changed in commit
- `steps.timestamp.outputs.epoch64` - Current Unix timestamp

#### Updating Version Numbers

**Scripts location:** `./scripts/version/update-version.sh`

**Available commands:**

```bash
# Increment build timestamp only (no version change)
./scripts/version/update-version.sh

# Increment patch version (e.g., 1.0.0 → 1.0.1)
./scripts/version/update-version.sh patch

# Increment minor version (e.g., 1.0.0 → 1.1.0, resets patch to 0)
./scripts/version/update-version.sh minor

# Increment major version (e.g., 1.0.0 → 2.0.0, resets minor and patch)
./scripts/version/update-version.sh major
```

### Build Optimization Guidelines

#### Efficiency Principles

**1. Parallel Builds**
- Use matrix strategies for multi-arch builds
- Build AMD64 and ARM64 simultaneously
- Parallelize independent build steps

**Example:**
```yaml
strategy:
  matrix:
    include:
      - platform: linux/amd64
        suffix: amd64
      - platform: linux/arm64
        suffix: arm64

- name: Build for ${{ matrix.suffix }}
  uses: docker/build-push-action@v5
  with:
    platforms: ${{ matrix.platform }}
    context: services/flask-backend
    # ... rest of config
```

**2. Caching**
- Cache Docker layers aggressively
- Cache npm/pip dependencies
- Use GitHub's built-in caching actions

**Docker layer caching:**
```yaml
- name: Build Docker image
  uses: docker/build-push-action@v5
  with:
    context: services/flask-backend
    cache-from: type=registry,ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:buildcache
    cache-to: type=registry,ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:buildcache,mode=max
```

**Dependency caching (Node.js):**
```yaml
- name: Cache node modules
  uses: actions/cache@v3
  with:
    path: services/webui/node_modules
    key: ${{ runner.os }}-node-${{ hashFiles('services/webui/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-node-
```

**Dependency caching (Python):**
```yaml
- name: Cache Python packages
  uses: actions/cache@v3
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('services/flask-backend/requirements.txt') }}
    restore-keys: |
      ${{ runner.os }}-pip-
```

**3. Selective Testing**
- Run full test suite only for main branch
- Run quick smoke tests for feature branches
- Skip tests for documentation-only changes

```yaml
- name: Run tests
  if: github.ref == 'refs/heads/main' || contains(github.event.pull_request.labels.*.name, 'needs-testing')
  run: make test

- name: Run smoke tests
  if: github.ref != 'refs/heads/main'
  run: make test-unit
```

**4. Minimal Artifacts**
- Remove unnecessary files before building
- Use multi-stage Docker builds
- Only push necessary artifacts

**Multi-stage Dockerfile:**
```dockerfile
# Build stage
FROM golang:1.24 AS builder
WORKDIR /build
COPY . .
RUN CGO_ENABLED=0 go build -o proxy ./cmd/main.go

# Runtime stage
FROM debian:bookworm-slim
COPY --from=builder /build/proxy /usr/local/bin/
CMD ["proxy"]
```

**5. Reuse Workflows**
- Define reusable workflow patterns
- Share security scanning logic
- Reduce duplication across projects

```yaml
name: Build Docker Service

on: [push]

jobs:
  build:
    uses: ./.github/workflows/templates/docker-build.yml
    with:
      service-name: flask-backend
      registry: ghcr.io
```

#### Speed Optimization Targets

| Component | Target Time | Strategy |
|-----------|------------|----------|
| Checkout | <10s | Use shallow clone for features |
| Dependencies | <30s | Cache aggressively |
| Linting | <15s | Run in parallel |
| Build | <2 min | Use layers, parallel jobs |
| Security scans | <1 min | Run in parallel |
| Tests | <2 min | Selective testing |
| **Total** | **<6 min** | Parallelize all steps |

#### Resource Allocation

**Recommended GitHub Actions runners:**
- Standard builds: `ubuntu-latest` (2 CPU, 7 GB RAM)
- Heavy builds (Go, large projects): `ubuntu-latest` with `timeout-minutes: 30`
- Multi-arch (ARM64): Use `buildx` with proper caching

**Dockerizing everything ensures consistent builds across all developer machines and CI/CD runners.**

---

## Licensing and Feature Gating

### License Enforcement Timing

**IMPORTANT: License enforcement is enabled ONLY when project is release-ready**

**Development Phase (Pre-Release):**
- License checking code is present but not enforced
- All features available during development
- Focus on feature development and testing
- No license validation failures

**Release Phase (Production):**
- User explicitly marks project as "release ready"
- License enforcement is enabled
- Feature gating becomes active
- License validation required for startup

**Implementation Pattern:**

```python
import os
from shared.licensing import license_client

# Check if in release mode
RELEASE_MODE = os.getenv('RELEASE_MODE', 'false').lower() == 'true'

def check_license():
    """Check license only in release mode"""
    if not RELEASE_MODE:
        # Development mode - bypass license checks
        return {'valid': True, 'tier': 'development', 'features': '*'}

    # Release mode - enforce license
    validation = license_client.validate()
    if not validation.get('valid'):
        raise Exception(f"License validation failed: {validation.get('message')}")
    return validation

def requires_feature(feature_name):
    """Decorator to gate features by license tier"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if RELEASE_MODE:
                # Enforce license in release mode
                if not license_client.has_feature(feature_name):
                    raise PermissionError(f"Feature '{feature_name}' requires higher license tier")
            # Development mode - allow all features
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

**Environment Variables:**
```bash
# Development (default)
RELEASE_MODE=false

# Production (explicitly set)
RELEASE_MODE=true
LICENSE_KEY=PENG-XXXX-XXXX-XXXX-XXXX-ABCD
```

### Enterprise Features

**ALWAYS license-gate these features as enterprise-only:**
- SSO (SAML, OAuth2, OIDC)
- Advanced AI capabilities
- Multi-tenancy
- Audit logging and compliance
- Advanced analytics
- Custom integrations
- Priority support

---

## Development Practices & Assumptions

### Code Changes & Container Rebuilds

**After any code changes, rebuild and restart containers:**

```bash
# All services
docker compose down && docker compose up -d --build

# Single service
docker compose up -d --build <service-name>
```

**IMPORTANT:** `docker compose restart` and `docker restart` do NOT apply code changes. Always use `--build` to rebuild images.

### Browser Cache & Hard Reload

**Developers will routinely perform hard reloads and cache clearing during development:**
- Hard reload (Ctrl+Shift+R / Cmd+Shift+R) clears browser cache
- Cache is explicitly cleared between development iterations
- DO NOT assume browser cache contains stale assets
- DO NOT blame caching when the issue is actual code

**Implementation Guidance:**
- Implement proper cache headers for assets
- Use content-based cache busting (filename hashing: `app.abc123.js`)
- Consider `Cache-Control: no-cache, must-revalidate` for development
- Version static assets in production builds

### Cache Dumping

**Developers will clear various caches during development:**
- Redis/Valkey cache flushes
- Docker layer cache clearing
- Browser local storage clearing
- Build artifact clearing

**DO NOT assume cache state is preserved between development sessions.**

---

## Quality Checklist

Before marking any task complete, verify:
- ✅ All error cases handled properly
- ✅ Unit tests cover all code paths
- ✅ Integration tests verify component interactions
- ✅ Security requirements fully implemented
- ✅ Performance meets acceptable standards
- ✅ Documentation complete and accurate
- ✅ Code review standards met
- ✅ No hardcoded secrets or credentials
- ✅ Logging and monitoring in place
- ✅ Build passes in containerized environment
- ✅ No security vulnerabilities in dependencies
- ✅ Edge cases and boundary conditions tested
- ✅ License enforcement configured correctly (if release-ready)
