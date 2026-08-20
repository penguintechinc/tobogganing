//! `node_agent_core`: shared config, error, machine-JWT signing, and the
//! transport-agnostic [`ControlPlaneClient`] contract implemented by
//! `node-agent-transport` and consumed by every capability module.
//!
//! This crate is the interface contract the rest of the `node-agent`
//! workspace is built against — `transport`, `connectivity`, and
//! `netsvcs-edge` depend on the types and trait defined here without
//! depending on each other, so they can be developed in parallel.

pub mod client;
pub mod config;
pub mod error;
pub mod jwt;
pub mod types;

pub use client::ControlPlaneClient;
pub use config::{AgentConfig, AgentFeatures, AgentMode};
pub use error::{AgentError, Result};
pub use jwt::{decode_unverified_claims, MachineJwtClaims, MachineJwtSigner};
pub use types::{
    ConnectivityConfig, DhcpConfig, DnsConfig, EnrollRequest, EnrollResponse, Heartbeat,
    IocVerdict, MetricSample, Metrics, NetsvcsEdgeConfig, NodeConfig, NodeIdentity, NtpConfig,
    RefreshResponse,
};
