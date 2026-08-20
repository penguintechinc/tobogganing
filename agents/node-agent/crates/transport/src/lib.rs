//! `node_agent_transport`: gRPC (`tonic`) and REST (`reqwest`)
//! implementations of `node_agent_core::ControlPlaneClient`, selected at
//! runtime by `AgentConfig::mode` — gRPC for intra-cluster DaemonSet
//! deployments talking to `hub_api`'s netsvcs manager, REST for bare-metal
//! edge nodes reaching `hub_api`'s public `/api/v1/netsvcs` surface.

mod grpc;
mod rest;
mod tls;

pub use grpc::GrpcClient;
pub use rest::RestClient;
pub use tls::install_crypto_provider;

use node_agent_core::{AgentConfig, AgentMode, ControlPlaneClient};
use std::sync::Arc;

/// Generated gRPC client/message types for `netsvcs.manager.v1`, produced
/// at build time by `tonic-prost-build` from the shared `proto/` contract
/// (see `build.rs`).
pub mod pb {
    tonic::include_proto!("netsvcs.manager.v1");
}

/// Builds the `ControlPlaneClient` implementation appropriate for
/// `cfg.mode` — `GrpcClient` for `Daemonset` (intra-cluster), `RestClient`
/// for `Edge` (bare-metal reaching `hub_api` over REST). Construction is
/// infallible; callers must invoke [`install_crypto_provider`] once before
/// calling this so the two transports share a single `rustls` backend.
pub fn build_client(cfg: &AgentConfig) -> Arc<dyn ControlPlaneClient> {
    match cfg.mode {
        AgentMode::Daemonset => Arc::new(GrpcClient::new(cfg)),
        AgentMode::Edge => Arc::new(RestClient::new(cfg)),
    }
}
