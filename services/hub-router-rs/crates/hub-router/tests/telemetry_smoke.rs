//! Telemetry-validation smoke test (critical-rules.md Observability +
//! testing.md Telemetry Validation): boots the real axum router against an
//! in-process mock OTLP collector (standard `TraceService`/
//! `MetricsService`/`LogsService` gRPC stubs from `opentelemetry-proto`),
//! drives one authenticated request through the protected route end-to-end
//! (exercising both the per-request and the JWT-verify-step histograms),
//! then asserts the collector actually received log records, metric data
//! points, and at least one histogram metric — never a bare "no error"
//! absence-of-failure signal. A sink that fails to start is a hard test
//! failure, never a skip.
//!
//! This is a *separate* test binary/process (Cargo integration test
//! convention) specifically so the process-global `tracing`/OTel state it
//! installs can only be initialized once, with no risk of colliding with
//! the crate's many `#[cfg(test)]` unit tests running in the lib's own
//! test binary. Mirrors `engines/testserver-rs`'s identical smoke test.

use hub_router_auth::inbound::PublicKeyCache;
use opentelemetry_proto::tonic::collector::logs::v1::{
    logs_service_server::{LogsService, LogsServiceServer},
    ExportLogsServiceRequest, ExportLogsServiceResponse,
};
use opentelemetry_proto::tonic::collector::metrics::v1::{
    metrics_service_server::{MetricsService, MetricsServiceServer},
    ExportMetricsServiceRequest, ExportMetricsServiceResponse,
};
use opentelemetry_proto::tonic::collector::trace::v1::{
    trace_service_server::{TraceService, TraceServiceServer},
    ExportTraceServiceRequest, ExportTraceServiceResponse,
};
use opentelemetry_proto::tonic::metrics::v1::metric::Data;
use p256::ecdsa::{SigningKey, VerifyingKey};
use p256::pkcs8::{EncodePrivateKey, EncodePublicKey, LineEnding};
use penguin_aaa::{Claims, Es256Signer};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tonic::{Request, Response, Status};

/// Counters the mock collector increments on every received export call —
/// `Arc`-shared with the test so it can assert on them after the request
/// runs.
#[derive(Default)]
struct Counts {
    log_records: AtomicUsize,
    metric_data_points: AtomicUsize,
    histogram_metrics: AtomicUsize,
    spans: AtomicUsize,
}

struct MockCollector {
    counts: Arc<Counts>,
}

mod service_impls {
    use super::*;

    #[tonic::async_trait]
    impl TraceService for MockCollector {
        async fn export(
            &self,
            request: Request<ExportTraceServiceRequest>,
        ) -> Result<Response<ExportTraceServiceResponse>, Status> {
            let req = request.into_inner();
            let span_count: usize = req
                .resource_spans
                .iter()
                .flat_map(|rs| rs.scope_spans.iter())
                .map(|ss| ss.spans.len())
                .sum();
            self.counts.spans.fetch_add(span_count, Ordering::SeqCst);
            Ok(Response::new(ExportTraceServiceResponse {
                partial_success: None,
            }))
        }
    }

    #[tonic::async_trait]
    impl MetricsService for MockCollector {
        async fn export(
            &self,
            request: Request<ExportMetricsServiceRequest>,
        ) -> Result<Response<ExportMetricsServiceResponse>, Status> {
            let req = request.into_inner();
            for metric in req
                .resource_metrics
                .iter()
                .flat_map(|rm| rm.scope_metrics.iter())
                .flat_map(|sm| sm.metrics.iter())
            {
                let n = match &metric.data {
                    Some(Data::Gauge(g)) => g.data_points.len(),
                    Some(Data::Sum(s)) => s.data_points.len(),
                    Some(Data::Histogram(h)) => {
                        self.counts.histogram_metrics.fetch_add(1, Ordering::SeqCst);
                        h.data_points.len()
                    }
                    Some(Data::ExponentialHistogram(h)) => {
                        self.counts.histogram_metrics.fetch_add(1, Ordering::SeqCst);
                        h.data_points.len()
                    }
                    Some(Data::Summary(s)) => s.data_points.len(),
                    None => 0,
                };
                self.counts
                    .metric_data_points
                    .fetch_add(n, Ordering::SeqCst);
            }
            Ok(Response::new(ExportMetricsServiceResponse {
                partial_success: None,
            }))
        }
    }

    #[tonic::async_trait]
    impl LogsService for MockCollector {
        async fn export(
            &self,
            request: Request<ExportLogsServiceRequest>,
        ) -> Result<Response<ExportLogsServiceResponse>, Status> {
            let req = request.into_inner();
            let record_count: usize = req
                .resource_logs
                .iter()
                .flat_map(|rl| rl.scope_logs.iter())
                .map(|sl| sl.log_records.len())
                .sum();
            self.counts
                .log_records
                .fetch_add(record_count, Ordering::SeqCst);
            Ok(Response::new(ExportLogsServiceResponse {
                partial_success: None,
            }))
        }
    }
}

fn now() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("system clock is after the Unix epoch")
        .as_secs() as i64
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn telemetry_pipeline_emits_logs_metrics_and_histograms() {
    // --- 1. Start the mock OTLP collector -----------------------------
    let counts = Arc::new(Counts::default());
    let collector_listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("mock OTLP collector must bind an ephemeral port — sink-fails-to-start is a hard FAIL, never a skip");
    let collector_addr = collector_listener
        .local_addr()
        .expect("bound listener must have a local address");
    let mock_trace = MockCollector {
        counts: counts.clone(),
    };
    let mock_metrics = MockCollector {
        counts: counts.clone(),
    };
    let mock_logs = MockCollector {
        counts: counts.clone(),
    };
    tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(TraceServiceServer::new(mock_trace))
            .add_service(MetricsServiceServer::new(mock_metrics))
            .add_service(LogsServiceServer::new(mock_logs))
            .serve_with_incoming(tokio_stream::wrappers::TcpListenerStream::new(
                collector_listener,
            ))
            .await
            .expect("mock OTLP collector must serve without error");
    });

    // --- 2. Point the OTLP pipeline at it, initialize telemetry --------
    // SAFETY: this test binary is the sole process touching this env var
    // (it is process-global) and initializes telemetry exactly once.
    unsafe {
        std::env::set_var(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            format!("http://{collector_addr}"),
        );
    }
    let telemetry_providers = hub_router::telemetry::init_tracing("hub-router-smoke");
    let meter_provider = hub_router::telemetry::init_meter_provider("hub-router-smoke");
    assert!(
        meter_provider.is_some(),
        "OTLP metrics pipeline must initialize when OTEL_EXPORTER_OTLP_ENDPOINT is set"
    );

    // --- 3. Boot the real axum router with a seeded public-key cache ---
    let signing_key = SigningKey::random(&mut rand_core::OsRng);
    let private_pem = signing_key
        .to_pkcs8_pem(LineEnding::LF)
        .expect("encoding a freshly generated P-256 key as PKCS#8 PEM must succeed")
        .to_string();
    let public_pem = VerifyingKey::from(&signing_key)
        .to_public_key_pem(LineEnding::LF)
        .expect("encoding the matching public key as SPKI PEM must succeed");

    let key_cache = PublicKeyCache::new("http://unused.invalid")
        .expect("building a client with no special TLS/proxy config must succeed");
    key_cache.inject_for_test(
        penguin_aaa::Es256Verifier::from_public_key_pem(public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier"),
    );
    let state = hub_router::AppState::new(Arc::new(key_cache));
    let app = hub_router::router(state);

    let http_listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("axum listener must bind");
    let http_addr = http_listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(http_listener, app)
            .await
            .expect("axum server must not exit with an error during the test");
    });

    // --- 4. Exercise the protected route end-to-end via real HTTP ------
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

    let client = reqwest::Client::new();
    let resp = client
        .get(format!("http://{http_addr}/api/v1/router/status"))
        .bearer_auth(token)
        .send()
        .await
        .expect("request must reach the running server");
    assert_eq!(
        resp.status(),
        reqwest::StatusCode::OK,
        "authenticated request to the protected route must succeed for the telemetry \
         pipeline to have anything to export"
    );

    // --- 5. Force an immediate export rather than waiting on batch/-----
    //        periodic timers, then poll the mock collector's counters.
    telemetry_providers.force_flush();
    if let Some(provider) = &meter_provider {
        let _ = provider.force_flush();
    }

    let deadline = tokio::time::Instant::now() + Duration::from_secs(10);
    loop {
        let logs = counts.log_records.load(Ordering::SeqCst);
        let points = counts.metric_data_points.load(Ordering::SeqCst);
        let histograms = counts.histogram_metrics.load(Ordering::SeqCst);
        if logs >= 1 && points >= 1 && histograms >= 1 {
            break;
        }
        if tokio::time::Instant::now() >= deadline {
            panic!(
                "telemetry did not arrive at the mock OTLP collector within 10s — \
                 log_records={logs}, metric_data_points={points}, histogram_metrics={histograms}"
            );
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }

    // --- 6. Assert with printed counts (never a bare pass/fail) ---------
    let log_records = counts.log_records.load(Ordering::SeqCst);
    let metric_data_points = counts.metric_data_points.load(Ordering::SeqCst);
    let histogram_metrics = counts.histogram_metrics.load(Ordering::SeqCst);
    let spans = counts.spans.load(Ordering::SeqCst);
    println!(
        "telemetry smoke counts: log_records={log_records} metric_data_points={metric_data_points} \
         histogram_metrics={histogram_metrics} spans={spans}"
    );
    assert!(
        log_records >= 1,
        "expected >=1 log record, got {log_records}"
    );
    assert!(
        metric_data_points >= 1,
        "expected >=1 metric data point, got {metric_data_points}"
    );
    assert!(
        histogram_metrics >= 1,
        "expected >=1 histogram metric, got {histogram_metrics}"
    );
}
