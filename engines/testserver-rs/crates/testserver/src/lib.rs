//! Library surface for the `testserver` binary — split out from `main.rs`
//! so integration tests (`tests/`) can drive the real axum router, gRPC
//! service, and telemetry pipeline in-process (a binary-only crate has no
//! importable target; `tests/*.rs` can only see `pub` items reachable
//! through a library crate). `main.rs` stays a thin CLI/bootstrap wrapper
//! around these modules.

pub mod app;
pub mod grpc_api;
pub mod http_api;
pub mod telemetry;
