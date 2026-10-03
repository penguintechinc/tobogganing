//! Wire configuration for the mirror subsystem — the Rust port of
//! `MirrorConfig` (`services/hub-router/config/manager.go`, lines
//! 110-118) plus the construction-time defaulting/gating logic that lives
//! in `services/hub-router/proxy/bootstrap.go` (lines 114-118, 211-238)
//! and `mirror.NewManager`/`mirror.NewManagerWithSuricata`
//! (`services/hub-router/proxy/mirror/manager.go`, lines 63-96).
//!
//! `sample_rate` and `filter` are parsed from the wire payload but **never
//! read anywhere** in the Go source (confirmed by grep across
//! `services/hub-router/` — struct-definition-only). This is a real Go
//! limitation (sampling and BPF-style filtering are configured but not
//! implemented), not something introduced by this port — both fields are
//! kept here only for schema compatibility with the hub-api wire format
//! and are otherwise dead, exactly matching the Go source.

use serde::{Deserialize, Serialize};

/// Default worker queue depth — the Rust port of `bootstrap.go`'s
/// `viper.SetDefault("mirror.buffer_size", 1000)`.
pub const DEFAULT_BUFFER_SIZE: usize = 1000;

/// Default encapsulation protocol applied whenever the configured value is
/// empty — the Rust port of `NewManager`/`NewManagerWithSuricata`'s
/// `if protocol == "" { protocol = "VXLAN" }`.
pub const DEFAULT_PROTOCOL: &str = "VXLAN";

/// Default Suricata TCP port — the Rust port of `bootstrap.go`'s
/// `viper.SetDefault("mirror.suricata_port", "9999")`.
pub const DEFAULT_SURICATA_PORT: &str = "9999";

/// Traffic-mirroring settings as received from the hub-api/Manager control
/// plane — field-for-field port of Go's `MirrorConfig`.
#[derive(Debug, Clone, PartialEq, Eq, Default, Deserialize, Serialize)]
pub struct MirrorConfig {
    pub enabled: bool,
    #[serde(default)]
    pub destinations: Vec<String>,
    #[serde(default)]
    pub protocol: String,
    #[serde(default)]
    pub buffer_size: usize,
    /// Parsed but unused — see module doc.
    #[serde(default)]
    pub sample_rate: i32,
    /// Parsed but unused — see module doc.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub filter: Option<String>,
    #[serde(default)]
    pub suricata_enabled: bool,
    #[serde(default)]
    pub suricata_host: String,
    #[serde(default)]
    pub suricata_port: String,
}

impl MirrorConfig {
    /// The protocol to actually construct the manager with — the Rust
    /// port of `NewManager`'s empty-string defaulting (`if protocol == ""
    /// { protocol = "VXLAN" }`). Returns the configured value verbatim
    /// (including an unrecognized value) otherwise, matching the Go
    /// source: protocol validity is only checked later, structurally, by
    /// `create_connection`/`encapsulate_*` falling back to their `default`
    /// match arm.
    #[must_use]
    pub fn resolved_protocol(&self) -> &str {
        if self.protocol.is_empty() {
            DEFAULT_PROTOCOL
        } else {
            &self.protocol
        }
    }

    /// The worker queue depth to actually construct the manager with — the
    /// Rust port of the plain `bufferSize int` parameter threaded straight
    /// through from `bootstrap.go`'s `viper.GetInt("mirror.buffer_size")`
    /// (default `1000`, see `DEFAULT_BUFFER_SIZE`) with no additional
    /// clamping in the Go source. `0` is passed through as-is — the Go
    /// source does the same (`make(chan *MirrorPacket, 0)` is a valid,
    /// always-full unbuffered channel in Go; the Rust port's
    /// [`crate::manager::Manager`] documents the equivalent behavior for
    /// `tokio::sync::mpsc::channel(0)`).
    #[must_use]
    pub fn resolved_buffer_size(&self) -> usize {
        self.buffer_size
    }

    /// Whether Suricata forwarding should be enabled for a manager built
    /// from this config — the Rust port of `NewManagerWithSuricata`'s
    /// `suricataEnabled: suricataHost != "" && suricataPort != ""`. Note
    /// this is independent of `suricata_enabled` on the wire: the Go
    /// source's `bootstrap.go` branches on `viper.GetBool
    /// ("mirror.suricata_enabled")` to *choose which constructor to call*,
    /// but the constructor itself re-derives enablement from
    /// host/port non-emptiness rather than trusting that flag directly.
    /// This method reproduces the constructor's own derivation.
    #[must_use]
    pub fn suricata_active(&self) -> bool {
        !self.suricata_host.is_empty() && !self.suricata_port.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_is_disabled_with_no_destinations() {
        let cfg = MirrorConfig::default();
        assert!(!cfg.enabled);
        assert!(cfg.destinations.is_empty());
    }

    #[test]
    fn empty_protocol_resolves_to_vxlan_default() {
        let cfg = MirrorConfig {
            protocol: String::new(),
            ..Default::default()
        };
        assert_eq!(cfg.resolved_protocol(), "VXLAN");
    }

    #[test]
    fn configured_protocol_is_returned_verbatim() {
        let cfg = MirrorConfig {
            protocol: "GRE".to_string(),
            ..Default::default()
        };
        assert_eq!(cfg.resolved_protocol(), "GRE");
    }

    /// Matches the Go source exactly: an unrecognized protocol string is
    /// not rejected at config-resolution time, only later falls back to
    /// the `default` match arm in encapsulation/connection code.
    #[test]
    fn unrecognized_protocol_is_passed_through_unvalidated() {
        let cfg = MirrorConfig {
            protocol: "NOT-A-REAL-PROTOCOL".to_string(),
            ..Default::default()
        };
        assert_eq!(cfg.resolved_protocol(), "NOT-A-REAL-PROTOCOL");
    }

    #[test]
    fn buffer_size_passes_through_including_zero() {
        let cfg = MirrorConfig {
            buffer_size: 0,
            ..Default::default()
        };
        assert_eq!(cfg.resolved_buffer_size(), 0);

        let cfg = MirrorConfig {
            buffer_size: 4096,
            ..Default::default()
        };
        assert_eq!(cfg.resolved_buffer_size(), 4096);
    }

    #[test]
    fn suricata_active_requires_both_host_and_port() {
        assert!(!MirrorConfig::default().suricata_active());

        let host_only = MirrorConfig {
            suricata_host: "10.0.0.5".to_string(),
            ..Default::default()
        };
        assert!(!host_only.suricata_active());

        let port_only = MirrorConfig {
            suricata_port: "9999".to_string(),
            ..Default::default()
        };
        assert!(!port_only.suricata_active());

        let both = MirrorConfig {
            suricata_host: "10.0.0.5".to_string(),
            suricata_port: "9999".to_string(),
            ..Default::default()
        };
        assert!(both.suricata_active());
    }

    #[test]
    fn deserializes_from_the_hub_api_wire_shape() {
        let json = serde_json::json!({
            "enabled": true,
            "destinations": ["10.0.0.5:4789"],
            "protocol": "VXLAN",
            "buffer_size": 1000,
            "sample_rate": 10,
            "filter": "tcp port 443"
        });
        let cfg: MirrorConfig = serde_json::from_value(json).unwrap();
        assert!(cfg.enabled);
        assert_eq!(cfg.destinations, vec!["10.0.0.5:4789".to_string()]);
        assert_eq!(cfg.sample_rate, 10);
        assert_eq!(cfg.filter, Some("tcp port 443".to_string()));
    }

    #[test]
    fn missing_optional_fields_default_sanely() {
        let cfg: MirrorConfig = serde_json::from_value(serde_json::json!({ "enabled": false }))
            .expect("all fields but `enabled` are defaultable");
        assert!(!cfg.enabled);
        assert!(cfg.destinations.is_empty());
        assert_eq!(cfg.protocol, "");
        assert_eq!(cfg.filter, None);
    }
}
