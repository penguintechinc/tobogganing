//! Inbound JWT verification for hub-router — the control-plane side that
//! verifies the `Authorization` bearer token on requests arriving AT
//! hub-router. This is the first real control-plane increment of the
//! Go→Rust hub-router port (`services/hub-router/proxy/auth/jwt.go`'s
//! `JWTProvider`), and is independent of this crate's root module (the
//! OUTBOUND machine-JWT client hub-router itself holds when calling OUT to
//! hub-api — see the crate root doc).
//!
//! Signature verification delegates to the shared
//! [`penguin_aaa::Es256Verifier`] (EC family — ES256/ES384/ES512/EdDSA —
//! plus RS256 as a verify-only legacy backup, hand-rolled JWS framing, zero
//! `rsa`-crate dependency) exactly as `engines/testserver-rs`'s
//! `testserver_core::JwtVerifier` does; see that module's doc for the full
//! algorithm-policy rationale (RUSTSEC-2023-0071 / Marvin Attack never
//! reaches this workspace — verify with `cargo tree | grep rsa`). On top
//! of verification this module adds hub-router's own authz policy: tenant
//! presence is checked first (tenant isolation runs before any scope
//! check — security.md Tenant Isolation), and the resulting [`AuthUser`]
//! (never raw claims) is handed to the caller for a per-route
//! [`require_scope`] check — authz decisions are scope-only, `roles` is
//! audit/display only (security.md OIDC Claims & Scopes).

use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;
use std::sync::{Arc, RwLock};
use std::time::Duration;

/// Sanitized, request-scoped identity extracted from a verified inbound
/// JWT — never the raw claims (security.md Output Validation: derived
/// request state is always an explicit DTO, not a passthrough of the
/// underlying token).
#[derive(Debug, Clone)]
pub struct AuthUser {
    pub id: String,
    pub tenant: String,
    /// Space-delimited `resource:action` scope string — the only field
    /// [`require_scope`] consults.
    pub scope: String,
    /// Audit/display only — never consulted for an authz decision.
    pub roles: Vec<String>,
}

/// Request-level failure for the inbound auth path — every variant maps
/// directly to an HTTP response via [`IntoResponse`]. Distinct from
/// [`crate::Error`] (`hub_router_common::Error`), which covers
/// startup/runtime failures of the outbound machine-JWT client, not
/// per-request outcomes.
#[derive(Debug, thiserror::Error)]
pub enum ApiError {
    #[error("missing or malformed Authorization header")]
    Unauthorized,
    #[error("invalid credentials")]
    InvalidCredentials,
    /// Covers both "tenant claim missing" and "insufficient scope" —
    /// collapsed to one opaque response so a caller can't distinguish
    /// which authz check failed (mirrors [`ApiError::InvalidCredentials`]
    /// never revealing which verification step failed).
    #[error("forbidden")]
    Forbidden,
    /// The public-key cache has no cached verifier yet (first fetch never
    /// succeeded) — a 503, not a 401/403: the caller's credentials were
    /// never evaluated at all.
    #[error("auth key material unavailable")]
    KeyUnavailable,
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let (status, message) = match &self {
            ApiError::Unauthorized => (StatusCode::UNAUTHORIZED, "unauthorized"),
            ApiError::InvalidCredentials => (StatusCode::UNAUTHORIZED, "invalid credentials"),
            ApiError::Forbidden => (StatusCode::FORBIDDEN, "forbidden"),
            ApiError::KeyUnavailable => (
                StatusCode::SERVICE_UNAVAILABLE,
                "auth key material unavailable",
            ),
        };
        (status, Json(json!({"error": message}))).into_response()
    }
}

/// Failure fetching/parsing hub-api's public key — always a fetch-time
/// failure (network error, bad status, malformed body, invalid key
/// material), never a per-request outcome; compare [`ApiError`].
#[derive(Debug, thiserror::Error)]
pub enum KeyFetchError {
    #[error("building http client: {0}")]
    ClientInit(reqwest::Error),
    #[error("requesting public key from {0}: {1}")]
    Request(String, reqwest::Error),
    #[error("hub-api returned status {0} fetching public key")]
    Status(u16),
    #[error("parsing public key response: {0}")]
    Decode(reqwest::Error),
    #[error("invalid public key material: {0}")]
    InvalidKey(#[from] penguin_aaa::AaaError),
}

/// Response shape of hub-api's `GET /api/v1/auth/public-key`
/// (`hub_api/api/headend_routes.py::get_auth_public_key`): only
/// `public_key` is consumed here — `kid`/`algorithm`/`use`/`meta` are
/// ignored, since `penguin_aaa::Es256Verifier` derives the accepted
/// algorithm from the key material itself, never from a server-supplied
/// label (the same alg-confusion-closing design as the verifier's `alg`
/// check at verify time).
#[derive(Debug, serde::Deserialize)]
struct PublicKeyResponse {
    public_key: String,
}

/// Default refresh interval — one hour, matching the Go headend's
/// `JWTProvider.ValidateToken`'s `1 * time.Hour` staleness window
/// (`services/hub-router/proxy/auth/jwt.go`).
pub const DEFAULT_REFRESH_INTERVAL: Duration = Duration::from_secs(3600);

/// Caches hub-api's current JWT verification public key, refreshed
/// periodically in the background via [`PublicKeyCache::spawn_refresh_loop`].
///
/// // TODO(migration): switch to gRPC GetPublicKeys when hub-api SSO PR-1
/// // lands — the settled architecture is worker<->hub-api gRPC; this REST
/// // call against hub-api's `/api/v1/auth/public-key` (the same endpoint
/// // the Go headend's `JWTProvider.fetchPublicKey` already used) is the
/// // transitional step while that gRPC surface doesn't exist yet.
///
/// A fetch failure never clears the cache — the last-known-good verifier
/// stays in use (graceful degradation: key server unreachable → cached
/// value, never a crash) until a refresh succeeds again. Only an empty
/// cache (no successful fetch has *ever* completed) causes inbound
/// requests to be rejected, with [`ApiError::KeyUnavailable`] rather than a
/// panic.
pub struct PublicKeyCache {
    hub_api_url: String,
    http_client: reqwest::Client,
    verifier: RwLock<Option<Arc<penguin_aaa::Es256Verifier>>>,
}

impl std::fmt::Debug for PublicKeyCache {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PublicKeyCache")
            .field("hub_api_url", &self.hub_api_url)
            .finish_non_exhaustive()
    }
}

impl PublicKeyCache {
    /// Builds an (initially empty) cache pointed at `hub_api_url` — no
    /// network call happens until [`PublicKeyCache::refresh`] or
    /// [`PublicKeyCache::spawn_refresh_loop`] runs.
    pub fn new(hub_api_url: impl Into<String>) -> Result<Self, KeyFetchError> {
        let http_client = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .map_err(KeyFetchError::ClientInit)?;
        Ok(Self {
            hub_api_url: hub_api_url.into(),
            http_client,
            verifier: RwLock::new(None),
        })
    }

    /// Fetches hub-api's current public key and, on success, replaces the
    /// cached verifier. On failure the previous cached verifier (if any)
    /// is left untouched — see struct docs on graceful degradation.
    pub async fn refresh(&self) -> Result<(), KeyFetchError> {
        let url = format!("{}/api/v1/auth/public-key", self.hub_api_url);

        let response = self
            .http_client
            .get(&url)
            .send()
            .await
            .map_err(|e| KeyFetchError::Request(url.clone(), e))?;

        if !response.status().is_success() {
            return Err(KeyFetchError::Status(response.status().as_u16()));
        }

        let body: PublicKeyResponse = response.json().await.map_err(KeyFetchError::Decode)?;
        let verifier = penguin_aaa::Es256Verifier::from_public_key_pem(body.public_key.as_bytes())?;

        let mut guard = self
            .verifier
            .write()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        *guard = Some(Arc::new(verifier));
        Ok(())
    }

    /// The current cached verifier, if any successful fetch has ever
    /// completed. Never blocks across an `.await` point (the lock is held
    /// only long enough to clone the `Arc`).
    pub fn current(&self) -> Option<Arc<penguin_aaa::Es256Verifier>> {
        self.verifier
            .read()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .clone()
    }

    /// Seeds the cache with an already-built verifier, bypassing the
    /// network fetch entirely — for a *different* crate's tests only
    /// (e.g. `hub-router`'s own middleware/route integration tests, which
    /// can't reach this module's private `verifier` field directly). Only
    /// compiled in with the `test-util` feature, which production builds
    /// never enable.
    #[cfg(feature = "test-util")]
    pub fn inject_for_test(&self, verifier: penguin_aaa::Es256Verifier) {
        *self
            .verifier
            .write()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(Arc::new(verifier));
    }

    /// Spawns a background task that calls [`PublicKeyCache::refresh`]
    /// immediately, then every `interval` thereafter — this single loop
    /// covers both the startup fetch and the periodic (default hourly)
    /// refresh the Go headend performed lazily on each `ValidateToken`
    /// call. Never exits and never panics: a failed refresh is logged at
    /// WARN and the loop continues with whatever verifier (or lack of one)
    /// was already cached.
    pub fn spawn_refresh_loop(self: Arc<Self>, interval: Duration) -> tokio::task::JoinHandle<()> {
        tokio::spawn(async move {
            loop {
                match self.refresh().await {
                    Ok(()) => tracing::info!("refreshed hub-api JWT public key"),
                    Err(error) => tracing::warn!(
                        %error,
                        "failed to refresh hub-api JWT public key — using cached key if available"
                    ),
                }
                tokio::time::sleep(interval).await;
            }
        })
    }
}

/// Verifies `token` against `cache`'s current public key and enforces
/// tenant isolation (security.md: tenant middleware/check runs first,
/// before any scope check) before returning the sanitized [`AuthUser`].
/// Every verification failure (bad/wrong-algorithm signature, expired,
/// malformed, missing required claim) collapses to
/// [`ApiError::InvalidCredentials`] — never leaking which check failed to
/// the caller (only to the sanitized debug/warn log).
pub fn verify_inbound(cache: &PublicKeyCache, token: &str) -> Result<AuthUser, ApiError> {
    let verifier = cache.current().ok_or(ApiError::KeyUnavailable)?;

    let claims = verifier.verify(token).map_err(|error| {
        tracing::debug!(%error, "inbound jwt verification failed");
        ApiError::InvalidCredentials
    })?;

    let tenant = claims.tenant.ok_or_else(|| {
        tracing::warn!(sub = %claims.sub, "rejected inbound token: missing tenant claim");
        ApiError::Forbidden
    })?;

    Ok(AuthUser {
        id: claims.sub,
        tenant,
        scope: claims.scope,
        roles: claims.roles,
    })
}

/// Checks `user`'s scope for `required` (`resource:action`, exact match on
/// one whitespace-delimited entry of `user.scope`). Authz decisions are
/// scope-only per security.md OIDC Claims & Scopes — `user.roles` is never
/// consulted here.
pub fn require_scope(user: &AuthUser, required: &str) -> Result<(), ApiError> {
    if user.scope.split_whitespace().any(|s| s == required) {
        Ok(())
    } else {
        tracing::warn!(
            sub = %user.id,
            tenant = %user.tenant,
            required,
            "rejected inbound request: insufficient scope"
        );
        Err(ApiError::Forbidden)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use hmac::{Hmac, Mac};
    use p256::ecdsa::{SigningKey, VerifyingKey};
    use p256::pkcs8::{EncodePrivateKey, EncodePublicKey, LineEnding};
    use penguin_aaa::{Claims, Es256Signer};
    use sha2::Sha256;
    use wiremock::matchers::{method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    /// Generates a fresh, throwaway EC P-256 keypair as PKCS#8/SPKI PEM —
    /// generated at test time, never a fixed/committed key (mirrors
    /// `engines/testserver-rs`'s identical helper).
    fn generate_test_keypair() -> (String, String) {
        let signing_key = SigningKey::random(&mut rand_core::OsRng);
        let private_pem = signing_key
            .to_pkcs8_pem(LineEnding::LF)
            .expect("encoding a freshly generated P-256 key as PKCS#8 PEM must succeed")
            .to_string();
        let public_pem = VerifyingKey::from(&signing_key)
            .to_public_key_pem(LineEnding::LF)
            .expect("encoding the matching public key as SPKI PEM must succeed");
        (private_pem, public_pem)
    }

    fn now() -> i64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system clock is after the Unix epoch")
            .as_secs() as i64
    }

    fn build_claims(sub: &str, tenant: Option<&str>, scope: &str, exp: i64) -> Claims {
        Claims {
            sub: sub.to_string(),
            iss: "hub-api-test".to_string(),
            aud: "hub-router".to_string(),
            iat: now(),
            exp,
            scope: scope.to_string(),
            tenant: tenant.map(str::to_string),
            teams: Vec::new(),
            roles: vec!["viewer".to_string()],
        }
    }

    fn sign_valid(private_pem: &str, claims: &Claims) -> String {
        Es256Signer::from_ec_pem(private_pem.as_bytes())
            .expect("a freshly generated EC PEM must load as a signing key")
            .sign(claims)
            .expect("signing a well-formed claim set must succeed")
    }

    /// Builds a cache with `verifier` already populated, bypassing any
    /// network fetch — valid because this `tests` module is a descendant
    /// of `inbound`, so it may touch the private `verifier` field
    /// directly.
    fn cache_with_verifier(verifier: penguin_aaa::Es256Verifier) -> PublicKeyCache {
        let cache = PublicKeyCache::new("http://unused.invalid")
            .expect("building a client with no special TLS/proxy config must succeed");
        *cache
            .verifier
            .write()
            .expect("freshly constructed lock is never poisoned") = Some(Arc::new(verifier));
        cache
    }

    #[test]
    fn verify_inbound_accepts_valid_token_with_tenant() {
        let (private_pem, public_pem) = generate_test_keypair();
        let cache = cache_with_verifier(
            penguin_aaa::Es256Verifier::from_public_key_pem(public_pem.as_bytes())
                .expect("a freshly generated EC public key must build a verifier"),
        );
        let claims = build_claims(
            "node-1",
            Some("acme"),
            "router:read router:write",
            now() + 3600,
        );
        let token = sign_valid(&private_pem, &claims);

        let user = verify_inbound(&cache, &token).expect("valid token with tenant must verify");
        assert_eq!(user.id, "node-1");
        assert_eq!(user.tenant, "acme");
        assert!(require_scope(&user, "router:read").is_ok());
    }

    #[test]
    fn verify_inbound_rejects_missing_tenant_as_forbidden() {
        let (private_pem, public_pem) = generate_test_keypair();
        let cache = cache_with_verifier(
            penguin_aaa::Es256Verifier::from_public_key_pem(public_pem.as_bytes())
                .expect("a freshly generated EC public key must build a verifier"),
        );
        // No tenant claim — structurally valid signature/claims, tenant
        // isolation must still reject it before any scope check runs.
        let claims = build_claims("node-1", None, "router:read", now() + 3600);
        let token = sign_valid(&private_pem, &claims);

        let err = verify_inbound(&cache, &token).expect_err("missing tenant must be rejected");
        assert!(matches!(err, ApiError::Forbidden));
    }

    #[test]
    fn require_scope_rejects_insufficient_scope_as_forbidden() {
        let user = AuthUser {
            id: "node-1".to_string(),
            tenant: "acme".to_string(),
            scope: "router:read".to_string(),
            roles: vec!["viewer".to_string()],
        };
        let err = require_scope(&user, "router:write").expect_err("missing scope must be rejected");
        assert!(matches!(err, ApiError::Forbidden));
    }

    #[test]
    fn verify_inbound_rejects_when_key_unavailable() {
        let cache = PublicKeyCache::new("http://unused.invalid")
            .expect("building a client with no special TLS/proxy config must succeed");
        let err = verify_inbound(&cache, "whatever.token.here")
            .expect_err("an empty cache must reject every token");
        assert!(matches!(err, ApiError::KeyUnavailable));
    }

    /// Alg-confusion guard: a token signed HS256 using the verifier's own
    /// ES256 *public* key bytes as the HMAC secret must be rejected —
    /// `Es256Verifier` has no HS256 code path at all (mirrors
    /// `engines/testserver-rs`'s identical regression test).
    #[test]
    fn verify_inbound_rejects_hs256_alg_confusion_token() {
        let (_, public_pem) = generate_test_keypair();
        let cache = cache_with_verifier(
            penguin_aaa::Es256Verifier::from_public_key_pem(public_pem.as_bytes())
                .expect("a freshly generated EC public key must build a verifier"),
        );

        let header = r#"{"alg":"HS256","typ":"JWT"}"#;
        let payload = format!(
            r#"{{"sub":"attacker","iss":"x","aud":"y","iat":{},"exp":{},"scope":"admin:*","tenant":"acme"}}"#,
            now(),
            now() + 3600
        );
        let signing_input = format!(
            "{}.{}",
            b64url(header.as_bytes()),
            b64url(payload.as_bytes())
        );
        let mut mac = <Hmac<Sha256> as Mac>::new_from_slice(public_pem.as_bytes())
            .expect("HMAC-SHA256 accepts a key of any length");
        mac.update(signing_input.as_bytes());
        let tag = mac.finalize().into_bytes();
        let forged = format!("{signing_input}.{}", b64url(&tag));

        let err = verify_inbound(&cache, &forged).expect_err("HS256 token must be rejected");
        assert!(matches!(err, ApiError::InvalidCredentials));
    }

    /// Alg-confusion guard: a token declaring `alg: none` with no signature
    /// segment must be rejected before any signature parsing is attempted.
    #[test]
    fn verify_inbound_rejects_alg_none_token() {
        let (_, public_pem) = generate_test_keypair();
        let cache = cache_with_verifier(
            penguin_aaa::Es256Verifier::from_public_key_pem(public_pem.as_bytes())
                .expect("a freshly generated EC public key must build a verifier"),
        );

        let header = b64url(br#"{"alg":"none","typ":"JWT"}"#);
        let payload = b64url(
            format!(
                r#"{{"sub":"attacker","iss":"x","aud":"y","iat":{},"exp":{},"scope":"admin:*","tenant":"acme"}}"#,
                now(),
                now() + 3600
            )
            .as_bytes(),
        );
        let forged = format!("{header}.{payload}.");

        let err = verify_inbound(&cache, &forged).expect_err("alg:none token must be rejected");
        assert!(matches!(err, ApiError::InvalidCredentials));
    }

    /// Proves [`PublicKeyCache::refresh`]'s graceful-degradation contract
    /// end-to-end over real HTTP: a successful fetch populates the cache;
    /// a subsequent failed fetch (connection refused) leaves the
    /// previously cached verifier untouched rather than clearing it.
    #[tokio::test]
    async fn refresh_falls_back_to_cached_key_when_endpoint_unreachable() {
        let (_, public_pem) = generate_test_keypair();
        let mock_server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/api/v1/auth/public-key"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "public_key": public_pem,
                "kid": "test-kid",
                "algorithm": "ES256",
            })))
            .mount(&mock_server)
            .await;

        let cache = PublicKeyCache::new(mock_server.uri())
            .expect("building a client with no special TLS/proxy config must succeed");
        cache
            .refresh()
            .await
            .expect("initial fetch against a healthy mock server must succeed");
        let first = cache
            .current()
            .expect("cache must be populated after a successful refresh");

        // Point at an address nothing is listening on — refresh must fail
        // without touching the cached verifier.
        let unreachable = PublicKeyCache::new("http://127.0.0.1:1")
            .expect("building a client with no special TLS/proxy config must succeed");
        *unreachable
            .verifier
            .write()
            .expect("freshly constructed lock is never poisoned") = Some(first.clone());
        let result = unreachable.refresh().await;
        assert!(
            result.is_err(),
            "fetch against an unreachable endpoint must fail"
        );

        let still_cached = unreachable
            .current()
            .expect("a failed refresh must never clear a previously cached verifier");
        assert!(
            Arc::ptr_eq(&first, &still_cached),
            "cached verifier must be the exact same instance after a failed refresh"
        );
    }

    /// Minimal unpadded base64url encoder for the hand-forged tokens above
    /// — deliberately hand-rolled instead of pulling in a `base64`
    /// dependency just to construct a few malformed/forged test tokens
    /// (mirrors `engines/testserver-rs`'s identical helper).
    fn b64url(input: &[u8]) -> String {
        const ALPHABET: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
        let mut out = String::new();
        for chunk in input.chunks(3) {
            let b0 = chunk[0];
            let b1 = chunk.get(1).copied().unwrap_or(0);
            let b2 = chunk.get(2).copied().unwrap_or(0);
            let n = ((b0 as u32) << 16) | ((b1 as u32) << 8) | (b2 as u32);
            out.push(ALPHABET[((n >> 18) & 0x3F) as usize] as char);
            out.push(ALPHABET[((n >> 12) & 0x3F) as usize] as char);
            if chunk.len() > 1 {
                out.push(ALPHABET[((n >> 6) & 0x3F) as usize] as char);
            }
            if chunk.len() > 2 {
                out.push(ALPHABET[(n & 0x3F) as usize] as char);
            }
        }
        out
    }
}
