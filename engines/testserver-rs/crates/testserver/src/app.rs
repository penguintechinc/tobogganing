//! Server orchestration: builds the DB lifecycle, HTTP + gRPC surfaces, and
//! runs both to completion — split out from `main.rs` so it's driven by an
//! explicit [`CancellationToken`] instead of OS signals directly, letting
//! integration tests exercise the *real* startup/shutdown path (DB
//! degraded-start, dual-server bind, graceful shutdown) end-to-end against
//! ephemeral ports, not just its individual pieces in isolation.

use std::net::SocketAddr;
use testserver_core::AppConfig;
use testserver_db::connection::{connect_with_retry, DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY};
use testserver_db::SwitchableStore;
use tokio_util::sync::CancellationToken;

/// Builds the DB lifecycle + HTTP/gRPC router surfaces from `cfg`, binds
/// both listeners, and serves until `shutdown` is cancelled — mirrors
/// `cmd/testserver/main.go`'s top-level run loop. Never panics or exits on
/// a DB connect failure (dials in the background, degraded until
/// connected); the two server futures are joined so either surface's bind
/// failure surfaces as an `Err` without leaking the other's task.
pub async fn serve(
    cfg: &AppConfig,
    shutdown: CancellationToken,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let db = SwitchableStore::new();
    {
        let db = db.clone();
        let db_cfg = cfg.db.clone();
        // Dials in the background — `/health` and every DB-independent
        // route serve immediately, mirroring `cmd/testserver/main.go`'s
        // `connectDB` goroutine. Never panics/exits on failure.
        tokio::spawn(async move {
            match connect_with_retry(&db_cfg, DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY).await {
                Ok(conn) => {
                    db.set_connection(conn).await;
                    tracing::info!("database connected — auth and result storage now active");
                }
                Err(error) => {
                    tracing::warn!(%error, "database unavailable, continuing in degraded mode");
                }
            }
        });
    }

    tracing::info!(
        db_type = ?cfg.db.db_type,
        auth_enabled = cfg.auth_enabled,
        max_concurrent_tests = cfg.max_concurrent_tests,
        allowed_origins = cfg.allowed_origins.len(),
        "config loaded"
    );

    let state = crate::http_api::AppState::new(db.clone(), cfg);
    let app = crate::http_api::router(state, cfg.allowed_origins.clone());

    let http_addr: SocketAddr = ([0, 0, 0, 0], cfg.http_port).into();
    let grpc_addr: SocketAddr = ([0, 0, 0, 0], cfg.grpc_port).into();
    tracing::info!(%http_addr, %grpc_addr, "testserver listening");

    let http_shutdown = shutdown.clone();
    let http_server = async {
        let listener = tokio::net::TcpListener::bind(http_addr).await?;
        axum::serve(
            listener,
            app.into_make_service_with_connect_info::<SocketAddr>(),
        )
        .with_graceful_shutdown(async move { http_shutdown.cancelled().await })
        .await
        .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)
    };

    let grpc_shutdown = shutdown.clone();
    let grpc_server = async {
        tonic::transport::Server::builder()
            .add_service(crate::grpc_api::TestServiceImpl::into_server(db.clone()))
            .serve_with_shutdown(grpc_addr, async move { grpc_shutdown.cancelled().await })
            .await
            .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)
    };

    let (http_result, grpc_result) = tokio::join!(http_server, grpc_server);
    http_result?;
    grpc_result?;

    Ok(())
}

/// Waits for SIGINT or (on Unix) SIGTERM, whichever arrives first — the
/// production graceful-shutdown trigger `main.rs` feeds into a
/// [`CancellationToken`] for [`serve`]. Never panics on signal-handler
/// installation failure; logs and falls back to pending (the other signal
/// source, or the process's own termination, still takes effect).
pub async fn wait_for_os_shutdown_signal() {
    let ctrl_c = async {
        if let Err(error) = tokio::signal::ctrl_c().await {
            tracing::error!(%error, "failed to install ctrl_c handler");
        }
    };

    #[cfg(unix)]
    let terminate = async {
        match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) {
            Ok(mut sig) => {
                sig.recv().await;
            }
            Err(error) => {
                tracing::error!(%error, "failed to install sigterm handler");
                std::future::pending::<()>().await;
            }
        }
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        () = ctrl_c => {},
        () = terminate => {},
    }
    tracing::info!("shutdown signal received");
}
