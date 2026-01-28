# 🔐 Authentication - Keeping the Bad Guys Out

Part of [Development Standards](../STANDARDS.md)

## How Authentication Works (Simple Version)

Think of authentication like a bouncer at a club. When someone shows up:
1. **They prove who they are** (login with email & password)
2. **We check if they're legit** (match against our user database)
3. **We give them a special pass** (JWT token)
4. **They show the pass for every action** (token in API requests)
5. **We know what they can do** (roles like Admin, Viewer, etc.)

That's it! Flask-Security-Too is our bouncer—it handles all of this automatically.

## The Three Main Roles (Simple Explanations)

**👑 Admin** = The Boss
- Full access to everything
- Can create users, change roles, access admin tools
- The one who sets the rules
- *Example: Company owner*

**🔧 Maintainer** = The Manager
- Can read and modify data
- Can't touch user management or system settings
- Runs the day-to-day operations
- *Example: Department head*

**👀 Viewer** = The Guest
- Can only look, not touch
- Perfect for reporting and analytics
- Read-only access to everything they're assigned
- *Example: Stakeholder watching progress*

---

## Getting Started (Step-by-Step Setup)

### Step 1: Install Flask-Security-Too

```bash
pip install flask-security-too flask-sqlalchemy flask-mail
```

### Step 2: Configure Flask

```python
import os
from flask import Flask
from flask_security import Security, hash_password

app = Flask(__name__)

# Security configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SECURITY_PASSWORD_SALT'] = os.getenv('SECURITY_PASSWORD_SALT', 'salt')
app.config['SECURITY_REGISTERABLE'] = True
app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
app.config['SECURITY_PASSWORD_HASH'] = 'bcrypt'
app.config['SECURITY_RECOVERABLE'] = True  # Enable password reset
app.config['SECURITY_CHANGEABLE'] = True   # Enable password change
```

### Step 3: Set Up Your Database Tables

```python
from pydal import DAL, Field

db = DAL(
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@"
    f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}",
    pool_size=10,
    migrate=True
)

# User table
db.define_table('auth_user',
    Field('email', 'string', requires=IS_EMAIL(), unique=True),
    Field('username', 'string', unique=True),
    Field('password', 'string'),
    Field('active', 'boolean', default=True),
    Field('fs_uniquifier', 'string', unique=True),
    Field('confirmed_at', 'datetime'),
    migrate=True
)

# Role table
db.define_table('auth_role',
    Field('name', 'string', unique=True),
    Field('description', 'text'),
    migrate=True
)

# User-Role mapping (many-to-many)
db.define_table('auth_user_roles',
    Field('user_id', 'reference auth_user'),
    Field('role_id', 'reference auth_role'),
    migrate=True
)
```

### Step 4: Create PyDAL Datastore

```python
from flask_security import DataStore

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
        return query.select().first()
```

### Step 5: Initialize Security

```python
user_datastore = PyDALUserDatastore(db, db.auth_user, db.auth_role)
security = Security(app, user_datastore)
```

### Step 6: Create Default Admin on Startup

```python
from datetime import datetime

def create_default_admin():
    """Create default admin user on app startup"""
    admin = user_datastore.find_user(email='admin@localhost.local')
    if admin:
        return  # Already exists

    # Create admin role
    admin_role = user_datastore.find_role('admin')
    if not admin_role:
        admin_role = user_datastore.create_role(
            name='admin',
            description='Administrator with full system access'
        )

    # Create admin user
    admin_user = user_datastore.create_user(
        email='admin@localhost.local',
        password=hash_password('admin123'),
        active=True,
        confirmed_at=datetime.utcnow()
    )

    user_datastore.add_role_to_user(admin_user, admin_role)
    db.commit()
    print("✅ Default admin created: admin@localhost.local / admin123")

@app.before_first_request
def init_app():
    db.create_all()
    create_default_admin()
```

---

## Protected Routes (How to Use Them)

```python
from flask_security import auth_required, roles_required
from flask import current_user

# Any authenticated user can access
@app.route('/api/v1/profile')
@auth_required()
def get_profile():
    return {'user': current_user.email}

# Only admins can access
@app.route('/api/v1/admin/users')
@auth_required()
@roles_required('admin')
def list_all_users():
    return {'users': []}

# Multiple roles (OR logic)
@app.route('/api/v1/reports')
@auth_required()
@roles_required('admin', 'maintainer')
def view_reports():
    return {'reports': []}
```

---

## Password Reset Flow (Simple Diagram)

```
┌─────────────────────────────────────────────────────────────┐
│ User clicks "Forgot Password" on login page                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ User enters their email address                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ System checks if SMTP is configured                         │
│ (If not: show "Email not available" message)                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼ (SMTP configured)
┌─────────────────────────────────────────────────────────────┐
│ System generates time-limited reset token (1 hour)          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Email sent with reset link + token                          │
│ User sees: "Check your email"                               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ User clicks link in email                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ User enters new password                                    │
│ System validates token (is it expired? valid?)              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼ (valid)
┌─────────────────────────────────────────────────────────────┐
│ Password updated + user can login                           │
│ User sees: "Password changed successfully"                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚨 Common Auth Issues (Troubleshooting)

### ❌ "Login not working"
**Check:**
- ✅ Is your admin user created? (`admin@localhost.local`)
- ✅ Is email/password correct?
- ✅ Are you using the right API endpoint? (`/api/v1/auth/login`)
- ✅ Is the database running?

### ❌ "Forgot password not sending emails"
**Check:**
- ✅ Is SMTP configured? (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`)
- ✅ Is it the right port? (587 for TLS, 25 for plain)
- ✅ Can the app reach the SMTP server? (firewall/network issue)

### ❌ "Token expired/invalid"
**Check:**
- ✅ Did user wait too long? (Default: 1 hour)
- ✅ Is `SECRET_KEY` the same? (Changed between restarts?)
- ✅ Is token format correct in the request header?

### ❌ "Can't change role/permissions"
**Check:**
- ✅ Is the user logged in as admin?
- ✅ Does the role exist? (admin, maintainer, viewer)
- ✅ Are you using the right endpoint?

### ❌ "CORS errors when logging in"
**Check:**
- ✅ Is the frontend on a different domain?
- ✅ Are CORS headers configured in Flask?
- ✅ Are cookies being sent in requests?

---

## JWT Explained Simply

**What is a JWT?** It's like a digital ticket with your name and permissions written on it.

```
Header.Payload.Signature

eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 = Header
.eyJzdWIiOiJhZG1pbkBsb2NhbGhvc3QubG9jYWwiLCJpYXQiOjE2ODgyMDAwMDB9 = Payload (your email + timestamp)
.signature_here = Signature (proves it's real)
```

**Why use it?**
- ✅ Stateless (no need to lookup in database every time)
- ✅ Secure (signature proves no one tampered with it)
- ✅ Works with microservices (each service can verify independently)

**How to use it in requests:**
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE" \
     https://api.example.com/api/v1/profile
```

---

## 🏢 Enterprise Single Sign-On (SSO)

SSO lets users login with their company account (Google, Azure, SAML). It's **license-gated**—only available in enterprise plans.

### Configuration

```python
from shared.licensing import requires_feature

# SAML SSO (enterprise only)
if license_client.has_feature('sso_saml'):
    app.config['SECURITY_SAML_ENABLED'] = True
    app.config['SECURITY_SAML_IDP_METADATA_URL'] = os.getenv('SAML_IDP_METADATA_URL')

# OAuth SSO (enterprise only)
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

# Protected SSO endpoints
@app.route('/auth/saml/login')
@requires_feature('sso_saml')
def saml_login():
    """SAML login (enterprise feature only)"""
    pass

@app.route('/auth/oauth/login')
@requires_feature('sso_oauth')
def oauth_login():
    """OAuth login (enterprise feature only)"""
    pass
```

### Environment Variables
```bash
# SAML (enterprise)
SAML_IDP_METADATA_URL=https://your-idp.com/metadata

# Google OAuth (enterprise)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-secret

# Azure OAuth (enterprise)
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-secret
```

---

## Testing Tips

### ✅ Test User Registration
```bash
curl -X POST http://localhost:5000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123!"
  }'
```

### ✅ Test Login
```bash
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@localhost.local",
    "password": "admin123"
  }'
```

### ✅ Test Protected Endpoint
```bash
TOKEN="your-jwt-token-here"
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:5000/api/v1/profile
```

### ✅ Test Admin Route
```bash
TOKEN="admin-jwt-token"
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:5000/api/v1/admin/users
```

### ✅ Test Forgot Password
```bash
curl -X POST http://localhost:5000/api/v1/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@localhost.local"}'
```

### ✅ Test Change Password
```bash
TOKEN="user-jwt-token"
curl -X POST http://localhost:5000/api/v1/auth/change-password \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "current_password": "admin123",
    "new_password": "NewSecurePass456!"
  }'
```

---

## Required Environment Variables

```bash
# Core authentication
SECRET_KEY=your-super-secret-key-change-in-production
SECURITY_PASSWORD_SALT=your-password-salt

# Password reset (optional - only needed for forgot password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_USER=noreply@example.com
SMTP_PASS=your-app-password
SMTP_FROM=noreply@example.com
APP_URL=https://app.example.com

# Flask-Security-Too features
SECURITY_RECOVERABLE=true
SECURITY_RESET_PASSWORD_WITHIN=1 hour
SECURITY_CHANGEABLE=true
SECURITY_SEND_REGISTER_EMAIL=false

# Enterprise SSO (license-gated)
SAML_IDP_METADATA_URL=https://your-idp.com/metadata
GOOGLE_CLIENT_ID=your-id
GOOGLE_CLIENT_SECRET=your-secret
AZURE_CLIENT_ID=your-id
AZURE_CLIENT_SECRET=your-secret
```

---

## Frontend Login Implementation

For React frontend applications, **use the `LoginPageBuilder` component** from `@penguin/react_libs`. It provides:

- Elder-style dark theme with gold accents
- ALTCHA CAPTCHA (proof-of-work) after failed attempts
- MFA/2FA support with 6-digit TOTP input
- Social login (OAuth2, OIDC, SAML)
- GDPR cookie consent banner

```tsx
import { LoginPageBuilder } from '@penguin/react_libs';

function LoginPage() {
  return (
    <LoginPageBuilder
      api={{ loginUrl: '/api/v1/auth/login' }}
      branding={{
        appName: 'My Application',
        githubRepo: 'penguintechinc/my-app',
      }}
      onSuccess={(response) => {
        localStorage.setItem('authToken', response.token);
        window.location.href = '/dashboard';
      }}
      gdpr={{ enabled: true, privacyPolicyUrl: '/privacy' }}
      captcha={{
        enabled: true,
        provider: 'altcha',
        challengeUrl: '/api/v1/captcha/challenge',
        failedAttemptsThreshold: 3,
      }}
      mfa={{ enabled: true, codeLength: 6 }}
    />
  );
}
```

📚 **Full documentation**: [React Libraries Standards](REACT_LIBS.md)

---

**Next Steps:** Check out [Database Standards](DATABASE.md) for data storage patterns and [API Standards](API_PROTOCOLS.md) for endpoint design.
