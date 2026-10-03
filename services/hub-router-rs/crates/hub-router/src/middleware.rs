//! Inbound JWT-verification middleware wiring — the axum-facing glue
//! between `hub_router_auth::inbound` (pure verification/authz logic) and
//! the route table ([`crate::routes`]). Applied via `.route_layer()` to
//! the protected route group only — `/health` never passes through this
//! middleware (see `crate::routes::router`).
//!
//! Tenant isolation runs first (inside
//! [`hub_router_auth::inbound::verify_inbound`], before this middleware
//! ever sees a result) — a token verifies successfully but is still
//! rejected with 403 if it carries no `tenant` claim. The resulting
//! [`AuthUser`] is inserted into the request's extensions for the route
//! handler's own per-route [`hub_router_auth::inbound::require_scope`]
//! check; this middleware does not itself know which scope any given
//! route requires.

use axum::extract::Request;
use axum::http::header;
use axum::middleware::Next;
use axum::response::Response;
use hub_router_auth::inbound::{verify_inbound, ApiError, PublicKeyCache};
use std::sync::Arc;
use std::time::Instant;

/// Shared state every protected route needs — currently just the inbound
/// public-key cache. Grows as later PRs add more control-plane routes.
#[derive(Clone)]
pub struct AppState {
    pub key_cache: Arc<PublicKeyCache>,
}

impl AppState {
    pub fn new(key_cache: Arc<PublicKeyCache>) -> Self {
        Self { key_cache }
    }
}

/// Extracts the `Bearer <token>` credential, verifies it against
/// `state.key_cache`'s current public key, and — on success — inserts the
/// sanitized [`hub_router_auth::inbound::AuthUser`] into the request's
/// extensions before calling through to the handler. Records
/// [`crate::telemetry::record_jwt_verify`] around the verification step
/// specifically (independent of the overall per-request histogram), and
/// never panics or blocks on a missing/stale public key — a cache miss is
/// a 503, not a crash (see [`PublicKeyCache`]'s graceful-degradation
/// contract).
pub async fn auth_middleware(
    axum::extract::State(state): axum::extract::State<AppState>,
    mut request: Request,
    next: Next,
) -> Result<Response, ApiError> {
    let token = request
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .ok_or(ApiError::Unauthorized)?
        .to_string();

    let verify_start = Instant::now();
    let result = verify_inbound(&state.key_cache, &token);
    let outcome = match &result {
        Ok(_) => "valid",
        Err(ApiError::Forbidden) => "forbidden",
        Err(ApiError::KeyUnavailable) => "key_unavailable",
        Err(_) => "invalid",
    };
    crate::telemetry::record_jwt_verify(verify_start.elapsed().as_secs_f64(), outcome);

    let user = result?;
    request.extensions_mut().insert(user);
    Ok(next.run(request).await)
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::extract::Extension;
    use axum::http::{Request as HttpRequest, StatusCode};
    use axum::routing::get;
    use axum::{middleware as axum_middleware, Router};
    use hub_router_auth::inbound::{require_scope, AuthUser};
    use p256::ecdsa::{SigningKey, VerifyingKey};
    use p256::pkcs8::{EncodePrivateKey, EncodePublicKey, LineEnding};
    use penguin_aaa::{Claims, Es256Signer};
    use tower::ServiceExt;

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

    fn sign(private_pem: &str, tenant: Option<&str>, scope: &str) -> String {
        let claims = Claims {
            sub: "node-1".to_string(),
            iss: "hub-api-test".to_string(),
            aud: "hub-router".to_string(),
            iat: now(),
            exp: now() + 3600,
            scope: scope.to_string(),
            tenant: tenant.map(str::to_string),
            teams: Vec::new(),
            roles: vec!["viewer".to_string()],
        };
        Es256Signer::from_ec_pem(private_pem.as_bytes())
            .expect("a freshly generated EC PEM must load as a signing key")
            .sign(&claims)
            .expect("signing a well-formed claim set must succeed")
    }

    /// A single protected test route requiring `router:read`, mirroring
    /// the real `/api/v1/router/status` route's shape without depending on
    /// `crate::routes` — keeps this test focused on the middleware itself.
    async fn protected_handler(
        Extension(user): Extension<AuthUser>,
    ) -> Result<axum::Json<serde_json::Value>, ApiError> {
        require_scope(&user, "router:read")?;
        Ok(axum::Json(serde_json::json!({"tenant": user.tenant})))
    }

    fn test_router(state: AppState) -> Router {
        Router::new()
            .route("/protected", get(protected_handler))
            .route_layer(axum_middleware::from_fn_with_state(state, auth_middleware))
    }

    fn request_with_bearer(token: &str) -> HttpRequest<Body> {
        HttpRequest::builder()
            .uri("/protected")
            .header(header::AUTHORIZATION, format!("Bearer {token}"))
            .body(Body::empty())
            .expect("building a request with a header must succeed")
    }

    #[tokio::test]
    async fn valid_token_with_scope_is_accepted() {
        let (private_pem, public_pem) = generate_test_keypair();
        let cache = PublicKeyCache::new("http://unused.invalid").expect("client build");
        cache.inject_for_test(
            penguin_aaa::Es256Verifier::from_public_key_pem(public_pem.as_bytes())
                .expect("verifier build"),
        );
        let state = AppState::new(Arc::new(cache));
        let token = sign(&private_pem, Some("acme"), "router:read");

        let response = test_router(state)
            .oneshot(request_with_bearer(&token))
            .await
            .expect("router must produce a response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn missing_tenant_is_rejected_with_403() {
        let (private_pem, public_pem) = generate_test_keypair();
        let cache = PublicKeyCache::new("http://unused.invalid").expect("client build");
        cache.inject_for_test(
            penguin_aaa::Es256Verifier::from_public_key_pem(public_pem.as_bytes())
                .expect("verifier build"),
        );
        let state = AppState::new(Arc::new(cache));
        let token = sign(&private_pem, None, "router:read");

        let response = test_router(state)
            .oneshot(request_with_bearer(&token))
            .await
            .expect("router must produce a response");
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn insufficient_scope_is_rejected_with_403() {
        let (private_pem, public_pem) = generate_test_keypair();
        let cache = PublicKeyCache::new("http://unused.invalid").expect("client build");
        cache.inject_for_test(
            penguin_aaa::Es256Verifier::from_public_key_pem(public_pem.as_bytes())
                .expect("verifier build"),
        );
        let state = AppState::new(Arc::new(cache));
        let token = sign(&private_pem, Some("acme"), "router:write");

        let response = test_router(state)
            .oneshot(request_with_bearer(&token))
            .await
            .expect("router must produce a response");
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn missing_bearer_header_is_rejected_with_401() {
        let cache = PublicKeyCache::new("http://unused.invalid").expect("client build");
        let state = AppState::new(Arc::new(cache));

        let request = HttpRequest::builder()
            .uri("/protected")
            .body(Body::empty())
            .expect("building a request without a header must succeed");
        let response = test_router(state)
            .oneshot(request)
            .await
            .expect("router must produce a response");
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn key_unavailable_is_rejected_with_503() {
        let cache = PublicKeyCache::new("http://unused.invalid").expect("client build");
        let state = AppState::new(Arc::new(cache));

        let response = test_router(state)
            .oneshot(request_with_bearer("whatever.token.here"))
            .await
            .expect("router must produce a response");
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }
}
