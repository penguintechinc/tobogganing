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
use testserver_protocols::{
    http::{HttpTestRequest, HttpTestResult},
    icmp::{IcmpTestRequest, IcmpTestResult},
    tcp::{TcpTestRequest, TcpTestResult},
    trace::{HttpTraceRequest, TcpTraceRequest, TraceResult, TracerouteRequest, UdpTraceRequest},
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
        Self {
            db,
            jwt_verifier: cfg.jwt_verifier.clone(),
            auth_enabled: cfg.auth_enabled,
        }
    }
}

/// Auth middleware for `/api/v1/test/*` — `Bearer <token>` is verified as a
/// real ES256-signed JWT against the platform auth service's public key
/// (the security fix this migration makes); `ApiKey <key>` still resolves
/// via the database, unchanged from the Go behavior. `AUTH_ENABLED=false`
/// bypasses this entirely, matching `internal/auth.Authenticator.Middleware`'s
/// early return.
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
            tracing::warn!(
                "Bearer token presented but no JWT public key is configured — rejecting"
            );
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
    crate::telemetry::record_probe("speedtest_upload", duration.as_secs_f64(), true);

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
    let probe_start = Instant::now();
    let outcome = testserver_protocols::test_http(req).await;
    let probe_elapsed = probe_start.elapsed().as_secs_f64();
    let result =
        outcome.map_err(|_| ApiError::TestExecution("Test execution failed".to_string()))?;
    crate::telemetry::record_probe("http", probe_elapsed, result.success);

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
    let probe_start = Instant::now();
    let outcome = testserver_protocols::test_tcp(req).await;
    let probe_elapsed = probe_start.elapsed().as_secs_f64();
    let result =
        outcome.map_err(|_| ApiError::TestExecution("Test execution failed".to_string()))?;
    crate::telemetry::record_probe("tcp", probe_elapsed, result.success);

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
    let probe_start = Instant::now();
    let outcome = testserver_protocols::test_udp(req).await;
    let probe_elapsed = probe_start.elapsed().as_secs_f64();
    let result =
        outcome.map_err(|_| ApiError::TestExecution("Test execution failed".to_string()))?;
    crate::telemetry::record_probe("udp", probe_elapsed, result.success);

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
// ICMP + traceroute family — shell out to `ping`/`traceroute`/
// `tcptraceroute` and regex-parse stdout (see testserver_protocols::icmp /
// ::trace module docs). SSH banner probe remains deferred to a follow-up
// PR (tcp.rs's `ssh` protocol branch returns ApiError::NotImplemented).
// ---------------------------------------------------------------------------

async fn icmp_test_handler(
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    user_ext: Option<axum::Extension<AuthUser>>,
    Json(mut req): Json<IcmpTestRequest>,
) -> Result<Json<IcmpTestResult>, ApiError> {
    validation::validate_target(&req.target).await?;
    validation::validate_icmp_protocol(&req.protocol)?;
    validation::validate_icmp_protocol(&req.protocol_detail)?;
    if req.count > 0 {
        validation::validate_count(req.count)?;
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
    let probe_start = Instant::now();
    let outcome = testserver_protocols::test_icmp(req).await;
    let probe_elapsed = probe_start.elapsed().as_secs_f64();
    let result =
        outcome.map_err(|_| ApiError::TestExecution("Test execution failed".to_string()))?;
    crate::telemetry::record_probe("icmp", probe_elapsed, result.success);

    let new_result = NewTestResult {
        user_id: user_ext.and_then(|axum::Extension(u)| u.id.parse::<i32>().ok()),
        test_type: "icmp".to_string(),
        protocol_detail: protocol,
        target_host: target,
        target_ip: result.target.clone(),
        client_ip: client_ip(&headers, &peer),
        latency_ms: Some(result.latency_ms),
        jitter_ms: (result.jitter_ms > 0.0).then_some(result.jitter_ms),
        raw_results: json!({
            "packets_sent": result.packets_sent,
            "packets_received": result.packets_received,
            "packet_loss_percent": result.packet_loss_percent,
            "min_latency_ms": result.min_latency_ms,
            "max_latency_ms": result.max_latency_ms,
        }),
        ..device_fields(&headers)
    };
    save_best_effort(&state, new_result).await;

    Ok(Json(result))
}

/// Shared validate → sanitize → save wiring for the `*_trace`/`traceroute`
/// endpoints — every variant validates target/port/timeout the same way and
/// persists the same `TraceResult` shape, differing only in which
/// `testserver_protocols::trace` function runs and the request's port field.
async fn save_trace_result(
    state: &AppState,
    headers: &HeaderMap,
    peer: &SocketAddr,
    user_ext: Option<axum::Extension<AuthUser>>,
    test_type: &str,
    target: String,
    result: &TraceResult,
) {
    let new_result = NewTestResult {
        user_id: user_ext.and_then(|axum::Extension(u)| u.id.parse::<i32>().ok()),
        test_type: test_type.to_string(),
        protocol_detail: result.protocol.clone(),
        target_host: target,
        target_ip: result.target.clone(),
        client_ip: client_ip(headers, peer),
        latency_ms: Some(result.latency_ms),
        raw_results: Value::Object(result.raw_results.clone()),
        ..device_fields(headers)
    };
    save_best_effort(state, new_result).await;
}

async fn traceroute_handler(
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    user_ext: Option<axum::Extension<AuthUser>>,
    Json(mut req): Json<TracerouteRequest>,
) -> Result<Json<TraceResult>, ApiError> {
    validation::validate_target(&req.target).await?;
    if req.timeout > 0 {
        validation::validate_timeout(req.timeout)?;
    }
    req.target = validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH);

    let target = req.target.clone();
    let probe_start = Instant::now();
    let outcome = testserver_protocols::test_traceroute(req).await;
    let probe_elapsed = probe_start.elapsed().as_secs_f64();
    let result =
        outcome.map_err(|_| ApiError::TestExecution("Test execution failed".to_string()))?;
    crate::telemetry::record_probe("traceroute", probe_elapsed, result.success);

    save_trace_result(
        &state,
        &headers,
        &peer,
        user_ext,
        "traceroute",
        target,
        &result,
    )
    .await;
    Ok(Json(result))
}

async fn http_trace_handler(
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    user_ext: Option<axum::Extension<AuthUser>>,
    Json(mut req): Json<HttpTraceRequest>,
) -> Result<Json<TraceResult>, ApiError> {
    validation::validate_target(&req.target).await?;
    if req.port > 0 {
        validation::validate_port(req.port)?;
    }
    if req.timeout > 0 {
        validation::validate_timeout(req.timeout)?;
    }
    req.target = validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH);

    let target = req.target.clone();
    let probe_start = Instant::now();
    let outcome = testserver_protocols::test_http_trace(req).await;
    let probe_elapsed = probe_start.elapsed().as_secs_f64();
    let result =
        outcome.map_err(|_| ApiError::TestExecution("Test execution failed".to_string()))?;
    crate::telemetry::record_probe("http_trace", probe_elapsed, result.success);

    save_trace_result(
        &state,
        &headers,
        &peer,
        user_ext,
        "http_trace",
        target,
        &result,
    )
    .await;
    Ok(Json(result))
}

async fn tcp_trace_handler(
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    user_ext: Option<axum::Extension<AuthUser>>,
    Json(mut req): Json<TcpTraceRequest>,
) -> Result<Json<TraceResult>, ApiError> {
    validation::validate_target(&req.target).await?;
    if req.port > 0 {
        validation::validate_port(req.port)?;
    }
    if req.timeout > 0 {
        validation::validate_timeout(req.timeout)?;
    }
    req.target = validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH);

    let target = req.target.clone();
    let probe_start = Instant::now();
    let outcome = testserver_protocols::test_tcp_trace(req).await;
    let probe_elapsed = probe_start.elapsed().as_secs_f64();
    let result =
        outcome.map_err(|_| ApiError::TestExecution("Test execution failed".to_string()))?;
    crate::telemetry::record_probe("tcp_trace", probe_elapsed, result.success);

    save_trace_result(
        &state,
        &headers,
        &peer,
        user_ext,
        "tcp_trace",
        target,
        &result,
    )
    .await;
    Ok(Json(result))
}

async fn udp_trace_handler(
    State(state): State<AppState>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    user_ext: Option<axum::Extension<AuthUser>>,
    Json(mut req): Json<UdpTraceRequest>,
) -> Result<Json<TraceResult>, ApiError> {
    validation::validate_target(&req.target).await?;
    if req.port > 0 {
        validation::validate_port(req.port)?;
    }
    if req.timeout > 0 {
        validation::validate_timeout(req.timeout)?;
    }
    req.target = validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH);

    let target = req.target.clone();
    let probe_start = Instant::now();
    let outcome = testserver_protocols::test_udp_trace(req).await;
    let probe_elapsed = probe_start.elapsed().as_secs_f64();
    let result =
        outcome.map_err(|_| ApiError::TestExecution("Test execution failed".to_string()))?;
    crate::telemetry::record_probe("udp_trace", probe_elapsed, result.success);

    save_trace_result(
        &state,
        &headers,
        &peer,
        user_ext,
        "udp_trace",
        target,
        &result,
    )
    .await;
    Ok(Json(result))
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

    fn test_state(auth_enabled: bool, jwt_public_key_pem: Option<&str>) -> AppState {
        AppState {
            db: SwitchableStore::new(),
            jwt_verifier: jwt_public_key_pem.map(|pem| {
                JwtVerifier::new_es256(pem.as_bytes())
                    .expect("a freshly generated EC public key must build a verifier")
            }),
            auth_enabled,
        }
    }

    /// Generates a fresh, throwaway EC P-256 keypair as PKCS#8/SPKI PEM —
    /// generated at test time, never a fixed/committed key (mirrors
    /// `testserver_core::auth`'s identical test helper).
    fn generate_test_keypair() -> (String, String) {
        use p256::ecdsa::{SigningKey, VerifyingKey};
        use p256::pkcs8::{EncodePrivateKey, EncodePublicKey, LineEnding};
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

    /// Signs a structurally-complete test claim set via
    /// [`penguin_aaa::Es256Signer`] — the same primitive the platform auth
    /// service and `agents/node-agent`'s `MachineJwtSigner` sign with in
    /// production. `penguin_aaa::Claims` requires `sub`/`iss`/`aud`/`iat`/
    /// `exp`/`scope` structurally, unlike the pre-migration inline `Claims`
    /// this replaced (which only required `sub`/`exp`).
    fn sign_test_jwt(private_key_pem: &str) -> String {
        use penguin_aaa::{Claims, Es256Signer};
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        let claims = Claims::new(
            "test-user",
            "testserver-test",
            "testserver",
            now,
            now + 3600,
            "test:run",
        );
        Es256Signer::from_ec_pem(private_key_pem.as_bytes())
            .expect("a freshly generated EC PEM must load as a signing key")
            .sign(&claims)
            .expect("signing a well-formed claim set must succeed")
    }

    /// Forges an HS256-labeled token, HMAC-SHA256-signed with `secret` —
    /// used only to prove the auth middleware's `JwtVerifier` rejects it
    /// (alg-confusion guard); hand-rolled instead of pulling in a `base64`
    /// dependency just to construct one malformed test token.
    fn forge_hs256(secret: &[u8], header_json: &str, payload_json: &str) -> String {
        use hmac::{Hmac, Mac};
        use sha2::Sha256;
        let signing_input = format!(
            "{}.{}",
            b64url(header_json.as_bytes()),
            b64url(payload_json.as_bytes())
        );
        let mut mac = <Hmac<Sha256> as Mac>::new_from_slice(secret)
            .expect("HMAC-SHA256 accepts a key of any length");
        mac.update(signing_input.as_bytes());
        let tag = mac.finalize().into_bytes();
        format!("{signing_input}.{}", b64url(&tag))
    }

    /// Minimal unpadded base64url encoder for [`forge_hs256`] — deliberately
    /// hand-rolled instead of pulling in a `base64` dependency just to
    /// construct one forged test token.
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

    // -----------------------------------------------------------------
    // Finding: "auth-missing" regression tests — every /api/v1/test/*
    // probe route must reject an unauthenticated request when
    // AUTH_ENABLED=true; /health and /speedtest/* stay public.
    // -----------------------------------------------------------------

    #[tokio::test]
    async fn health_is_public_without_auth() {
        let (_, public_pem) = generate_test_keypair();
        let app = test_router(test_state(true, Some(&public_pem)));
        let resp = app.oneshot(get_request("/health")).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn speedtest_ping_is_public_without_auth() {
        let (_, public_pem) = generate_test_keypair();
        let app = test_router(test_state(true, Some(&public_pem)));
        let resp = app.oneshot(get_request("/speedtest/ping")).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn api_v1_test_http_rejects_missing_auth_header() {
        let (_, public_pem) = generate_test_keypair();
        let app = test_router(test_state(true, Some(&public_pem)));
        let resp = app
            .oneshot(post_json("/api/v1/test/http", None, "{}"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn api_v1_test_tcp_rejects_missing_auth_header() {
        let (_, public_pem) = generate_test_keypair();
        let app = test_router(test_state(true, Some(&public_pem)));
        let resp = app
            .oneshot(post_json("/api/v1/test/tcp", None, "{}"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn api_v1_test_udp_rejects_missing_auth_header() {
        let (_, public_pem) = generate_test_keypair();
        let app = test_router(test_state(true, Some(&public_pem)));
        let resp = app
            .oneshot(post_json("/api/v1/test/udp", None, "{}"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn icmp_and_trace_routes_reject_missing_auth_header() {
        // ICMP/traceroute-family probes sit behind the same auth middleware
        // as http/tcp/udp — an unauthenticated caller must never reach the
        // shell-out probes (or trigger a subprocess) either.
        for path in [
            "/api/v1/test/icmp",
            "/api/v1/test/http_trace",
            "/api/v1/test/tcp_trace",
            "/api/v1/test/udp_trace",
            "/api/v1/test/traceroute",
        ] {
            let (_, public_pem) = generate_test_keypair();
            let app = test_router(test_state(true, Some(&public_pem)));
            let resp = app.oneshot(post_json(path, None, "{}")).await.unwrap();
            assert_eq!(resp.status(), StatusCode::UNAUTHORIZED, "path={path}");
        }
    }

    #[tokio::test]
    async fn api_v1_test_http_rejects_invalid_bearer_token() {
        let (_, public_pem) = generate_test_keypair();
        let app = test_router(test_state(true, Some(&public_pem)));
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
        let (private_pem, public_pem) = generate_test_keypair();
        let token = sign_test_jwt(&private_pem);
        let app = test_router(test_state(true, Some(&public_pem)));
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

    #[tokio::test]
    async fn api_v1_test_http_rejects_bearer_when_no_jwt_verifier_configured() {
        // auth_enabled=true but jwt_verifier=None (e.g. AUTH_ENABLED=true
        // with only an API-key path configured, no JWT public key) — a
        // Bearer token must still be rejected, not panic on `.unwrap()`.
        let app = test_router(test_state(true, None));
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/http",
                Some("Bearer some-token"),
                "{}",
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn api_v1_test_http_accepts_valid_api_key() {
        use sea_orm::{DatabaseBackend, MockDatabase};
        use testserver_db::entities::users;

        let conn = MockDatabase::new(DatabaseBackend::Postgres)
            .append_query_results([vec![users::Model {
                id: 42,
                username: "svc".to_string(),
                email: "svc@example.com".to_string(),
                role: "maintainer".to_string(),
                ou_id: None,
                is_active: true,
                api_key: Some("valid-api-key".to_string()),
            }]])
            .into_connection();
        let db = SwitchableStore::new();
        db.set_connection(conn).await;
        let (_, public_pem) = generate_test_keypair();
        let app = test_router(AppState {
            db,
            jwt_verifier: Some(
                JwtVerifier::new_es256(public_pem.as_bytes())
                    .expect("a freshly generated EC public key must build a verifier"),
            ),
            auth_enabled: true,
        });

        let resp = app
            .oneshot(post_json(
                "/api/v1/test/http",
                Some("ApiKey valid-api-key"),
                "{}",
            ))
            .await
            .unwrap();
        // A valid API key must clear the auth middleware — the empty body
        // then fails request validation (missing `target`), never 401.
        assert_ne!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn api_v1_test_http_rejects_invalid_api_key() {
        let db = SwitchableStore::new(); // starts degraded — validate_api_key always Err
        let (_, public_pem) = generate_test_keypair();
        let app = test_router(AppState {
            db,
            jwt_verifier: Some(
                JwtVerifier::new_es256(public_pem.as_bytes())
                    .expect("a freshly generated EC public key must build a verifier"),
            ),
            auth_enabled: true,
        });
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/http",
                Some("ApiKey bogus-key"),
                "{}",
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    // -----------------------------------------------------------------
    // Alg-confusion guard, exercised through the real middleware (not just
    // JwtVerifier::verify in isolation — see testserver_core::auth's unit
    // tests for that layer).
    // -----------------------------------------------------------------

    #[tokio::test]
    async fn api_v1_test_http_rejects_hs256_alg_confusion_token() {
        let (_, public_pem) = generate_test_keypair();
        let app = test_router(test_state(true, Some(&public_pem)));

        // This forged, HS256-signed JWT reuses this verifier's own ES256
        // *public* key bytes as the HMAC secret — the textbook
        // asymmetric-to-HS256 confusion attack. It must be rejected because
        // `penguin_aaa::Es256Verifier` derives its accepted algorithm from
        // the key's own type (EC P-256 here) and has no HS256 code path at
        // all.
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        let forged = forge_hs256(
            public_pem.as_bytes(),
            r#"{"alg":"HS256","typ":"JWT"}"#,
            &format!(
                r#"{{"sub":"attacker","iss":"x","aud":"y","iat":{now},"exp":{},"scope":"admin:*"}}"#,
                now + 3600
            ),
        );

        let resp = app
            .oneshot(post_json(
                "/api/v1/test/http",
                Some(&format!("Bearer {forged}")),
                "{}",
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
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

    // -----------------------------------------------------------------
    // Speedtest handlers — public, no auth.
    // -----------------------------------------------------------------

    #[tokio::test]
    async fn speedtest_download_defaults_to_10mb() {
        let app = test_router(test_state(false, None));
        let resp = app
            .oneshot(get_request("/speedtest/download"))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
            .await
            .unwrap();
        assert_eq!(body.len(), 10 * 1024 * 1024);
    }

    #[tokio::test]
    async fn speedtest_download_honours_valid_size_param() {
        let app = test_router(test_state(false, None));
        let resp = app
            .oneshot(get_request("/speedtest/download?size=1"))
            .await
            .unwrap();
        let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
            .await
            .unwrap();
        assert_eq!(body.len(), 1024 * 1024);
    }

    #[tokio::test]
    async fn speedtest_download_clamps_out_of_range_size_to_default() {
        let app = test_router(test_state(false, None));
        // 0, negative-equivalent, and > 100 all fall through the
        // `filter(|&v| v > 0 && v <= 100)` guard to the 10MB default.
        for size in ["0", "-5", "500", "not-a-number"] {
            let app = app.clone();
            let resp = app
                .oneshot(get_request(&format!("/speedtest/download?size={size}")))
                .await
                .unwrap();
            let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
                .await
                .unwrap();
            assert_eq!(body.len(), 10 * 1024 * 1024, "size={size}");
        }
    }

    #[tokio::test]
    async fn speedtest_upload_reports_bytes_and_throughput() {
        let app = test_router(test_state(false, None));
        let payload = vec![b'x'; 4096];
        let req = Request::builder()
            .method("POST")
            .uri("/speedtest/upload")
            .extension(ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 12345))))
            .body(Body::from(payload))
            .unwrap();
        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["success"], true);
        assert_eq!(json["bytes_received"], 4096);
    }

    #[tokio::test]
    async fn speedtest_info_returns_static_metadata() {
        let app = test_router(test_state(false, None));
        let resp = app.oneshot(get_request("/speedtest/info")).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["name"], "WaddlePerf SpeedTest");
        assert_eq!(json["max_streams"], 32);
    }

    #[tokio::test]
    async fn speedtest_result_returns_500_when_db_disconnected() {
        // Unlike save_best_effort (used by the probe handlers),
        // speedtest_result propagates an insert failure via `?` rather than
        // swallowing it — a disconnected SwitchableStore therefore surfaces
        // as a real error response, not a silent best-effort 200.
        let app = test_router(test_state(false, None));
        let body = serde_json::json!({
            "download_mbps": 100.0,
            "upload_mbps": 50.0,
            "latency_ms": 12.5,
            "jitter_ms": 1.0,
            "server_url": "speedtest.local",
        });
        let resp = app
            .oneshot(post_json(
                "/speedtest/result",
                None,
                &serde_json::to_string(&body).unwrap(),
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::INTERNAL_SERVER_ERROR);
    }

    #[tokio::test]
    async fn speedtest_result_saves_and_returns_success_once_db_connected() {
        use sea_orm::{DatabaseBackend, MockDatabase};
        use testserver_db::entities::server_test_results;

        // `ActiveModelTrait::insert()` always calls `exec_with_returning()`
        // regardless of backend — on Postgres that's a single
        // `INSERT ... RETURNING` (a *query*), so the mock only needs a
        // queued query result for the returned row, no `MockExecResult` at
        // all. See testserver-db's `switchable_store_delegates_once_connected`
        // for the full rationale.
        let conn = MockDatabase::new(DatabaseBackend::Postgres)
            .append_query_results([vec![server_test_results::Model {
                id: 1,
                user_id: None,
                device_serial: "unknown".to_string(),
                device_hostname: "unknown".to_string(),
                device_os: "unknown".to_string(),
                device_os_version: "unknown".to_string(),
                test_type: "speedtest".to_string(),
                protocol_detail: "download_upload".to_string(),
                target_host: "speedtest.local".to_string(),
                target_ip: "self".to_string(),
                client_ip: String::new(),
                latency_ms: Some(12.5),
                throughput_mbps: Some(100.0),
                jitter_ms: Some(1.0),
                packet_loss_percent: None,
                raw_results: "{}".to_string(),
            }]])
            .into_connection();
        let db = SwitchableStore::new();
        db.set_connection(conn).await;
        let app = test_router(AppState {
            db,
            jwt_verifier: None,
            auth_enabled: false,
        });

        let body = serde_json::json!({
            "download_mbps": 100.0,
            "upload_mbps": 50.0,
            "latency_ms": 12.5,
            "jitter_ms": 1.0,
            "server_url": "speedtest.local",
        });
        let resp = app
            .oneshot(post_json(
                "/speedtest/result",
                None,
                &serde_json::to_string(&body).unwrap(),
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let resp_body = axum::body::to_bytes(resp.into_body(), usize::MAX)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&resp_body).unwrap();
        assert_eq!(json["success"], true);
    }

    // -----------------------------------------------------------------
    // Validation-failure paths — every `/api/v1/test/*` handler must reject
    // an invalid request *before* dispatching to a probe/subprocess.
    // -----------------------------------------------------------------

    fn auth_bypassed_state() -> AppState {
        test_state(false, None)
    }

    #[tokio::test]
    async fn http_test_rejects_empty_target() {
        let app = test_router(auth_bypassed_state());
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/http",
                None,
                r#"{"target":"","protocol":"http1"}"#,
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn http_test_rejects_invalid_protocol() {
        let app = test_router(auth_bypassed_state());
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/http",
                None,
                r#"{"target":"10.255.255.1","protocol":"gopher"}"#,
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn http_test_rejects_ssrf_blocked_loopback_target() {
        let app = test_router(auth_bypassed_state());
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/http",
                None,
                r#"{"target":"127.0.0.1","protocol":"http1"}"#,
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn tcp_test_rejects_invalid_port() {
        let app = test_router(auth_bypassed_state());
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/tcp",
                None,
                r#"{"target":"10.255.255.1","protocol":"raw","port":999999}"#,
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn udp_test_rejects_invalid_dns_query() {
        let app = test_router(auth_bypassed_state());
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/udp",
                None,
                r#"{"target":"10.255.255.1","protocol":"dns","query":"not a domain!!"}"#,
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn icmp_test_rejects_invalid_count() {
        // count must be > 0 to even enter the validate_count() check (0/negative
        // means "unset, use default" — see icmp_test_handler) — 1001 is
        // positive but exceeds MAX_COUNT, so it actually reaches and fails
        // validation instead of falling through to a real ping subprocess
        // against an unreachable target.
        let app = test_router(auth_bypassed_state());
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/icmp",
                None,
                r#"{"target":"10.255.255.1","protocol":"ping","count":1001}"#,
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn traceroute_rejects_invalid_timeout() {
        let app = test_router(auth_bypassed_state());
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/traceroute",
                None,
                r#"{"target":"10.255.255.1","timeout":9999}"#,
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn http_trace_rejects_invalid_port() {
        // port=0 is treated as "unset" by the handler's `if port > 0` guard
        // (falls through to a real probe attempt instead) — 999999 is
        // positive but out of the valid 1..=65535 range, so it actually
        // reaches and fails validate_port().
        let app = test_router(auth_bypassed_state());
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/http_trace",
                None,
                r#"{"target":"10.255.255.1","port":999999}"#,
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn tcp_trace_rejects_invalid_target() {
        let app = test_router(auth_bypassed_state());
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/tcp_trace",
                None,
                r#"{"target":""}"#,
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn udp_trace_rejects_invalid_target() {
        let app = test_router(auth_bypassed_state());
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/udp_trace",
                None,
                r#"{"target":""}"#,
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    // -----------------------------------------------------------------
    // Success paths — exercised against a real local listener bound to
    // this host's own (non-loopback) network address, since
    // `validate_target` deliberately rejects loopback as an SSRF guard
    // (see `testserver_core::validation`'s doc comment). Determined via a
    // connected-UDP-socket routing lookup — no packets are actually sent by
    // that `connect()` call, it only resolves the outbound interface.
    // -----------------------------------------------------------------

    fn local_test_ip() -> std::net::IpAddr {
        let sock = std::net::UdpSocket::bind("0.0.0.0:0").expect("bind an ephemeral UDP socket");
        sock.connect("8.8.8.8:80")
            .expect("connect() on a UDP socket only resolves a route, no packet is sent");
        sock.local_addr()
            .expect("a connected UDP socket always has a local address")
            .ip()
    }

    #[tokio::test]
    async fn tcp_test_succeeds_against_local_listener() {
        let ip = local_test_ip();
        let listener = tokio::net::TcpListener::bind((ip, 0)).await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            loop {
                if listener.accept().await.is_err() {
                    return;
                }
            }
        });

        let app = test_router(auth_bypassed_state());
        let body = format!(
            r#"{{"target":"{ip}","protocol":"raw","port":{},"timeout":3}}"#,
            addr.port()
        );
        let resp = app
            .oneshot(post_json("/api/v1/test/tcp", None, &body))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let resp_body = axum::body::to_bytes(resp.into_body(), usize::MAX)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&resp_body).unwrap();
        assert_eq!(json["success"], true);
    }

    #[tokio::test]
    async fn udp_test_succeeds_against_local_echo_listener() {
        let ip = local_test_ip();
        let sock = tokio::net::UdpSocket::bind((ip, 0)).await.unwrap();
        let addr = sock.local_addr().unwrap();
        tokio::spawn(async move {
            let mut buf = [0u8; 1024];
            if let Ok((n, peer)) = sock.recv_from(&mut buf).await {
                let _ = sock.send_to(&buf[..n], peer).await;
            }
        });

        let app = test_router(auth_bypassed_state());
        let body = format!(
            r#"{{"target":"{ip}","protocol":"raw","port":{},"timeout":3}}"#,
            addr.port()
        );
        let resp = app
            .oneshot(post_json("/api/v1/test/udp", None, &body))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let resp_body = axum::body::to_bytes(resp.into_body(), usize::MAX)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&resp_body).unwrap();
        assert_eq!(json["success"], true);
    }

    #[tokio::test]
    async fn http_test_succeeds_against_local_http1_server() {
        let ip = local_test_ip();
        let listener = tokio::net::TcpListener::bind((ip, 0)).await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            loop {
                let Ok((stream, _)) = listener.accept().await else {
                    return;
                };
                tokio::spawn(async move {
                    let io = hyper_util::rt::TokioIo::new(stream);
                    let service = hyper::service::service_fn(
                        move |_req: hyper::Request<hyper::body::Incoming>| {
                            let resp = hyper::Response::builder()
                                .status(200)
                                .body(http_body_util::Empty::<bytes::Bytes>::new())
                                .unwrap();
                            async move { Ok::<_, std::convert::Infallible>(resp) }
                        },
                    );
                    let _ = hyper::server::conn::http1::Builder::new()
                        .serve_connection(io, service)
                        .await;
                });
            }
        });

        let app = test_router(auth_bypassed_state());
        let body = format!(r#"{{"target":"http://{addr}","protocol":"http1","timeout":5}}"#);
        let resp = app
            .oneshot(post_json("/api/v1/test/http", None, &body))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let resp_body = axum::body::to_bytes(resp.into_body(), usize::MAX)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&resp_body).unwrap();
        assert_eq!(json["success"], true);
        assert_eq!(json["status_code"], 200);
    }

    #[tokio::test]
    async fn tcp_trace_succeeds_against_local_listener_via_dial_fallback() {
        // Mirrors testserver_protocols::trace's
        // `tcp_trace_fallback_dial_success_when_traceroute_unavailable` —
        // exercised here through the full authenticated handler + result
        // save path instead of the bare protocol function.
        let ip = local_test_ip();
        let listener = tokio::net::TcpListener::bind((ip, 0)).await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            loop {
                if listener.accept().await.is_err() {
                    return;
                }
            }
        });

        let app = test_router(auth_bypassed_state());
        let body = format!(r#"{{"target":"{ip}","port":{},"timeout":3}}"#, addr.port());
        let resp = app
            .oneshot(post_json("/api/v1/test/tcp_trace", None, &body))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn udp_trace_succeeds_via_dial_fallback() {
        // Mirrors testserver_protocols::trace's
        // `udp_trace_fallback_dial_is_always_success` — UDP is
        // connectionless, so this succeeds even without a real listener
        // (no `traceroute` binary is required in this sandbox either).
        let app = test_router(auth_bypassed_state());
        let resp = app
            .oneshot(post_json(
                "/api/v1/test/udp_trace",
                None,
                r#"{"target":"10.255.255.1","port":33434,"timeout":2}"#,
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
        let body = axum::body::to_bytes(resp.into_body(), usize::MAX)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["success"], true);
    }

    #[tokio::test]
    async fn http_trace_succeeds_against_local_http1_server() {
        let ip = local_test_ip();
        let listener = tokio::net::TcpListener::bind((ip, 0)).await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            loop {
                let Ok((stream, _)) = listener.accept().await else {
                    return;
                };
                tokio::spawn(async move {
                    let io = hyper_util::rt::TokioIo::new(stream);
                    let service = hyper::service::service_fn(
                        move |_req: hyper::Request<hyper::body::Incoming>| {
                            let resp = hyper::Response::builder()
                                .status(200)
                                .body(http_body_util::Empty::<bytes::Bytes>::new())
                                .unwrap();
                            async move { Ok::<_, std::convert::Infallible>(resp) }
                        },
                    );
                    let _ = hyper::server::conn::http1::Builder::new()
                        .serve_connection(io, service)
                        .await;
                });
            }
        });

        // The actual HTTP GET reconstructs its URL from `target` alone
        // (`{scheme}://{rest}`) — `port` only feeds the traceroute/
        // tcptraceroute subprocess args, so the port must be embedded in
        // `target` itself for the HTTP leg to reach this mock server.
        let app = test_router(auth_bypassed_state());
        let body = format!(r#"{{"target":"http://{addr}","timeout":5}}"#);
        let resp = app
            .oneshot(post_json("/api/v1/test/http_trace", None, &body))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn tcp_test_records_device_headers_when_present() {
        // Exercises header_or_unknown's "present and non-empty" branch —
        // every other test in this file omits these headers, hitting only
        // the "unknown" default.
        let ip = local_test_ip();
        let listener = tokio::net::TcpListener::bind((ip, 0)).await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            loop {
                if listener.accept().await.is_err() {
                    return;
                }
            }
        });

        let app = test_router(auth_bypassed_state());
        let mut req = post_json(
            "/api/v1/test/tcp",
            None,
            &format!(
                r#"{{"target":"{ip}","protocol":"raw","port":{},"timeout":3}}"#,
                addr.port()
            ),
        );
        let headers = req.headers_mut();
        headers.insert("x-device-serial", "SN123".parse().unwrap());
        headers.insert("x-device-hostname", "test-host".parse().unwrap());
        headers.insert("x-device-os", "linux".parse().unwrap());
        headers.insert("x-device-os-version", "6.8".parse().unwrap());
        let resp = app.oneshot(req).await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }
}
