//! Route table: `/health` (unauthenticated, liveness/readiness probe) plus
//! `/api/v1/router/status` — the first protected control-plane endpoint,
//! gated by [`crate::middleware::auth_middleware`] (inbound JWT
//! verification + tenant check) and a per-route `router:read` scope check.
//! Later PRs add more protected routes (firewall rules, port config, etc.)
//! as those subsystems' own Rust ports land; this establishes the pattern
//! every one of them will follow.

use axum::extract::{Extension, State};
use axum::middleware as axum_middleware;
use axum::response::{IntoResponse, Json};
use axum::routing::get;
use axum::Router;
use hub_router_auth::inbound::{require_scope, ApiError, AuthUser};
use serde_json::json;
use std::time::Instant;

use crate::middleware::{auth_middleware, AppState};

/// Health check response — unauthenticated, no tenant/scope context.
async fn health_handler() -> impl IntoResponse {
    Json(json!({"status": "ok"}))
}

/// First protected control-plane endpoint — requires the `router:read`
/// scope. Placeholder response; real router-status reporting (active
/// WireGuard peers, firewall rule counts, port bindings) lands as those
/// crates' own Rust ports wire into this route table.
async fn router_status_handler(
    Extension(user): Extension<AuthUser>,
) -> Result<impl IntoResponse, ApiError> {
    require_scope(&user, "router:read")?;
    Ok(Json(json!({
        "status": "ok",
        "tenant": user.tenant,
    })))
}

/// Wraps `inner` so every request/response (across both the public and
/// protected route groups) records [`crate::telemetry::record_request`] —
/// the per-request latency histogram, independent of
/// [`crate::telemetry::record_jwt_verify`]'s narrower verify-step timing.
async fn timing_middleware(
    State(_state): State<AppState>,
    request: axum::extract::Request,
    next: axum_middleware::Next,
) -> axum::response::Response {
    let path = request.uri().path().to_string();
    let start = Instant::now();
    let response = next.run(request).await;
    crate::telemetry::record_request(
        &path,
        start.elapsed().as_secs_f64(),
        response.status().as_u16(),
    );
    response
}

/// Builds the full axum router: `/health` unauthenticated, `/api/v1/*`
/// behind [`auth_middleware`]. `state` is captured by value directly into
/// each `from_fn_with_state` layer (cheap — just an `Arc` clone per
/// layer); no handler here extracts `State<AppState>` through the
/// router's own state mechanism, so the returned `Router` needs no
/// `.with_state()` call and is immediately servable.
pub fn router(state: AppState) -> Router {
    let protected = Router::new()
        .route("/api/v1/router/status", get(router_status_handler))
        .route_layer(axum_middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ));

    Router::new()
        .route("/health", get(health_handler))
        .merge(protected)
        .route_layer(axum_middleware::from_fn_with_state(
            state,
            timing_middleware,
        ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::{Request, StatusCode};
    use hub_router_auth::inbound::PublicKeyCache;
    use p256::ecdsa::{SigningKey, VerifyingKey};
    use p256::pkcs8::{EncodePrivateKey, EncodePublicKey, LineEnding};
    use penguin_aaa::{Claims, Es256Signer};
    use std::sync::Arc;
    use tower::ServiceExt;

    fn now() -> i64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system clock is after the Unix epoch")
            .as_secs() as i64
    }

    #[tokio::test]
    async fn health_is_reachable_without_a_bearer_token() {
        let cache = PublicKeyCache::new("http://unused.invalid").expect("client build");
        let app = router(AppState::new(Arc::new(cache)));

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .body(Body::empty())
                    .expect("building a bare request must succeed"),
            )
            .await
            .expect("router must produce a response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn protected_status_route_requires_a_valid_scoped_token() {
        let signing_key = SigningKey::random(&mut rand_core::OsRng);
        let private_pem = signing_key
            .to_pkcs8_pem(LineEnding::LF)
            .expect("encoding a freshly generated P-256 key as PKCS#8 PEM must succeed")
            .to_string();
        let public_pem = VerifyingKey::from(&signing_key)
            .to_public_key_pem(LineEnding::LF)
            .expect("encoding the matching public key as SPKI PEM must succeed");

        let cache = PublicKeyCache::new("http://unused.invalid").expect("client build");
        cache.inject_for_test(
            penguin_aaa::Es256Verifier::from_public_key_pem(public_pem.as_bytes())
                .expect("verifier build"),
        );
        let app = router(AppState::new(Arc::new(cache)));

        let claims = Claims {
            sub: "node-1".to_string(),
            iss: "hub-api-test".to_string(),
            aud: "hub-router".to_string(),
            iat: now(),
            exp: now() + 3600,
            scope: "router:read".to_string(),
            tenant: Some("acme".to_string()),
            teams: Vec::new(),
            roles: vec!["viewer".to_string()],
        };
        let token = Es256Signer::from_ec_pem(private_pem.as_bytes())
            .expect("a freshly generated EC PEM must load as a signing key")
            .sign(&claims)
            .expect("signing a well-formed claim set must succeed");

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/api/v1/router/status")
                    .header(axum::http::header::AUTHORIZATION, format!("Bearer {token}"))
                    .body(Body::empty())
                    .expect("building a request with a header must succeed"),
            )
            .await
            .expect("router must produce a response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn protected_status_route_rejects_an_unauthenticated_request() {
        let cache = PublicKeyCache::new("http://unused.invalid").expect("client build");
        let app = router(AppState::new(Arc::new(cache)));

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/api/v1/router/status")
                    .body(Body::empty())
                    .expect("building a bare request must succeed"),
            )
            .await
            .expect("router must produce a response");
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }
}
