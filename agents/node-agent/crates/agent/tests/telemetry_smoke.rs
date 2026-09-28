//! Telemetry smoke test — the mandatory gate from testing.md Telemetry
//! Validation: runs the real `node-agent` binary (subprocess, matching
//! `cli_integration.rs`'s pattern) through one real enrollment against a
//! loopback wiremock control plane, with `OTEL_EXPORTER_OTLP_ENDPOINT`
//! pointed at an in-process mock OTLP collector, and asserts the
//! collector received real, counted data — never a bare pass/fail.
//!
//! Batch/periodic export intervals are tightened via env vars
//! (`OTEL_BSP_SCHEDULE_DELAY`, `OTEL_BLRP_SCHEDULE_DELAY`,
//! `OTEL_METRIC_EXPORT_INTERVAL`) so the test doesn't need to wait out the
//! SDK's multi-second/60s production defaults or rely on a graceful
//! subprocess shutdown to force a flush.

use opentelemetry_proto::tonic::collector::logs::v1::logs_service_server::{
    LogsService, LogsServiceServer,
};
use opentelemetry_proto::tonic::collector::logs::v1::{
    ExportLogsServiceRequest, ExportLogsServiceResponse,
};
use opentelemetry_proto::tonic::collector::metrics::v1::metrics_service_server::{
    MetricsService, MetricsServiceServer,
};
use opentelemetry_proto::tonic::collector::metrics::v1::{
    ExportMetricsServiceRequest, ExportMetricsServiceResponse,
};
use opentelemetry_proto::tonic::collector::trace::v1::trace_service_server::{
    TraceService, TraceServiceServer,
};
use opentelemetry_proto::tonic::collector::trace::v1::{
    ExportTraceServiceRequest, ExportTraceServiceResponse,
};
use opentelemetry_proto::tonic::metrics::v1::metric::Data;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio_util::sync::CancellationToken;
use tonic::transport::server::TcpIncoming;
use tonic::transport::Server;
use tonic::{Request, Response, Status};

/// Real counts observed by the mock OTLP collector — asserted at the end
/// against a non-zero denominator, per critical-rules.md Verification
/// Integrity ("report how many items were examined").
#[derive(Default)]
struct Counts {
    log_records: AtomicUsize,
    spans: AtomicUsize,
    metric_data_points: AtomicUsize,
    histogram_data_points: AtomicUsize,
}

#[derive(Clone, Default)]
struct MockCollector(Arc<Counts>);

#[tonic::async_trait]
impl LogsService for MockCollector {
    async fn export(
        &self,
        request: Request<ExportLogsServiceRequest>,
    ) -> Result<Response<ExportLogsServiceResponse>, Status> {
        let count: usize = request
            .into_inner()
            .resource_logs
            .iter()
            .flat_map(|rl| rl.scope_logs.iter())
            .map(|sl| sl.log_records.len())
            .sum();
        self.0.log_records.fetch_add(count, Ordering::SeqCst);
        Ok(Response::new(ExportLogsServiceResponse::default()))
    }
}

#[tonic::async_trait]
impl TraceService for MockCollector {
    async fn export(
        &self,
        request: Request<ExportTraceServiceRequest>,
    ) -> Result<Response<ExportTraceServiceResponse>, Status> {
        let count: usize = request
            .into_inner()
            .resource_spans
            .iter()
            .flat_map(|rs| rs.scope_spans.iter())
            .map(|ss| ss.spans.len())
            .sum();
        self.0.spans.fetch_add(count, Ordering::SeqCst);
        Ok(Response::new(ExportTraceServiceResponse::default()))
    }
}

#[tonic::async_trait]
impl MetricsService for MockCollector {
    async fn export(
        &self,
        request: Request<ExportMetricsServiceRequest>,
    ) -> Result<Response<ExportMetricsServiceResponse>, Status> {
        let req = request.into_inner();
        let mut data_points = 0usize;
        let mut histogram_points = 0usize;
        for metric in req
            .resource_metrics
            .iter()
            .flat_map(|rm| rm.scope_metrics.iter())
            .flat_map(|sm| sm.metrics.iter())
        {
            match &metric.data {
                Some(Data::Gauge(d)) => data_points += d.data_points.len(),
                Some(Data::Sum(d)) => data_points += d.data_points.len(),
                Some(Data::Histogram(d)) => {
                    data_points += d.data_points.len();
                    histogram_points += d.data_points.len();
                }
                Some(Data::ExponentialHistogram(d)) => {
                    data_points += d.data_points.len();
                    histogram_points += d.data_points.len();
                }
                Some(Data::Summary(d)) => data_points += d.data_points.len(),
                None => {}
            }
        }
        self.0
            .metric_data_points
            .fetch_add(data_points, Ordering::SeqCst);
        self.0
            .histogram_data_points
            .fetch_add(histogram_points, Ordering::SeqCst);
        Ok(Response::new(ExportMetricsServiceResponse::default()))
    }
}

/// Starts the mock OTLP collector (all three signal services) on an
/// OS-assigned loopback port, mirroring `transport::grpc`'s own
/// `spawn_manager` test helper's bind pattern.
async fn spawn_mock_collector() -> (String, Arc<Counts>, CancellationToken) {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("binding an ephemeral loopback port must succeed");
    let addr = listener
        .local_addr()
        .expect("a bound listener has a local address");
    let incoming = TcpIncoming::from(listener);

    let collector = MockCollector::default();
    let counts = collector.0.clone();
    let shutdown = CancellationToken::new();
    let stop = shutdown.clone();

    tokio::spawn(async move {
        Server::builder()
            .add_service(LogsServiceServer::new(collector.clone()))
            .add_service(TraceServiceServer::new(collector.clone()))
            .add_service(MetricsServiceServer::new(collector))
            .serve_with_incoming_shutdown(incoming, stop.cancelled())
            .await
            .expect("mock OTLP collector must not fail to serve");
    });

    (format!("http://{addr}"), counts, shutdown)
}

/// Generates a fresh, throwaway P-256 keypair PEM — good only for this
/// test's machine-JWT signer, never a committed key value. Duplicated
/// from `run.rs`'s own private test helper since integration tests in
/// `tests/` can't reach a binary-only crate's internal test code.
fn generate_test_ec_key_pem() -> String {
    use p256::pkcs8::EncodePrivateKey;
    let signing_key = p256::ecdsa::SigningKey::random(&mut rand_core::OsRng);
    signing_key
        .to_pkcs8_pem(p256::pkcs8::LineEnding::LF)
        .expect("encoding a freshly generated P-256 key as PKCS#8 PEM must succeed")
        .to_string()
}

/// Polls `child.try_wait()` (non-blocking) until it exits or `timeout`
/// elapses, returning whether it exited on its own. Used to bound the
/// wait for a graceful post-SIGTERM shutdown without blocking the async
/// test's runtime on a synchronous `Child::wait()`.
fn wait_with_timeout(child: &mut std::process::Child, timeout: Duration) -> bool {
    let deadline = std::time::Instant::now() + timeout;
    loop {
        match child.try_wait() {
            Ok(Some(_status)) => return true,
            Ok(None) if std::time::Instant::now() < deadline => {
                std::thread::sleep(Duration::from_millis(50));
            }
            Ok(None) | Err(_) => return false,
        }
    }
}

#[tokio::test(flavor = "multi_thread")]
async fn run_emits_real_otlp_logs_metrics_and_a_histogram_on_enrollment() {
    let dir =
        std::env::temp_dir().join(format!("node-agent-telemetry-smoke-{}", std::process::id()));
    std::fs::create_dir_all(&dir).expect("temp dir must be creatable");

    let key_path = dir.join("machine.pem");
    std::fs::write(&key_path, generate_test_ec_key_pem())
        .expect("writing the test key must succeed");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&key_path, std::fs::Permissions::from_mode(0o600))
            .expect("chmod on the test key must succeed");
    }

    let control_plane = wiremock::MockServer::start().await;
    wiremock::Mock::given(wiremock::matchers::method("POST"))
        .and(wiremock::matchers::path("/api/v1/netsvcs/enroll"))
        .respond_with(
            wiremock::ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "status": "success",
                "data": {
                    "node_id": "node-telemetry-smoke",
                    "tenant": "tenant-telemetry-smoke",
                    "access_token": "token-1",
                    "refresh_token": "refresh-1",
                    "config": {"connectivity": {}, "edge": {}, "config_version": 1},
                },
            })),
        )
        .mount(&control_plane)
        .await;

    let (otlp_endpoint, counts, collector_shutdown) = spawn_mock_collector().await;

    let config_path = dir.join("config.toml");
    std::fs::write(
        &config_path,
        format!(
            r#"
            mode = "edge"
            control_plane_url = "{}"
            machine_jwt_path = "{}"

            [features]
            connectivity = false
            netsvcs_edge = false
            "#,
            control_plane.uri(),
            key_path.display(),
        ),
    )
    .expect("writing the test config file must succeed");

    let mut child = Command::new(env!("CARGO_BIN_EXE_node-agent"))
        .arg("--config")
        .arg(&config_path)
        .arg("run")
        .env("HOSTNAME", "node-agent-telemetry-smoke")
        .env("OTEL_EXPORTER_OTLP_ENDPOINT", &otlp_endpoint)
        // Tighten every batch/periodic export interval far below the
        // SDK's multi-second (traces/logs) and 60s (metrics) production
        // defaults, so this test's poll loop below converges in seconds
        // rather than needing a graceful subprocess shutdown to force a
        // flush.
        .env("OTEL_BSP_SCHEDULE_DELAY", "100")
        .env("OTEL_BLRP_SCHEDULE_DELAY", "100")
        .env("OTEL_METRIC_EXPORT_INTERVAL", "200")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawning the node-agent binary must succeed");

    // Poll the mock collector until every signal has arrived at least
    // once, rather than a fixed sleep — enrollment latency (machine-JWT
    // signing + the loopback HTTP round-trip + OTLP batch scheduling)
    // varies under coverage instrumentation/CPU load. Ceiling ~10s is
    // only ever reached on genuine failure.
    let mut log_records = 0;
    let mut spans = 0;
    let mut metric_data_points = 0;
    let mut histogram_data_points = 0;
    for _ in 0..100 {
        tokio::time::sleep(Duration::from_millis(100)).await;
        log_records = counts.log_records.load(Ordering::SeqCst);
        spans = counts.spans.load(Ordering::SeqCst);
        metric_data_points = counts.metric_data_points.load(Ordering::SeqCst);
        histogram_data_points = counts.histogram_data_points.load(Ordering::SeqCst);
        if log_records >= 1 && spans >= 1 && histogram_data_points >= 1 {
            break;
        }
    }

    // SIGTERM, not `child.kill()` (SIGKILL): `run()` handles SIGTERM via
    // its normal `wait_for_shutdown_signal` path, returns `Ok(())`, and
    // `main` runs `telemetry_guard.shutdown()` (flushing every OTLP
    // provider) before the process exits normally — the same graceful
    // path a real SIGTERM'd pod takes. A SIGKILL would skip that path
    // entirely and, incidentally, also skip the LLVM coverage runtime's
    // atexit profile write, undercounting this file's own coverage.
    let _ = Command::new("kill")
        .arg("-TERM")
        .arg(child.id().to_string())
        .status();
    let exited_gracefully = wait_with_timeout(&mut child, Duration::from_secs(5));
    if !exited_gracefully {
        let _ = child.kill();
        let _ = child.wait();
    }
    collector_shutdown.cancel();
    let _ = std::fs::remove_dir_all(&dir);

    eprintln!(
        "telemetry smoke counts: log_records={log_records} spans={spans} \
         metric_data_points={metric_data_points} histogram_data_points={histogram_data_points}"
    );

    // Real counts, never a bare pass/fail — a zero denominator here is a
    // FAIL per critical-rules.md Verification Integrity / testing.md
    // Telemetry Validation, not a skip.
    assert!(
        log_records >= 1,
        "expected >=1 OTLP log record, got {log_records}"
    );
    assert!(spans >= 1, "expected >=1 OTLP span, got {spans}");
    assert!(
        metric_data_points >= 1,
        "expected >=1 OTLP metric data point, got {metric_data_points}"
    );
    assert!(
        histogram_data_points >= 1,
        "expected >=1 OTLP histogram data point (node_agent_enrollment_duration_seconds), got {histogram_data_points}"
    );
}
