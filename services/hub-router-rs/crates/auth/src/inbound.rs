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
//!
//! ## Key fetch: gRPC `GetPublicKeys`, multi-key/`kid`-selected (SSO PR-2)
//!
//! [`PublicKeyCache`] fetches hub-api's current JWT verification key
//! *set* (JWKS-shaped, not a single key — see
//! `proto/hubauth/v1/hubauth.proto`) over gRPC, replacing the earlier
//! REST `GET /api/v1/auth/public-key` poll. This is what lets a later
//! rekey (ES256-primary + RS256-legacy-verify-only, bake-out window) land
//! without hub-router needing a second transport/schema migration: the
//! wire shape already supports several simultaneously-valid keys. Each
//! returned key builds its own [`penguin_aaa::Es256Verifier`] (that crate
//! verifies against exactly one key at a time; there is no bundled
//! multi-key/JWKS type to hand it — see the PR description's
//! `penguin-aaa` v0.2 note), cached by `kid` in [`KeySet`].
//!
//! [`verify_inbound`] selects which cached verifier(s) to try from the
//! token's own (unverified) JWS header `kid` field, via [`peek_kid`] — a
//! plain base64url+JSON decode, never itself a trust decision; the
//! decoded claims are only accepted once `Es256Verifier::verify` has
//! cryptographically checked the signature. An exact `kid` match tries
//! only that one key; no `kid` (or no match — e.g. a stale cache during
//! key rotation) falls back to trying the primary key first, then every
//! other key in the set, so a token never fails to verify merely because
//! `kid` selection missed.

use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;
use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use std::time::Duration;

use crate::pb::hub_auth_key_service_client::HubAuthKeyServiceClient;
use crate::pb::GetPublicKeysRequest;

/// `api_version` stamped on every `GetPublicKeysRequest` — this crate only
/// speaks `"v1"` today (backend.md API Versioning's runtime-routing rule).
const API_VERSION: &str = "v1";

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

/// Failure fetching/parsing hub-api's public key set over gRPC — always a
/// fetch-time failure (channel/transport error, RPC status, an
/// unusable/empty response), never a per-request outcome; compare
/// [`ApiError`].
#[derive(Debug, thiserror::Error)]
pub enum KeyFetchError {
    #[error("invalid hub-api gRPC endpoint {0}: {1}")]
    InvalidEndpoint(String, tonic::transport::Error),
    #[error("GetPublicKeys RPC failed: {0}")]
    Rpc(#[from] tonic::Status),
    #[error("hub-api's GetPublicKeys response carried no keys")]
    EmptyKeySet,
    #[error("hub-api's GetPublicKeys response carried no key this crate can parse")]
    NoUsableKeys,
}

/// Default refresh interval — one hour, matching the Go headend's
/// `JWTProvider.ValidateToken`'s `1 * time.Hour` staleness window
/// (`services/hub-router/proxy/auth/jwt.go`); the transport changed
/// (REST poll → gRPC `GetPublicKeys`, SSO PR-2) but the cadence didn't.
pub const DEFAULT_REFRESH_INTERVAL: Duration = Duration::from_secs(3600);

/// Per-RPC timeout (connect + request) for the `GetPublicKeys` call —
/// without one, `tonic`'s default `Channel` has no deadline at all and a
/// hung dial/call would block the refresh loop indefinitely (mirrors
/// `node-agent-transport::GrpcClient`'s identical bound).
const GRPC_REQUEST_TIMEOUT: Duration = Duration::from_secs(10);

/// One verified JWT verification key, keyed by the `kid` hub-api assigned
/// it, plus whether it was the response's `primary` (currently-active
/// signing) key.
struct KeySet {
    /// Every usable key from the most recent successful fetch, by `kid`.
    by_kid: HashMap<String, Arc<penguin_aaa::Es256Verifier>>,
    /// Fallback try-order for a token with no `kid` (or a `kid` this
    /// cache doesn't recognize, e.g. a stale cache mid-rotation): the
    /// `primary` key first (if any was flagged), then every other key in
    /// the order hub-api returned them.
    ordered: Vec<Arc<penguin_aaa::Es256Verifier>>,
}

impl KeySet {
    fn empty() -> Self {
        Self {
            by_kid: HashMap::new(),
            ordered: Vec::new(),
        }
    }

    fn is_empty(&self) -> bool {
        self.ordered.is_empty()
    }

    /// Candidate verifiers to try, in order, for a token whose (unverified)
    /// header `kid` is `kid` — see module doc for the selection policy.
    fn candidates(&self, kid: Option<&str>) -> Vec<Arc<penguin_aaa::Es256Verifier>> {
        if let Some(verifier) = kid.and_then(|kid| self.by_kid.get(kid)) {
            return vec![verifier.clone()];
        }
        self.ordered.clone()
    }
}

/// Caches hub-api's current JWT verification public key *set*, refreshed
/// periodically in the background via [`PublicKeyCache::spawn_refresh_loop`].
/// Fetched over gRPC (`HubAuthKeyService.GetPublicKeys`,
/// `proto/hubauth/v1/hubauth.proto`) — the SSO PR-2 replacement for the
/// transitional REST `GET /api/v1/auth/public-key` poll this cache used
/// before hub-api's gRPC key surface existed (SSO PR-1).
///
/// A fetch failure never clears the cache — the last-known-good key set
/// stays in use (graceful degradation: hub-api unreachable → cached
/// value, never a crash) until a refresh succeeds again. Only an empty
/// cache (no successful fetch has *ever* completed) causes inbound
/// requests to be rejected, with [`ApiError::KeyUnavailable`] rather than a
/// panic.
pub struct PublicKeyCache {
    channel: tonic::transport::Channel,
    keys: RwLock<KeySet>,
}

impl std::fmt::Debug for PublicKeyCache {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PublicKeyCache").finish_non_exhaustive()
    }
}

impl PublicKeyCache {
    /// Builds an (initially empty) cache pointed at `grpc_endpoint` (e.g.
    /// `http://hub-api:50051`, or `https://...` for a TLS-terminated
    /// endpoint — see this crate's Cargo.toml for the `tls-*` feature
    /// note). The channel connects lazily (`connect_lazy`): construction
    /// only fails on a syntactically invalid endpoint, never on a dial
    /// failure; no network call happens until
    /// [`PublicKeyCache::refresh`]/[`PublicKeyCache::spawn_refresh_loop`]
    /// runs.
    pub fn new(grpc_endpoint: impl Into<String>) -> Result<Self, KeyFetchError> {
        let grpc_endpoint = grpc_endpoint.into();
        let endpoint = tonic::transport::Endpoint::from_shared(grpc_endpoint.clone())
            .map_err(|error| KeyFetchError::InvalidEndpoint(grpc_endpoint, error))?
            .connect_timeout(GRPC_REQUEST_TIMEOUT)
            .timeout(GRPC_REQUEST_TIMEOUT);
        Ok(Self {
            channel: endpoint.connect_lazy(),
            keys: RwLock::new(KeySet::empty()),
        })
    }

    fn client(&self) -> HubAuthKeyServiceClient<tonic::transport::Channel> {
        HubAuthKeyServiceClient::new(self.channel.clone())
    }

    /// Fetches hub-api's current public key set and, on success, replaces
    /// the cached [`KeySet`] wholesale. On failure the previous cached set
    /// (if any) is left untouched — see struct docs on graceful
    /// degradation. A key entry that fails to parse as a usable verifier
    /// (malformed PEM, unsupported algorithm) is logged and skipped rather
    /// than failing the whole refresh, unless *every* entry is unusable
    /// (then [`KeyFetchError::NoUsableKeys`]).
    pub async fn refresh(&self) -> Result<(), KeyFetchError> {
        let request = tonic::Request::new(GetPublicKeysRequest {
            api_version: API_VERSION.to_string(),
        });
        let response = self.client().get_public_keys(request).await?.into_inner();

        if response.keys.is_empty() {
            return Err(KeyFetchError::EmptyKeySet);
        }

        let mut by_kid = HashMap::with_capacity(response.keys.len());
        let mut primary = None;
        let mut others = Vec::with_capacity(response.keys.len());

        for key in &response.keys {
            let verifier =
                match penguin_aaa::Es256Verifier::from_public_key_pem(key.public_key_pem.as_bytes())
                {
                    Ok(verifier) => Arc::new(verifier),
                    Err(error) => {
                        tracing::warn!(
                            kid = %key.kid,
                            algorithm = %key.algorithm,
                            %error,
                            "skipping unusable key from hub-api's GetPublicKeys response"
                        );
                        continue;
                    }
                };
            by_kid.insert(key.kid.clone(), verifier.clone());
            if key.primary {
                primary = Some(verifier);
            } else {
                others.push(verifier);
            }
        }

        if by_kid.is_empty() {
            return Err(KeyFetchError::NoUsableKeys);
        }
        if primary.is_none() {
            tracing::warn!(
                "hub-api's GetPublicKeys response has no key flagged primary — every key will \
                 still be tried, just with no preferred first attempt"
            );
        }

        let mut ordered = Vec::with_capacity(by_kid.len());
        ordered.extend(primary);
        ordered.extend(others);

        let mut guard = self
            .keys
            .write()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        *guard = KeySet { by_kid, ordered };
        Ok(())
    }

    /// The candidate verifiers to try for a token whose (unverified)
    /// header `kid` is `kid` — empty only when no successful fetch has
    /// *ever* completed (see struct docs).
    fn candidates(&self, kid: Option<&str>) -> Vec<Arc<penguin_aaa::Es256Verifier>> {
        self.keys
            .read()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .candidates(kid)
    }

    /// `true` once at least one successful fetch has populated the cache.
    fn has_keys(&self) -> bool {
        !self
            .keys
            .read()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .is_empty()
    }

    /// Seeds the cache with a single already-built verifier as the
    /// `primary` (and only) key, bypassing the network fetch entirely —
    /// for a *different* crate's tests only (e.g. `hub-router`'s own
    /// middleware/route integration tests, which can't reach this
    /// module's private fields directly). Only compiled in with the
    /// `test-util` feature, which production builds never enable.
    #[cfg(feature = "test-util")]
    pub fn inject_for_test(&self, verifier: penguin_aaa::Es256Verifier) {
        let verifier = Arc::new(verifier);
        *self
            .keys
            .write()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = KeySet {
            by_kid: HashMap::new(),
            ordered: vec![verifier],
        };
    }

    /// Spawns a background task that calls [`PublicKeyCache::refresh`]
    /// immediately, then every `interval` thereafter — this single loop
    /// covers both the startup fetch and the periodic (default hourly)
    /// refresh the Go headend performed lazily on each `ValidateToken`
    /// call. Never exits and never panics: a failed refresh is logged at
    /// WARN and the loop continues with whatever key set (or lack of one)
    /// was already cached.
    pub fn spawn_refresh_loop(self: Arc<Self>, interval: Duration) -> tokio::task::JoinHandle<()> {
        tokio::spawn(async move {
            loop {
                match self.refresh().await {
                    Ok(()) => tracing::info!("refreshed hub-api JWT public key set"),
                    Err(error) => tracing::warn!(
                        %error,
                        "failed to refresh hub-api JWT public key set — using cached keys if available"
                    ),
                }
                tokio::time::sleep(interval).await;
            }
        })
    }
}

/// Reads the (unverified) `kid` field off a compact JWS's header segment,
/// if present. This is **never** a trust decision by itself — it only
/// narrows which cached [`penguin_aaa::Es256Verifier`] to try first;
/// [`Es256Verifier::verify`] still performs the actual cryptographic
/// check, and a wrong/missing/forged `kid` just falls back to trying
/// every cached key (see [`KeySet::candidates`]), never to accepting the
/// token.
fn peek_kid(token: &str) -> Option<String> {
    use base64::engine::general_purpose::URL_SAFE_NO_PAD;
    use base64::Engine as _;

    let header_b64 = token.split('.').next()?;
    let header_bytes = URL_SAFE_NO_PAD.decode(header_b64).ok()?;
    let header: serde_json::Value = serde_json::from_slice(&header_bytes).ok()?;
    header.get("kid")?.as_str().map(str::to_string)
}

/// Verifies `token` against `cache`'s current public key set (selecting a
/// candidate verifier by the token's own `kid` header, falling back to
/// the full set — see module doc) and enforces tenant isolation
/// (security.md: tenant middleware/check runs first, before any scope
/// check) before returning the sanitized [`AuthUser`]. Every verification
/// failure (bad/wrong-algorithm signature, expired, malformed, missing
/// required claim, no matching key) collapses to
/// [`ApiError::InvalidCredentials`] — never leaking which check failed to
/// the caller (only to the sanitized debug/warn log). Once a candidate
/// key's signature check succeeds, the tenant check runs and its outcome
/// (success or [`ApiError::Forbidden`]) is final — a verified-but-missing-
/// tenant token is never retried against another key.
pub fn verify_inbound(cache: &PublicKeyCache, token: &str) -> Result<AuthUser, ApiError> {
    if !cache.has_keys() {
        return Err(ApiError::KeyUnavailable);
    }

    let kid = peek_kid(token);
    let candidates = cache.candidates(kid.as_deref());

    let mut last_error = None;
    for verifier in candidates {
        let claims = match verifier.verify(token) {
            Ok(claims) => claims,
            Err(error) => {
                last_error = Some(error);
                continue;
            }
        };

        let tenant = claims.tenant.ok_or_else(|| {
            tracing::warn!(sub = %claims.sub, "rejected inbound token: missing tenant claim");
            ApiError::Forbidden
        })?;

        return Ok(AuthUser {
            id: claims.sub,
            tenant,
            scope: claims.scope,
            roles: claims.roles,
        });
    }

    if let Some(error) = last_error {
        tracing::debug!(%error, "inbound jwt verification failed against every candidate key");
    }
    Err(ApiError::InvalidCredentials)
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
    use crate::pb::hub_auth_key_service_server::{HubAuthKeyService, HubAuthKeyServiceServer};
    use crate::pb::{PublicKey, PublicKeySetResponse};
    use async_trait::async_trait;
    use hmac::{Hmac, Mac};
    use p256::ecdsa::signature::Signer as _;
    use p256::ecdsa::{Signature, SigningKey, VerifyingKey};
    use p256::pkcs8::{DecodePrivateKey, EncodePrivateKey, EncodePublicKey, LineEnding};
    use penguin_aaa::{Claims, Es256Signer};
    use sha2::Sha256;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use tokio::sync::Mutex as AsyncMutex;
    use tokio_util::sync::CancellationToken;
    use tonic::transport::server::TcpIncoming;
    use tonic::transport::Server;
    use tonic::{Request as TonicRequest, Response as TonicResponse, Status};

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

    /// Hand-forges a well-formed ES256 JWS carrying a `kid` header field —
    /// `penguin_aaa::Es256Signer` never adds one (its header is fixed to
    /// `{alg, typ}`, see that crate's `token::Header`), so this crate's own
    /// `kid`-based selection tests need to build the token by hand, reusing
    /// the exact same raw fixed-size (r||s) ECDSA signature format
    /// `Es256Signer::sign`/`Es256Verifier::verify` use.
    fn sign_with_kid(private_pem: &str, kid: &str, claims: &Claims) -> String {
        let signing_key = SigningKey::from_pkcs8_pem(private_pem)
            .expect("a freshly generated EC PEM must load as a signing key");
        let header = serde_json::json!({"alg": "ES256", "typ": "JWT", "kid": kid});
        let header_b64 = b64url(&serde_json::to_vec(&header).expect("header serializes"));
        let payload_b64 = b64url(&serde_json::to_vec(claims).expect("claims serialize"));
        let signing_input = format!("{header_b64}.{payload_b64}");
        let signature: Signature = signing_key
            .try_sign(signing_input.as_bytes())
            .expect("signing a well-formed signing input must succeed");
        format!("{signing_input}.{}", b64url(&signature.to_bytes()))
    }

    /// Builds a cache with a single verifier already populated as the
    /// `primary` (and only) key, bypassing any network fetch — valid
    /// because this `tests` module is a descendant of `inbound`, so it may
    /// touch private fields directly.
    fn cache_with_verifier(verifier: penguin_aaa::Es256Verifier) -> PublicKeyCache {
        let cache = PublicKeyCache::new("http://unused.invalid")
            .expect("building a client against a syntactically valid endpoint must succeed");
        let verifier = Arc::new(verifier);
        *cache
            .keys
            .write()
            .expect("freshly constructed lock is never poisoned") = KeySet {
            by_kid: HashMap::new(),
            ordered: vec![verifier],
        };
        cache
    }

    // `PublicKeyCache::new`'s `Endpoint::connect_lazy()` needs a Tokio
    // runtime context to set up the channel even though it never dials
    // out (mirrors `node-agent-transport::GrpcClient`'s identical note),
    // so every test touching a `PublicKeyCache` is `#[tokio::test]`.
    #[tokio::test]
    async fn verify_inbound_accepts_valid_token_with_tenant() {
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

    #[tokio::test]
    async fn verify_inbound_rejects_missing_tenant_as_forbidden() {
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

    #[tokio::test]
    async fn verify_inbound_rejects_when_key_unavailable() {
        let cache = PublicKeyCache::new("http://unused.invalid")
            .expect("building a client against a syntactically valid endpoint must succeed");
        let err = verify_inbound(&cache, "whatever.token.here")
            .expect_err("an empty cache must reject every token");
        assert!(matches!(err, ApiError::KeyUnavailable));
    }

    /// Alg-confusion guard: a token signed HS256 using the verifier's own
    /// ES256 *public* key bytes as the HMAC secret must be rejected —
    /// `Es256Verifier` has no HS256 code path at all (mirrors
    /// `engines/testserver-rs`'s identical regression test).
    #[tokio::test]
    async fn verify_inbound_rejects_hs256_alg_confusion_token() {
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
        let signing_input = format!("{}.{}", b64url(header.as_bytes()), b64url(payload.as_bytes()));
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
    #[tokio::test]
    async fn verify_inbound_rejects_alg_none_token() {
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

    /// An in-process `hubauth.v1.HubAuthKeyService` double: each RPC pops
    /// one canned `Result` (panicking on a second call). This is what
    /// makes these tests a real end-to-end exercise of
    /// `PublicKeyCache::refresh` over the wire rather than a unit test of
    /// request builders alone — mirrors
    /// `agents/node-agent/crates/transport/src/grpc.rs`'s identical
    /// `ScriptedManager` pattern.
    #[derive(Default)]
    struct ScriptedKeyService {
        response: AsyncMutex<Option<Result<PublicKeySetResponse, Status>>>,
        calls: AtomicUsize,
    }

    #[async_trait]
    impl HubAuthKeyService for ScriptedKeyService {
        async fn get_public_keys(
            &self,
            _request: TonicRequest<GetPublicKeysRequest>,
        ) -> Result<TonicResponse<PublicKeySetResponse>, Status> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            self.response
                .lock()
                .await
                .take()
                .expect("scripted RPC called more times than configured")
                .map(TonicResponse::new)
        }
    }

    /// Starts `service` as a real loopback gRPC server on an OS-assigned
    /// port, returning its `http://127.0.0.1:<port>` endpoint and a
    /// [`CancellationToken`] that stops the server when cancelled.
    async fn spawn_key_service(
        service: Arc<ScriptedKeyService>,
    ) -> (String, CancellationToken) {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
            .await
            .expect("binding an ephemeral loopback port must succeed");
        let addr = listener
            .local_addr()
            .expect("a bound listener has a local address");
        let incoming = TcpIncoming::from(listener);
        let shutdown = CancellationToken::new();
        let stop = shutdown.clone();

        tokio::spawn(async move {
            Server::builder()
                .add_service(HubAuthKeyServiceServer::from_arc(service))
                .serve_with_incoming_shutdown(incoming, stop.cancelled())
                .await
                .expect("mock HubAuthKeyService server must not fail to serve");
        });

        (format!("http://{addr}"), shutdown)
    }

    fn one_key_response(public_pem: &str, kid: &str) -> PublicKeySetResponse {
        PublicKeySetResponse {
            keys: vec![PublicKey {
                kid: kid.to_string(),
                algorithm: "ES256".to_string(),
                public_key_pem: public_pem.to_string(),
                r#use: "sig".to_string(),
                primary: true,
                fetched_at_unix: now(),
            }],
        }
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn refresh_fetches_a_single_key_over_grpc_and_it_verifies_a_token() {
        let (private_pem, public_pem) = generate_test_keypair();
        let service = Arc::new(ScriptedKeyService::default());
        *service.response.lock().await = Some(Ok(one_key_response(&public_pem, "key-a")));

        let (url, shutdown) = spawn_key_service(Arc::clone(&service)).await;
        let cache = PublicKeyCache::new(url).expect("building a client must succeed");
        cache
            .refresh()
            .await
            .expect("fetching from a healthy mock server must succeed");

        let claims = build_claims("node-1", Some("acme"), "router:read", now() + 3600);
        let token = sign_valid(&private_pem, &claims);
        let user = verify_inbound(&cache, &token)
            .expect("a token signed by the gRPC-fetched key must verify");
        assert_eq!(user.tenant, "acme");

        assert_eq!(service.calls.load(Ordering::SeqCst), 1);
        shutdown.cancel();
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn refresh_rejects_an_empty_key_set() {
        let service = Arc::new(ScriptedKeyService::default());
        *service.response.lock().await = Some(Ok(PublicKeySetResponse { keys: vec![] }));

        let (url, shutdown) = spawn_key_service(Arc::clone(&service)).await;
        let cache = PublicKeyCache::new(url).expect("building a client must succeed");
        let err = cache
            .refresh()
            .await
            .expect_err("an empty key set must be rejected, not silently cached");
        assert!(matches!(err, KeyFetchError::EmptyKeySet));
        shutdown.cancel();
    }

    /// Proves the multi-key/`kid`-selection contract end-to-end: hub-api
    /// returns two keys (one `primary`), and a token signed under *either*
    /// key — each carrying that key's own `kid` in its header — verifies,
    /// because `verify_inbound` selects the matching verifier by `kid`
    /// rather than only ever trying the primary.
    #[tokio::test(flavor = "multi_thread")]
    async fn multi_key_set_verifies_tokens_signed_under_either_key_by_kid() {
        let (private_a, public_a) = generate_test_keypair();
        let (private_b, public_b) = generate_test_keypair();
        let service = Arc::new(ScriptedKeyService::default());
        *service.response.lock().await = Some(Ok(PublicKeySetResponse {
            keys: vec![
                PublicKey {
                    kid: "key-a".to_string(),
                    algorithm: "ES256".to_string(),
                    public_key_pem: public_a.clone(),
                    r#use: "sig".to_string(),
                    primary: true,
                    fetched_at_unix: now(),
                },
                PublicKey {
                    kid: "key-b".to_string(),
                    algorithm: "ES256".to_string(),
                    public_key_pem: public_b.clone(),
                    r#use: "sig".to_string(),
                    primary: false,
                    fetched_at_unix: now(),
                },
            ],
        }));

        let (url, shutdown) = spawn_key_service(Arc::clone(&service)).await;
        let cache = PublicKeyCache::new(url).expect("building a client must succeed");
        cache.refresh().await.expect("fetching two keys must succeed");

        let claims_a = build_claims("node-a", Some("acme"), "router:read", now() + 3600);
        let token_a = sign_with_kid(&private_a, "key-a", &claims_a);
        let user_a =
            verify_inbound(&cache, &token_a).expect("a token signed under key-a must verify");
        assert_eq!(user_a.id, "node-a");

        let claims_b = build_claims("node-b", Some("acme"), "router:read", now() + 3600);
        let token_b = sign_with_kid(&private_b, "key-b", &claims_b);
        let user_b = verify_inbound(&cache, &token_b)
            .expect("a token signed under the non-primary key-b must also verify");
        assert_eq!(user_b.id, "node-b");

        shutdown.cancel();
    }

    /// A `kid` the cache doesn't recognize (stale cache mid-rotation, or no
    /// `kid` at all) must still verify by falling back to trying every
    /// cached key, not just the one named — the fallback-sweep half of the
    /// selection contract.
    #[tokio::test(flavor = "multi_thread")]
    async fn unknown_kid_falls_back_to_trying_every_cached_key() {
        let (_private_a, public_a) = generate_test_keypair();
        let (private_b, public_b) = generate_test_keypair();
        let service = Arc::new(ScriptedKeyService::default());
        *service.response.lock().await = Some(Ok(PublicKeySetResponse {
            keys: vec![
                PublicKey {
                    kid: "key-a".to_string(),
                    algorithm: "ES256".to_string(),
                    public_key_pem: public_a,
                    r#use: "sig".to_string(),
                    primary: true,
                    fetched_at_unix: now(),
                },
                PublicKey {
                    kid: "key-b".to_string(),
                    algorithm: "ES256".to_string(),
                    public_key_pem: public_b,
                    r#use: "sig".to_string(),
                    primary: false,
                    fetched_at_unix: now(),
                },
            ],
        }));

        let (url, shutdown) = spawn_key_service(Arc::clone(&service)).await;
        let cache = PublicKeyCache::new(url).expect("building a client must succeed");
        cache.refresh().await.expect("fetching two keys must succeed");

        // Signed under key-b but declares a `kid` the cache has never seen
        // — must still verify via the fallback sweep.
        let claims = build_claims("node-b", Some("acme"), "router:read", now() + 3600);
        let token = sign_with_kid(&private_b, "key-unknown", &claims);
        let user = verify_inbound(&cache, &token)
            .expect("an unrecognized kid must fall back to trying every cached key");
        assert_eq!(user.id, "node-b");

        shutdown.cancel();
    }

    /// Proves [`PublicKeyCache::refresh`]'s graceful-degradation contract
    /// end-to-end over a real gRPC connection: a successful fetch
    /// populates the cache; a subsequent failed fetch (connection refused)
    /// leaves the previously cached key set untouched rather than clearing
    /// it.
    #[tokio::test(flavor = "multi_thread")]
    async fn refresh_falls_back_to_cached_keys_when_endpoint_unreachable() {
        let (_, public_pem) = generate_test_keypair();
        let service = Arc::new(ScriptedKeyService::default());
        *service.response.lock().await = Some(Ok(one_key_response(&public_pem, "key-a")));

        let (url, shutdown) = spawn_key_service(Arc::clone(&service)).await;
        let cache = PublicKeyCache::new(url)
            .expect("building a client against a healthy endpoint must succeed");
        cache
            .refresh()
            .await
            .expect("initial fetch against a healthy mock server must succeed");
        assert!(cache.has_keys());

        // Point a *different* cache at an address nothing is listening on,
        // seed it with the same key set as if it had previously succeeded,
        // then prove a failed refresh never clears what's already cached.
        let unreachable = PublicKeyCache::new("http://127.0.0.1:1")
            .expect("building a client with no special TLS/proxy config must succeed");
        {
            let seeded = cache
                .keys
                .read()
                .expect("freshly constructed lock is never poisoned");
            *unreachable
                .keys
                .write()
                .expect("freshly constructed lock is never poisoned") = KeySet {
                by_kid: seeded.by_kid.clone(),
                ordered: seeded.ordered.clone(),
            };
        }
        let result = tokio::time::timeout(Duration::from_secs(5), unreachable.refresh())
            .await
            .expect("an unreachable gRPC endpoint must fail well inside this test's own bound");
        assert!(result.is_err(), "fetch against an unreachable endpoint must fail");
        assert!(
            unreachable.has_keys(),
            "a failed refresh must never clear a previously cached key set"
        );

        shutdown.cancel();
    }

    /// Minimal unpadded base64url encoder for the hand-forged tokens above
    /// — deliberately hand-rolled instead of pulling in a `base64`
    /// dependency just to construct a few malformed/forged test tokens
    /// (mirrors `engines/testserver-rs`'s identical helper). Production
    /// code's own base64url need ([`peek_kid`]) uses the real `base64`
    /// crate instead, since decoding untrusted input by hand is exactly
    /// the kind of thing not to hand-roll outside a test.
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
