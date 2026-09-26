//! Port of `engines/testserver/internal/protocols/udp.go`'s `TestUDP` — raw
//! UDP and DNS in this PR; UDP+TLS (DTLS) stays unimplemented in both
//! languages (Go: "DTLS not commonly implemented in Go stdlib").
//!
//! Deliberately permissive parity behavior preserved from Go: UDP is
//! connectionless, so a write-succeeded/read-timed-out raw UDP attempt is
//! still reported as `success: true` with `response: "No response (expected
//! for raw UDP)"` — never treated as a failure.

use hickory_resolver::config::{ConnectionConfig, NameServerConfig, ResolverConfig};
use hickory_resolver::net::runtime::TokioRuntimeProvider;
use hickory_resolver::TokioResolver;
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;
use std::time::{Duration, Instant};
use testserver_core::ApiError;
use tokio::net::UdpSocket;

#[derive(Debug, Clone, Default, Deserialize)]
pub struct UdpTestRequest {
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
    #[serde(default)]
    pub query: String,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct UdpTestResult {
    pub target: String,
    pub protocol: String,
    pub success: bool,
    pub latency_ms: f64,
    pub min_latency_ms: f64,
    pub max_latency_ms: f64,
    pub jitter_ms: f64,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub error: String,
    pub remote_addr: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub response: String,
}

/// Extracts `host:port` from various input formats — mirrors Go's
/// `parseUDPTarget` (same naive colon-splitting caveat as `tcp::parse_target`).
fn parse_udp_target(target: &str, port_override: i64, protocol: &str) -> Result<String, ApiError> {
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
            "dns" => 53,
            _ => 161, // SNMP default, matches Go's fallback for raw UDP
        };
    }

    Ok(format!("{host}:{port}"))
}

async fn test_raw_udp(target: &str, timeout_dur: Duration) -> UdpTestResult {
    let mut result = UdpTestResult {
        target: target.to_string(),
        protocol: "raw".to_string(),
        ..Default::default()
    };
    let start = Instant::now();

    // Bind/connect/send failures are hard errors. The read is timed
    // *separately* (matching Go's `conn.SetReadDeadline` — a per-operation
    // deadline, not one timeout wrapping the whole attempt): a read timeout
    // means "no response", which is still `success: true` for connectionless
    // UDP, never treated as a failure.
    let setup = tokio::time::timeout(timeout_dur, async {
        let sock = UdpSocket::bind("0.0.0.0:0").await?;
        sock.connect(target).await?;
        sock.send(b"PING").await?;
        Ok::<_, std::io::Error>(sock)
    })
    .await;

    let sock = match setup {
        Ok(Ok(sock)) => sock,
        Ok(Err(e)) => {
            result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
            result.success = false;
            result.error = format!("write error: {e}");
            return result;
        }
        Err(_) => {
            result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
            result.success = false;
            result.error = "i/o timeout".to_string();
            return result;
        }
    };

    let mut buf = [0u8; 1024];
    let recv = tokio::time::timeout(timeout_dur, sock.recv(&mut buf)).await;
    result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
    result.remote_addr = sock.peer_addr().map(|a| a.to_string()).unwrap_or_default();

    match recv {
        Ok(Ok(n)) => {
            result.success = true;
            result.response = format!("Received {n} bytes");
        }
        // Both a read error and a read timeout mean "no response" — still
        // successful connectivity, mirroring Go's testRawUDP exactly.
        _ => {
            result.success = true;
            result.response = "No response (expected for raw UDP)".to_string();
        }
    }
    result
}

async fn test_dns(target: &str, query: &str, timeout_dur: Duration) -> UdpTestResult {
    let mut result = UdpTestResult {
        target: target.to_string(),
        protocol: "dns".to_string(),
        remote_addr: target.to_string(),
        ..Default::default()
    };
    let query = if query.is_empty() {
        "google.com"
    } else {
        query
    };
    let start = Instant::now();

    let ns_addr: SocketAddr = match target.parse() {
        Ok(addr) => addr,
        Err(e) => {
            result.success = false;
            result.error = format!("invalid nameserver address {target:?}: {e}");
            result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
            return result;
        }
    };

    let mut connection = ConnectionConfig::udp();
    connection.port = ns_addr.port();
    let ns_config = NameServerConfig::new(ns_addr.ip(), true, vec![connection]);
    let resolver_config = ResolverConfig::from_name_servers(vec![ns_config]);

    let mut builder =
        TokioResolver::builder_with_config(resolver_config, TokioRuntimeProvider::default());
    builder.options_mut().timeout = timeout_dur;
    builder.options_mut().attempts = 1;
    let resolver = match builder.build() {
        Ok(r) => r,
        Err(e) => {
            result.success = false;
            result.error = e.to_string();
            result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
            return result;
        }
    };

    match tokio::time::timeout(timeout_dur, resolver.lookup_ip(query)).await {
        Ok(Ok(lookup)) => {
            let ips: Vec<String> = lookup.iter().map(|ip| ip.to_string()).collect();
            result.latency_ms = start.elapsed().as_secs_f64() * 1000.0;
            result.success = true;
            result.response = format!("Resolved {query} to {} IPs: {ips:?}", ips.len());
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

pub async fn test_udp(req: UdpTestRequest) -> Result<UdpTestResult, ApiError> {
    let mut protocol = if !req.protocol.is_empty() {
        req.protocol.clone()
    } else {
        req.protocol_detail.clone()
    };
    if protocol.is_empty() {
        protocol = "dns".to_string();
    }
    let protocol = protocol.to_lowercase();

    match protocol.as_str() {
        "raw" | "dns" => {}
        "tls" => {
            return Err(ApiError::TestExecution(
                "UDP+TLS (DTLS) not yet implemented".to_string(),
            ))
        }
        other => {
            return Err(ApiError::TestExecution(format!(
                "unsupported protocol: {other}"
            )))
        }
    }

    let target = parse_udp_target(&req.target, req.port, &protocol)?;
    let mut result = UdpTestResult {
        target: target.clone(),
        protocol: protocol.clone(),
        ..Default::default()
    };

    let timeout_dur = if req.timeout > 0 {
        Duration::from_secs(req.timeout as u64)
    } else {
        Duration::from_secs(5)
    };
    let count = if req.count > 0 { req.count } else { 1 };

    let mut latencies: Vec<f64> = Vec::new();
    let mut last_result: Option<UdpTestResult> = None;
    let mut last_error: Option<String> = None;

    for i in 0..count {
        let r = match protocol.as_str() {
            "dns" => test_dns(&target, &req.query, timeout_dur).await,
            _ => test_raw_udp(&target, timeout_dur).await,
        };
        if r.success {
            latencies.push(r.latency_ms);
            last_result = Some(r);
        } else {
            last_error = Some(r.error.clone());
        }

        if i < count - 1 {
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    }

    let Some(last_result) = last_result else {
        result.success = false;
        result.error = last_error.unwrap_or_else(|| "No successful requests".to_string());
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

    result.success = last_result.success;
    result.remote_addr = last_result.remote_addr;
    result.response = last_result.response;

    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::net::UdpSocket;

    #[tokio::test]
    async fn unsupported_protocol_returns_error() {
        let req = UdpTestRequest {
            target: "127.0.0.1".into(),
            port: 1234,
            protocol: "quic".into(),
            timeout: 2,
            count: 1,
            ..Default::default()
        };
        assert!(test_udp(req).await.is_err());
    }

    #[tokio::test]
    async fn dtls_not_implemented_returns_error() {
        let req = UdpTestRequest {
            target: "127.0.0.1".into(),
            port: 1234,
            protocol: "tls".into(),
            timeout: 2,
            count: 1,
            ..Default::default()
        };
        assert!(test_udp(req).await.is_err());
    }

    #[tokio::test]
    async fn raw_udp_echo_succeeds_with_response() {
        let sock = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let addr = sock.local_addr().unwrap();
        tokio::spawn(async move {
            let mut buf = [0u8; 1024];
            if let Ok((n, peer)) = sock.recv_from(&mut buf).await {
                let _ = sock.send_to(&buf[..n], peer).await;
            }
        });

        let req = UdpTestRequest {
            target: "127.0.0.1".into(),
            port: addr.port() as i64,
            protocol: "raw".into(),
            timeout: 3,
            count: 1,
            ..Default::default()
        };
        let result = test_udp(req).await.expect("echoed raw UDP must succeed");
        assert!(result.success);
        assert!(result.response.contains("Received"));
    }

    #[tokio::test]
    async fn raw_udp_no_response_is_still_success() {
        // Bind a socket that never replies — simulates a one-way sink.
        let sock = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let addr = sock.local_addr().unwrap();
        // Keep the socket alive for the duration of the test without replying.
        tokio::spawn(async move {
            let mut buf = [0u8; 1024];
            let _ = sock.recv_from(&mut buf).await;
        });

        let req = UdpTestRequest {
            target: "127.0.0.1".into(),
            port: addr.port() as i64,
            protocol: "raw".into(),
            timeout: 1,
            count: 1,
            ..Default::default()
        };
        let result = test_udp(req)
            .await
            .expect("no-response raw UDP is still success");
        assert!(
            result.success,
            "UDP no-response must still report success=true"
        );
        assert!(result.response.contains("No response"));
    }

    #[tokio::test]
    async fn multiple_count_raw_computes_jitter() {
        let sock = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let addr = sock.local_addr().unwrap();
        tokio::spawn(async move {
            let mut buf = [0u8; 1024];
            loop {
                match sock.recv_from(&mut buf).await {
                    Ok((n, peer)) => {
                        let _ = sock.send_to(&buf[..n], peer).await;
                    }
                    Err(_) => return,
                }
            }
        });

        let req = UdpTestRequest {
            target: "127.0.0.1".into(),
            port: addr.port() as i64,
            protocol: "raw".into(),
            timeout: 3,
            count: 3,
            ..Default::default()
        };
        let result = test_udp(req).await.expect("must succeed");
        assert!(result.min_latency_ms <= result.max_latency_ms);
    }

    #[test]
    fn parse_udp_target_uses_protocol_default_port() {
        assert_eq!(parse_udp_target("8.8.8.8", 0, "dns").unwrap(), "8.8.8.8:53");
        assert_eq!(
            parse_udp_target("8.8.8.8", 5000, "dns").unwrap(),
            "8.8.8.8:5000"
        );
        assert_eq!(
            parse_udp_target("8.8.8.8:53", 0, "dns").unwrap(),
            "8.8.8.8:53"
        );
    }
}
