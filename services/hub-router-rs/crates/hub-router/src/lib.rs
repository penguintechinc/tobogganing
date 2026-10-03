//! Library surface for the hub-router service — split from `main.rs` so
//! integration tests can drive the real axum router (middleware + routes)
//! via `tower::ServiceExt::oneshot`/a real bound listener, mirroring
//! `engines/testserver-rs`'s lib/bin split.

pub mod middleware;
pub mod routes;
pub mod telemetry;

pub use middleware::AppState;
pub use routes::router;

/// Parses the `PORT` env var (raw string, already read by the caller) into
/// a `u16`, defaulting to 8080 on absence or a malformed value — pure/no
/// I/O so it's unit-testable without mutating the process environment
/// (mirrors `engines/testserver-rs`'s `healthcheck_port` pattern).
pub fn resolve_port(raw: Option<&str>) -> u16 {
    raw.and_then(|v| v.parse::<u16>().ok()).unwrap_or(8080)
}

/// Resolves hub-api's base URL from the `HUB_API_URL` env var (raw string,
/// already read by the caller), defaulting to the in-cluster service name
/// when unset.
pub fn resolve_hub_api_url(raw: Option<&str>) -> String {
    raw.filter(|v| !v.is_empty())
        .unwrap_or("http://hub-api:8000")
        .to_string()
}

/// Waits for SIGINT or (on Unix) SIGTERM, whichever arrives first — the
/// production graceful-shutdown trigger `main` feeds into
/// `axum::serve(...).with_graceful_shutdown`. Never panics on
/// signal-handler installation failure; logs and falls back to pending
/// (the other signal source, or the process's own termination, still
/// takes effect). Mirrors `engines/testserver-rs`'s identical helper.
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_port_defaults_when_unset_or_unparseable() {
        assert_eq!(resolve_port(None), 8080);
        assert_eq!(resolve_port(Some("")), 8080);
        assert_eq!(resolve_port(Some("not-a-port")), 8080);
        assert_eq!(resolve_port(Some("99999999")), 8080); // out of u16 range
    }

    #[test]
    fn resolve_port_parses_valid_value() {
        assert_eq!(resolve_port(Some("9091")), 9091);
    }

    #[test]
    fn resolve_hub_api_url_defaults_when_unset_or_empty() {
        assert_eq!(resolve_hub_api_url(None), "http://hub-api:8000");
        assert_eq!(resolve_hub_api_url(Some("")), "http://hub-api:8000");
    }

    #[test]
    fn resolve_hub_api_url_passes_through_a_configured_value() {
        assert_eq!(
            resolve_hub_api_url(Some("https://hub-api.internal")),
            "https://hub-api.internal"
        );
    }

    /// Drives `wait_for_os_shutdown_signal`'s real SIGINT path end-to-end:
    /// `tokio::signal::ctrl_c()`'s listener registration replaces the
    /// process's default SIGINT disposition with a self-pipe-based tokio
    /// handler the moment it's first awaited, so by the time this test
    /// `raise()`s SIGINT against its own process the signal is delivered
    /// to that handler, not the default (process-terminating) one — no
    /// other code in this crate's test binary registers a competing
    /// signal listener, so this is safe within the shared test process.
    #[tokio::test]
    async fn wait_for_os_shutdown_signal_returns_on_sigint() {
        let handle = tokio::spawn(wait_for_os_shutdown_signal());
        // Yield so the spawned task actually reaches and registers its
        // `ctrl_c()`/`signal()` listeners before the signal is raised.
        tokio::task::yield_now().await;
        // SAFETY: `raise` with a valid signal number (SIGINT = 2 on every
        // platform this workspace targets, per rust-toolchain.toml's
        // x86_64-unknown-linux-gnu target) is always safe to call.
        unsafe {
            raise_sigint();
        }
        tokio::time::timeout(std::time::Duration::from_secs(5), handle)
            .await
            .expect("wait_for_os_shutdown_signal must return promptly after SIGINT")
            .expect("task must not panic");
    }

    extern "C" {
        fn raise(sig: i32) -> i32;
    }

    unsafe fn raise_sigint() {
        raise(2);
    }
}
