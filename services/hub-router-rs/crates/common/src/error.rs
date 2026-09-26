//! Error types for hub-router.

use thiserror::Error;

/// Hub router error type.
#[derive(Error, Debug)]
pub enum Error {
    /// Configuration error.
    #[error("config error: {0}")]
    Config(String),

    /// Runtime error.
    #[error("runtime error: {0}")]
    Runtime(String),
}
