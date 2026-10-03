//! Hub router syslog log-forwarding subsystem — the Rust port of the Go
//! headend's `syslog` package
//! (`services/hub-router/proxy/syslog/logger.go`). See each submodule's
//! doc for its slice of the port: [`config`] (wire `SyslogConfig` +
//! `bootstrap.go`'s activation-gating branch, characterization-tested
//! against the Go source's observed behavior before this port's own
//! logic existed), [`message`] (pure framing/formatting: `AccessLog`,
//! facility/severity priority calculation, the `<pri>timestamp hostname
//! appname: json` wire frame — byte-exact against Go where
//! deterministic), [`logger`] (the queue/worker-pool lifecycle + public
//! API, including this port's scope boundary and its three deliberate
//! Go-behavior deviations), and [`metrics`] (OTel instrumentation).

pub mod config;
pub mod logger;
pub mod message;
pub mod metrics;

pub use config::{Activation, SyslogConfig};
pub use logger::{Logger, LoggerError};
pub use message::{AccessLog, Facility, Severity};
