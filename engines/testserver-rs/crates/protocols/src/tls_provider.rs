//! Installs a single process-wide `rustls` crypto provider (`ring`), mirroring
//! `agents/node-agent/crates/transport/src/tls.rs`: `reqwest` (HTTP probe)
//! and our own `tokio-rustls` client (TCP+TLS probe) can each try to install
//! a default provider on first use, which panics if two different providers
//! race. Called once from `main` at startup, and defensively at the top of
//! every probe entry point so unit/integration tests exercising `test_http`/
//! `test_tcp` directly (without going through `main`) still get a provider
//! installed before the first TLS handshake.

/// Installs the `ring` crypto provider as the process-wide default. Safe to
/// call more than once — `install_default` returns `Err` only when a
/// *different* provider is already installed, which we deliberately ignore:
/// either outcome leaves a valid provider in place.
pub fn install_crypto_provider() {
    let _ = rustls::crypto::ring::default_provider().install_default();
}
