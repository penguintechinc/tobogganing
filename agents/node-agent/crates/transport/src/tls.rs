//! Installs a single process-wide `rustls` crypto provider (`ring`) so the
//! `tonic` (gRPC) and `reqwest` (REST) clients — each capable of installing
//! their own default provider on first use — never race to install
//! conflicting ones, which would otherwise panic at the first TLS handshake.

use node_agent_core::Result;

/// Installs the `ring` crypto provider as the process-wide default for
/// `rustls`. Must be called once, before `build_client` constructs either
/// the gRPC or REST client; safe to call more than once — a second install
/// is a documented no-op, not an error.
pub fn install_crypto_provider() -> Result<()> {
    // `install_default` returns `Err` only when a *different* provider is
    // already installed; either outcome leaves a valid provider in place,
    // so we deliberately ignore the result rather than treat it as fatal.
    let _ = rustls::crypto::ring::default_provider().install_default();
    Ok(())
}
