# Phase 0: Security Hardening + Licensing Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the HIGH/MEDIUM-severity security findings in tobogganing and consolidate the duplicated licensing code onto one v2 client with a PostHog-flag + license-entitlement wrapper — before the WaddlePerf module merge builds on this tree.

**Architecture:** Targeted fixes on the current `services/hub-api` (py4web) and `services/hub-router` (Go) trees, plus `shared/licensing` and infra (Docker/K8s/CI). No framework migration yet (that is Phase 1). Where the spec says "core/entitlements", Phase 0 lands the reusable wrapper in `shared/licensing/entitlements.py` so both the current hub-api and the future `core/` import the same helper.

**Tech Stack:** Python 3.12 (py4web/asyncio, cryptography, PyJWT, bcrypt, `requests`, `posthog`), Go 1.23 (gin, viper, `crypto/subtle`, `crypto/tls`), Docker (Debian bookworm), K8s, GitHub Actions, `uv` for pinned requirements.

## Global Constraints

- Work on branch `feature/phase-0-security-hardening` (already created off `release/v1.2.X`). Commit per task. PR into `release/v1.2.X` at the end.
- Never log secrets/passwords/tokens; log masked only.
- Python: type hints on new/edited functions; no bare `except:`; `python3` never bare `python`.
- Go: non-root, only `NET_ADMIN`; constant-time secret comparison; TLS `MinVersion` ≥ 1.2.
- Docker: Debian bookworm bases, external images pinned by `@sha256:` digest, non-root `USER`.
- GitHub Actions: pin third-party actions to full commit SHA.
- pip: `requirements.in` + `uv pip compile --generate-hashes` → hashed `requirements.txt`.
- License env: `LICENSE_KEY`, `PRODUCT_NAME=tobogganing`, `LICENSE_SERVER_URL`. Flags: `POSTHOG_KEY`, `POSTHOG_HOST` (default `https://license.penguintech.io`). Flag key convention `tobogganing.{module}.{feature}`.
- Do not delete `clients/native`, `clients/mobile` in this phase (client removal is tracked separately); only stop shipping Alpine/EOL bases where a Dockerfile is otherwise edited. Client Dockerfile base fixes are OUT of Phase 0 scope except `services/hub-router/Dockerfile`.

---

## File Structure

- `services/hub-api/auth/keys.py` — **new**: `KeyProvider` abstraction + `InAppKeyProvider` (load-or-generate persistent RSA PEM). KMS backends are stubbed with a clear `NotImplementedError` and wired in Phase 4b.
- `services/hub-api/auth/jwt_manager.py` — modify: consume a `KeyProvider`; drop the broken raw-`secret_key` path.
- `services/hub-api/main.py` — modify: build the `KeyProvider` from env and pass it to `JWTManager`.
- `services/hub-api/auth/http_auth.py` — **new**: `extract_bearer_token(headers) -> Optional[str]` shared helper.
- `services/hub-api/api/routes.py` — modify: await `validate_token`; require auth on cluster/client registration + cert issuance; use the bearer helper.
- `services/hub-api/security/middleware.py` — modify: real `require_admin_role`; delete `check_security_bypass`.
- `services/hub-api/web/auth.py` — modify: replace `run_until_complete` + bare `except`.
- `services/hub-api/auth/user_manager.py` — modify: stop logging password; remove unused `hashlib`.
- `services/hub-api/licensing/__init__.py` — **delete**; callers move to the shared wrapper.
- `shared/licensing/entitlements.py` — **new**: `feature_enabled(module, feature)` = PostHog flag AND (license entitlement if gated). Graceful cached degradation.
- `services/hub-api/requirements.in` — **new**; `requirements.txt` — regenerate hashed (adds `posthog`).
- `.env.example` — modify: add licensing/PostHog keys; fix `METRICS_TOKEN`.
- `services/hub-router/proxy/main.go` — modify: require metrics token (no default), constant-time compare, TLS `MinVersion`.
- `services/hub-router/proxy/main_test.go` — **new**: token compare + config-required tests.
- `services/hub-router/Dockerfile` — modify: Debian bookworm digest-pinned, `USER wireguard`.
- `k8s/manifests/hub-router-deployment.yaml`, `deploy/kubernetes/headend.yaml` — modify: non-root securityContext + documented cap exception.
- `.gitignore` — modify: ignore built headend binaries; `git rm` the 6 committed binaries.
- `deploy/docker-compose/docker-compose.dev.yml` — modify: move dev secrets to env interpolation with safe placeholders.
- `.github/workflows/*.yml` — modify: SHA-pin floating action refs.

---

### Task 1: Persistent, pluggable JWT signing key

**Files:**
- Create: `services/hub-api/auth/keys.py`
- Test: `services/hub-api/tests/test_keys.py`
- Modify: `services/hub-api/auth/jwt_manager.py:27-66`, `services/hub-api/main.py:50-54`

**Interfaces:**
- Produces: `class KeyProvider(Protocol)` with `private_pem: bytes`, `public_pem: bytes`; `class InAppKeyProvider(KeyProvider)`; `build_key_provider() -> KeyProvider` (reads env `JWT_PRIVATE_KEY_PEM`, or `JWT_PRIVATE_KEY_PATH`, else generates once and, if `JWT_PRIVATE_KEY_PATH` set, persists).
- Consumes (Task 3, existing code): `JWTManager(..., key_provider: KeyProvider)`.

- [ ] **Step 1: Write the failing test**

```python
# services/hub-api/tests/test_keys.py
import os
from auth.keys import InAppKeyProvider, build_key_provider

def test_inapp_provider_generates_valid_pem_pair():
    p = InAppKeyProvider()
    assert p.private_pem.startswith(b"-----BEGIN PRIVATE KEY-----")
    assert p.public_pem.startswith(b"-----BEGIN PUBLIC KEY-----")

def test_provider_loads_persistent_key_from_env(monkeypatch):
    seed = InAppKeyProvider()
    monkeypatch.setenv("JWT_PRIVATE_KEY_PEM", seed.private_pem.decode())
    p = build_key_provider()
    assert p.private_pem == seed.private_pem
    assert p.public_pem == seed.public_pem

def test_two_providers_from_same_env_pem_match(monkeypatch):
    seed = InAppKeyProvider()
    monkeypatch.setenv("JWT_PRIVATE_KEY_PEM", seed.private_pem.decode())
    a, b = build_key_provider(), build_key_provider()
    assert a.public_pem == b.public_pem  # cross-worker stability
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/hub-api && python3 -m pytest tests/test_keys.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'auth.keys'`).

- [ ] **Step 3: Write minimal implementation**

```python
# services/hub-api/auth/keys.py
"""Pluggable JWT/at-rest key providers. In-app default now; KMS in Phase 4b."""
from __future__ import annotations
import os
from typing import Protocol, runtime_checkable
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


@runtime_checkable
class KeyProvider(Protocol):
    private_pem: bytes
    public_pem: bytes


class InAppKeyProvider:
    """RSA keypair loaded from a PEM or generated in-process."""

    def __init__(self, private_pem: bytes | None = None) -> None:
        if private_pem:
            key = serialization.load_pem_private_key(
                private_pem, password=None, backend=default_backend()
            )
        else:
            key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048, backend=default_backend()
            )
        self.private_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.public_pem = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )


def build_key_provider() -> KeyProvider:
    """Env-driven: JWT_PRIVATE_KEY_PEM inline, or JWT_PRIVATE_KEY_PATH file, else generate."""
    pem = os.getenv("JWT_PRIVATE_KEY_PEM")
    if pem:
        return InAppKeyProvider(pem.encode())
    path = os.getenv("JWT_PRIVATE_KEY_PATH")
    if path and os.path.exists(path):
        with open(path, "rb") as fh:
            return InAppKeyProvider(fh.read())
    provider = InAppKeyProvider()
    if path:
        with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as fh:
            fh.write(provider.private_pem)
    return provider
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/hub-api && python3 -m pytest tests/test_keys.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Wire JWTManager to the provider**

In `services/hub-api/auth/jwt_manager.py`, replace the constructor key logic (lines 27-66). Change the signature to accept `key_provider: Optional["KeyProvider"] = None`, delete the `secret_key` param and the `if secret_key:` branch, and set the PEMs from the provider:

```python
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        token_expiry_hours: int = 24,
        refresh_expiry_days: int = 7,
        key_provider: Optional["KeyProvider"] = None,
    ):
        self.redis_url = redis_url
        self.token_expiry = timedelta(hours=token_expiry_hours)
        self.refresh_expiry = timedelta(days=refresh_expiry_days)
        self.redis_pool = None

        from auth.keys import InAppKeyProvider, KeyProvider  # noqa: F401
        provider = key_provider or InAppKeyProvider()
        self.private_pem = provider.private_pem
        self.public_pem = provider.public_pem
```

Delete the now-unused `_generate_rsa_keys` method and the `self.private_key`/`self.public_key` attributes if nothing else references them (grep first: `grep -rn "self.private_key\|self.public_key" services/hub-api/auth/jwt_manager.py`; if referenced, keep by deriving from `provider` — but signing at lines 129-139/185-189 uses `self.private_pem`/`self.public_pem`, which are set).

- [ ] **Step 6: Wire main.py to build the provider**

In `services/hub-api/main.py` replace lines 50-54:

```python
    from auth.keys import build_key_provider
    jwt_manager = JWTManager(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        token_expiry_hours=int(os.getenv("TOKEN_EXPIRY_HOURS", "24")),
        refresh_expiry_days=int(os.getenv("REFRESH_EXPIRY_DAYS", "7")),
        key_provider=build_key_provider(),
    )
```

- [ ] **Step 7: Run existing auth tests + new test**

Run: `cd services/hub-api && python3 -m pytest tests/test_keys.py tests/test_auth.py -v`
Expected: PASS (no regressions; if `test_auth.py` constructed `JWTManager(secret_key=...)`, update it to `key_provider=InAppKeyProvider()`).

- [ ] **Step 8: Commit**

```bash
git add services/hub-api/auth/keys.py services/hub-api/tests/test_keys.py \
        services/hub-api/auth/jwt_manager.py services/hub-api/main.py
git commit -m "fix(auth): persistent pluggable JWT signing key across workers"
```

---

### Task 2: Await validate_token + shared bearer helper

**Files:**
- Create: `services/hub-api/auth/http_auth.py`
- Test: `services/hub-api/tests/test_http_auth.py`
- Modify: `services/hub-api/api/routes.py:207`, `:388`, and the inline bearer parses at `:157-162,198-204,289-294,331-336`.

**Interfaces:**
- Produces: `extract_bearer_token(headers) -> Optional[str]` — returns the token after `Bearer `, else `None`.

- [ ] **Step 1: Write the failing test**

```python
# services/hub-api/tests/test_http_auth.py
from auth.http_auth import extract_bearer_token

def test_extracts_token():
    assert extract_bearer_token({"Authorization": "Bearer abc.def"}) == "abc.def"

def test_missing_or_wrong_scheme_returns_none():
    assert extract_bearer_token({}) is None
    assert extract_bearer_token({"Authorization": "Basic xxx"}) is None
    assert extract_bearer_token({"Authorization": "Bearer "}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/hub-api && python3 -m pytest tests/test_http_auth.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# services/hub-api/auth/http_auth.py
"""Shared HTTP auth helpers for hub-api routes."""
from __future__ import annotations
from typing import Mapping, Optional

_PREFIX = "Bearer "

def extract_bearer_token(headers: Mapping[str, str]) -> Optional[str]:
    value = headers.get("Authorization", "") or ""
    if not value.startswith(_PREFIX):
        return None
    token = value[len(_PREFIX):].strip()
    return token or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/hub-api && python3 -m pytest tests/test_http_auth.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Fix the two un-awaited calls**

In `services/hub-api/api/routes.py` line 207 and line 388, add `await`:

```python
            user_info = await jwt_manager.validate_token(token)
```

(both sites — line 207 inside `update_tunnel_config`, line 388 inside `submit_headend_metrics`).

- [ ] **Step 6: Replace inline bearer parses with the helper (optional-but-DRY)**

At the top of `routes.py` add `from auth.http_auth import extract_bearer_token`. At each of the four sites (157-162, 198-204, 289-294, 331-336) replace the 5-line inline parse with:

```python
            token = extract_bearer_token(request.headers)
            if token is None:
                response.status = 401
                return {"error": "Invalid authorization header"}
```

(rename the local to `token`/`api_key` to match each site's later usage — keep the existing variable name used downstream in that handler).

- [ ] **Step 7: Run tests**

Run: `cd services/hub-api && python3 -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add services/hub-api/auth/http_auth.py services/hub-api/tests/test_http_auth.py services/hub-api/api/routes.py
git commit -m "fix(auth): await validate_token and centralize bearer parsing"
```

---

### Task 3: Authenticate cluster/client registration + cert issuance

**Files:**
- Modify: `services/hub-api/api/routes.py:11-49` (`register_cluster`), `:70-91` (`list_clusters`), `:93-150` (`register_client`), `:51-68` (`cluster_heartbeat`).
- Test: `services/hub-api/tests/test_registration_auth.py`

**Interfaces:**
- Consumes: `extract_bearer_token` (Task 2); a bootstrap secret from env `ENROLLMENT_BOOTSTRAP_TOKEN`.
- Produces: helper `require_bootstrap(request) -> bool` local to routes (or in `http_auth.py`): constant-time compare of the bearer token to `ENROLLMENT_BOOTSTRAP_TOKEN`.

Rationale: full tenant scoping arrives with `core/` in Phase 1; Phase 0 closes the anonymous-cert hole with a shared bootstrap/enrollment secret that headends/clients must present to register. Registration without a valid token → 401. `list_clusters` requires a valid admin JWT.

- [ ] **Step 1: Write the failing test**

```python
# services/hub-api/tests/test_registration_auth.py
import hmac
from auth.http_auth import verify_bootstrap_token

def test_bootstrap_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("ENROLLMENT_BOOTSTRAP_TOKEN", "secret-xyz")
    assert verify_bootstrap_token("nope") is False

def test_bootstrap_accepts_correct_token(monkeypatch):
    monkeypatch.setenv("ENROLLMENT_BOOTSTRAP_TOKEN", "secret-xyz")
    assert verify_bootstrap_token("secret-xyz") is True

def test_bootstrap_unset_denies(monkeypatch):
    monkeypatch.delenv("ENROLLMENT_BOOTSTRAP_TOKEN", raising=False)
    assert verify_bootstrap_token("anything") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/hub-api && python3 -m pytest tests/test_registration_auth.py -v`
Expected: FAIL (`ImportError: cannot import name 'verify_bootstrap_token'`).

- [ ] **Step 3: Implement the verifier**

Append to `services/hub-api/auth/http_auth.py`:

```python
import hmac
import os

def verify_bootstrap_token(token: Optional[str]) -> bool:
    """Constant-time check of an enrollment/bootstrap token. Deny if unset."""
    expected = os.getenv("ENROLLMENT_BOOTSTRAP_TOKEN", "")
    if not expected or not token:
        return False
    return hmac.compare_digest(token, expected)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/hub-api && python3 -m pytest tests/test_registration_auth.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Gate the registration routes**

In `register_cluster` (after line 13) and `register_client` (after line 95) and `cluster_heartbeat` (after line 53), add at the top of the `try`:

```python
            from auth.http_auth import extract_bearer_token, verify_bootstrap_token
            if not verify_bootstrap_token(extract_bearer_token(request.headers)):
                response.status = 401
                return {"error": "Unauthorized: enrollment token required"}
```

In `list_clusters` (after line 72) require a valid admin JWT:

```python
            token = extract_bearer_token(request.headers)
            claims = await jwt_manager.validate_token(token) if token else None
            if not claims or claims.get("role") != "admin":
                response.status = 401
                return {"error": "Unauthorized"}
```

- [ ] **Step 6: Run tests**

Run: `cd services/hub-api && python3 -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/hub-api/auth/http_auth.py services/hub-api/tests/test_registration_auth.py services/hub-api/api/routes.py
git commit -m "fix(api): require enrollment token for registration + cert issuance"
```

---

### Task 4: Real require_admin_role; remove check_security_bypass

**Files:**
- Modify: `services/hub-api/security/middleware.py:78-96`
- Test: `services/hub-api/tests/test_admin_role.py`

- [ ] **Step 1: Write the failing test**

```python
# services/hub-api/tests/test_admin_role.py
import pytest
from security.middleware import require_admin_role

class _Req:
    def __init__(self, user): self.user = user

def test_denies_non_admin(monkeypatch):
    import security.middleware as m
    monkeypatch.setattr(m, "request", _Req({"role": "viewer"}))
    called = []
    @require_admin_role
    def handler(): called.append(True); return "ok"
    with pytest.raises(Exception):
        handler()
    assert not called

def test_allows_admin(monkeypatch):
    import security.middleware as m
    monkeypatch.setattr(m, "request", _Req({"role": "admin"}))
    @require_admin_role
    def handler(): return "ok"
    assert handler() == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/hub-api && python3 -m pytest tests/test_admin_role.py -v`
Expected: FAIL (current impl reads `request.environ.get('user')`, which the test does not set → both raise).

- [ ] **Step 3: Implement**

Replace lines 78-96 of `security/middleware.py`:

```python
import functools


def require_admin_role(func):
    """Require an authenticated admin user (populated on request.user)."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        user = getattr(request, "user", None)
        if not user or (user.get("role") if isinstance(user, dict) else getattr(user, "role", None)) != "admin":
            abort(403, "Admin role required")
        return func(*args, **kwargs)
    return wrapper
```

Delete `check_security_bypass` entirely and grep for callers: `grep -rn "check_security_bypass" services/hub-api`; remove any `@check_security_bypass` decorator usages found.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/hub-api && python3 -m pytest tests/test_admin_role.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add services/hub-api/security/middleware.py services/hub-api/tests/test_admin_role.py
git commit -m "fix(security): enforce admin role; remove security bypass decorator"
```

---

### Task 5: Fix web/auth.py event-loop misuse

**Files:**
- Modify: `services/hub-api/web/auth.py:13-29`

- [ ] **Step 1: Replace the broken sync-over-async**

Replace lines 19-29 with `asyncio.run` guarded by explicit exception types (no bare except):

```python
    import asyncio
    try:
        return asyncio.run(user_manager.validate_session(session_id))
    except RuntimeError:
        # Already inside a running loop (async server): run on a private loop.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(user_manager.validate_session(session_id))
        finally:
            loop.close()
    except Exception as exc:  # noqa: BLE001 - log and fail closed
        logger.warning("session validation failed", error=str(exc))
        return None
```

Add `import structlog` + `logger = structlog.get_logger()` near the top if not present (grep first).

- [ ] **Step 2: Verify import + lint**

Run: `cd services/hub-api && python3 -c "import ast,sys; ast.parse(open('web/auth.py').read())" && python3 -m flake8 web/auth.py --select=E999,E722`
Expected: no `E722` (bare except) and no syntax error.

- [ ] **Step 3: Commit**

```bash
git add services/hub-api/web/auth.py
git commit -m "fix(web): safe session validation; drop bare except and run_until_complete-on-running-loop"
```

---

### Task 6: Stop logging default admin password; drop unused import

**Files:**
- Modify: `services/hub-api/auth/user_manager.py:108-111`, `:6`

- [ ] **Step 1: Redact the password log**

Replace lines 108-111 (the `logger.warning(... password=password ...)`) with a delivery via a one-time secret file / env, never the log:

```python
        logger.warning(
            "Created default admin user; retrieve the generated password from the "
            "ADMIN_BOOTSTRAP_PASSWORD_FILE path or reset it via the CLI",
            username="admin",
        )
        bootstrap_path = os.getenv("ADMIN_BOOTSTRAP_PASSWORD_FILE")
        if bootstrap_path:
            with open(os.open(bootstrap_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
                fh.write(password)
```

Add `import os` if not already imported (grep). Do NOT print `password` anywhere.

- [ ] **Step 2: Remove unused hashlib import**

Delete line 6 `import hashlib` (confirm unused: `grep -n "hashlib" services/hub-api/auth/user_manager.py` → only the import).

- [ ] **Step 3: Verify**

Run: `cd services/hub-api && python3 -m flake8 auth/user_manager.py --select=F401,E999 && ! grep -n "password=password" auth/user_manager.py`
Expected: no F401, no syntax error, grep finds nothing.

- [ ] **Step 4: Commit**

```bash
git add services/hub-api/auth/user_manager.py
git commit -m "fix(auth): never log default admin password; remove unused hashlib"
```

---

### Task 7: Consolidate licensing onto shared v2 + entitlements wrapper

**Files:**
- Create: `shared/licensing/entitlements.py`
- Test: `shared/licensing/tests/test_entitlements.py`
- Delete: `services/hub-api/licensing/__init__.py`
- Modify: caller `services/hub-api/api/routes.py:322` (`check_feature('client_metrics')`)
- Modify: `services/hub-api/requirements.in` (Task 12 regenerates txt) to add `posthog`.

**Interfaces:**
- Produces: `feature_enabled(module: str, feature: str, distinct_id: str = "system", licensed: bool = False) -> bool` — returns `True` only if the PostHog flag `tobogganing.{module}.{feature}` is enabled AND, when `licensed=True`, the license entitlement `check_feature(feature)` passes. Graceful: on PostHog/license error, fall back to last cached value; unseen flag → `False`.
- Consumes: `shared/licensing/python_client.py` `check_feature` / `get_client`.

- [ ] **Step 1: Write the failing test**

```python
# shared/licensing/tests/test_entitlements.py
import shared.licensing.entitlements as ent

def test_flag_off_denies(monkeypatch):
    monkeypatch.setattr(ent, "_flag_on", lambda key, did: False)
    assert ent.feature_enabled("waddleperf_c2c", "region_matrix") is False

def test_flag_on_unlicensed_feature_allows(monkeypatch):
    monkeypatch.setattr(ent, "_flag_on", lambda key, did: True)
    assert ent.feature_enabled("sase", "firewall") is True

def test_licensed_feature_requires_entitlement(monkeypatch):
    monkeypatch.setattr(ent, "_flag_on", lambda key, did: True)
    monkeypatch.setattr(ent, "_licensed", lambda f: False)
    assert ent.feature_enabled("sase", "sso", licensed=True) is False
    monkeypatch.setattr(ent, "_licensed", lambda f: True)
    assert ent.feature_enabled("sase", "sso", licensed=True) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/penguin/code/tobogganing && python3 -m pytest shared/licensing/tests/test_entitlements.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# shared/licensing/entitlements.py
"""Unified feature gate: PostHog flag AND (optional) license entitlement."""
from __future__ import annotations
import os
import logging
from typing import Dict

logger = logging.getLogger(__name__)
_cache: Dict[str, bool] = {}
_posthog = None

def _client():
    global _posthog
    if _posthog is None:
        key = os.getenv("POSTHOG_KEY")
        if not key:
            return None
        import posthog
        posthog.project_api_key = key
        posthog.host = os.getenv("POSTHOG_HOST", "https://license.penguintech.io")
        _posthog = posthog
    return _posthog

def _flag_on(key: str, distinct_id: str) -> bool:
    client = _client()
    if client is None:
        return _cache.get(key, False)  # no flags configured → default OFF
    try:
        result = bool(client.feature_enabled(key, distinct_id))
        _cache[key] = result
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("posthog flag lookup failed for %s: %s", key, exc)
        return _cache.get(key, False)

def _licensed(feature: str) -> bool:
    try:
        from shared.licensing.python_client import check_feature
        return bool(check_feature(feature))
    except Exception as exc:  # noqa: BLE001
        logger.warning("license check failed for %s: %s", feature, exc)
        return False

def feature_enabled(module: str, feature: str, distinct_id: str = "system",
                    licensed: bool = False) -> bool:
    key = f"tobogganing.{module}.{feature}"
    if not _flag_on(key, distinct_id):
        return False
    if licensed and not _licensed(feature):
        return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/penguin/code/tobogganing && python3 -m pytest shared/licensing/tests/test_entitlements.py -v`
Expected: PASS (4 passed). (Add empty `shared/licensing/tests/__init__.py` if needed for import.)

- [ ] **Step 5: Repoint the one existing gate + delete v1 module**

In `services/hub-api/api/routes.py` around line 322, replace `from ..licensing import check_feature` / `if not check_feature('client_metrics')` with:

```python
            from shared.licensing.entitlements import feature_enabled
            if not feature_enabled("waddleperf_client", "client_metrics", licensed=True):
```

Then `git rm services/hub-api/licensing/__init__.py` and grep for any other importers: `grep -rn "from.*licensing import\|import licensing" services/hub-api` → repoint or remove. (Import path for `shared` must resolve; if hub-api can't see `shared/`, add it via the existing sys.path/setup used for other `shared` imports — grep `grep -rn "shared" services/hub-api/*.py`.)

- [ ] **Step 6: Run tests**

Run: `cd /home/penguin/code/tobogganing && python3 -m pytest shared/licensing/tests/ services/hub-api/tests/ -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shared/licensing/entitlements.py shared/licensing/tests/ services/hub-api/api/routes.py
git rm services/hub-api/licensing/__init__.py
git commit -m "feat(licensing): consolidate on v2 client + PostHog entitlements wrapper"
```

---

### Task 8: .env.example — licensing/PostHog keys + metrics token

**Files:**
- Modify: `.env.example` (has `JWT_SECRET` L38 dead, `METRICS_TOKEN=prometheus-scraper-token` L40)

- [ ] **Step 1: Edit .env.example**

Change line 40 to remove the well-known default and add the new keys after the auth section:

```bash
METRICS_TOKEN=change_this_to_a_random_metrics_token
JWT_PRIVATE_KEY_PATH=/run/secrets/jwt_private_key.pem
ENROLLMENT_BOOTSTRAP_TOKEN=change_this_enrollment_token
ADMIN_BOOTSTRAP_PASSWORD_FILE=/run/secrets/admin_bootstrap_password

# Licensing & feature flags
LICENSE_KEY=
PRODUCT_NAME=tobogganing
LICENSE_SERVER_URL=https://license.penguintech.io
POSTHOG_KEY=
POSTHOG_HOST=https://license.penguintech.io
```

Remove the now-superseded dead `JWT_SECRET` line (38) — the service signs with the RSA key provider, not `JWT_SECRET`.

- [ ] **Step 2: Verify no secret literal defaults remain**

Run: `! grep -nE "prometheus-scraper-token|dev-jwt-secret|dev-api-key" .env.example`
Expected: no matches.

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "chore(config): document licensing/PostHog env; drop default metrics token"
```

---

### Task 9: Go metrics token — require config + constant-time + TLS MinVersion

**Files:**
- Modify: `services/hub-router/proxy/main.go:15-41` (imports), `:402-438` (metricsHandler), `:533-536` (tls.Config)
- Test: `services/hub-router/proxy/main_test.go`

- [ ] **Step 1: Write the failing test**

```go
// services/hub-router/proxy/main_test.go
package main

import "testing"

func TestTokenMatchConstantTime(t *testing.T) {
    if !tokensEqual("abc", "abc") {
        t.Fatal("equal tokens should match")
    }
    if tokensEqual("abc", "abd") {
        t.Fatal("different tokens must not match")
    }
    if tokensEqual("", "") {
        t.Fatal("empty expected token must never match")
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/hub-router && go test ./proxy/ -run TestTokenMatchConstantTime`
Expected: FAIL (`undefined: tokensEqual`).

- [ ] **Step 3: Implement**

Add `"crypto/subtle"` to the import block (line ~17). Add a helper and rewrite the token branch in `metricsHandler`:

```go
// tokensEqual is a constant-time comparison that always denies an empty expected token.
func tokensEqual(got, expected string) bool {
    if expected == "" {
        return false
    }
    return subtle.ConstantTimeCompare([]byte(got), []byte(expected)) == 1
}
```

Replace lines 414-424 (the default-token block) with:

```go
        token := strings.TrimPrefix(authHeader, "Bearer ")
        expectedToken := viper.GetString("metrics.auth_token")
        if tokensEqual(token, expectedToken) {
            promhttp.Handler().ServeHTTP(c.Writer, c.Request)
            return
        }
```

In the outbound `tls.Config` (line 534) add `MinVersion`:

```go
        TLSClientConfig: &tls.Config{
            MinVersion:         tls.VersionTLS12,
            InsecureSkipVerify: viper.GetBool("proxy.skip_tls_verify"),
        },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/hub-router && go test ./proxy/ -run TestTokenMatchConstantTime && go vet ./proxy/`
Expected: PASS, no vet errors.

- [ ] **Step 5: Commit**

```bash
git add services/hub-router/proxy/main.go services/hub-router/proxy/main_test.go
git commit -m "fix(hub-router): require metrics token, constant-time compare, TLS 1.2 min"
```

---

### Task 10: hub-router rootless Dockerfile + K8s securityContext

**Files:**
- Modify: `services/hub-router/Dockerfile`
- Modify: `k8s/manifests/hub-router-deployment.yaml:75-82`
- Modify: `deploy/kubernetes/headend.yaml:74-79`

- [ ] **Step 1: Dockerfile → Debian bookworm digest-pinned + non-root**

Use the `pinning-dependency-digests` skill to fetch current digests for `golang:1.23-bookworm` and `debian:bookworm-slim`. Replace the FROM lines and add `USER wireguard` before ENTRYPOINT:

```dockerfile
FROM golang:1.23-bookworm@sha256:<BUILDER_DIGEST> AS builder
...
FROM debian:bookworm-slim@sha256:<RUNTIME_DIGEST>
RUN apt-get update && apt-get install -y --no-install-recommends \
    wireguard-tools iptables iproute2 openssl ca-certificates iputils-ping curl jq bash \
    && rm -rf /var/lib/apt/lists/*
...
RUN groupadd -r wireguard && useradd -r -g wireguard wireguard \
    && chown -R wireguard:wireguard /etc/wireguard /certs /app /config
USER wireguard
WORKDIR /app
ENTRYPOINT ["/app/entrypoint.sh"]
```

Note: `entrypoint.sh` must not require root beyond `NET_ADMIN` for `wg`/`ip` (granted via capability). If it currently runs `iptables` needing more, capture that in the K8s cap list, not by running as root.

- [ ] **Step 2: K8s manifest — non-root + documented cap exception**

In `k8s/manifests/hub-router-deployment.yaml` replace lines 75-82:

```yaml
          securityContext:
            # ROOT EXCEPTION (approved): WireGuard needs NET_ADMIN for tunnel setup.
            runAsNonRoot: true
            runAsUser: 1000
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: [ALL]
              add: [NET_ADMIN]
```

Remove `SYS_MODULE` (modules should be loaded on the host, not by the pod). If a writable path is needed, add an `emptyDir` volume mount rather than disabling `readOnlyRootFilesystem`.

In `deploy/kubernetes/headend.yaml` lines 74-79, replace `privileged: true` with the same non-root + `NET_ADMIN`-only block and the `ROOT EXCEPTION (approved)` comment.

- [ ] **Step 3: Validate manifests**

Run: `kubectl --context local-alpha kustomize k8s/kustomize/base >/dev/null 2>&1 || kubectl apply --dry-run=client -f k8s/manifests/hub-router-deployment.yaml -o yaml >/dev/null`
Expected: no schema errors. (If no cluster context available, `python3 -c "import yaml,sys; list(yaml.safe_load_all(open('k8s/manifests/hub-router-deployment.yaml')))"`.)

- [ ] **Step 4: Commit**

```bash
git add services/hub-router/Dockerfile k8s/manifests/hub-router-deployment.yaml deploy/kubernetes/headend.yaml
git commit -m "fix(hub-router): rootless container + NET_ADMIN-only securityContext"
```

---

### Task 11: Remove committed binaries + dev secrets

**Files:**
- Modify: `.gitignore`
- Delete (git rm): 6 headend binaries under `services/hub-router/`
- Modify: `deploy/docker-compose/docker-compose.dev.yml:12,28,29,32,86,125`

- [ ] **Step 1: Remove the committed binaries + ignore them**

```bash
git rm --cached services/hub-router/test-headend services/hub-router/headend-test \
  services/hub-router/headend-proxy services/hub-router/proxy/headend-proxy \
  services/hub-router/headend-proxy-arm64 services/hub-router/headend-proxy-arm64-test
```

Append to `.gitignore`:

```gitignore
# Built Go headend binaries
services/hub-router/headend-proxy*
services/hub-router/headend-test
services/hub-router/test-headend
services/hub-router/proxy/headend-proxy
```

- [ ] **Step 2: Replace committed dev secrets with interpolation**

In `deploy/docker-compose/docker-compose.dev.yml`, replace literal secrets with `${VAR:?set in .env}` style so no secret ships in the file:

```yaml
    command: redis-server --requirepass ${REDIS_PASSWORD:?set REDIS_PASSWORD} --appendonly yes
      - REDIS_URL=redis://:${REDIS_PASSWORD:?set REDIS_PASSWORD}@redis:6379
      - JWT_PRIVATE_KEY_PATH=/run/secrets/jwt_private_key.pem
      - ADMIN_BOOTSTRAP_PASSWORD_FILE=/run/secrets/admin_bootstrap_password
      - API_KEY=${DEV_API_KEY:?set DEV_API_KEY}
      - REDIS_HOSTS=local:redis:6379:0:${REDIS_PASSWORD:?set REDIS_PASSWORD}
```

- [ ] **Step 3: Verify no secrets remain**

Run: `! grep -nE "devpassword|dev-jwt-secret-not-for-production|dev-api-key-12345" deploy/docker-compose/docker-compose.dev.yml && git status --short | grep -E "^D  services/hub-router/(headend|test)"`
Expected: grep finds no secret literals; the binaries show as deleted.

- [ ] **Step 4: Commit**

```bash
git add .gitignore deploy/docker-compose/docker-compose.dev.yml
git commit -m "chore(security): drop committed binaries and dev secret literals"
```

---

### Task 12: SHA-pin GitHub Actions

**Files:**
- Modify: all `.github/workflows/*.yml` with floating third-party action refs.

- [ ] **Step 1: Resolve each floating ref to a commit SHA**

Use the `pinning-dependency-digests` skill (or `gh api repos/{owner}/{action}/commits/{tag}` — high-level `gh` only) to resolve each of the distinct floating refs to a full commit SHA, keeping a `# vX` comment. The distinct floating refs to pin (dedupe already done):
`actions/cache@v3`, `actions/checkout@v3`, `actions/checkout@v4`, `actions/download-artifact@v3|v4`, `actions/github-script@v7`, `actions/setup-go@v4|v5`, `actions/setup-java@v4`, `actions/setup-node@v4`, `actions/setup-python@v4`, `actions/upload-artifact@v3|v4`, `android-actions/setup-android@v3`, `ansible/ansible-lint-action@v6.11.0`, `aquasecurity/trivy-action@master`, `codecov/codecov-action@v3`, `docker/build-push-action@v5`, `docker/login-action@v3`, `docker/metadata-action@v5`, `docker/setup-buildx-action@v3`, `docker/setup-qemu-action@v3`, `linear-b/gitstream-github-action@v1`, `r0adkll/upload-google-play@v1`, `ruby/setup-ruby@v1`, `softprops/action-gh-release@v1`, `github/codeql-action/upload-sarif@v2`.

Replace `aquasecurity/trivy-action@master` with a pinned release SHA (the tree already pins it to `57a97c7e...  # v0.35.0` elsewhere — reuse that SHA).

- [ ] **Step 2: Apply edits across workflows**

For each workflow file, replace `uses: owner/action@vX` with `uses: owner/action@<full-sha>  # vX`. (Leave the refs already SHA-pinned untouched.)

- [ ] **Step 3: Verify no floating third-party refs remain**

Run: `grep -rnE "uses: [^@]+@(v[0-9]|master|main)([^0-9a-f]|$)" .github/workflows/ | grep -v "penguintechinc/"`
Expected: no matches (any remaining are first-party/local composite actions).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/
git commit -m "chore(ci): pin third-party GitHub Actions to commit SHAs"
```

---

### Task 13: requirements.in + hashed compile (adds posthog)

**Files:**
- Create: `services/hub-api/requirements.in`
- Regenerate: `services/hub-api/requirements.txt`

- [ ] **Step 1: Author requirements.in**

Create `services/hub-api/requirements.in` from the current direct deps, converting `>=` floors to exact pins and adding `posthog`:

```
py4web==1.20240901.1
uvicorn[standard]==0.24.0
uvloop==0.19.0
aiohttp==3.9.1
aiofiles==23.2.1
httpx==0.25.2
bcrypt==4.1.2
cryptography==41.0.7
pyjwt==2.8.0
pydal==20231112.1
pymysql==1.1.0
psycopg2-binary==2.9.9
asyncpg==0.29.0
sqlalchemy==2.0.23
redis==5.0.1
aioredis==2.0.1
prometheus-client==0.19.0
psutil==5.9.6
pydantic==2.5.3
pyyaml==6.0.1
structlog==23.2.0
dnspython==2.4.2
python-dotenv==1.0.0
boto3==1.34.0
botocore==1.34.0
posthog==3.7.0
requests==2.31.0
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
pylint==3.0.3
mypy==1.7.1
```

(`requests` is a direct dep — the licensing client uses it — so pin it explicitly rather than relying on it transitively.)

- [ ] **Step 2: Compile with hashes**

Run: `cd services/hub-api && pip install uv 2>/dev/null; uv pip compile requirements.in --generate-hashes -o requirements.txt`
Expected: `requirements.txt` regenerated with `--hash=sha256:` lines for every package.

- [ ] **Step 3: Verify hashes present**

Run: `grep -c "hash=sha256" services/hub-api/requirements.txt`
Expected: a count > 30.

- [ ] **Step 4: Commit**

```bash
git add services/hub-api/requirements.in services/hub-api/requirements.txt
git commit -m "chore(deps): pin hub-api requirements with hashes; add posthog"
```

---

## Self-Review

- **Spec coverage:** Every Phase 0 bullet maps to a task — unauth cert issuance (T3), ephemeral/pluggable JWT keys (T1), hardcoded metrics token + constant-time + TLS min (T9), root hub-router (T10), await validate_token / admin-role stub / run_until_complete / password log / refresh_token (T2, T4, T5, T6; refresh_token permission downgrade is documented as a known follow-up — see note below), licensing consolidation + entitlements wrapper + .env (T7, T8), supply-chain: Actions SHA-pin (T12), Docker digest+bookworm (T10 for hub-router; other client Dockerfiles explicitly out of Phase 0 scope), committed binaries + dev secrets (T11), hashed pip deps (T13). README brand drift is cosmetic and folded into Phase 2's SASE port (documented; recon found NO conflict markers, so that item is dropped).
- **refresh_token downgrade:** the fix (store original claims to reissue with correct permissions) depends on the persistent token store that arrives with `core/` in Phase 1; Phase 0 leaves a `# TODO(phase-1)` only where the store is introduced, and does not weaken current behavior. Tracked in the Phase 1 plan.
- **Placeholder scan:** no TBD/"handle edge cases" — every code step has concrete code; the only intentional lookups are digest/SHA resolution via the pinning skill (T10, T12), which cannot be hardcoded.
- **Type consistency:** `KeyProvider.private_pem/public_pem` (T1) consumed by JWTManager; `extract_bearer_token`/`verify_bootstrap_token` (T2/T3) reused in T3; `feature_enabled(module, feature, distinct_id, licensed)` (T7) used consistently at the one call site; Go `tokensEqual(got, expected)` (T9) matches its test.

## Execution Handoff

Recommended: subagent-driven — one specialist agent per task (penguin-python-dev for T1–T8, penguin-go-dev for T9, moby-expert for T10 Dockerfile, penguintech-dev for T11–T13), review between tasks, commit per task, PR into `release/v1.2.X` at the end.
