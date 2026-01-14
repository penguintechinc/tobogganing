# Authentication Standards

Part of [Development Standards](../STANDARDS.md)

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

### Password Reset and Recovery

**ALL applications with user authentication MUST implement password reset functionality:**

#### Requirements

1. **Forgot Password Flow** (SMTP server required):
   - Link on login page: "Forgot password?"
   - User enters email address
   - System sends password reset email with time-limited token
   - User clicks link in email and sets new password
   - Token expires after configurable time (default: 1 hour)
   - ONLY enabled when SMTP server is configured

2. **Change Password (Authenticated Users)**:
   - Available in user profile/settings page
   - ALWAYS enabled regardless of SMTP configuration
   - Requires current password for verification
   - New password must meet complexity requirements
   - Validates new password against current password (no reuse)

#### Flask-Security-Too Configuration

```python
# Environment variables for password reset
SECURITY_RECOVERABLE = True  # Enable forgot password flow
SECURITY_RESET_PASSWORD_WITHIN = '1 hour'  # Token expiration
SECURITY_CHANGEABLE = True  # Enable change password
SECURITY_SEND_PASSWORD_RESET_EMAIL = True  # Send reset emails (requires SMTP)

# SMTP configuration (required for forgot password)
MAIL_SERVER = os.getenv('SMTP_HOST', '')
MAIL_PORT = int(os.getenv('SMTP_PORT', 587))
MAIL_USE_TLS = os.getenv('SMTP_TLS', 'true').lower() == 'true'
MAIL_USERNAME = os.getenv('SMTP_USER', '')
MAIL_PASSWORD = os.getenv('SMTP_PASS', '')
MAIL_DEFAULT_SENDER = os.getenv('SMTP_FROM', 'noreply@example.com')
```

#### Backend Implementation

```python
from flask import Flask, request, jsonify
from flask_security import Security, hash_password, verify_password
from flask_mail import Mail, Message

app = Flask(__name__)
mail = Mail(app)

# Check if SMTP is configured
def is_smtp_configured():
    """Check if SMTP server is configured for email sending"""
    return bool(os.getenv('SMTP_HOST'))

@app.route('/api/v1/auth/forgot-password', methods=['POST'])
def forgot_password():
    """Initiate password reset - requires SMTP configuration"""
    if not is_smtp_configured():
        return jsonify({
            'error': 'Password reset via email is not available. '
                     'Please contact your administrator.'
        }), 503

    data = request.get_json()
    email = data.get('email')

    # Find user by email
    user = user_datastore.find_user(email=email)
    if not user:
        # Return success even if user not found (security best practice)
        return jsonify({'message': 'If an account exists, a reset email has been sent.'})

    # Generate reset token (Flask-Security-Too handles this)
    token = user_datastore.generate_reset_password_token(user)

    # Send reset email
    reset_url = f"{os.getenv('APP_URL')}/reset-password?token={token}"
    msg = Message(
        subject='Password Reset Request',
        recipients=[email],
        body=f'Click here to reset your password: {reset_url}'
    )
    mail.send(msg)

    return jsonify({'message': 'If an account exists, a reset email has been sent.'})

@app.route('/api/v1/auth/reset-password', methods=['POST'])
def reset_password():
    """Complete password reset with token"""
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('password')

    # Verify token and reset password (Flask-Security-Too handles this)
    user = user_datastore.find_user_by_reset_token(token)
    if not user:
        return jsonify({'error': 'Invalid or expired reset token'}), 400

    # Update password
    user.password = hash_password(new_password)
    user_datastore.put(user)
    db.commit()

    return jsonify({'message': 'Password reset successfully'})

@app.route('/api/v1/auth/change-password', methods=['POST'])
@auth_required()
def change_password():
    """Change password for authenticated user"""
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    # Verify current password
    if not verify_password(current_password, current_user.password):
        return jsonify({'error': 'Current password is incorrect'}), 400

    # Ensure new password is different
    if verify_password(new_password, current_user.password):
        return jsonify({'error': 'New password must be different from current password'}), 400

    # Update password
    current_user.password = hash_password(new_password)
    user_datastore.put(current_user)
    db.commit()

    return jsonify({'message': 'Password changed successfully'})
```

#### Frontend Implementation

**Forgot Password Page** (only shown if SMTP configured):

```jsx
// src/pages/ForgotPassword.jsx
import React, { useState } from 'react';
import { apiClient } from '../services/apiClient';

export function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);

    try {
      const response = await apiClient.post('/api/v1/auth/forgot-password', { email });
      setMessage(response.data.message);
    } catch (err) {
      if (err.response?.status === 503) {
        setError('Password reset via email is not available. Please contact your administrator.');
      } else {
        setError('An error occurred. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="forgot-password-container">
      <h2>Forgot Password</h2>
      <form onSubmit={handleSubmit}>
        {message && <div className="success-message">{message}</div>}
        {error && <div className="error-message">{error}</div>}

        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Enter your email"
          required
        />

        <button type="submit" disabled={loading}>
          {loading ? 'Sending...' : 'Send Reset Link'}
        </button>

        <a href="/login">Back to Login</a>
      </form>
    </div>
  );
}
```

**Change Password Component** (user profile/settings):

```jsx
// src/components/ChangePassword.jsx
import React, { useState } from 'react';
import { apiClient } from '../services/apiClient';

export function ChangePassword() {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');

    // Validate passwords match
    if (newPassword !== confirmPassword) {
      setError('New passwords do not match');
      return;
    }

    try {
      const response = await apiClient.post('/api/v1/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      });

      setMessage(response.data.message);
      // Clear form
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setError(err.response?.data?.error || 'Password change failed');
    }
  };

  return (
    <div className="change-password-section">
      <h3>Change Password</h3>
      <form onSubmit={handleSubmit}>
        {message && <div className="success-message">{message}</div>}
        {error && <div className="error-message">{error}</div>}

        <div className="form-group">
          <label>Current Password</label>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
          />
        </div>

        <div className="form-group">
          <label>New Password</label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
        </div>

        <div className="form-group">
          <label>Confirm New Password</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
          />
        </div>

        <button type="submit">Change Password</button>
      </form>
    </div>
  );
}
```

#### Environment Variables

```bash
# SMTP Configuration (required for forgot password flow)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_USER=noreply@example.com
SMTP_PASS=smtp-password-here
SMTP_FROM=noreply@example.com

# Application URL (for reset links)
APP_URL=https://app.example.com

# Flask-Security-Too password reset settings
SECURITY_RECOVERABLE=true
SECURITY_RESET_PASSWORD_WITHIN=1 hour
SECURITY_CHANGEABLE=true
SECURITY_SEND_PASSWORD_RESET_EMAIL=true
```

#### UI/UX Guidelines

1. **Forgot Password Link**: Always visible on login page, even if SMTP not configured
2. **Graceful Degradation**: If SMTP not configured, show helpful error message
3. **Change Password**: Always available in user profile/settings (no SMTP required)
4. **Security Messaging**: Use same response for valid/invalid emails to prevent user enumeration
5. **Token Expiration**: Clearly communicate token lifetime to users
6. **Password Complexity**: Display password requirements inline
7. **Success Confirmation**: Provide clear feedback when password changed successfully
