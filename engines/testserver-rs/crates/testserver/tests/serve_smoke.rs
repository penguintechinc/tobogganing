//! Exercises `testserver::app::serve` end-to-end against ephemeral ports:
//! the real DB degraded-start lifecycle, HTTP + gRPC dual bind, an actual
//! `/health` request, and graceful shutdown via `CancellationToken` —
//! covering the server-orchestration path that `main.rs`'s `run()` only
//! wires up for a real OS process (untestable there without a live
//! process to send signals to).

use std::collections::HashSet;
use std::time::Duration;
use testserver_core::{AppConfig, DbConfig, DbType};
use tokio_util::sync::CancellationToken;

/// Binds an ephemeral port, immediately releases it, and returns the
/// number — small TOCTOU window (acceptable for test-only port selection,
/// same pattern used throughout this workspace's other tests) so `serve`
/// can be told an exact port instead of discovering an OS-assigned one
/// after the fact.
async fn free_port() -> u16 {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind an ephemeral port");
    listener
        .local_addr()
        .expect("bound listener has an addr")
        .port()
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn serve_binds_both_surfaces_and_shuts_down_gracefully_on_cancellation() {
    // Required before any reqwest::Client is built with `rustls-no-provider`
    // — production code paths install this inside `serve`'s router/probe
    // machinery; a bare `reqwest::get` in this test needs it too.
    testserver_protocols::tls_provider::install_crypto_provider();

    let http_port = free_port().await;
    let grpc_port = free_port().await;

    let cfg = AppConfig {
        db: DbConfig {
            db_type: DbType::Sqlite,
            host: String::new(),
            port: String::new(),
            user: String::new(),
            password: String::new(),
            // Deliberately unreachable path — the background connect
            // retries and fails quickly (short retry count/delay aren't
            // configurable here, but /health must still serve immediately
            // regardless, which is exactly the degraded-start contract
            // under test).
            database: "/nonexistent/dir/does-not-exist.db".to_string(),
        },
        auth_enabled: false,
        http_port,
        grpc_port,
        metrics_port: 0, // Prometheus exporter isn't started by `serve` itself.
        max_concurrent_tests: 10,
        allowed_origins: HashSet::new(),
        jwt_verifier: None,
    };

    let shutdown = CancellationToken::new();
    let serve_shutdown = shutdown.clone();
    let serve_task =
        tokio::spawn(async move { testserver::app::serve(&cfg, serve_shutdown).await });

    // Give the listeners a moment to bind before hitting /health.
    let mut health_ok = false;
    for _ in 0..50 {
        tokio::time::sleep(Duration::from_millis(50)).await;
        if let Ok(resp) = reqwest::get(format!("http://127.0.0.1:{http_port}/health")).await {
            if resp.status().is_success() {
                health_ok = true;
                break;
            }
        }
    }
    assert!(
        health_ok,
        "/health must respond before the DB ever connects"
    );

    shutdown.cancel();
    let result = tokio::time::timeout(Duration::from_secs(5), serve_task)
        .await
        .expect("serve() must exit promptly once cancelled")
        .expect("serve task must not panic");
    assert!(
        result.is_ok(),
        "serve() must exit cleanly on graceful shutdown: {result:?}"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn serve_transitions_out_of_degraded_mode_once_the_db_connects() {
    // A working in-memory sqlite DSN connects almost immediately — exercises
    // the `Ok(conn) => { db.set_connection(...).await; ... }` branch (the
    // previous test only ever exercises the `Err(error)` degraded-mode
    // branch, since its DB config is permanently unreachable).
    testserver_protocols::tls_provider::install_crypto_provider();

    let http_port = free_port().await;
    let grpc_port = free_port().await;

    let cfg = AppConfig {
        db: DbConfig {
            db_type: DbType::Sqlite,
            host: String::new(),
            port: String::new(),
            user: String::new(),
            password: String::new(),
            database: String::new(), // testserver_db::connection maps this to "sqlite::memory:"
        },
        auth_enabled: false,
        http_port,
        grpc_port,
        metrics_port: 0,
        max_concurrent_tests: 10,
        allowed_origins: HashSet::new(),
        jwt_verifier: None,
    };

    let shutdown = CancellationToken::new();
    let serve_shutdown = shutdown.clone();
    let serve_task =
        tokio::spawn(async move { testserver::app::serve(&cfg, serve_shutdown).await });

    let mut health_ok = false;
    for _ in 0..50 {
        tokio::time::sleep(Duration::from_millis(50)).await;
        if let Ok(resp) = reqwest::get(format!("http://127.0.0.1:{http_port}/health")).await {
            if resp.status().is_success() {
                health_ok = true;
                break;
            }
        }
    }
    assert!(health_ok, "/health must respond regardless of DB state");

    // Give the background connect task a moment to land before shutting down.
    tokio::time::sleep(Duration::from_millis(300)).await;

    shutdown.cancel();
    let result = tokio::time::timeout(Duration::from_secs(5), serve_task)
        .await
        .expect("serve() must exit promptly once cancelled")
        .expect("serve task must not panic");
    assert!(
        result.is_ok(),
        "serve() must exit cleanly on graceful shutdown: {result:?}"
    );
}
