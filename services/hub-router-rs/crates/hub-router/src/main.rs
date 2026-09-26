//! Hub Router service.
//!
//! Entry point for the hub-router service. Initializes logging and starts
//! an Axum HTTP server with basic health check endpoints.

use axum::{http::StatusCode, response::IntoResponse, routing::get, Json, Router};
use std::net::SocketAddr;
use tokio::net::TcpListener;
use tracing::info;

/// Health check response.
#[derive(serde::Serialize)]
struct HealthResponse {
    status: String,
}

/// Health check handler.
async fn health() -> impl IntoResponse {
    (
        StatusCode::OK,
        Json(HealthResponse {
            status: "ok".to_string(),
        }),
    )
}

#[tokio::main]
async fn main() {
    // Initialize tracing.
    tracing_subscriber::fmt()
        .with_max_level(tracing::Level::INFO)
        .init();

    info!("Hub Router service starting");

    // Build the router.
    let app = Router::new().route("/health", get(health));

    // Get port from environment or use default.
    let port = std::env::var("PORT")
        .unwrap_or_else(|_| "8080".to_string())
        .parse::<u16>()
        .expect("PORT must be a valid u16");

    let addr = SocketAddr::from(([0, 0, 0, 0], port));
    let listener = TcpListener::bind(&addr)
        .await
        .expect("Failed to bind to address");

    info!("Server listening on {}", addr);

    axum::serve(listener, app).await.expect("Server failed");
}
