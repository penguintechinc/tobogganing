//! tonic gRPC surface for `testserver.v1.TestService` — the new surface
//! this PR adds alongside the pre-existing REST routes (the Go testserver
//! was REST-only). Same validation and protocol probes as `http_api.rs`;
//! every request enforces the two-layer `api_version` versioning contract
//! (backend.md API Versioning): unknown/missing routes to `UNIMPLEMENTED`,
//! never a silent fall-through to a mismatched handler.

use std::sync::Arc;
use std::time::Instant;
use testserver_core::{check_api_version, validation, ApiError};
use testserver_db::SwitchableStore;
use tonic::{Request, Response, Status};

pub mod pb {
    tonic::include_proto!("testserver.v1");
}

use pb::test_service_server::{TestService, TestServiceServer};
use pb::{
    HealthRequest, HealthResponse, HttpTestRequest as PbHttpTestRequest,
    HttpTestResult as PbHttpTestResult, HttpTraceRequest as PbHttpTraceRequest,
    IcmpTestRequest as PbIcmpTestRequest, IcmpTestResult as PbIcmpTestResult,
    TcpTestRequest as PbTcpTestRequest, TcpTestResult as PbTcpTestResult,
    TcpTraceRequest as PbTcpTraceRequest, TraceResult as PbTraceResult,
    TracerouteRequest as PbTracerouteRequest, UdpTestRequest as PbUdpTestRequest,
    UdpTestResult as PbUdpTestResult, UdpTraceRequest as PbUdpTraceRequest,
};

pub struct TestServiceImpl {
    /// Reserved for the follow-up PR that wires gRPC result persistence
    /// (currently only the REST handlers save results — see
    /// `http_api.rs::save_best_effort`). Kept here now so adding it later
    /// is a method-body change, not a constructor signature change.
    #[allow(dead_code)]
    db: Arc<SwitchableStore>,
}

impl TestServiceImpl {
    pub fn into_server(db: Arc<SwitchableStore>) -> TestServiceServer<Self> {
        TestServiceServer::new(Self { db })
    }
}

fn to_status(err: ApiError) -> Status {
    Status::from(err)
}

#[tonic::async_trait]
impl TestService for TestServiceImpl {
    async fn health(
        &self,
        request: Request<HealthRequest>,
    ) -> Result<Response<HealthResponse>, Status> {
        check_api_version(&request.into_inner().api_version)?;
        Ok(Response::new(HealthResponse {
            status: "healthy".to_string(),
            version: "1.0.0".to_string(),
        }))
    }

    async fn run_http_test(
        &self,
        request: Request<PbHttpTestRequest>,
    ) -> Result<Response<PbHttpTestResult>, Status> {
        let req = request.into_inner();
        check_api_version(&req.api_version)?;

        validation::validate_target(&req.target)
            .await
            .map_err(to_status)?;
        validation::validate_http_protocol(&req.protocol).map_err(to_status)?;
        validation::validate_http_protocol(&req.protocol_detail).map_err(to_status)?;
        validation::validate_http_method(&req.method).map_err(to_status)?;
        if req.timeout > 0 {
            validation::validate_timeout(req.timeout as i64).map_err(to_status)?;
        }

        let inner = testserver_protocols::http::HttpTestRequest {
            target: validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH),
            protocol: validation::sanitize_string(&req.protocol, validation::MAX_PROTOCOL_LENGTH),
            protocol_detail: validation::sanitize_string(
                &req.protocol_detail,
                validation::MAX_PROTOCOL_LENGTH,
            ),
            method: validation::sanitize_string(&req.method, validation::MAX_METHOD_LENGTH),
            timeout: req.timeout as i64,
            count: req.count as i64,
        };

        let probe_start = Instant::now();
        let outcome = testserver_protocols::test_http(inner).await;
        let elapsed = probe_start.elapsed().as_secs_f64();
        let result = outcome.map_err(to_status)?;
        crate::telemetry::record_probe("http", elapsed, result.success);

        Ok(Response::new(PbHttpTestResult {
            target: result.target,
            protocol: result.protocol,
            status_code: result.status_code,
            latency_ms: result.latency_ms,
            min_latency_ms: result.min_latency_ms,
            max_latency_ms: result.max_latency_ms,
            jitter_ms: result.jitter_ms,
            ttfb_ms: result.ttfb_ms,
            total_time_ms: result.total_time_ms,
            success: result.success,
            error: result.error,
            connected_proto: result.connected_proto,
        }))
    }

    async fn run_tcp_test(
        &self,
        request: Request<PbTcpTestRequest>,
    ) -> Result<Response<PbTcpTestResult>, Status> {
        let req = request.into_inner();
        check_api_version(&req.api_version)?;

        validation::validate_target(&req.target)
            .await
            .map_err(to_status)?;
        validation::validate_tcp_protocol(&req.protocol).map_err(to_status)?;
        validation::validate_tcp_protocol(&req.protocol_detail).map_err(to_status)?;
        if req.port > 0 {
            validation::validate_port(req.port as i64).map_err(to_status)?;
        }
        if req.timeout > 0 {
            validation::validate_timeout(req.timeout as i64).map_err(to_status)?;
        }

        let inner = testserver_protocols::tcp::TcpTestRequest {
            target: validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH),
            protocol: validation::sanitize_string(&req.protocol, validation::MAX_PROTOCOL_LENGTH),
            protocol_detail: validation::sanitize_string(
                &req.protocol_detail,
                validation::MAX_PROTOCOL_LENGTH,
            ),
            port: req.port as i64,
            timeout: req.timeout as i64,
            count: req.count as i64,
        };

        let probe_start = Instant::now();
        let outcome = testserver_protocols::test_tcp(inner).await;
        let elapsed = probe_start.elapsed().as_secs_f64();
        let result = outcome.map_err(to_status)?;
        crate::telemetry::record_probe("tcp", elapsed, result.success);

        Ok(Response::new(PbTcpTestResult {
            target: result.target,
            protocol: result.protocol,
            connected: result.connected,
            latency_ms: result.latency_ms,
            min_latency_ms: result.min_latency_ms,
            max_latency_ms: result.max_latency_ms,
            jitter_ms: result.jitter_ms,
            handshake_ms: result.handshake_ms,
            success: result.success,
            error: result.error,
            remote_addr: result.remote_addr,
            tls_version: result.tls_version,
            ssh_version: result.ssh_version,
        }))
    }

    async fn run_udp_test(
        &self,
        request: Request<PbUdpTestRequest>,
    ) -> Result<Response<PbUdpTestResult>, Status> {
        let req = request.into_inner();
        check_api_version(&req.api_version)?;

        validation::validate_target(&req.target)
            .await
            .map_err(to_status)?;
        validation::validate_udp_protocol(&req.protocol).map_err(to_status)?;
        validation::validate_udp_protocol(&req.protocol_detail).map_err(to_status)?;
        validation::validate_dns_query(&req.query).map_err(to_status)?;
        if req.port > 0 {
            validation::validate_port(req.port as i64).map_err(to_status)?;
        }
        if req.timeout > 0 {
            validation::validate_timeout(req.timeout as i64).map_err(to_status)?;
        }

        let inner = testserver_protocols::udp::UdpTestRequest {
            target: validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH),
            protocol: validation::sanitize_string(&req.protocol, validation::MAX_PROTOCOL_LENGTH),
            protocol_detail: validation::sanitize_string(
                &req.protocol_detail,
                validation::MAX_PROTOCOL_LENGTH,
            ),
            port: req.port as i64,
            timeout: req.timeout as i64,
            count: req.count as i64,
            query: validation::sanitize_string(&req.query, validation::MAX_QUERY_LENGTH),
        };

        let probe_start = Instant::now();
        let outcome = testserver_protocols::test_udp(inner).await;
        let elapsed = probe_start.elapsed().as_secs_f64();
        let result = outcome.map_err(to_status)?;
        crate::telemetry::record_probe("udp", elapsed, result.success);

        Ok(Response::new(PbUdpTestResult {
            target: result.target,
            protocol: result.protocol,
            success: result.success,
            latency_ms: result.latency_ms,
            min_latency_ms: result.min_latency_ms,
            max_latency_ms: result.max_latency_ms,
            jitter_ms: result.jitter_ms,
            error: result.error,
            remote_addr: result.remote_addr,
            response: result.response,
        }))
    }

    async fn run_icmp_test(
        &self,
        request: Request<PbIcmpTestRequest>,
    ) -> Result<Response<PbIcmpTestResult>, Status> {
        let req = request.into_inner();
        check_api_version(&req.api_version)?;

        validation::validate_icmp_protocol(&req.protocol).map_err(to_status)?;
        validation::validate_icmp_protocol(&req.protocol_detail).map_err(to_status)?;
        if req.timeout > 0 {
            validation::validate_timeout(req.timeout as i64).map_err(to_status)?;
        }
        if req.count > 0 {
            validation::validate_count(req.count as i64).map_err(to_status)?;
        }

        let inner = testserver_protocols::icmp::IcmpTestRequest {
            target: validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH),
            protocol: validation::sanitize_string(&req.protocol, validation::MAX_PROTOCOL_LENGTH),
            protocol_detail: validation::sanitize_string(
                &req.protocol_detail,
                validation::MAX_PROTOCOL_LENGTH,
            ),
            count: req.count as i64,
            timeout: req.timeout as i64,
        };

        let probe_start = Instant::now();
        let outcome = testserver_protocols::test_icmp(inner).await;
        let elapsed = probe_start.elapsed().as_secs_f64();
        let result = outcome.map_err(to_status)?;
        crate::telemetry::record_probe("icmp", elapsed, result.success);

        Ok(Response::new(PbIcmpTestResult {
            target: result.target,
            protocol: result.protocol,
            success: result.success,
            packets_sent: result.packets_sent as i32,
            packets_received: result.packets_received as i32,
            packet_loss_percent: result.packet_loss_percent,
            latency_ms: result.latency_ms,
            min_latency_ms: result.min_latency_ms,
            max_latency_ms: result.max_latency_ms,
            jitter_ms: result.jitter_ms,
            error: result.error,
            hops: result.hops,
        }))
    }

    async fn run_traceroute(
        &self,
        request: Request<PbTracerouteRequest>,
    ) -> Result<Response<PbTraceResult>, Status> {
        let req = request.into_inner();
        check_api_version(&req.api_version)?;
        validation::validate_target(&req.target)
            .await
            .map_err(to_status)?;
        if req.timeout > 0 {
            validation::validate_timeout(req.timeout as i64).map_err(to_status)?;
        }

        let inner = testserver_protocols::trace::TracerouteRequest {
            target: validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH),
            timeout: req.timeout as i64,
        };
        let probe_start = Instant::now();
        let outcome = testserver_protocols::test_traceroute(inner).await;
        let elapsed = probe_start.elapsed().as_secs_f64();
        let result = outcome.map_err(to_status)?;
        crate::telemetry::record_probe("traceroute", elapsed, result.success);
        Ok(Response::new(to_pb_trace_result(result)))
    }

    async fn run_http_trace(
        &self,
        request: Request<PbHttpTraceRequest>,
    ) -> Result<Response<PbTraceResult>, Status> {
        let req = request.into_inner();
        check_api_version(&req.api_version)?;
        validation::validate_target(&req.target)
            .await
            .map_err(to_status)?;
        if req.port > 0 {
            validation::validate_port(req.port as i64).map_err(to_status)?;
        }
        if req.timeout > 0 {
            validation::validate_timeout(req.timeout as i64).map_err(to_status)?;
        }

        let inner = testserver_protocols::trace::HttpTraceRequest {
            target: validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH),
            port: req.port as i64,
            timeout: req.timeout as i64,
        };
        let probe_start = Instant::now();
        let outcome = testserver_protocols::test_http_trace(inner).await;
        let elapsed = probe_start.elapsed().as_secs_f64();
        let result = outcome.map_err(to_status)?;
        crate::telemetry::record_probe("http_trace", elapsed, result.success);
        Ok(Response::new(to_pb_trace_result(result)))
    }

    async fn run_tcp_trace(
        &self,
        request: Request<PbTcpTraceRequest>,
    ) -> Result<Response<PbTraceResult>, Status> {
        let req = request.into_inner();
        check_api_version(&req.api_version)?;
        validation::validate_target(&req.target)
            .await
            .map_err(to_status)?;
        if req.port > 0 {
            validation::validate_port(req.port as i64).map_err(to_status)?;
        }
        if req.timeout > 0 {
            validation::validate_timeout(req.timeout as i64).map_err(to_status)?;
        }

        let inner = testserver_protocols::trace::TcpTraceRequest {
            target: validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH),
            port: req.port as i64,
            timeout: req.timeout as i64,
        };
        let probe_start = Instant::now();
        let outcome = testserver_protocols::test_tcp_trace(inner).await;
        let elapsed = probe_start.elapsed().as_secs_f64();
        let result = outcome.map_err(to_status)?;
        crate::telemetry::record_probe("tcp_trace", elapsed, result.success);
        Ok(Response::new(to_pb_trace_result(result)))
    }

    async fn run_udp_trace(
        &self,
        request: Request<PbUdpTraceRequest>,
    ) -> Result<Response<PbTraceResult>, Status> {
        let req = request.into_inner();
        check_api_version(&req.api_version)?;
        validation::validate_target(&req.target)
            .await
            .map_err(to_status)?;
        if req.port > 0 {
            validation::validate_port(req.port as i64).map_err(to_status)?;
        }
        if req.timeout > 0 {
            validation::validate_timeout(req.timeout as i64).map_err(to_status)?;
        }

        let inner = testserver_protocols::trace::UdpTraceRequest {
            target: validation::sanitize_string(&req.target, validation::MAX_TARGET_LENGTH),
            port: req.port as i64,
            timeout: req.timeout as i64,
        };
        let probe_start = Instant::now();
        let outcome = testserver_protocols::test_udp_trace(inner).await;
        let elapsed = probe_start.elapsed().as_secs_f64();
        let result = outcome.map_err(to_status)?;
        crate::telemetry::record_probe("udp_trace", elapsed, result.success);
        Ok(Response::new(to_pb_trace_result(result)))
    }
}

/// Converts a `testserver_protocols::trace::TraceResult` to its gRPC wire
/// shape — `raw_results` (a `serde_json::Map`, the Rust equivalent of Go's
/// `map[string]interface{}`) has no direct proto3 scalar/message
/// equivalent in this workspace (no `google.protobuf.Struct` dependency),
/// so it's carried as a JSON-encoded string. REST callers (`http_api.rs`)
/// get the native nested JSON object instead — this flattening only
/// affects the gRPC surface.
fn to_pb_trace_result(result: testserver_protocols::trace::TraceResult) -> PbTraceResult {
    PbTraceResult {
        target: result.target,
        protocol: result.protocol,
        success: result.success,
        latency_ms: result.latency_ms,
        hops: result.hops,
        error: result.error,
        route_info: result.route_info,
        raw_results_json: if result.raw_results.is_empty() {
            String::new()
        } else {
            serde_json::to_string(&result.raw_results).unwrap_or_default()
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn health_rejects_unknown_api_version() {
        let svc = TestServiceImpl {
            db: SwitchableStore::new(),
        };
        let resp = svc
            .health(Request::new(HealthRequest {
                api_version: "v99".to_string(),
            }))
            .await;
        let err = resp.unwrap_err();
        assert_eq!(err.code(), tonic::Code::Unimplemented);
        assert!(err.message().contains("api_version"));
    }

    #[tokio::test]
    async fn health_accepts_v1() {
        let svc = TestServiceImpl {
            db: SwitchableStore::new(),
        };
        let resp = svc
            .health(Request::new(HealthRequest {
                api_version: "v1".to_string(),
            }))
            .await
            .expect("v1 must be accepted");
        assert_eq!(resp.into_inner().status, "healthy");
    }

    fn local_test_ip() -> std::net::IpAddr {
        let sock = std::net::UdpSocket::bind("0.0.0.0:0").expect("bind an ephemeral UDP socket");
        sock.connect("8.8.8.8:80")
            .expect("connect() on a UDP socket only resolves a route, no packet is sent");
        sock.local_addr()
            .expect("a connected UDP socket always has a local address")
            .ip()
    }

    #[tokio::test]
    async fn run_http_test_rejects_unknown_api_version() {
        let svc = TestServiceImpl {
            db: SwitchableStore::new(),
        };
        let err = svc
            .run_http_test(Request::new(PbHttpTestRequest {
                api_version: "v99".to_string(),
                target: "10.255.255.1".to_string(),
                protocol: "http1".to_string(),
                ..Default::default()
            }))
            .await
            .unwrap_err();
        assert_eq!(err.code(), tonic::Code::Unimplemented);
    }

    #[tokio::test]
    async fn run_http_test_rejects_invalid_target() {
        let svc = TestServiceImpl {
            db: SwitchableStore::new(),
        };
        let err = svc
            .run_http_test(Request::new(PbHttpTestRequest {
                api_version: "v1".to_string(),
                target: String::new(),
                protocol: "http1".to_string(),
                ..Default::default()
            }))
            .await
            .unwrap_err();
        assert_eq!(err.code(), tonic::Code::InvalidArgument);
    }

    #[tokio::test]
    async fn run_tcp_test_rejects_invalid_protocol() {
        let svc = TestServiceImpl {
            db: SwitchableStore::new(),
        };
        let err = svc
            .run_tcp_test(Request::new(PbTcpTestRequest {
                api_version: "v1".to_string(),
                target: "10.255.255.1".to_string(),
                protocol: "quic".to_string(),
                ..Default::default()
            }))
            .await
            .unwrap_err();
        assert_eq!(err.code(), tonic::Code::InvalidArgument);
    }

    #[tokio::test]
    async fn run_tcp_test_succeeds_against_local_listener() {
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

        let svc = TestServiceImpl {
            db: SwitchableStore::new(),
        };
        let resp = svc
            .run_tcp_test(Request::new(PbTcpTestRequest {
                api_version: "v1".to_string(),
                target: ip.to_string(),
                protocol: "raw".to_string(),
                port: addr.port() as i32,
                timeout: 3,
                ..Default::default()
            }))
            .await
            .expect("must succeed");
        assert!(resp.into_inner().success);
    }

    #[tokio::test]
    async fn run_udp_test_rejects_invalid_dns_query() {
        let svc = TestServiceImpl {
            db: SwitchableStore::new(),
        };
        let err = svc
            .run_udp_test(Request::new(PbUdpTestRequest {
                api_version: "v1".to_string(),
                target: "10.255.255.1".to_string(),
                protocol: "dns".to_string(),
                query: "not a domain!!".to_string(),
                ..Default::default()
            }))
            .await
            .unwrap_err();
        assert_eq!(err.code(), tonic::Code::InvalidArgument);
    }

    #[tokio::test]
    async fn run_icmp_test_rejects_invalid_count() {
        // count must be > 0 to enter the validate_count() check at all (see
        // run_icmp_test's `if req.count > 0` guard) — 1001 is positive but
        // exceeds MAX_COUNT, so it actually reaches and fails validation
        // instead of falling through to a real ping subprocess.
        let svc = TestServiceImpl {
            db: SwitchableStore::new(),
        };
        let err = svc
            .run_icmp_test(Request::new(PbIcmpTestRequest {
                api_version: "v1".to_string(),
                target: "10.255.255.1".to_string(),
                protocol: "ping".to_string(),
                count: 1001,
                ..Default::default()
            }))
            .await
            .unwrap_err();
        assert_eq!(err.code(), tonic::Code::InvalidArgument);
    }

    #[tokio::test]
    async fn run_traceroute_rejects_invalid_target() {
        let svc = TestServiceImpl {
            db: SwitchableStore::new(),
        };
        let err = svc
            .run_traceroute(Request::new(PbTracerouteRequest {
                api_version: "v1".to_string(),
                target: String::new(),
                ..Default::default()
            }))
            .await
            .unwrap_err();
        assert_eq!(err.code(), tonic::Code::InvalidArgument);
    }

    #[tokio::test]
    async fn run_http_trace_rejects_invalid_port() {
        let svc = TestServiceImpl {
            db: SwitchableStore::new(),
        };
        let err = svc
            .run_http_trace(Request::new(PbHttpTraceRequest {
                api_version: "v1".to_string(),
                target: "10.255.255.1".to_string(),
                port: 999_999,
                ..Default::default()
            }))
            .await
            .unwrap_err();
        assert_eq!(err.code(), tonic::Code::InvalidArgument);
    }

    #[tokio::test]
    async fn run_tcp_trace_succeeds_against_local_listener_via_dial_fallback() {
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

        let svc = TestServiceImpl {
            db: SwitchableStore::new(),
        };
        let resp = svc
            .run_tcp_trace(Request::new(PbTcpTraceRequest {
                api_version: "v1".to_string(),
                target: ip.to_string(),
                port: addr.port() as i32,
                timeout: 3,
            }))
            .await
            .expect("must succeed");
        assert!(resp.into_inner().success);
    }

    #[tokio::test]
    async fn run_udp_trace_rejects_invalid_target() {
        let svc = TestServiceImpl {
            db: SwitchableStore::new(),
        };
        let err = svc
            .run_udp_trace(Request::new(PbUdpTraceRequest {
                api_version: "v1".to_string(),
                target: String::new(),
                ..Default::default()
            }))
            .await
            .unwrap_err();
        assert_eq!(err.code(), tonic::Code::InvalidArgument);
    }

    #[test]
    fn to_pb_trace_result_empty_raw_results_yields_empty_json_string() {
        let result = testserver_protocols::trace::TraceResult {
            raw_results: serde_json::Map::new(),
            ..Default::default()
        };
        assert_eq!(to_pb_trace_result(result).raw_results_json, "");
    }

    #[test]
    fn to_pb_trace_result_nonempty_raw_results_serializes_to_json() {
        let mut raw_results = serde_json::Map::new();
        raw_results.insert("hops".to_string(), serde_json::json!(3));
        let result = testserver_protocols::trace::TraceResult {
            raw_results,
            ..Default::default()
        };
        let json = to_pb_trace_result(result).raw_results_json;
        assert!(json.contains("\"hops\":3"));
    }
}
