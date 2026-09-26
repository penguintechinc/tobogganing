//! WaddlePerf diagnostic probe target — Rust rewrite of `engines/testserver`
//! (Go). Serves REST (axum, `:8080`) + gRPC (tonic, `:50051`) surfaces
//! against the same probe implementations (`testserver-protocols`), backed
//! by SeaORM (`testserver-db`) with a degraded-start/reconnect DB lifecycle,
//! and emits OTLP traces + Prometheus metrics (`:9090`).

mod grpc_api;
mod http_api;
mod telemetry;

use clap::{Parser, Subcommand};
use std::net::SocketAddr;
use std::time::Duration;
use testserver_core::AppConfig;
use testserver_db::connection::{connect_with_retry, DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY};
use testserver_db::SwitchableStore;

#[derive(Parser)]
#[command(
    name = "testserver",
    version,
    about = "WaddlePerf diagnostic probe target"
)]
struct Cli {
    #[command(subcommand)]
    command: Option<Command>,
}

#[derive(Subcommand)]
enum Command {
    /// Run the HTTP + gRPC servers (default when no subcommand is given).
    Run,
    /// Native Rust liveness check for the container HEALTHCHECK — never
    /// curl, per devops-containers.md.
    Healthcheck,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    match cli.command.unwrap_or(Command::Run) {
        Command::Run => run().await,
        Command::Healthcheck => healthcheck().await,
    }
}

async fn healthcheck() -> Result<(), Box<dyn std::error::Error>> {
    let port = std::env::var("PORT")
        .ok()
        .and_then(|v| v.parse::<u16>().ok())
        .unwrap_or(8080);

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()?;
    let url = format!("http://127.0.0.1:{port}/health");

    match client.get(&url).send().await {
        Ok(resp) if resp.status().is_success() => Ok(()),
        Ok(resp) => {
            eprintln!("healthcheck: unhealthy status {}", resp.status());
            std::process::exit(1);
        }
        Err(e) => {
            eprintln!("healthcheck: request failed: {e}");
            std::process::exit(1);
        }
    }
}

async fn run() -> Result<(), Box<dyn std::error::Error>> {
    let cfg = AppConfig::from_env();
    let _tracer_provider = telemetry::init_tracing("testserver");
    telemetry::init_metrics(cfg.metrics_port);
    testserver_protocols::tls_provider::install_crypto_provider();

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

    let state = http_api::AppState::new(db.clone(), &cfg);
    let app = http_api::router(state, cfg.allowed_origins.clone());

    let http_addr: SocketAddr = ([0, 0, 0, 0], cfg.http_port).into();
    let grpc_addr: SocketAddr = ([0, 0, 0, 0], cfg.grpc_port).into();
    tracing::info!(%http_addr, %grpc_addr, "testserver listening");

    let http_server = async {
        let listener = tokio::net::TcpListener::bind(http_addr).await?;
        axum::serve(
            listener,
            app.into_make_service_with_connect_info::<SocketAddr>(),
        )
        .with_graceful_shutdown(shutdown_signal())
        .await
        .map_err(|e| Box::new(e) as Box<dyn std::error::Error>)
    };

    let grpc_server = async {
        tonic::transport::Server::builder()
            .add_service(grpc_api::TestServiceImpl::into_server(db.clone()))
            .serve_with_shutdown(grpc_addr, shutdown_signal())
            .await
            .map_err(|e| Box::new(e) as Box<dyn std::error::Error>)
    };

    let (http_result, grpc_result) = tokio::join!(http_server, grpc_server);
    http_result?;
    grpc_result?;

    Ok(())
}

/// Waits for SIGINT or (on Unix) SIGTERM, whichever arrives first — used as
/// the graceful-shutdown future for both the HTTP and gRPC servers. Never
/// panics on signal-handler installation failure; logs and falls back to
/// pending (the other signal source, or the process's own termination,
/// still takes effect).
async fn shutdown_signal() {
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
