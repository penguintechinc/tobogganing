//! Port of `engines/testserver/internal/protocols/tcp.go`'s `TestTCP` — raw
//! TCP and TLS only in this PR; `ssh` is validated (accepted by
//! `testserver_core::validation::validate_tcp_protocol`) but returns
//! `ApiError::NotImplemented` until the russh-backed banner probe lands in
//! a follow-up PR (see PR description).
//!
//! Parity quirk preserved from the Go source: the aggregated result's
//! `error` field is only ever populated by the "no successful connections"
//! branch, which is unreachable in practice (`test_raw_tcp`/`test_tls_tcp`
//! always return a populated result, even on connection failure — mirrors
//! Go's `testRawTCP`/`testTLSTCP` always returning a non-nil `*TCPTestResult`).
//! A connection failure therefore surfaces as `success: false` with an
//! *empty* top-level `error` string, not the underlying error text.

use rustls_pki_types::ServerName;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::{Duration, Instant};
use testserver_core::ApiError;
use tokio::net::TcpStream;

#[derive(Debug, Clone, Default, Deserialize)]
pub struct TcpTestRequest {
    pub target: String,
    #[serde(default)]
    pub protocol: String,
    #[serde(default)]
    pub protocol_detail: String,
    #[serde(default)]
    pub port: i64,
    #[serde(default)]
    pub timeout: i64,
    #[serde(default)]
    pub count: i64,
}

fn is_zero_f64(v: &f64) -> bool {
    *v == 0.0
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct TcpTestResult {
    pub target: String,
    pub protocol: String,
    pub connected: bool,
    pub latency_ms: f64,
    pub min_latency_ms: f64,
    pub max_latency_ms: f64,
    pub jitter_ms: f64,
    #[serde(skip_serializing_if = "is_zero_f64")]
    pub handshake_ms: f64,
    pub success: bool,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub error: String,
    pub remote_addr: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub tls_version: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub ssh_version: String,
}

/// Extracts `host:port` from various input formats — naive colon-splitting,
/// matching the Go implementation's `parseTarget` (neither is fully
/// IPv6-bracket-aware; this is a direct port, not a hardening pass).
fn parse_target(target: &str, port_override: i64, protocol: &str) -> Result<String, ApiError> {
    if target.contains(':') && !target.contains("://") {
        return Ok(target.to_string());
    }

    let host;
    let mut port = 0i64;
    if target.contains("://") {
        let parsed = url::Url::parse(target)
            .map_err(|e| ApiError::TestExecution(format!("invalid target URL: {e}")))?;
        host = parsed.host_str().unwrap_or("").to_string();
        if let Some(p) = parsed.port() {
            port = p as i64;
        }
    } else {
        host = target.to_string();
    }

    if port_override > 0 {
        port = port_override;
    }
    if port == 0 {
        port = match protocol {
            "tls" => 443,
            "ssh" => 22,
            _ => 80,
        };
    }

    Ok(format!("{host}:{port}"))
}

async fn test_raw_tcp(target: &str, timeout_dur: Duration) -> TcpTestResult {
    let mut result = TcpTestResult {
        target: target.to_string(),
        protocol: "raw".to_string(),
        ..Default::default()
    };
    let start = Instant::now();

    match tokio::time::timeout(timeout_dur, TcpStream::connect(target)).await {
        Ok(Ok(stream)) => {
            result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
            result.connected = true;
            result.success = true;
            result.remote_addr = stream
                .peer_addr()
                .map(|a| a.to_string())
                .unwrap_or_default();
        }
        Ok(Err(e)) => {
            result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
            result.success = false;
            result.error = e.to_string();
        }
        Err(_) => {
            result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
            result.success = false;
            result.error = "i/o timeout".to_string();
        }
    }
    result
}

fn tls_version_to_string(version: Option<rustls::ProtocolVersion>) -> String {
    match version {
        Some(rustls::ProtocolVersion::TLSv1_2) => "TLS 1.2".to_string(),
        Some(rustls::ProtocolVersion::TLSv1_3) => "TLS 1.3".to_string(),
        Some(v) => format!("Unknown ({v:?})"),
        None => String::new(),
    }
}

fn tls_root_store() -> rustls::RootCertStore {
    let mut store = rustls::RootCertStore::empty();
    store.extend(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());
    store
}

async fn test_tls_tcp(target: &str, timeout_dur: Duration) -> TcpTestResult {
    let mut result = TcpTestResult {
        target: target.to_string(),
        protocol: "tls".to_string(),
        ..Default::default()
    };
    let start = Instant::now();

    let host = target.rsplit_once(':').map(|(h, _)| h).unwrap_or(target);
    let server_name = match ServerName::try_from(host.to_string()) {
        Ok(name) => name,
        Err(e) => {
            result.success = false;
            result.error = format!("invalid server name {host:?}: {e}");
            result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
            return result;
        }
    };

    let attempt = tokio::time::timeout(timeout_dur, async {
        let tcp = TcpStream::connect(target).await?;
        let remote_addr = tcp.peer_addr()?;

        let config = rustls::ClientConfig::builder()
            .with_root_certificates(tls_root_store())
            .with_no_client_auth();
        let connector = tokio_rustls::TlsConnector::from(Arc::new(config));

        let handshake_start = Instant::now();
        let tls_stream = connector.connect(server_name, tcp).await?;
        let handshake_ms = handshake_start.elapsed().as_secs_f64() * 1000.0;

        let version = tls_stream.get_ref().1.protocol_version();
        Ok::<_, std::io::Error>((remote_addr, handshake_ms, version))
    })
    .await;

    match attempt {
        Ok(Ok((remote_addr, handshake_ms, version))) => {
            result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
            result.connected = true;
            result.success = true;
            result.handshake_ms = handshake_ms;
            result.remote_addr = remote_addr.to_string();
            result.tls_version = tls_version_to_string(version);
        }
        Ok(Err(e)) => {
            result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
            result.success = false;
            result.error = format!("TLS handshake failed: {e}");
        }
        Err(_) => {
            result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
            result.success = false;
            result.error = "i/o timeout".to_string();
        }
    }
    result
}

pub async fn test_tcp(req: TcpTestRequest) -> Result<TcpTestResult, ApiError> {
    crate::tls_provider::install_crypto_provider();

    let mut protocol = if !req.protocol.is_empty() {
        req.protocol.clone()
    } else {
        req.protocol_detail.clone()
    };
    if protocol.is_empty() {
        protocol = "raw".to_string();
    }
    let mut protocol = protocol.to_lowercase().replace(' ', "");
    if protocol.contains("raw") {
        protocol = "raw".to_string();
    }

    match protocol.as_str() {
        "raw" | "tcp" | "tls" => {}
        "ssh" => return Err(ApiError::NotImplemented(
            "SSH banner probe not yet implemented in testserver-rs — tracked for a follow-up PR"
                .to_string(),
        )),
        other => {
            return Err(ApiError::TestExecution(format!(
                "unsupported protocol: {other}"
            )))
        }
    }

    let target = parse_target(&req.target, req.port, &protocol)?;
    let mut result = TcpTestResult {
        target: target.clone(),
        protocol: protocol.clone(),
        ..Default::default()
    };

    let timeout_dur = if req.timeout > 0 {
        Duration::from_secs(req.timeout as u64)
    } else {
        Duration::from_secs(10)
    };
    let count = if req.count > 0 { req.count } else { 1 };

    let mut latencies: Vec<f64> = Vec::new();
    let mut last_result: Option<TcpTestResult> = None;

    for i in 0..count {
        let r = match protocol.as_str() {
            "tls" => test_tls_tcp(&target, timeout_dur).await,
            _ => test_raw_tcp(&target, timeout_dur).await,
        };
        latencies.push(r.latency_ms);
        last_result = Some(r);

        if i < count - 1 {
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    }

    let Some(last_result) = last_result else {
        result.success = false;
        result.error = "No successful connections".to_string();
        return Err(ApiError::TestExecution(result.error.clone()));
    };

    let sum: f64 = latencies.iter().sum();
    let min = latencies.iter().cloned().fold(f64::INFINITY, f64::min);
    let max = latencies.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

    result.latency_ms = sum / latencies.len() as f64;
    result.min_latency_ms = min;
    result.max_latency_ms = max;

    if latencies.len() > 1 {
        let jitter_sum: f64 = latencies.windows(2).map(|w| (w[1] - w[0]).abs()).sum();
        result.jitter_ms = jitter_sum / (latencies.len() - 1) as f64;
    }

    // Copy fields from the last iteration — deliberately excludes `.error`,
    // matching Go's field-by-field copy that never touches `result.Error`.
    result.connected = last_result.connected;
    result.success = last_result.success;
    result.remote_addr = last_result.remote_addr;
    result.tls_version = last_result.tls_version;
    result.ssh_version = last_result.ssh_version;
    result.handshake_ms = last_result.handshake_ms;

    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::net::TcpListener;

    #[tokio::test]
    async fn raw_tcp_connects_to_local_listener() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            loop {
                if listener.accept().await.is_err() {
                    return;
                }
            }
        });

        let req = TcpTestRequest {
            target: addr.ip().to_string(),
            protocol: "raw".into(),
            port: addr.port() as i64,
            timeout: 3,
            count: 1,
            ..Default::default()
        };
        let result = test_tcp(req).await.expect("connect must succeed");
        assert!(result.connected);
        assert!(result.success);
        assert!(result.error.is_empty());
    }

    #[tokio::test]
    async fn raw_tcp_connection_refused_is_success_false_with_empty_error() {
        let req = TcpTestRequest {
            target: "127.0.0.1".into(),
            protocol: "raw".into(),
            port: 1, // privileged/closed port, connection refused
            timeout: 2,
            count: 1,
            ..Default::default()
        };
        let result = test_tcp(req)
            .await
            .expect("a refused connection is not a hard error");
        assert!(!result.success);
        // Parity quirk: outer result.error stays empty (see module docs).
        assert!(result.error.is_empty());
    }

    #[tokio::test]
    async fn multiple_count_computes_jitter() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            loop {
                if listener.accept().await.is_err() {
                    return;
                }
            }
        });

        let req = TcpTestRequest {
            target: addr.ip().to_string(),
            protocol: "raw".into(),
            port: addr.port() as i64,
            timeout: 3,
            count: 3,
            ..Default::default()
        };
        let result = test_tcp(req).await.expect("connect must succeed");
        assert!(result.min_latency_ms <= result.max_latency_ms);
    }

    #[tokio::test]
    async fn raw_tcp_variant_names_normalize_to_raw() {
        let req = TcpTestRequest {
            target: "127.0.0.1".into(),
            protocol: "Raw TCP".into(),
            port: 1,
            timeout: 1,
            count: 1,
            ..Default::default()
        };
        let result = test_tcp(req).await.expect("must return a result");
        assert_eq!(result.protocol, "raw");
    }

    #[tokio::test]
    async fn ssh_protocol_returns_not_implemented() {
        let req = TcpTestRequest {
            target: "127.0.0.1".into(),
            protocol: "ssh".into(),
            port: 22,
            timeout: 1,
            count: 1,
            ..Default::default()
        };
        assert!(test_tcp(req).await.is_err());
    }

    #[tokio::test]
    async fn unknown_protocol_returns_error() {
        let req = TcpTestRequest {
            target: "127.0.0.1".into(),
            protocol: "quic".into(),
            port: 1,
            timeout: 1,
            count: 1,
            ..Default::default()
        };
        assert!(test_tcp(req).await.is_err());
    }

    #[test]
    fn parse_target_uses_protocol_default_port() {
        assert_eq!(
            parse_target("example.com", 0, "tls").unwrap(),
            "example.com:443"
        );
        assert_eq!(
            parse_target("example.com", 0, "raw").unwrap(),
            "example.com:80"
        );
        assert_eq!(
            parse_target("example.com", 9000, "raw").unwrap(),
            "example.com:9000"
        );
        assert_eq!(
            parse_target("example.com:22", 0, "raw").unwrap(),
            "example.com:22"
        );
    }
}
