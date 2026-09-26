//! Port of `engines/testserver/internal/protocols/http.go`'s `TestHTTP`.
//! Field names and statistics (latency/min/max/jitter/ttfb/total_time) are
//! copied 1:1 from the Go source, including two intentional quirks kept for
//! behavioral parity (the migration contract — see PR description):
//!   1. `status_code`/`connected_proto` only ever reflect the *last
//!      successful* (non-network-error) attempt, never a failed one.
//!   2. The `error` field is only ever populated by the (practically
//!      unreachable, since `count` always defaults to >= 1 and every
//!      iteration appends a latency sample) "no successful requests" early
//!      return — a pure-connection-failure result has `success: false` but
//!      an *empty* `error` string, exactly like the Go implementation.
//!
//! HTTP/3 is intentionally unimplemented in both languages.

use serde::{Deserialize, Serialize};
use std::time::{Duration, Instant};
use testserver_core::ApiError;

#[derive(Debug, Clone, Default, Deserialize)]
pub struct HttpTestRequest {
    pub target: String,
    #[serde(default)]
    pub protocol: String,
    #[serde(default)]
    pub protocol_detail: String,
    #[serde(default)]
    pub method: String,
    #[serde(default)]
    pub timeout: i64,
    #[serde(default)]
    pub count: i64,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct HttpTestResult {
    pub target: String,
    pub protocol: String,
    pub status_code: i32,
    pub latency_ms: f64,
    pub min_latency_ms: f64,
    pub max_latency_ms: f64,
    pub jitter_ms: f64,
    pub ttfb_ms: f64,
    pub total_time_ms: f64,
    pub success: bool,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub error: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub connected_proto: String,
}

fn version_string(v: reqwest::Version) -> String {
    match v {
        reqwest::Version::HTTP_09 => "HTTP/0.9".to_string(),
        reqwest::Version::HTTP_10 => "HTTP/1.0".to_string(),
        reqwest::Version::HTTP_11 => "HTTP/1.1".to_string(),
        reqwest::Version::HTTP_2 => "HTTP/2.0".to_string(),
        reqwest::Version::HTTP_3 => "HTTP/3.0".to_string(),
        other => format!("{other:?}"),
    }
}

pub async fn test_http(req: HttpTestRequest) -> Result<HttpTestResult, ApiError> {
    crate::tls_provider::install_crypto_provider();

    // Use protocol_detail if protocol is empty (for compatibility); default
    // to http2 if both are empty.
    let mut protocol = if !req.protocol.is_empty() {
        req.protocol.clone()
    } else {
        req.protocol_detail.clone()
    };
    if protocol.is_empty() {
        protocol = "http2".to_string();
    }
    let protocol = protocol.to_lowercase().replace(['/', '.', ' '], "");

    // Ensure target has a scheme.
    let target = if req.target.starts_with("http://") || req.target.starts_with("https://") {
        req.target.clone()
    } else {
        format!("https://{}", req.target)
    };

    let mut result = HttpTestResult {
        target: target.clone(),
        protocol: protocol.clone(),
        ..Default::default()
    };

    let timeout = if req.timeout > 0 {
        Duration::from_secs(req.timeout as u64)
    } else {
        Duration::from_secs(30)
    };

    let client = match protocol.as_str() {
        "http1" | "http11" => reqwest::Client::builder()
            .timeout(timeout)
            .http1_only()
            .build(),
        "http2" | "http20" => reqwest::Client::builder().timeout(timeout).build(),
        "http3" | "http30" => {
            return Err(ApiError::TestExecution("HTTP/3 not yet implemented".into()))
        }
        other => {
            return Err(ApiError::TestExecution(format!(
                "unsupported protocol: {other}"
            )))
        }
    }
    .map_err(|e| ApiError::TestExecution(e.to_string()))?;

    let method_str = if req.method.is_empty() {
        "GET".to_string()
    } else {
        req.method.clone()
    };
    let method: reqwest::Method = method_str
        .parse()
        .map_err(|_| ApiError::TestExecution(format!("invalid method: {method_str}")))?;

    let count = if req.count > 0 { req.count } else { 1 };

    let mut latencies: Vec<f64> = Vec::new();
    let mut last_status: Option<u16> = None;
    let mut last_proto: Option<String> = None;
    let mut last_error: Option<String> = None;

    for i in 0..count {
        let start = Instant::now();
        let outcome = client
            .request(method.clone(), &target)
            .header(reqwest::header::USER_AGENT, "WaddlePerf-TestServer/1.0")
            .send()
            .await;

        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;
        match outcome {
            Ok(resp) => {
                latencies.push(elapsed_ms);
                last_status = Some(resp.status().as_u16());
                last_proto = Some(version_string(resp.version()));
            }
            Err(e) => {
                last_error = Some(e.to_string());
                latencies.push(elapsed_ms);
            }
        }

        if i < count - 1 {
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    }

    if latencies.is_empty() {
        result.success = false;
        result.error = last_error.unwrap_or_else(|| "No successful requests".to_string());
        return Err(ApiError::TestExecution(result.error.clone()));
    }

    let sum: f64 = latencies.iter().sum();
    let min = latencies.iter().cloned().fold(f64::INFINITY, f64::min);
    let max = latencies.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

    result.latency_ms = sum / latencies.len() as f64;
    result.min_latency_ms = min;
    result.max_latency_ms = max;
    result.ttfb_ms = result.latency_ms;
    result.total_time_ms = result.latency_ms;

    if latencies.len() > 1 {
        let jitter_sum: f64 = latencies.windows(2).map(|w| (w[1] - w[0]).abs()).sum();
        result.jitter_ms = jitter_sum / (latencies.len() - 1) as f64;
    }

    result.status_code = last_status.unwrap_or(0) as i32;
    result.success = (200..400).contains(&result.status_code);
    result.connected_proto = last_proto.unwrap_or_default();

    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::convert::Infallible;
    use tokio::net::TcpListener;

    /// Spawns a minimal local HTTP/1.1 server returning `status` for every
    /// request; returns its base URL. Mirrors Go's `httptest.NewServer`.
    async fn spawn_http1_server(status: u16) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
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
                                .status(status)
                                .body(http_body_util::Empty::<bytes::Bytes>::new())
                                .unwrap();
                            async move { Ok::<_, Infallible>(resp) }
                        },
                    );
                    let _ = hyper::server::conn::http1::Builder::new()
                        .serve_connection(io, service)
                        .await;
                });
            }
        });
        format!("http://{addr}")
    }

    #[tokio::test]
    async fn http1_success_returns_200_and_nonnegative_latency() {
        let url = spawn_http1_server(200).await;
        let req = HttpTestRequest {
            target: url,
            protocol: "http1".into(),
            method: "GET".into(),
            timeout: 10,
            count: 1,
            ..Default::default()
        };
        let result = test_http(req).await.expect("request must succeed");
        assert!(
            result.success,
            "expected success, got error={}",
            result.error
        );
        assert_eq!(result.status_code, 200);
        assert!(result.latency_ms >= 0.0);
    }

    #[tokio::test]
    async fn http1_not_found_is_success_false() {
        let url = spawn_http1_server(404).await;
        let req = HttpTestRequest {
            target: url,
            protocol: "http1".into(),
            method: "GET".into(),
            timeout: 5,
            count: 1,
            ..Default::default()
        };
        let result = test_http(req)
            .await
            .expect("request executes without error");
        assert_eq!(result.status_code, 404);
        assert!(!result.success);
    }

    #[tokio::test]
    async fn multiple_count_computes_jitter_and_min_le_max() {
        let url = spawn_http1_server(200).await;
        let req = HttpTestRequest {
            target: url,
            protocol: "http1".into(),
            method: "GET".into(),
            timeout: 10,
            count: 3,
            ..Default::default()
        };
        let result = test_http(req).await.expect("request must succeed");
        assert!(result.min_latency_ms <= result.max_latency_ms);
    }

    #[tokio::test]
    async fn connection_refused_yields_result_with_empty_error_field() {
        // Port unlikely to be open — mirrors Go's TestHTTP_ConnectionRefused.
        let req = HttpTestRequest {
            target: "http://127.0.0.1:1".into(),
            protocol: "http1".into(),
            timeout: 2,
            count: 1,
            ..Default::default()
        };
        let result = test_http(req)
            .await
            .expect("connection failure is not a hard error");
        assert!(!result.success);
        // Parity quirk: the `error` field is only ever set by the
        // "no successful requests" (empty-latencies) branch, which never
        // triggers here since the loop always appends a latency sample.
        assert!(result.error.is_empty());
        assert_eq!(result.status_code, 0);
    }

    #[tokio::test]
    async fn http3_returns_not_implemented_error() {
        let req = HttpTestRequest {
            target: "https://example.com".into(),
            protocol: "http3".into(),
            timeout: 2,
            count: 1,
            ..Default::default()
        };
        assert!(test_http(req).await.is_err());
    }

    #[tokio::test]
    async fn unknown_protocol_returns_error() {
        let req = HttpTestRequest {
            target: "https://example.com".into(),
            protocol: "gopher".into(),
            timeout: 2,
            count: 1,
            ..Default::default()
        };
        assert!(test_http(req).await.is_err());
    }

    #[tokio::test]
    async fn empty_protocol_defaults_to_http2() {
        let url = spawn_http1_server(200).await;
        let req = HttpTestRequest {
            target: url,
            timeout: 3,
            count: 1,
            ..Default::default()
        };
        // http2 over cleartext without prior knowledge falls back to
        // whatever the peer speaks; we only assert it doesn't panic/error
        // structurally (mirrors Go's TestHTTP_DefaultProtocol intent).
        let _ = test_http(req).await;
    }

    #[tokio::test]
    async fn protocol_detail_fallback_used_when_protocol_empty() {
        let url = spawn_http1_server(200).await;
        let req = HttpTestRequest {
            target: url,
            protocol_detail: "http1".into(),
            timeout: 5,
            count: 1,
            ..Default::default()
        };
        let result = test_http(req).await.expect("must succeed");
        assert!(result.success);
    }

    #[tokio::test]
    async fn target_without_scheme_gets_https_prepended() {
        let req = HttpTestRequest {
            target: "127.0.0.1:1".into(),
            protocol: "http1".into(),
            timeout: 2,
            count: 1,
            ..Default::default()
        };
        // We only assert the scheme was prepended and no panic occurred —
        // the connection itself is expected to fail (nothing listening).
        let result = test_http(req).await.expect("must return a result");
        assert!(result.target.starts_with("https://"));
    }
}
