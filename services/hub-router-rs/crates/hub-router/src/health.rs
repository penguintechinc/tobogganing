//! `grpc.health.v1` status surface for hub-router — replaces the former
//! REST `/health` + `/api/v1/router/status` endpoints (org rule: in-cluster
//! Rust services are gRPC only, probed natively via `grpc.health.v1`).
//!
//! Two service names are reported:
//! - `""` (overall) — liveness: SERVING while the process serves gRPC.
//! - [`SERVICE_NAME`] — readiness: derived from live component state
//!   (inbound JWT public-key cache populated from hub-api); NOT_SERVING
//!   whenever hub-router could not authenticate a single protected call.

use hub_router_auth::inbound::PublicKeyCache;
use std::future::Future;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::net::TcpListener;
use tonic_health::server::HealthReporter;
use tonic_health::ServingStatus;

/// Readiness service name probed by Kubernetes (`grpc.service`).
pub const SERVICE_NAME: &str = "hub-router";

/// How often the reporter re-derives readiness from component state.
pub const DEFAULT_EVALUATE_INTERVAL: Duration = Duration::from_secs(5);

/// Derives the readiness status from live component state. Pure (no I/O)
/// so every branch is unit-testable; the auth key cache is currently the
/// only in-process component hub-router depends on to serve requests.
pub fn evaluate(key_cache: &PublicKeyCache) -> ServingStatus {
    if key_cache.has_keys() {
        ServingStatus::Serving
    } else {
        ServingStatus::NotServing
    }
}

/// Evaluates component state once and publishes it to `reporter`, logging
/// transitions against `previous` and recording the evaluation latency
/// histogram. Returns the status it published.
pub async fn publish(
    reporter: &HealthReporter,
    key_cache: &PublicKeyCache,
    previous: Option<ServingStatus>,
) -> ServingStatus {
    let start = Instant::now();
    let status = evaluate(key_cache);
    reporter
        .set_service_status("", ServingStatus::Serving)
        .await;
    reporter.set_service_status(SERVICE_NAME, status).await;
    let code = if status == ServingStatus::Serving {
        200
    } else {
        503
    };
    crate::telemetry::record_request(
        "grpc.health.v1/evaluate",
        start.elapsed().as_secs_f64(),
        code,
    );
    if previous != Some(status) {
        if status == ServingStatus::Serving {
            tracing::info!(service = SERVICE_NAME, "health status SERVING");
        } else {
            tracing::warn!(
                service = SERVICE_NAME,
                "health status NOT_SERVING: no hub-api JWT public key cached"
            );
        }
    }
    status
}

/// Spawns the background loop that keeps `reporter` in sync with live
/// component state every `interval`.
pub fn spawn_reporter(
    reporter: HealthReporter,
    key_cache: Arc<PublicKeyCache>,
    interval: Duration,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let mut previous = None;
        loop {
            previous = Some(publish(&reporter, &key_cache, previous).await);
            tokio::time::sleep(interval).await;
        }
    })
}

/// Serves `grpc.health.v1` on `listener` until `shutdown` resolves. The
/// initial status is published before the server accepts connections, so
/// a probe never observes the default SERVING for [`SERVICE_NAME`].
pub async fn serve(
    listener: TcpListener,
    key_cache: Arc<PublicKeyCache>,
    interval: Duration,
    shutdown: impl Future<Output = ()> + Send,
) -> Result<(), tonic::transport::Error> {
    let (reporter, health_service) = tonic_health::server::health_reporter();
    let initial = publish(&reporter, &key_cache, None).await;
    let reporter_task = spawn_reporter(reporter, key_cache, interval);
    tracing::debug!(?initial, "initial health status published");
    let result = tonic::transport::Server::builder()
        .add_service(health_service)
        .serve_with_incoming_shutdown(
            tokio_stream::wrappers::TcpListenerStream::new(listener),
            shutdown,
        )
        .await;
    reporter_task.abort();
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use p256::ecdsa::{SigningKey, VerifyingKey};
    use p256::pkcs8::{EncodePublicKey, LineEnding};
    use tonic_health::pb::health_check_response::ServingStatus as PbStatus;
    use tonic_health::pb::health_client::HealthClient;
    use tonic_health::pb::HealthCheckRequest;

    fn empty_cache() -> PublicKeyCache {
        PublicKeyCache::new("http://unused.invalid").expect("client build")
    }

    fn seed(cache: &PublicKeyCache) {
        let key = SigningKey::random(&mut rand_core::OsRng);
        let pem = VerifyingKey::from(&key)
            .to_public_key_pem(LineEnding::LF)
            .expect("SPKI PEM encode");
        cache.inject_for_test(
            penguin_aaa::Es256Verifier::from_public_key_pem(pem.as_bytes()).expect("verifier"),
        );
    }

    #[tokio::test]
    async fn evaluate_is_not_serving_without_keys() {
        assert_eq!(evaluate(&empty_cache()), ServingStatus::NotServing);
    }

    #[tokio::test]
    async fn evaluate_is_serving_with_keys() {
        let cache = empty_cache();
        seed(&cache);
        assert_eq!(evaluate(&cache), ServingStatus::Serving);
    }

    async fn check(addr: std::net::SocketAddr, service: &str) -> PbStatus {
        let mut client = HealthClient::new(
            tonic::transport::Endpoint::from_shared(format!("http://{addr}"))
                .expect("valid endpoint")
                .connect()
                .await
                .expect("health client connects"),
        );
        let resp = client
            .check(HealthCheckRequest {
                service: service.to_string(),
            })
            .await
            .expect("check succeeds")
            .into_inner();
        PbStatus::try_from(resp.status).expect("valid status")
    }

    #[tokio::test]
    async fn grpc_health_reflects_live_key_cache_state() {
        let cache = Arc::new(empty_cache());
        let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
        let addr = listener.local_addr().expect("addr");
        let (tx, rx) = tokio::sync::oneshot::channel::<()>();
        let server = tokio::spawn(serve(
            listener,
            cache.clone(),
            Duration::from_millis(20),
            async {
                let _ = rx.await;
            },
        ));

        assert_eq!(check(addr, "").await, PbStatus::Serving);
        assert_eq!(check(addr, SERVICE_NAME).await, PbStatus::NotServing);

        seed(&cache);
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            if check(addr, SERVICE_NAME).await == PbStatus::Serving {
                break;
            }
            assert!(Instant::now() < deadline, "status never became SERVING");
            tokio::time::sleep(Duration::from_millis(20)).await;
        }

        tx.send(()).expect("shutdown signal");
        server
            .await
            .expect("server task joins")
            .expect("server exits cleanly");
    }

    #[tokio::test]
    async fn grpc_health_rejects_unknown_service() {
        let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
        let addr = listener.local_addr().expect("addr");
        let (tx, rx) = tokio::sync::oneshot::channel::<()>();
        let server = tokio::spawn(serve(
            listener,
            Arc::new(empty_cache()),
            DEFAULT_EVALUATE_INTERVAL,
            async {
                let _ = rx.await;
            },
        ));
        let mut client = HealthClient::new(
            tonic::transport::Endpoint::from_shared(format!("http://{addr}"))
                .expect("valid endpoint")
                .connect()
                .await
                .expect("connect"),
        );
        let err = client
            .check(HealthCheckRequest {
                service: "nope".to_string(),
            })
            .await
            .expect_err("unknown service must fail");
        assert_eq!(err.code(), tonic::Code::NotFound);
        tx.send(()).expect("shutdown");
        server.await.expect("join").expect("clean exit");
    }

    #[tokio::test]
    async fn publish_logs_transition_and_returns_status() {
        let (reporter, _svc) = tonic_health::server::health_reporter();
        let cache = empty_cache();
        let first = publish(&reporter, &cache, None).await;
        assert_eq!(first, ServingStatus::NotServing);
        seed(&cache);
        let second = publish(&reporter, &cache, Some(first)).await;
        assert_eq!(second, ServingStatus::Serving);
        assert_eq!(publish(&reporter, &cache, Some(second)).await, second);
    }
}
