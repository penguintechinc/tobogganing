//! Wire configuration for the syslog log-forwarding subsystem — the Rust
//! port of `bootstrap.go`'s `syslog.*` viper defaults (lines 125-129)
//! and its construction-gating branch (lines 271-285).
//!
//! `facility` and `tag` are parsed from the wire payload but **never
//! passed to `NewSyslogLogger`** (confirmed by grep across
//! `services/hub-router/`: the only call site,
//! `syslog.NewSyslogLogger(syslogHost, syslogPort)`, takes just two
//! arguments) — a real Go limitation (facility/tag are configured but
//! silently ignored; the logger always hardcodes `FacilityLocal0`/
//! `"sasewaddle-headend"`, see [`crate::message`]/[`crate::logger`]'s
//! module docs), not something introduced by this port. Both fields are
//! kept here only for schema compatibility with the hub-api wire format
//! and are otherwise dead — exactly mirroring
//! `hub_router_mirror::config::MirrorConfig`'s `sample_rate`/`filter`
//! fields.

use serde::{Deserialize, Serialize};

/// Default syslog UDP port — the Rust port of `bootstrap.go`'s
/// `viper.SetDefault("syslog.port", "514")`.
pub const DEFAULT_PORT: &str = "514";

/// Outcome of evaluating a [`SyslogConfig`] against `bootstrap.go`'s
/// three-way branch (lines 271-285) for whether/how to construct and
/// start a [`crate::logger::Logger`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Activation {
    /// `syslog.enabled` is false — the Rust port of the outer `else`
    /// branch (`log.Info("Syslog logging disabled")`). No logger is
    /// constructed.
    Disabled,
    /// `syslog.enabled` is true but `syslog.host` is empty — the Rust
    /// port of the inner `else` branch (`log.Warn("Syslog enabled but no
    /// host configured")`). No logger is constructed in this case
    /// either.
    MissingHost,
    /// `syslog.enabled` is true and `syslog.host` is non-empty — a
    /// [`crate::logger::Logger`] should be constructed (from `host` and
    /// [`SyslogConfig::resolved_port`]) and started.
    Active,
}

/// Syslog log-forwarding settings as received from the hub-api control
/// plane — field-for-field port of `bootstrap.go`'s `syslog.*` viper
/// keys.
#[derive(Debug, Clone, PartialEq, Eq, Default, Deserialize, Serialize)]
pub struct SyslogConfig {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default)]
    pub host: String,
    #[serde(default)]
    pub port: String,
    /// Parsed but unused — see module doc.
    #[serde(default)]
    pub facility: String,
    /// Parsed but unused — see module doc.
    #[serde(default)]
    pub tag: String,
}

impl SyslogConfig {
    /// The port to actually dial — the Rust port of
    /// `viper.GetString("syslog.port")`'s implicit default resolution
    /// (viper falls back to `SetDefault`'s `"514"` whenever the key is
    /// unset; this port makes that explicit since it has no viper layer
    /// of its own to fall back through).
    #[must_use]
    pub fn resolved_port(&self) -> &str {
        if self.port.is_empty() {
            DEFAULT_PORT
        } else {
            &self.port
        }
    }

    /// Evaluates the three-way branch from `bootstrap.go` (lines
    /// 271-285) — see [`Activation`].
    #[must_use]
    pub fn activation(&self) -> Activation {
        if !self.enabled {
            Activation::Disabled
        } else if self.host.is_empty() {
            Activation::MissingHost
        } else {
            Activation::Active
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_is_disabled() {
        assert_eq!(SyslogConfig::default().activation(), Activation::Disabled);
    }

    #[test]
    fn enabled_without_host_is_missing_host() {
        let cfg = SyslogConfig {
            enabled: true,
            ..Default::default()
        };
        assert_eq!(cfg.activation(), Activation::MissingHost);
    }

    #[test]
    fn enabled_with_host_is_active() {
        let cfg = SyslogConfig {
            enabled: true,
            host: "10.0.0.5".to_string(),
            ..Default::default()
        };
        assert_eq!(cfg.activation(), Activation::Active);
    }

    #[test]
    fn disabled_with_host_set_is_still_disabled() {
        // Matches Go: the outer `if viper.GetBool("syslog.enabled")`
        // check short-circuits before the host is ever inspected.
        let cfg = SyslogConfig {
            enabled: false,
            host: "10.0.0.5".to_string(),
            ..Default::default()
        };
        assert_eq!(cfg.activation(), Activation::Disabled);
    }

    #[test]
    fn empty_port_resolves_to_default() {
        assert_eq!(SyslogConfig::default().resolved_port(), DEFAULT_PORT);
    }

    #[test]
    fn configured_port_is_returned_verbatim() {
        let cfg = SyslogConfig {
            port: "1514".to_string(),
            ..Default::default()
        };
        assert_eq!(cfg.resolved_port(), "1514");
    }

    #[test]
    fn deserializes_from_the_hub_api_wire_shape() {
        let json = serde_json::json!({
            "enabled": true,
            "host": "10.0.0.5",
            "port": "514",
            "facility": "local0",
            "tag": "sasewaddle-headend"
        });
        let cfg: SyslogConfig = serde_json::from_value(json).unwrap();
        assert!(cfg.enabled);
        assert_eq!(cfg.host, "10.0.0.5");
        assert_eq!(cfg.facility, "local0");
        assert_eq!(cfg.tag, "sasewaddle-headend");
    }

    #[test]
    fn missing_optional_fields_default_sanely() {
        let cfg: SyslogConfig =
            serde_json::from_value(serde_json::json!({ "enabled": false })).unwrap();
        assert!(!cfg.enabled);
        assert_eq!(cfg.host, "");
        assert_eq!(cfg.port, "");
        assert_eq!(cfg.facility, "");
        assert_eq!(cfg.tag, "");
    }
}
