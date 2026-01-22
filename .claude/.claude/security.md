# Security Standards

## ⚠️ CRITICAL RULES

**NEVER:**
- ❌ Commit hardcoded secrets, API keys, credentials, or private keys
- ❌ Skip input validation "just this once"
- ❌ Ignore security vulnerabilities in dependencies
- ❌ Deploy without running security scans
- ❌ Use TLS < 1.2 or weak encryption
- ❌ Skip authentication or authorization checks
- ❌ Assume data is valid without verification
- ❌ Use deprecated or vulnerable dependencies

---

## TLS/Encryption Requirements

- **TLS 1.2+ mandatory**, prefer TLS 1.3 for all connections
- HTTPS for all external-facing APIs
- Disable SSLv3, TLS 1.0, TLS 1.1
- Use strong cipher suites (AES-GCM preferred)
- Certificate validation required for mTLS scenarios
- Rotate certificates before expiration

---

## Input Validation (Mandatory)

- **ALL inputs** require validation before processing
- Framework-native validators (PyDAL, Flask, Go libraries)
- Server-side validation on all client input
- XSS prevention: Escape HTML/JS in outputs
- SQL injection prevention: Use parameterized queries (PyDAL handles this)
- CSRF protection via framework features
- Type checking and bounds validation

---

## Authentication & Authorization

**Requirements:**
- Multi-factor authentication (MFA) support
- JWT tokens with proper expiration (default 1 hour, max 24 hours)
- Role-Based Access Control (RBAC) with three tiers:
  - **Global**: Admin, Maintainer, Viewer
  - **Container/Team**: Team Admin, Team Maintainer, Team Viewer
  - **Resource**: Owner, Editor, Viewer
- OAuth2-style scopes for granular permissions
- Session management with secure HTTP-only cookies
- API key rotation required
- No hardcoded user credentials

**Standard Scopes Pattern:**
```
users:read, users:write, users:admin
reports:read, reports:write
analytics:read, analytics:admin
```

---

## Security Scanning (Mandatory Before Commit)

**Python Services:**
- `bandit -r .` - Security issue detection
- `safety check` - Dependency vulnerability check
- `pip-audit` - PyPI package vulnerabilities

**Go Services:**
- `gosec ./...` - Go security checker
- `go mod audit` - Dependency vulnerabilities

**Node.js Services:**
- `npm audit` - Dependency vulnerability scan
- ESLint with security plugins

**Container Images:**
- `trivy image <image>` - Image vulnerability scanning
- Check for exposed secrets, CVEs, weak configs

**Code Analysis:**
- CodeQL analysis (GitHub Actions)
- All code MUST pass security checks before commit

---

## Secrets & Credentials Management

**Environment Variables Only:**
- Store all secrets in `.env` (development) or environment variables (production)
- Never commit `.env` files or credential files
- Use `.gitignore` to prevent accidental commits
- Rotate secrets regularly

**Required Files in .gitignore:**
```
.env
.env.local
.env.*.local
*.key
*.pem
credentials.json
secrets/
```

**Verification Before Commit:**
```bash
# Scan for secrets
git diff --cached | grep -E 'password|secret|key|token|credential'
```

---

## OWASP Top 10 Awareness

1. **Broken Access Control** - Implement RBAC with proper scope checking
2. **Cryptographic Failures** - Use TLS 1.2+, strong encryption
3. **Injection** - Parameterized queries, input validation
4. **Insecure Design** - Security by design, threat modeling
5. **Security Misconfiguration** - Minimal permissions, default deny
6. **Vulnerable Components** - Scan dependencies, keep updated
7. **Authentication Failures** - MFA, JWT validation, secure sessions
8. **Data Integrity Issues** - Validate all inputs, use transactions
9. **Logging & Monitoring Failures** - Log security events, monitor for anomalies
10. **SSRF** - Validate URLs, restrict internal network access

---

## SSO (Enterprise-Only Feature)

- SAML 2.0 for enterprise customers
- OAuth2 for third-party integrations
- Only enable when explicitly requested
- Requires additional licensing
- Document SSO configuration in deployment guide

---

## Standard Security Checklist

- [ ] All inputs validated server-side
- [ ] Authentication and authorization working
- [ ] No hardcoded secrets or credentials
- [ ] TLS 1.2+ enforced
- [ ] Security scans pass (bandit, gosec, npm audit, trivy)
- [ ] Dependencies up-to-date and vulnerability-free
- [ ] CodeQL analysis passed
- [ ] CSRF and XSS protections enabled
- [ ] Secure cookies (HTTP-only, Secure, SameSite flags)
- [ ] Rate limiting implemented on API endpoints
- [ ] SQL injection prevention (parameterized queries)
- [ ] Error messages don't leak sensitive info
- [ ] Access logs enabled and monitored
