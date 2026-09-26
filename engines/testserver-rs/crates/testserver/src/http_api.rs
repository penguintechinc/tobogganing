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

fn client_ip(headers: &HeaderMap, connect_info: &SocketAddr) -> String {
    headers
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok())
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| connect_info.to_string())
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
    validation::validate_target(&req.target)?;
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
    validation::validate_target(&req.target)?;
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
    validation::validate_target(&req.target)?;
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
