//! Hub Router service entry point.
//!
//! Initializes telemetry (tracing + OTLP + Prometheus), builds the inbound
//! JWT public-key cache (fetched from hub-api over gRPC
//! `HubAuthKeyService.GetPublicKeys`, refreshed hourly in the background
//! — see `hub_router_auth::inbound::PublicKeyCache`), and serves the axum
//! router (`hub_router::routes::router`) until a shutdown signal arrives.
//! Kept deliberately thin — the testable logic
//! (`resolve_port`/`resolve_hub_api_grpc_url`/`wait_for_os_shutdown_signal`)
//! lives in `hub_router`'s lib surface, mirroring
//! `engines/testserver-rs`'s main.rs/app.rs split.

use hub_router::telemetry;
use hub_router_auth::inbound::{PublicKeyCache, DEFAULT_REFRESH_INTERVAL};
use std::net::SocketAddr;
use std::sync::Arc;
use tokio::net::TcpListener;
use tracing::info;

#[tokio::main]
async fn main() {
    let telemetry_providers = telemetry::init_tracing("hub-router");
    let meter_provider = telemetry::init_meter_provider("hub-router");
    telemetry::init_metrics(
        std::env::var("METRICS_PORT")
            .ok()
            .and_then(|v| v.parse::<u16>().ok())
            .unwrap_or(9090),
    );

    info!("Hub Router service starting");

    // hub-api's gRPC endpoint for the inbound JWT public-key fetch
    // (`HubAuthKeyService.GetPublicKeys`, SSO PR-2 — replaces the
    // transitional REST `GET /api/v1/auth/public-key` poll). Degrades
    // gracefully if unset or unreachable: the key cache simply stays
    // empty and every protected request gets 503 until a fetch succeeds,
    // never a crash.
    let hub_api_grpc_url =
        hub_router::resolve_hub_api_grpc_url(std::env::var("HUB_API_GRPC_URL").ok().as_deref());
    let key_cache = Arc::new(
        PublicKeyCache::new(hub_api_grpc_url)
            .expect("failed to build the inbound JWT key-fetch client"),
    );
    key_cache
        .clone()
        .spawn_refresh_loop(DEFAULT_REFRESH_INTERVAL);

    let state = hub_router::AppState::new(key_cache);
    let app = hub_router::router(state);

    let port = hub_router::resolve_port(std::env::var("PORT").ok().as_deref());
    let addr = SocketAddr::from(([0, 0, 0, 0], port));
    let listener = TcpListener::bind(&addr)
        .await
        .expect("failed to bind to address");

    info!(%addr, "hub-router listening");

    if let Err(error) = axum::serve(listener, app)
        .with_graceful_shutdown(hub_router::wait_for_os_shutdown_signal())
        .await
    {
        tracing::error!(%error, "hub-router server exited with an error");
    }

    telemetry_providers.force_flush();
    if let Some(provider) = &meter_provider {
        let _ = provider.force_flush();
    }
}
