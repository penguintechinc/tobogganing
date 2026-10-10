# Design: Relocate SSO (Google OAuth2 / SAML 2.0 / OIDC) from hub-router (Go) into hub-api (Python/Quart)

Surveyed at `origin/release/v1.2.X` via `git show` (working tree NOT used — has unrelated uncommitted changes).

> **Scope addition (post-review correction):** two changes beyond the original SSO-relocation ask, both landing in this same effort because it already rebuilds/unifies `AuthService`'s issuance path:
> 1. **ES256 (EC P-256) becomes the PRIMARY signing algorithm for ALL new hub-api JWT issuance — password login AND SSO alike, not SSO-only.** RS256 becomes a legacy, verify-only algorithm during a bake-out transition; it is never used for new issuance after cutover. This touches the pre-existing password-login path (`AuthService._generate_access_token`), which is why it's called out explicitly rather than folded silently into the SSO work.
> 2. **Authz stays strictly scope-based; `roles` is display/audit-only.** SSO-delivered IdP groups are never treated as authz directly — they are mapped server-side to an internal role bundle, which is then expanded to `scope` at issuance via the existing `ROLE_SCOPES` table, identically to password login. The worker-facing JWT carries no PII (no email/name/username) — see §2's new mapping subsection and §4.

## 1. Current State Findings

### hub-api (Python/Quart) — NO SSO today (confirmed)
`git grep -ilE "saml|oauth2|oidc"` across `hub_api/` (excluding tests) returns **zero hits**. Current auth surface:

| File | Role |
|---|---|
| `hub_api/api/auth_routes.py` | `auth_bp` (`/api/v1/auth`): `/login` (email+bcrypt+TOTP MFA), `/refresh-token`, `/logout`. Sets HttpOnly cookies + JSON body, double-submit CSRF, per-IP+per-account rate limiting, timing-safe dummy-hash to prevent user enumeration. |
| `hub_api/auth/service.py` | `AuthService` — bcrypt auth, `ROLE_SCOPES` (admin/maintainer/viewer → scope bundles), mints claims `{sub, iss, aud, tenant, scope, teams, roles}`, single-use rotating refresh tokens with replay-detection revoke-all. |
| `hub_api/auth/jwt.py` | Manual RS256 JWS assembly (`encode_access_token`/`decode_token`), required claims `{sub, iss, aud, tenant}`, `kid` header. Decoder makes iss/aud checks opt-in (shared across user/machine JWT types with different audiences). |
| `hub_api/crypto/keys.py` | `KeyProvider` protocol + `InAppKeyProvider` (PEM env/file/dev-gen), `AwsKmsKeyProvider`, `GcpKmsKeyProvider`. **All RSA/RS256 today** (`rsa.generate_private_key`, `padding.PKCS1v15`); `kid = sha256(public_pem)[:16]`. **Design change required** (this correction's added scope): each provider needs an EC P-256 counterpart — `cryptography`'s `ec.generate_private_key(ec.SECP256R1())` locally, `SigningAlgorithm="ECDSA_SHA_256"` for AWS KMS, `EC_SIGN_P256_SHA256` for GCP KMS. No new dependency — `cryptography` already supports EC. `AuthService`/`encode_access_token` switch their default signing alg to ES256; the RSA provider is kept configured but demoted to verify-only (see §6/§7). |
| `hub_api/api/headend_routes.py:300` | `GET /api/v1/auth/public-key` (public, unauthenticated) → `{public_key, kid, algorithm:"RS256", use:"sig", meta}`. This is the REST endpoint hub-router polls. Single-key shape — cannot represent an EC-primary + RSA-legacy set, which is exactly why the new gRPC surface (§6) must be multi-key and why hub-router must migrate onto it *before* the algorithm rekey happens. |
| `hub_api/entitlements/gate.py`, `hub_api/flags/__init__.py` | Tier resolution (`TIER_COMMUNITY/PROFESSIONAL/ENTERPRISE`, `_licensed_tier()` cached w/ graceful fallback) + `feature_enabled()` → `shared.licensing.entitlements`. Existing, reusable as-is. |

**Already a dependency**: `penguin-aaa>=0.1.0` in `hub_api/requirements.in` (installed version locally: 0.2.1), pulling in `authlib` transitively. **Not yet imported anywhere in hub_api** — this migration is the first consumer. `penguin_aaa.authn.oidc_rp.ALLOWED_RP_ALGORITHMS` and `penguin_aaa.crypto.jwks.public_key_to_jwk` **already support ES256/EC P-256 today** — no penguin-aaa changes needed for the rekey.

### hub-router (Go) — SSO handlers to be dropped
`services/hub-router/proxy/auth/`:

| File | Behavior | Problem for platform-JWT unification |
|---|---|---|
| `oauth2.go` | `NewOAuth2Provider` via `coreos/go-oidc` + `golang.org/x/oauth2`. `LoginHandler`: generates state (crypto/rand, fail-closed), sets `oauth_state` cookie, redirects to IdP. `CallbackHandler`: validates state, exchanges code, verifies `id_token` via OIDC verifier, extracts `{sub, email, name, groups}`. | Mints its **own** session JWT, **HS256**, signed with a local `sessionSigningKey` (`PROXY_SESSION_SIGNING_KEY`, ≥32 bytes, validated). Claims are `{sub, email, name, groups, exp}` — **no `tenant`, `scope`, `iss`, `aud`, `roles`**. Never touches hub-api's `users` table or `ROLE_SCOPES`. **Also the anti-pattern the new design must not repeat**: raw `groups` are embedded directly in the session JWT and `middleware/auth.go::PermissionRequired` matches them as flat authz strings — i.e. today's Go code treats IdP groups as authz directly. hub-api's replacement must map groups to role bundles server-side before any scope is derived (§2). |
| `saml2.go` | Full manual SAML2 SP: fetches IdP metadata (`etree` + `goxmldsig`), builds `AuthnRequest`, validates response signature via `dsig.ValidationContext.Validate` (XSW-safe — claims read only from the *validated* element), checks Audience/Conditions/SubjectConfirmationData/Recipient/InResponseTo, in-memory replay cache keyed by assertion ID. Solid security posture — worth preserving semantics, not code (Go dropped). | Same HS256 local-session-JWT problem as oauth2.go. |
| `provider.go` | `Provider` interface (`LoginHandler/CallbackHandler/LogoutHandler/ValidateToken/GetUser`), `validateSessionSigningKey` (≥32 bytes, must be independent of client_id/entity_id — public values). | N/A — interface shape informs Quart route/service split. |
| `jwt.go` | `JWTProvider.fetchPublicKey()`: `GET {managerURL}/api/v1/auth/public-key`, parses RSA PEM. `ValidateToken` re-fetches if `time.Since(lastKeyFetch) > 1*time.Hour` (on-demand lazy refresh, not a background ticker). | This is the REST poll to replace with gRPC. |
| `proxy/middleware/auth.go` | `AuthRequired` — TLS client-cert (handled at TLS layer) + Bearer JWT via `Provider.ValidateToken`; `PermissionRequired` does flat string-list matching (not `resource:action` scope wildcards like hub-api's `_scope_satisfied`). | Confirms hub-router should become verify-only against hub-api-shaped claims, not invent its own permission model. |

**Critical gap this design must close**: SSO logins currently produce a session token with **no tenant/scope**, disconnected from hub-api's user/role model. Moving SSO into hub-api means SSO-authenticated identities must resolve to a real hub-api user record (tenant, role→scope, teams) — i.e. **JIT provisioning or account linking**, not just claim pass-through.

## 2. New hub-api Quart Endpoints

New blueprint `hub_api/api/sso_routes.py`, `sso_bp = Blueprint("sso", __name__, url_prefix="/api/v1/auth/sso")`, registered in `app.py` alongside `auth_bp`.

| Route | Method | Tier gate | Flag |
|---|---|---|---|
| `/google/login` | GET | Professional | `hub_api.sso_google_oauth2` |
| `/google/callback` | GET | Professional | `hub_api.sso_google_oauth2` |
| `/oidc/login` | GET | Enterprise | `hub_api.sso_oidc` |
| `/oidc/callback` | GET | Enterprise | `hub_api.sso_oidc` |
| `/saml/login` | GET | Enterprise | `hub_api.sso_saml` |
| `/saml/acs` | POST | Enterprise | `hub_api.sso_saml` |
| `/saml/metadata` | GET | Enterprise | `hub_api.sso_saml` (SP metadata; public, no gate needed for metadata exposure itself but route existence still flagged off) |

Google OAuth2 and generic OIDC share one handler family (`OIDCRelyingParty`-backed, Google is just a preset issuer `https://accounts.google.com`); SAML is a second, structurally distinct family. Both terminate at the same helper:

```
async def _issue_platform_session(idp_claims: IdpClaims) -> tuple[Response, int]:
    """Resolve/JIT-provision a hub_api user from federated IdP claims, then
    mint hub-api's own ES256 access+refresh JWT pair exactly as
    AuthService.authenticate() does for password login, and set the same
    HttpOnly cookies via auth/middleware.set_auth_cookies."""
```

This reuses `AuthService._generate_access_token` / `_generate_and_store_refresh_token` / `set_auth_cookies` unmodified — SSO is just a second way to *reach* `AuthResult`, never a second JWT format, and never a second signing algorithm: post-rekey (§6/§7), both password and SSO logins sign with the same primary EC key. Claims minted: `{sub: hub_api user.id (UUID), iss, aud, tenant, scope (from ROLE_SCOPES[role bundle]), teams, roles}` — identical shape to password login, and **PII-free by construction**: no `email`/`name`/`username` field is ever added to this claim set, regardless of what the IdP callback returned. `email`/`name` from the IdP are used transiently, server-side only, to resolve-or-create the `users` row (and are stored there, inside the PII boundary, exactly like a password-registered user's email) — they never cross into the worker-facing token itself. `roles` is carried for display/audit only; every authz decision downstream resolves on `scope` alone (§4).

**JIT provisioning rule**: on first SSO login for an email not in `users`, auto-create with `tenant` resolved from a configured domain→tenant map (Enterprise SAML/OIDC deployments are typically single-tenant per IdP) or from an existing invite record — never trust a `tenant` claim asserted by the IdP itself (per security.md Tenant Isolation — tenant must come from hub-api's own resolution, not federated input). Role bundle resolution is the group-mapping step below; a user with no mapped group defaults to `viewer` (least privilege), never to an elevated default.

### Group → Role-Bundle → Scope Mapping (SSO claim assembly)

IdP-asserted groups (SAML `groups`/`memberOf` `<Attribute>` values; OIDC/Google Workspace `groups` claim or Directory API membership) are **never used as authz directly and never stored verbatim as `scope` or `roles`** — mirroring the tenant rule above: an IdP claim is untrusted input for anything security-relevant until hub-api resolves it through its own config.

1. **Per-tenant/per-IdP group→role mapping table** (new, e.g. `sso_group_role_mappings`: `tenant_id, idp_id, external_group, role_bundle`), configured by a tenant admin, not the IdP. `role_bundle` is one of the existing bundles already defined in `ROLE_SCOPES` (`admin`/`maintainer`/`viewer`) or a team-scoped bundle (Owner/Admin/Member/Viewer, per security.md's Team/OU layer) — no new bundle vocabulary invented for SSO.
2. **Resolution at login time**: intersect the IdP's asserted raw groups against this tenant's mapping table. Zero matches → `viewer` default (per JIT rule above). Multiple matches → deterministic highest-privilege-wins precedence (`admin` > `maintainer` > `viewer`), fixed in code, not caller-influenced.
3. **Expansion to scope**: the *resolved* role bundle — never the raw group string — is looked up in `ROLE_SCOPES` exactly as password login already does. This is the same `role → scope` expansion function reused unmodified; SSO only adds a *new upstream step* (group → role) feeding the *same* existing function.
4. **Raw group strings are discarded after mapping** — never written to the JWT (not even in an `ext` field), never persisted beyond the mapping-decision audit log entry (`structlog`, group names hashed/truncated if treated as sensitive per tenant policy), never returned in any API response.
5. Sensitive-claim exception: if a future IdP integration genuinely needs to carry a non-PII but sensitive attribute end-to-end (e.g. an internal compliance flag), that alone would justify nested sign-then-encrypt (JWS-in-JWE, §4) — not required for the standard group/role/scope/tenant claim set defined here.

## 3. License + Feature-Flag Gating

Per `critical-rules.md` Feature Flags & License Tiers: Google OAuth2 SSO = **Professional**; SAML 2.0 / OIDC SSO = **Enterprise**.

```python
from hub_api.entitlements.gate import require_feature, TIER_PROFESSIONAL, TIER_ENTERPRISE

@sso_bp.route("/google/login", methods=["GET"])
@require_feature("hub_api.sso_google_oauth2", min_tier=TIER_PROFESSIONAL)
async def google_login() -> tuple[Response, int]: ...

@sso_bp.route("/saml/login", methods=["GET"])
@require_feature("hub_api.sso_saml", min_tier=TIER_ENTERPRISE)
async def saml_login() -> tuple[Response, int]: ...
```

- Flags default OFF (PostHog, `hub_api.{feature}` key convention already used elsewhere in this repo).
- Resolve via existing `_licensed_tier()` (cached, graceful-degrade to last-known on license-server outage, never crash) — **reuse `hub_api/entitlements/gate.py` as-is**, do not build a parallel gate.
- Domain-bypass (`*.penguintech.cloud`, `*.penguincloud.io`) already handled by the shared license client — no new code needed here.
- `--dev` flag interaction: unlocks Professional/Enterprise SSO for single-user eval same as any other gated feature — no SSO-specific exception.

## 4. Security Requirements (mapped to existing hub-api primitives)

| Requirement | Implementation |
|---|---|
| Signing algorithm: ES256 primary, RS256 verify-only | **Added scope, applies to password login too.** `AuthService._generate_access_token`/`encode_access_token` default `alg` switches to ES256 (EC P-256) for all new issuance; RSA key retained in the exposed key set as verify-only during bake-out (§6/§7). `decode_token`'s `algorithms` allow-list becomes `["ES256", "RS256"]` during the transition window, `["ES256"]` only once the RSA key is retired. |
| Scope-based authz ONLY; `roles` is display/audit-only | Middleware (`_scope_satisfied` et al.) never branches on role names — unchanged, existing behavior. **Explicitly extended to SSO**: IdP groups are never treated as authz — they resolve to a role bundle server-side (§2 mapping subsection), which `_generate_access_token` then expands to `scope` via the existing `ROLE_SCOPES` table, identically for password and SSO logins. `roles` in the issued token reflects the resolved bundle for display/audit only; a regression test asserts a request with a tampered `roles` claim but correct `scope` still authorizes (proving no code path reads `roles` for access decisions). |
| Tenant claim mandatory; **now equally: group/role resolution is server-side only** | `encode_access_token` already rejects claims missing `tenant`; JIT-provisioning resolves tenant from domain map/invite, never from IdP assertion — the same "IdP claims are untrusted input" principle now explicitly covers group→role resolution too (§2), not just tenant. |
| Secure/HttpOnly/SameSite cookies | Reuse `auth/middleware.py::set_auth_cookies` verbatim — same cookie names/TTLs as password login. |
| PKCE for OAuth2 | `penguin_aaa.authn.oidc_rp.generate_pkce_pair()` + `build_authorization_url(code_challenge=...)` — already implemented, verifier stored server-side keyed by `state` (short-TTL cache, e.g. `hub_api.cache.client`), never in a client-readable cookie. |
| OIDC state/CSRF | `OIDCRelyingParty.generate_state()` / `.validate_state()` (constant-time `hmac.compare_digest`) — store state+nonce+pkce_verifier together, single-use, short TTL (5 min, matching hub-router's `oauth_state` cookie precedent). |
| SAML signature + audience validation | New Python implementation must replicate `saml2.go`'s validated-element-only claim extraction (XSW defense), Audience/Conditions/SubjectConfirmationData/Recipient/InResponseTo checks, and single-use replay cache — see Library Choices below; this is the one area with no existing hub-api or penguin-aaa code to reuse. |
| Worker-facing token is PII-free; sign-then-encrypt (JWS-in-JWE) only if that changes | By design (§2), the issued token never carries `email`/`name`/`username` — `sub` is the hub-api user UUID, not an identifier derived from PII. Because of that, standard `{sub,iss,aud,tenant,scope,teams,roles}` claims need no nested encryption. JWS-in-JWE (sign then encrypt, never the reverse — RFC 8725 §3.4) is reserved for a future case where a genuinely sensitive *non-PII* claim must be added — not required for this PR stack. |
| No hardcoded secrets | `client_id`/`client_secret`/SAML SP key from `penguin_sal.SecretClient`, per-tenant/per-IdP config stored encrypted in DB (existing `hub_api/crypto/secrets.py::encrypt_secret`, same helper `AuthService` already uses for TOTP secrets). |
| Response DTOs | `quart-schema` `@validate_response` on every new route — no raw claims dict ever returned to the client; only the same `{access_token, refresh_token, expires_in, token_type}` shape as `/login`. |

## 5. Library Choices (supply-chain checked)

| Need | Library | License | Advisory check | Verdict |
|---|---|---|---|---|
| OAuth2/OIDC RP (Google + generic OIDC) | **`penguin_aaa.authn.oidc_rp.OIDCRelyingParty`** (in-house, already a dependency) | MIT (penguin-aaa) | Wraps `authlib` (BSD-3, no PRC/sanctioned origin, already transitively pinned in `requirements.txt`) + `PyJWT`. No new dependency. | **Use as-is.** Already implements discovery, PKCE, state, nonce, JWKS validation. |
| SAML 2.0 SP | No penguin-aaa module exists (`grep -ril saml` on the installed package returns nothing). Candidates: `python3-saml` (OneLogin, MIT) vs `pysaml2` (Apache-2.0, IdentityPython/Sunet — Swedish university consortium). | `python3-saml`: MIT, actively maintained, thin xmlsec1-backed wrapper, smaller attack surface, no known RUSTSEC-equivalent (PyPI Advisory DB) open CVEs as of survey date. `pysaml2` has a larger, harder-to-audit surface and slower release cadence historically. | Run `pip-audit` against the pinned version before merge (gate, not skip). Neither vendor is PRC-based or sanctioned. | **Recommend `python3-saml`** — smaller surface, MIT license, avoids reinventing XML-DSig validation (which is the highest-risk part of `saml2.go` to port by hand). Confirm exact pin + hash in the PR that adds it; do not hand-roll XML-DSig parsing in Python — a from-scratch port of `saml2.go`'s etree/goxmldsig logic is exactly the kind of security-sensitive code a maintained library exists to avoid. |
| TenantMiddleware / JWTMiddleware | `penguin_aaa.middleware.asgi` (`TenantMiddleware`, `OIDCAuthMiddleware`) | MIT | N/A (in-house) | Only relevant if a future service other than hub-api needs to *verify* federated OIDC tokens directly (not applicable to hub-api's own SSO login routes, which mint hub-api's own RS256 token after federation — downstream services keep verifying that RS256 token exactly as today, via `decode_token`/gRPC-served public key, not via penguin-aaa's OIDC RP path). |
| JWKS serialization (ES256 rekey — now in scope, not deferred) | `penguin_aaa.crypto.jwks.public_key_to_jwk` | MIT | N/A | **Corrected from initial draft**: this is directly usable now, not a future nicety — it already serializes both RSA and EC (P-256/384/521) public keys to RFC 7517 JWK dicts, which is exactly what the multi-key gRPC surface (§6) needs to represent an EC-primary + RSA-legacy key set. `hub_api/crypto/keys.py`'s new EC provider (see §1) plugs directly into it; no new dependency, no new JWK-serialization code to write. |
| EC (P-256) signing key management | Extend existing `hub_api/crypto/keys.py` providers (`InAppKeyProvider`, `AwsKmsKeyProvider`, `GcpKmsKeyProvider`) | N/A (same `cryptography` package already a dependency) | `cryptography` is already pinned/audited; no new package. | Add an EC counterpart per provider (`ec.generate_private_key(ec.SECP256R1())` in-app; `ECDSA_SHA_256` AWS KMS signing algorithm; `EC_SIGN_P256_SHA256` GCP KMS algorithm) — same `sign()`/`public_pem`/`kid` protocol shape, just `alg="ES256"`. |

**No PRC/sanctioned dependencies introduced.** `authlib` (already present), `python3-saml` (OneLogin, US-based), `penguin-aaa` (in-house) — all clear.

## 6. gRPC Public-Key Surface (replaces REST poll; multi-key/JWKS-shaped)

**Correction from initial draft**: the original single-key `PublicKeyResponse` cannot represent an EC-primary + RSA-legacy key set. The gRPC surface is JWKS-style (a *set* of keys) from day one, not single-key — this is required precisely because the ES256 rekey (§1/§7) means hub-api will, for a bake-out period, have two simultaneously valid verification keys (one primary signing key, one legacy verify-only key), and any consumer must be able to select the right one per token's `kid`/`alg` header.

New proto: `proto/hubauth/v1/hubauth.proto` (module-scoped, matching existing `proto/netsvcs/v1/`, `proto/testserver/v1/` convention):

```protobuf
service HubAuthKeyService {
  rpc GetPublicKeys(GetPublicKeysRequest) returns (PublicKeySetResponse);
}
message GetPublicKeysRequest {}
message PublicKeySetResponse {
  repeated PublicKey keys = 1;
}
message PublicKey {
  string kid = 1;
  string algorithm = 2;       // "ES256" (primary) | "RS256" (legacy, verify-only)
  string public_key_pem = 3;  // SubjectPublicKeyInfo PEM
  string use = 4;             // "sig"
  bool   primary = 5;         // true only for the currently-active signing key; at most one key is primary
  int64  fetched_at_unix = 6;
}
```

- Server: `hub_api/api/grpc/hubauth_server.py`, following `hub_api/modules/netsvcs/grpc/server.py`'s existing pattern (message-size + concurrent-RPC caps, structlog, no unconditional reflection). Backed by a `KeyProviderSet` (ordered list: one primary `KeyProvider` + zero-or-more verify-only legacy providers) replacing the single `KEY_PROVIDER` app-config object `headend_routes.py` uses today — **one source of truth, two transports** during transition. `penguin_aaa.crypto.jwks.public_key_to_jwk` can additionally serialize each entry to RFC 7517 JWK format if a standard `.well-known/jwks.json` REST fallback is ever wanted for external tooling (optional, not required for hub-router).
- Client (Go, `services/hub-router`): replace `jwt.go`'s `fetchPublicKey()` HTTP GET with a gRPC unary call to `GetPublicKeys`, select the key by `kid` from the token's header (falling back to the `primary`-flagged key when minting is irrelevant, i.e. verification only ever needs `kid` lookup) — using the intra-cluster gRPC channel already established for other hub-router↔hub-api calls (per `grpc-rest-transport-boundary` convention: gRPC intra-cluster, REST external). Keep the same lazy-refresh-on->1h-staleness trigger logic — only the transport and multi-key handling change, not the caching cadence.
- Client (Rust, `node-agent`): same gRPC call via `tonic`, once node-agent needs it (currently node-agent is REST/JWT-verify-only per its own aaa migration — this gRPC method should be exposed for it from day one even if node-agent doesn't consume it in this PR stack). `penguin-aaa` (Rust) and hub-api verification already accept the EC family, per the correction — no algorithm-support gap on the Rust side.
- REST `GET /api/v1/auth/public-key` (`headend_routes.py:300`) stays **during transition** as a single-key, backward-compatible view (returns whichever key is currently `primary`) for any consumer not yet migrated — but **must not be relied on once the RSA→EC rekey happens**, since a single-key shape cannot expose the legacy RS256 verify-only key alongside the new ES256 primary. This is the hard ordering constraint in §7: hub-router must be off REST and onto the multi-key gRPC surface *before* the rekey lands, or its in-flight RS256-verified tokens would have no way to resolve their key once REST starts reporting only the new EC key.

## 7. Cutover Plan (hub-router keeps working throughout)

**Hard ordering constraint (added by this correction)**: the ES256 rekey (step 3 below) MUST NOT happen until hub-router is confirmed off the single-key REST endpoint and onto the multi-key gRPC surface (step 2). A single-key REST response cannot expose both the new EC primary and the legacy RSA verify-only key simultaneously, so rekeying before that migration would strand any consumer still on REST.

1. **PR-1**: Land gRPC `GetPublicKeys` (multi-key/JWKS-shaped, §6) in hub-api, dual-served alongside the existing single-key REST endpoint. Initially returns just the one existing RSA key (`primary=true`, `algorithm="RS256"`) wrapped in the new list shape — zero algorithm change yet, purely a schema/transport addition.
2. **PR-2**: Update hub-router's `jwt.go` to call `GetPublicKeys` instead of the REST poll, select by `kid`, tolerate a multi-entry response (same lazy-refresh-on->1h-staleness trigger). Verify hub-router still validates hub-api-issued user/machine JWTs identically. This is a pure transport/schema swap — no new auth semantics, nothing to debug alongside an algorithm change.
3. **PR-3 (algorithm rekey — new step, this correction's added scope)**: Add EC P-256 support to `hub_api/crypto/keys.py`'s providers; switch `AuthService`/`encode_access_token` to sign new tokens with ES256 by default — **for password login AND SSO alike**, since both share this one issuance path. The existing RSA key stays configured, now served with `primary=false` (verify-only) in the gRPC key set. `decode_token`'s accepted-algorithms allow-list becomes `["ES256", "RS256"]` for the bake-out window.
4. **Bake-out window**: hold the RSA key in the key set as verify-only for at least the max configured access-token TTL (`jwt_expiration_hours`, ≤24h per JWT Claims policy) past the last RS256-signed token, then retire it from the key set entirely (small follow-up PR-3b, not blocking anything below).
5. **PR-4**: Land hub-api `sso_routes.py` + `OIDCRelyingParty`-backed Google/OIDC handlers, flags **OFF** by default, Professional/Enterprise gated. Built directly against ES256 issuance from the start (no separate SSO-specific algorithm decision, since PR-3 already landed) — additive only, does not touch hub-router.
6. **PR-5**: Land hub-api SAML SP (`python3-saml`-backed), flag OFF, Enterprise gated.
7. **PR-6**: JIT-provisioning + domain→tenant resolution + group→role-bundle→scope mapping (§2) + regression tests proving SSO-issued tokens carry identical claim shape to password-issued tokens (and are PII-free, and authorize on `scope` alone).
8. **Flip flags ON in a lower environment (alpha/beta)**, validate end-to-end against a real IdP (Google Workspace test tenant + a SAML test IdP e.g. `samltest.id`), confirm hub-router's gRPC-based JWT verification accepts hub-api-minted ES256 SSO tokens with no hub-router changes required (this is the point that proves the unification — hub-router needs zero awareness of SSO vs password, or of ES256 vs the retired RS256).
9. **PR-7 (hub-router)**: Delete `services/hub-router/proxy/auth/oauth2.go`, `saml2.go`, their `_test.go` files, and the `Provider` interface's login/callback methods (keep `ValidateToken`/`GetUser` — verify-only) — **not ported to Rust**, dropped outright. Update `proxy/middleware/auth.go` callers accordingly.
10. **PR-8 (cleanup)**: Remove the REST `/api/v1/auth/public-key` poll path once confirmed unused (grep all consumers first — this is cross-repo, check `agents/node-agent` too).

Ordering rationale: gRPC multi-key surface lands and is validated *before either* the algorithm rekey *or* any SSO code exists, so each subsequent step is a single, isolated variable to debug — transport swap (PR-2), then algorithm swap (PR-3), then new auth-method surface (PR-4+) — never more than one of those three changing at once. SSO lands fully flagged-off so it carries zero blast radius until explicitly enabled per-tenant, and lands already ES256-native so there's no second issuance-algorithm migration for it later.

## 8. Suggested PR Stack (smallest-first, each independently mergeable/revertable)

| # | PR | Scope | Depends on |
|---|---|---|---|
| 1 | `feat(hub-api): gRPC GetPublicKeys (multi-key/JWKS) alongside REST` | proto + server, dual-serve, single RSA key wrapped in new list shape | none |
| 2 | `feat(hub-router): consume gRPC GetPublicKeys, drop REST poll` | Go client swap, `kid`-based key selection | 1 |
| 3 | `feat(hub-api): EC P-256 KeyProvider + rekey AuthService issuance to ES256` | password login AND SSO issuance path both affected; RSA key demoted to verify-only in the key set; `decode_token` allow-list `["ES256","RS256"]` during bake-out | 2 (hub-router must be off REST first) |
| 3b | `chore(hub-api): retire RSA verify-only key from key set` | after bake-out window (§7) elapses | 3 |
| 4 | `feat(hub-api): OIDCRelyingParty-backed Google OAuth2 login/callback` | flag OFF, Professional-gated, ES256-native | 3 |
| 5 | `feat(hub-api): generic OIDC login/callback` | flag OFF, Enterprise-gated, shares helper from #4 | 4 |
| 6 | `feat(hub-api): SAML 2.0 SP (python3-saml)` | flag OFF, Enterprise-gated | 3 (parallel to 4/5) |
| 7 | `feat(hub-api): JIT user provisioning + domain-tenant resolution + group→role-bundle→scope mapping for federated logins` | shared by 4/5/6 | 4, 6 |
| 8 | `test: SSO claim-shape parity + PII-free-token + scope-only-authz + security regression suite` | ≥90% coverage on new code | 4–7 |
| 9 | `chore(hub-router): drop Go SSO handlers` | delete oauth2.go/saml2.go + tests | flags validated ON in alpha/beta |
| 10 | `chore(hub-api): remove REST public-key poll endpoint` | after all consumers confirmed migrated | 2, 9 |

## 9. Test Plan

**Unit** (`hub_api/tests/test_sso_*.py`):
- OIDC/Google: state/nonce/PKCE round-trip, expired/reused state rejected, `validate_token` rejects wrong-audience/expired/malformed tokens (reuse `OIDCRelyingParty` test doubles — mock `httpx` discovery).
- SAML: signature validation (valid + tampered), XSW attack fixture (signed assertion wrapped in unsigned outer response — must reject), replay of same assertion ID rejected, Audience/Recipient/InResponseTo mismatch rejected, expired Conditions rejected — mirror `saml2_test.go`'s existing Go test fixtures as the reference threat model, ported to Python fixtures.
- JIT provisioning: new-email creates viewer-role user in resolved tenant; existing-email account-links without privilege escalation; unresolvable domain → 403, no silent tenant fallback.
- Feature-flag gating: flag OFF → 404/403 regardless of tier; flag ON + tier below requirement → 403; flag ON + tier met → 200. Domain-bypass path exercised explicitly.
- Claim-shape parity regression: SSO-issued token decodes to the exact same claim key set as a password-issued token for an equivalent role (`gh-<issue>` once filed).
- **Algorithm (added by this correction)**: post-rekey, `AuthService._generate_access_token` produces `alg=ES256` in the JWT header for BOTH password and SSO login; `decode_token` accepts `ES256` (primary) and `RS256` (legacy, bake-out only) and rejects any other alg — an alg-confusion regression test (unsigned/`none`/HS256-with-public-key-as-secret) must fail closed, mirroring the ES256 pinning already done in `testserver-rs`/`license-server`.
- **Scope-only authz / PII-free token (added by this correction)**: exact-key-set assertion that the issued token never contains `email`, `name`, or `username` (not a substring check — an explicit allow-listed key set); a request carrying a forged/mismatched `roles` claim but a correct `scope` claim still authorizes (proves `roles` is never read for access decisions); group→role mapping unit tests — unmapped group → `viewer` default, multiple mapped groups → highest-privilege-wins, and a malicious/unrecognized group string never appears in the issued `scope` claim.

**Integration**:
- Full redirect→callback flow against a stub IdP (OIDC: local discovery doc + JWKS; SAML: `samltest.id` or an in-repo fixture IdP) issuing tokens that `_issue_platform_session` must convert into a valid hub-api RS256 access/refresh pair with cookies set.
- gRPC `GetPublicKey` — same key material as REST endpoint, hub-router test client validates a hub-api-minted token end-to-end via the gRPC-fetched key.
- Cross-repo: hub-router's Go test suite (`oauth2_test.go`/`saml2_test.go` equivalents deleted in PR-8) replaced by a hub-router integration test that only exercises `ValidateToken` against hub-api-minted SSO tokens — proving hub-router needs no SSO-awareness post-cutover.

**Coverage**: ≥90% lines/branches on all new `hub_api/api/sso_routes.py`, SAML SP module, JIT-provisioning module — gate in CI, not `|| true`.

**OTel**: every new route emits structured logs (`sso_login_attempt`, `sso_login_success`, `sso_login_failed`, `saml_replay_detected`, etc., masked email per existing `_mask_email` convention) + histogram metric for login latency + span for the IdP token-exchange/JWKS-fetch call — smoke test asserts ≥1 log record, ≥1 metric data point, ≥1 span (external-call span), per `testing.md` Telemetry Validation.

---

**Confirmed finding**: hub-api has zero SSO code today (`git grep -ilE "saml|oauth2|oidc" hub_api/` outside tests = 0 hits); all SSO logic lives in `services/hub-router/proxy/auth/{oauth2,saml2}.go` and mints a disconnected HS256 session JWT with no tenant/scope — the core problem this design fixes is that SSO must become a second path *into* `AuthService`'s existing issuance (rekeyed to ES256-primary/RS256-legacy-verify-only as part of this same effort, for password login and SSO alike), not a parallel token format and not a parallel authz model — IdP groups map to role bundles server-side before any scope is derived, and the resulting worker-facing token carries no PII.
