//! Hub-router dynamic port management.
//!
//! Rust port of the Go headend's `ports` package
//! (`services/hub-router/proxy/ports/{manager,config_client}.go`):
//! parsing/validating a configured TCP/UDP port-range string, managing
//! the resulting set of listening sockets (dispatching each accepted
//! connection/packet to caller-supplied handlers), and fetching that
//! configuration from the Manager/hub-api control plane. See
//! [`manager`]'s module doc for what is deliberately *not* in this crate's
//! scope (the Go `proxy/dynamic_ports.go` data-plane dispatch logic —
//! tracked as a follow-up port).
//!
//! Characterization tests throughout this crate's modules capture the Go
//! source's exact observable behavior (including two Go quirks preserved
//! as-is and one bug fixed) before/while implementing — see each module's
//! doc comment for specifics, and the PR description for the full list.

pub mod config_client;
pub mod manager;
mod metrics;
pub mod range;
pub mod validate;

pub use config_client::{
    ConfigClient, ConfigClientError, PortConfig, PortRangeDetail, TokenProvider,
};
pub use manager::{
    ConnHandler, ManagerError, PacketHandler, PortListenerInfo, PortManager, StartListeningReport,
};
pub use range::{parse_port_ranges, PortRange, Protocol, RangeParseError};
pub use validate::{validate_port_ranges, ValidateError};
