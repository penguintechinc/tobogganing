//! Shared config, error, validation, and JWT-auth types for the tobogganing
//! testserver — the Rust rewrite of `engines/testserver` (Go). Kept as its
//! own crate so both the axum REST surface and the tonic gRPC surface in
//! `testserver` (the bin crate) share one validation/error/auth contract.

pub mod auth;
pub mod config;
pub mod error;
pub mod validation;

pub use auth::{AuthUser, JwtKeyError, JwtVerifier};
pub use config::{AppConfig, ConfigError, DbConfig, DbType};
pub use error::{check_api_version, ApiError};
