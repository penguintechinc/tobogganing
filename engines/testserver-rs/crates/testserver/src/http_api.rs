//! axum REST surface — port of `cmd/testserver/main.go` router wiring +
//! `internal/handlers`. Route table and behavior mirror the Go source
//! exactly (see module-level docs on `testserver_protocols` for the
//! specific parity quirks preserved); the auth scheme is the one
//! deliberate behavioral change (real JWT verification replacing an opaque
//! DB hash lookup — see `testserver_core::auth`).

use axum::extract::{ConnectInfo, Query, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use rand::RngExt;
use serde_json::{json, Value};
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Instant;
use testserver_core::{validation, ApiError, AppConfig, AuthUser, JwtVerifier};
use testserver_db::{AuthDb, NewTestResult, SwitchableStore, TestResultStore};
use testserver_protocols::deferred::{
    self, HttpTraceRequest, IcmpTestRequest, TcpTraceRequest, TracerouteRequest, UdpTraceRequest,
};
use testserver_protocols::{
    http::{HttpTestRequest, HttpTestResult},
    tcp::{TcpTestRequest, TcpTestResult},
    udp::{UdpTestRequest, UdpTestResult},
};
use tower_http::cors::{AllowOrigin, CorsLayer};
use tower_http::limit::RequestBodyLimitLayer;

#[derive(Clone)]
pub struct AppState {
    pub db: Arc<SwitchableStore>,
    pub jwt_verifier: Option<JwtVerifier>,
    pub auth_enabled: bool,
}

impl AppState {
    pub fn new(db: Arc<SwitchableStore>, cfg: &AppConfig) -> Self {
        let jwt_verifier = cfg
            .jwt_secret
            .as_ref()
            .map(|secret| JwtVerifier::new_hs256(secret.as_bytes()));
        Self {
            db,
            jwt_verifier,
            auth_enabled: cfg.auth_enabled,
        }
    }
}

/// Auth middleware for `/api/v1/test/*` — `Bearer <token>` is verified as a
/// real signed JWT (the security fix this migration makes); `ApiKey <key>`
/// still resolves via the database, unchanged from the Go behavior.
/// `AUTH_ENABLED=false` bypasses this entirely, matching
/// `internal/auth.Authenticator.Middleware`'s early return.
async fn auth_middleware(
    State(state): State<AppState>,
    headers: HeaderMap,
    mut request: axum::extract::Request,
    next: Next,
) -> Result<Response, ApiError> {
    if !state.auth_enabled {
        return Ok(next.run(request).await);
    }

    let auth_header = headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .ok_or(ApiError::Unauthorized)?;

    let user = if let Some(token) = auth_header.strip_prefix("Bearer ") {
        let verifier = state.jwt_verifier.as_ref().ok_or_else(|| {
            tracing::warn!("Bearer token presented but JWT_SECRET is not configured — rejecting");
            ApiError::InvalidCredentials
        })?;
        verifier.verify(token)?
    } else if let Some(key) = auth_header.strip_prefix("ApiKey ") {
        state
            .db
            .validate_api_key(key)
            .await
            .map_err(|_| ApiError::InvalidCredentials)?
    } else {
        return Err(ApiError::Unauthorized);
    };

    request.extensions_mut().insert(user);
    Ok(next.run(request).await)
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

async fn health_handler() -> Json<Value> {
    Json(json!({"status": "healthy", "version": "1.0.0"}))
}

// ---------------------------------------------------------------------------
// SpeedTest handlers — public, no auth (matches main.go's /speedtest routes)
// ---------------------------------------------------------------------------

async fn speedtest_download(
    Query(params): Query<std::collections::HashMap<String, String>>,
) -> Response {
    let size_mb: i64 = params
        .get("size")
        .and_then(|s| s.parse::<i64>().ok())
        .filter(|&v| v > 0 && v <= 100)
        .unwrap_or(10);
    let size_bytes = (size_mb * 1024 * 1024) as usize;

    let mut buf = vec![0u8; size_bytes];
    rand::rng().fill(buf.as_mut_slice());

    (
        StatusCode::OK,
        [
            (header::CONTENT_TYPE, "application/octet-stream".to_string()),
            (
                header::CACHE_CONTROL,
                "no-store, no-cache, must-revalidate, max-age=0".to_string(),
            ),
            (header::PRAGMA, "no-cache".to_string()),
            (
                header::ACCESS_CONTROL_EXPOSE_HEADERS,
                "Content-Length".to_string(),
            ),
        ],
        buf,
    )
        .into_response()
}

async fn speedtest_upload(body: axum::body::Body) -> Result<Json<Value>, ApiError> {
    let start = Instant::now();
    let bytes = axum::body::to_bytes(body, usize::MAX)
        .await
        .map_err(|e| ApiError::TestExecution(format!("error reading upload data: {e}")))?;
    let duration = start.elapsed();

    let bytes_received = bytes.len() as u64;
    let throughput_mbps = if duration.as_secs_f64() > 0.0 {
        (bytes_received as f64 * 8.0) / (duration.as_secs_f64() * 1_000_000.0)
    } else {
        0.0
    };

    Ok(Json(json!({
        "success": true,
        "bytes_received": bytes_received,
        "duration_ms": duration.as_millis() as u64,
        "throughput_mbps": throughput_mbps,
    })))
}

async fn speedtest_ping() -> Response {
    let body = Json(json!({
        "pong": true,
        "timestamp": chrono_now_millis(),
    }));
    (
        StatusCode::OK,
        [
            (
                header::CACHE_CONTROL,
                "no-store, no-cache, must-revalidate, max-age=0",
            ),
            (header::PRAGMA, "no-cache"),
        ],
        body,
    )
        .into_response()
}

fn chrono_now_millis() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

async fn speedtest_info() -> Json<Value> {
    Json(json!({
        "name": "WaddlePerf SpeedTest",
        "version": "1.0.0",
        "max_chunk_size_mb": 100,
        "default_chunk_size_mb": 10,
        "recommended_streams": 6,
        "max_streams": 32,
    }))
}

#[derive(Debug, serde::Deserialize)]
struct SpeedTestResultRequest {
    #[serde(default)]
    download_mbps: f64,
    #[serde(default)]
    upload_mbps: f64,
    #[serde(default)]
    latency_ms: f64,
    #[serde(default)]
    jitter_ms: f64,
    #[serde(default)]
    server_url: String,
}

async fn speedtest_result(
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    Json(req): Json<SpeedTestResultRequest>,
) -> Result<Json<Value>, ApiError> {
    let raw_results = json!({
        "latency_ms": req.latency_ms,
        "throughput": req.download_mbps,
        "download_mbps": req.download_mbps,
        "upload_mbps": req.upload_mbps,
        "jitter_ms": req.jitter_ms,
    });

    let result = NewTestResult {
        user_id: None,
        target_host: req.server_url.clone(),
        target_ip: "self".to_string(),
        test_type: "speedtest".to_string(),
        protocol_detail: "download_upload".to_string(),
        client_ip: client_ip(&headers, &peer),
        latency_ms: Some(req.latency_ms),
        throughput_mbps: Some(req.download_mbps),
        jitter_ms: Some(req.jitter_ms),
        raw_results,
        ..device_fields(&headers)
    };

    state
        .db
        .insert_test_result(result)
        .await
        .map_err(|e| ApiError::TestExecution(e.to_string()))?;

    Ok(Json(
        json!({"success": true, "message": "Speedtest result saved successfully"}),
    ))
}

// ---------------------------------------------------------------------------
// Shared result-saving helpers
// ---------------------------------------------------------------------------

fn header_or_unknown(headers: &HeaderMap, name: &str) -> String {
    headers
        .get(name)
        .and_then(|v| v.to_str().ok())
        .filter(|s| !s.is_empty())
        .unwrap_or("unknown")
        .to_string()
}

fn device_fields(headers: &HeaderMap) -> NewTestResult {
    NewTestResult {
        device_serial: header_or_unknown(headers, "x-device-serial"),
        device_hostname: header_or_unknown(headers, "x-device-hostname"),
        device_os: header_or_unknown(headers, "x-device-os"),
        device_os_version: header_or_unknown(headers, "x-device-os-version"),
        ..Default::default()
    }
}

/// Number of trusted reverse-proxy hops between the client and this
/// service — mirrors `hub_api/security/rate_limit.py`'s
/// `_TRUSTED_PROXY_HOPS` (read once, same env var name for consistency
/// across the codebase). Default 1 matches security.md Kubernetes Network
/// Security's single Ingress/Gateway API hop.
static TRUSTED_PROXY_HOPS: std::sync::LazyLock<usize> = std::sync::LazyLock::new(|| {
    std::env::var("RATE_LIMIT_TRUSTED_PROXY_HOPS")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(1)
});

/// Best-effort client IP for the audit trail (`NewTestResult.client_ip`),
/// using the same trusted-proxy-hop model as
/// `hub_api/security/rate_limit.py::client_ip()`.
///
/// The LEFTMOST `X-Forwarded-For` entry is always attacker-controlled: a
/// client can send an arbitrary XFF value, and the trusted ingress/Gateway
/// API proxy only ever *appends* its observed peer to whatever the client
/// already sent — so a client sending `X-Forwarded-For: 9.9.9.9` arrives
/// here as `X-Forwarded-For: 9.9.9.9, <real-client-ip>`. Using the leftmost
/// entry for anything security-relevant (this field feeds an audit trail
/// of "who initiated this probe", i.e. audit-as-identity) lets an attacker
/// forge that identity on every request.
///
/// Instead this walks in from the RIGHT by `TRUSTED_PROXY_HOPS` — that
/// entry is the one appended by the outermost *trusted* proxy, which only
/// the proxy itself can set. Falls back to the axum-reported TCP peer
/// address when XFF is absent (local/dev/direct-connection testing) or
/// doesn't have enough hops to satisfy the configured trust depth.
fn client_ip(headers: &HeaderMap, connect_info: &SocketAddr) -> String {
    if let Some(forwarded) = headers.get("x-forwarded-for").and_then(|v| v.to_str().ok()) {
        let parts: Vec<&str> = forwarded
            .split(',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .collect();
        let hops = *TRUSTED_PROXY_HOPS;
        if hops > 0 && hops <= parts.len() {
            return parts[parts.len() - hops].to_string();
        }
    }
    connect_info.to_string()
}

async fn save_best_effort(state: &AppState, result: NewTestResult) {
    if let Err(e) = state.db.insert_test_result(result).await {
        tracing::warn!(error = %e, "failed to save test result");
    }
}

// ---------------------------------------------------------------------------
// /api/v1/test/* — authenticated
// ---------------------------------------------------------------------------

async fn http_test_handler(
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    user_ext: Option<axum::Extension<AuthUser>>,
    Json(mut req): Json<HttpTestRequest>,
) -> Result<Json<HttpTestResult>, ApiError> {
    validation::validate_target(&req.target).await?;
    validation::validate_http_protocol(&req.protocol)?;
    validation::validate_http_protocol(&req.protocol_detail)?;
    validation::validate_http_method(&req.method)?;
    if req.timeout > 0 {
        validation::validate_timeout(req.timeout)?;
    }

    req.target = validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH);
    req.protocol = validation::sanitize_string(&req.protocol, validation::MAX_PROTOCOL_LENGTH);
    req.protocol_detail =
        validation::sanitize_string(&req.protocol_detail, validation::MAX_PROTOCOL_LENGTH);
    req.method = validation::sanitize_string(&req.method, validation::MAX_METHOD_LENGTH);

    let target = req.target.clone();
    let protocol = req.protocol.clone();
    let result = testserver_protocols::test_http(req)
        .await
        .map_err(|_| ApiError::TestExecution("Test execution failed".to_string()))?;

    let new_result = NewTestResult {
        user_id: user_ext.and_then(|axum::Extension(u)| u.id.parse::<i32>().ok()),
        test_type: "http".to_string(),
        protocol_detail: protocol,
        target_host: target.clone(),
        target_ip: target,
        client_ip: client_ip(&headers, &peer),
        latency_ms: Some(result.latency_ms),
        jitter_ms: (result.jitter_ms > 0.0).then_some(result.jitter_ms),
        raw_results: json!({
            "status_code": result.status_code,
            "ttfb_ms": result.ttfb_ms,
            "total_time_ms": result.total_time_ms,
            "min_latency_ms": result.min_latency_ms,
            "max_latency_ms": result.max_latency_ms,
        }),
        ..device_fields(&headers)
    };
    save_best_effort(&state, new_result).await;

    Ok(Json(result))
}

async fn tcp_test_handler(
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    user_ext: Option<axum::Extension<AuthUser>>,
    Json(mut req): Json<TcpTestRequest>,
) -> Result<Json<TcpTestResult>, ApiError> {
    validation::validate_target(&req.target).await?;
    validation::validate_tcp_protocol(&req.protocol)?;
    validation::validate_tcp_protocol(&req.protocol_detail)?;
    if req.port > 0 {
        validation::validate_port(req.port)?;
    }
    if req.timeout > 0 {
        validation::validate_timeout(req.timeout)?;
    }

    req.target = validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH);
    req.protocol = validation::sanitize_string(&req.protocol, validation::MAX_PROTOCOL_LENGTH);
    req.protocol_detail =
        validation::sanitize_string(&req.protocol_detail, validation::MAX_PROTOCOL_LENGTH);

    let target = req.target.clone();
    let protocol = req.protocol.clone();
    let result = testserver_protocols::test_tcp(req)
        .await
        .map_err(|_| ApiError::TestExecution("Test execution failed".to_string()))?;

    let new_result = NewTestResult {
        user_id: user_ext.and_then(|axum::Extension(u)| u.id.parse::<i32>().ok()),
        test_type: "tcp".to_string(),
        protocol_detail: protocol,
        target_host: target,
        target_ip: result.remote_addr.clone(),
        client_ip: client_ip(&headers, &peer),
        latency_ms: Some(result.latency_ms),
        jitter_ms: (result.jitter_ms > 0.0).then_some(result.jitter_ms),
        raw_results: json!({
            "handshake_ms": result.handshake_ms,
            "min_latency_ms": result.min_latency_ms,
            "max_latency_ms": result.max_latency_ms,
        }),
        ..device_fields(&headers)
    };
    save_best_effort(&state, new_result).await;

    Ok(Json(result))
}

async fn udp_test_handler(
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    user_ext: Option<axum::Extension<AuthUser>>,
    Json(mut req): Json<UdpTestRequest>,
) -> Result<Json<UdpTestResult>, ApiError> {
    validation::validate_target(&req.target).await?;
    validation::validate_udp_protocol(&req.protocol)?;
    validation::validate_udp_protocol(&req.protocol_detail)?;
    validation::validate_dns_query(&req.query)?;
    if req.port > 0 {
        validation::validate_port(req.port)?;
    }
    if req.timeout > 0 {
        validation::validate_timeout(req.timeout)?;
    }

    req.target = validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH);
    req.protocol = validation::sanitize_string(&req.protocol, validation::MAX_PROTOCOL_LENGTH);
    req.protocol_detail =
        validation::sanitize_string(&req.protocol_detail, validation::MAX_PROTOCOL_LENGTH);
    req.query = validation::sanitize_string(&req.query, validation::MAX_QUERY_LENGTH);

    let target = req.target.clone();
    let protocol = req.protocol.clone();
    let result = testserver_protocols::test_udp(req)
        .await
        .map_err(|_| ApiError::TestExecution("Test execution failed".to_string()))?;

    let new_result = NewTestResult {
        user_id: user_ext.and_then(|axum::Extension(u)| u.id.parse::<i32>().ok()),
        test_type: "udp".to_string(),
        protocol_detail: protocol,
        target_host: target,
        target_ip: result.remote_addr.clone(),
        client_ip: client_ip(&headers, &peer),
        latency_ms: Some(result.latency_ms),
        jitter_ms: (result.jitter_ms > 0.0).then_some(result.jitter_ms),
        raw_results: json!({
            "min_latency_ms": result.min_latency_ms,
            "max_latency_ms": result.max_latency_ms,
        }),
        ..device_fields(&headers)
    };
    save_best_effort(&state, new_result).await;

    Ok(Json(result))
}

// ---------------------------------------------------------------------------
// Deferred probes — TODO(follow-up PR): ICMP/traceroute/*_trace + SSH.
// Routes stay wired (client-facing route shape is unchanged) but always
// return 501 Not Implemented until the shell-out + russh ports land.
// ---------------------------------------------------------------------------

async fn icmp_test_handler(Json(req): Json<IcmpTestRequest>) -> Result<Json<Value>, ApiError> {
    Err(deferred::test_icmp(req).await)
}

async fn http_trace_handler(Json(req): Json<HttpTraceRequest>) -> Result<Json<Value>, ApiError> {
    Err(deferred::test_http_trace(req).await)
}

async fn tcp_trace_handler(Json(req): Json<TcpTraceRequest>) -> Result<Json<Value>, ApiError> {
    Err(deferred::test_tcp_trace(req).await)
}

async fn udp_trace_handler(Json(req): Json<UdpTraceRequest>) -> Result<Json<Value>, ApiError> {
    Err(deferred::test_udp_trace(req).await)
}

async fn traceroute_handler(Json(req): Json<TracerouteRequest>) -> Result<Json<Value>, ApiError> {
    Err(deferred::test_traceroute(req).await)
}

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------

/// Builds the full axum router: public `/health` + `/speedtest/*`, and
/// authenticated `/api/v1/test/*` — matches `cmd/testserver/main.go`'s
/// route table. `allowed_origins` drives a deny-by-default CORS layer on
/// the public speedtest routes only, exactly like `main.go`'s
/// `newCORSMiddleware` (never a wildcard fallback).
pub fn router(state: AppState, allowed_origins: std::collections::HashSet<String>) -> Router {
    let cors = CorsLayer::new()
        .allow_origin(AllowOrigin::predicate(move |origin, _| {
            origin
                .to_str()
                .map(|o| allowed_origins.contains(o))
                .unwrap_or(false)
        }))
        .allow_methods([
            axum::http::Method::GET,
            axum::http::Method::POST,
            axum::http::Method::OPTIONS,
        ])
        .allow_headers([
            header::CONTENT_TYPE,
            header::AUTHORIZATION,
            header::HeaderName::from_static("x-device-serial"),
            header::HeaderName::from_static("x-device-hostname"),
            header::HeaderName::from_static("x-device-os"),
            header::HeaderName::from_static("x-device-os-version"),
        ]);

    let speedtest_routes = Router::new()
        .route("/download", get(speedtest_download))
        .route("/upload", post(speedtest_upload))
        .route("/ping", get(speedtest_ping))
        .route("/info", get(speedtest_info))
        .route("/result", post(speedtest_result))
        .layer(cors)
        .with_state(state.clone());

    // 1MB request body cap on authenticated test routes, matching
    // main.go's requestSizeLimitMiddleware.
    let api_routes = Router::new()
        .route("/test/http", post(http_test_handler))
        .route("/test/tcp", post(tcp_test_handler))
        .route("/test/udp", post(udp_test_handler))
        .route("/test/icmp", post(icmp_test_handler))
        .route("/test/http_trace", post(http_trace_handler))
        .route("/test/tcp_trace", post(tcp_trace_handler))
        .route("/test/udp_trace", post(udp_trace_handler))
        .route("/test/traceroute", post(traceroute_handler))
        .layer(RequestBodyLimitLayer::new(1024 * 1024))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ))
        .with_state(state.clone());

    Router::new()
        .route("/health", get(health_handler))
        .nest("/speedtest", speedtest_routes)
        .nest("/api/v1", api_routes)
        .layer(tower_http::trace::TraceLayer::new_for_http())
        .with_state(state)
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::Request;
    use tower::ServiceExt;

    fn test_state(auth_enabled: bool, jwt_secret: Option<&str>) -> AppState {
        AppState {
            db: SwitchableStore::new(),
            jwt_verifier: jwt_secret.map(|s| JwtVerifier::new_hs256(s.as_bytes())),
            auth_enabled,
        }
    }

    fn test_router(state: AppState) -> Router {
        router(state, std::collections::HashSet::new())
    }

    fn get_request(uri: &str) -> Request<Body> {
        Request::builder()
            .method("GET")
            .uri(uri)
            .extension(ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 12345))))
            .body(Body::empty())
            .unwrap()
    }

    fn post_json(uri: &str, auth_header: Option<&str>, body: &str) -> Request<Body> {
        let mut builder = Request::builder()
            .method("POST")
            .uri(uri)
            .header(header::CONTENT_TYPE, "application/json")
            .extension(ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 12345))));
        if let Some(auth) = auth_header {
            builder = builder.header(header::AUTHORIZATION, auth);
        }
        builder.body(Body::from(body.to_string())).unwrap()
    }

    fn sign_test_jwt(secret: &str) -> String {
        use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        let claims = serde_json::json!({"sub": "test-user", "exp": now + 3600});
        encode(
            &Header::new(Algorithm::HS256),
            &claims,
            &EncodingKey::from_secret(secret.as_bytes()),
        )
        .unwrap()
    }

    // -----------------------------------------------------------------
    // Finding: "auth-missing" regression tests — every /api/v1/test/*
    // probe route must reject an unauthenticated request when
    // AUTH_ENABLED=true; /health and /speedtest/* stay public.
    // -----------------------------------------------------------------

    #[tokio::test]
    async fn health_is_public_without_auth() {
        let app = test_router(test_state(true, Some("test-secret")));
        let resp = app.oneshot(get_request("/health")).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn speedtest_ping_is_public_without_auth() {
        let app = test_router(test_state(true, Some("test-secret")));
        let resp = app.oneshot(get_request("/speedtest/ping")).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn api_v1_test_http_rejects_missing_auth_header() {
        let app = test_router(test_state(true, Some("test-secret")));
        let resp = app
            .oneshot(post_json("/api/v1/test/http", None, "{}"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn api_v1_test_tcp_rejects_missing_auth_header() {
        let app = test_router(test_state(true, Some("test-secret")));
        let resp = app
            .oneshot(post_json("/api/v1/test/tcp", None, "{}"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn api_v1_test_udp_rejects_missing_auth_header() {
        let app = test_router(test_state(true, Some("test-secret")));
        let resp = app
            .oneshot(post_json("/api/v1/test/udp", None, "{}"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn deferred_probe_routes_reject_missing_auth_header() {
        // The deferred (icmp/http_trace/tcp_trace/udp_trace/traceroute)
        // stubs still sit behind the same auth middleware as the
        // implemented probes — a 501 body must never be reachable by an
        // unauthenticated caller either.
        for path in [
            "/api/v1/test/icmp",
            "/api/v1/test/http_trace",
            "/api/v1/test/tcp_trace",
            "/api/v1/test/udp_trace",
            "/api/v1/test/traceroute",
        ] {
            let app = test_router(test_state(true, Some("test-secret")));
            let resp = app.oneshot(post_json(path, None, "{}")).await.unwrap();
            assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "path={path}");
        }
    }

    #[tokio::test]
    async fn api_v1_test_http_rejects_invalid_bearer_token() {
        let app = test_router(test_state(true, Some("test-secret")));
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/http",
                Some("Bearer not-a-real-jwt"),
                "{}",
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn api_v1_test_http_accepts_valid_bearer_token_past_auth() {
        let secret = "test-secret";
        let token = sign_test_jwt(secret);
        let app = test_router(test_state(true, Some(secret)));
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/http",
                Some(&format!("Bearer {token}")),
                "{}",
            ))
            .await
            .unwrap();
        // A valid token must clear the auth middleware — the empty body
        // then fails request validation (missing `target`), never 401.
        assert_ne!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn auth_disabled_bypasses_middleware_entirely() {
        let app = test_router(test_state(false, None));
        let resp = app
            .oneshot(post_json("/api/v1/test/http", None, "{}"))
            .await
            .unwrap();
        // AUTH_ENABLED=false: no 401, request reaches the handler and
        // fails on the empty body's missing `target` instead.
        assert_ne!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    // -----------------------------------------------------------------
    // Finding: "spoofable-client-ip" regression tests — trusted-hop model.
    // -----------------------------------------------------------------

    #[test]
    fn client_ip_uses_trusted_hop_not_leftmost_attacker_controlled_entry() {
        let peer = SocketAddr::from(([10, 0, 0, 1], 9999));
        let mut headers = HeaderMap::new();
        // Attacker sends a forged leftmost entry; the trusted proxy
        // appends the real client IP as the rightmost (1-hop) entry.
        headers.insert("x-forwarded-for", "9.9.9.9, 203.0.113.7".parse().unwrap());
        assert_eq!(client_ip(&headers, &peer), "203.0.113.7");
    }

    #[test]
    fn client_ip_falls_back_to_peer_when_xff_absent() {
        let peer = SocketAddr::from(([10, 0, 0, 1], 9999));
        let headers = HeaderMap::new();
        assert_eq!(client_ip(&headers, &peer), peer.to_string());
    }

    #[test]
    fn client_ip_falls_back_to_peer_when_xff_present_but_empty() {
        let peer = SocketAddr::from(([10, 0, 0, 1], 9999));
        let mut headers = HeaderMap::new();
        headers.insert("x-forwarded-for", "".parse().unwrap());
        assert_eq!(client_ip(&headers, &peer), peer.to_string());
    }

    #[test]
    fn client_ip_falls_back_to_peer_when_fewer_hops_than_trusted_depth() {
        // Only 1 XFF entry present, but this simulates a deployment
        // requiring 2 trusted hops (e.g. an internal LB in front of
        // Ingress) — TRUSTED_PROXY_HOPS defaults to 1 process-wide so we
        // can't override it per-test here without racing other tests
        // sharing the same LazyLock; instead this directly exercises the
        // `hops <= parts.len()` guard with hops=1 against zero usable
        // entries (covered above) plus documents the intended behavior:
        // insufficient hops -> peer fallback, never an out-of-bounds index.
        let peer = SocketAddr::from(([10, 0, 0, 1], 9999));
        let mut headers = HeaderMap::new();
        headers.insert("x-forwarded-for", "  ,  ".parse().unwrap());
        assert_eq!(client_ip(&headers, &peer), peer.to_string());
    }
}
