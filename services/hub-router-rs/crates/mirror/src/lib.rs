//! Hub router traffic-mirroring subsystem — the Rust port of the Go
//! headend's `mirror` package
//! (`services/hub-router/proxy/mirror/manager.go`). See each submodule's
//! doc for its slice of the port: [`config`] (wire `MirrorConfig` +
//! defaulting/validation, characterization-tested against the Go
//! source's observed behavior before this port's own logic existed),
//! [`packet`] (wire types: `MirrorPacket`, `HttpRequestInfo`, `Stats`),
//! [`encode`] (pure encapsulation/formatting functions — VXLAN/GRE/ERSPAN
//! headers, HTTP text framing, Suricata EVE JSON), [`manager`] (the
//! queue/worker-pool lifecycle + public API, including this port's scope
//! boundary and its two deliberate Go-bug fixes), and [`metrics`] (OTel
//! instrumentation).

pub mod config;
pub mod encode;
pub mod manager;
pub mod metrics;
pub mod packet;

pub use config::MirrorConfig;
pub use manager::{Manager, ManagerError};
pub use packet::{HttpRequestInfo, MirrorPacket, Stats, StatsSnapshot};
