//! Defines the crate-wide error type shared by every crate in the node-agent
//! workspace. `AgentError` is the single enum returned by fallible public
//! functions so call sites match on variants instead of downcasting.

use thiserror::Error;

/// Crate-wide result alias binding the error type to [`AgentError`]. Every
/// fallible public function across `core`, `transport`, `connectivity`, and
/// `netsvcs-edge` returns this alias so call sites never spell out the error
/// type explicitly.
pub type Result<T> = std::result::Result<T, AgentError>;

/// The single error type returned by every fallible operation in the
/// node-agent workspace. Each variant maps to one failure domain so callers
/// can match without downcasting; `#[from]` conversions keep `?` ergonomic.
#[derive(Debug, Error)]
pub enum AgentError {
    /// A required configuration value was missing or structurally invalid.
    #[error("configuration error: {0}")]
    Config(String),

    /// Layered config sources (defaults/file/env) failed to parse or merge.
    /// Boxed: `figment::Error` is large enough to otherwise blow up
    /// `AgentError`'s size for every `Result<T>` in the workspace
    /// (`clippy::result_large_err`).
    #[error("configuration parsing failed: {0}")]
    ConfigParse(#[from] Box<figment::Error>),

    /// Reading or writing a file (e.g. the machine-JWT signing key) failed.
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    /// Signing, encoding, or decoding a JWT failed.
    #[error("machine-JWT error: {0}")]
    Jwt(#[from] jsonwebtoken::errors::Error),

    /// The underlying transport (gRPC channel, HTTP client) failed before a
    /// control-plane response could be interpreted.
    #[error("control-plane transport error: {0}")]
    Transport(String),

    /// The control plane rejected the call's `api_version` — mirrors the
    /// `UNIMPLEMENTED` / `"api_version {v} not supported"` contract from
    /// `backend.md`.
    #[error("control-plane rejected api_version \"{version}\": {reason}")]
    UnsupportedApiVersion { version: String, reason: String },

    /// The control plane returned a well-formed but semantically failing
    /// response (e.g. non-"success" status envelope, enrollment denied).
    #[error("control-plane error: {0}")]
    ControlPlane(String),

    /// A supervised background task (connectivity, netsvcs-edge, heartbeat
    /// loop) failed or was cancelled unexpectedly.
    #[error("task supervision error: {0}")]
    Task(String),
}
