//! Request shapes + stub entry points for probes deferred to a follow-up
//! PR: ICMP/traceroute/`*_trace` (all shell out to `ping`/`traceroute` via
//! `tokio::process::Command` + regex parsing in the Go source — see
//! `engines/testserver/internal/protocols/icmp.go` and `trace.go`) and the
//! SSH banner probe (`russh`, tracked in `tcp.rs`).
//!
//! TODO(follow-up PR): implement `test_icmp`/`test_traceroute`/
//! `test_http_trace`/`test_tcp_trace`/`test_udp_trace` by shelling out via
//! `tokio::process::Command` + `regex`, porting `icmp_test.go`/
//! `trace_test.go` (1.2K+ lines of Go parity tests) alongside them. Request
//! field names below already match the Go structs so the axum/tonic
//! handlers wired in this PR need no changes when the real implementation
//! lands.

use serde::Deserialize;
use testserver_core::ApiError;

#[derive(Debug, Clone, Default, Deserialize)]
pub struct IcmpTestRequest {
    pub target: String,
    #[serde(default)]
    pub protocol: String,
    #[serde(default)]
    pub protocol_detail: String,
    #[serde(default)]
    pub count: i64,
    #[serde(default)]
    pub timeout: i64,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct TracerouteRequest {
    pub target: String,
    #[serde(default)]
    pub timeout: i64,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct HttpTraceRequest {
    pub target: String,
    #[serde(default)]
    pub port: i64,
    #[serde(default)]
    pub timeout: i64,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct TcpTraceRequest {
    pub target: String,
    #[serde(default)]
    pub port: i64,
    #[serde(default)]
    pub timeout: i64,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct UdpTraceRequest {
    pub target: String,
    #[serde(default)]
    pub port: i64,
    #[serde(default)]
    pub timeout: i64,
}

fn deferred(probe: &str) -> ApiError {
    ApiError::NotImplemented(format!(
        "{probe} is not yet implemented in testserver-rs — tracked for a follow-up PR (shells out to ping/traceroute in the Go implementation; deferred pending a tokio::process::Command + regex port)"
    ))
}

// These always return an error (never `Ok`) — the return type is `ApiError`
// directly, not `Result<(), ApiError>`, so call sites never need an
// `.unwrap_err()`/`unreachable!()` to satisfy the type checker (both are
// unwrap-flavored patterns this org forbids outside tests).

pub async fn test_icmp(_req: IcmpTestRequest) -> ApiError {
    deferred("icmp")
}

pub async fn test_traceroute(_req: TracerouteRequest) -> ApiError {
    deferred("traceroute")
}

pub async fn test_http_trace(_req: HttpTraceRequest) -> ApiError {
    deferred("http_trace")
}

pub async fn test_tcp_trace(_req: TcpTraceRequest) -> ApiError {
    deferred("tcp_trace")
}

pub async fn test_udp_trace(_req: UdpTraceRequest) -> ApiError {
    deferred("udp_trace")
}
