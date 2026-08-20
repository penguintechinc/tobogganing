//! Top-level agent configuration: deployment mode, control-plane endpoint,
//! machine-JWT key location, and runtime feature toggles. Loaded by
//! layering defaults, an optional TOML file, and `NODE_AGENT_`-prefixed
//! environment variables via `figment`.

use crate::error::{AgentError, Result};
use clap::ValueEnum;
use figment::providers::{Env, Format, Serialized, Toml};
use figment::Figment;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// Deployment mode, which selects both the transport (`transport::build_client`)
/// and which capability defaults apply — `Daemonset` for intra-cluster gRPC,
/// `Edge` for bare-metal REST.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
pub enum AgentMode {
    Daemonset,
    Edge,
}

/// Runtime toggles for the two capability modules, independent of the
/// `connectivity`/`netsvcs-edge` cargo compile-time features — a module
/// compiled in can still be disabled at runtime via config.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentFeatures {
    #[serde(default = "default_true")]
    pub connectivity: bool,
    #[serde(default = "default_true")]
    pub netsvcs_edge: bool,
}

impl Default for AgentFeatures {
    fn default() -> Self {
        Self {
            connectivity: true,
            netsvcs_edge: true,
        }
    }
}

/// Top-level agent configuration, loaded once at startup and handed to
/// `transport::build_client` and both capability modules' `run()` entrypoints.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentConfig {
    pub mode: AgentMode,
    pub control_plane_url: String,
    pub machine_jwt_path: PathBuf,
    #[serde(default)]
    pub features: AgentFeatures,
    #[serde(default = "default_heartbeat_interval_secs")]
    pub heartbeat_interval_secs: u64,
    #[serde(default = "default_request_timeout_secs")]
    pub request_timeout_secs: u64,
}

impl Default for AgentConfig {
    fn default() -> Self {
        Self {
            mode: AgentMode::Edge,
            control_plane_url: "https://hub-api.tobogganing.svc:8443".to_string(),
            machine_jwt_path: PathBuf::from("/etc/node-agent/machine.pem"),
            features: AgentFeatures::default(),
            heartbeat_interval_secs: default_heartbeat_interval_secs(),
            request_timeout_secs: default_request_timeout_secs(),
        }
    }
}

impl AgentConfig {
    /// Loads configuration by layering, in increasing precedence: built-in
    /// defaults, an optional TOML file at `config_path`, then
    /// `NODE_AGENT_`-prefixed environment variables (`__` splits nested
    /// keys, e.g. `NODE_AGENT_FEATURES__CONNECTIVITY=false`).
    pub fn load(config_path: Option<&Path>) -> Result<Self> {
        let mut figment = Figment::from(Serialized::defaults(AgentConfig::default()));
        if let Some(path) = config_path {
            figment = figment.merge(Toml::file(path));
        }
        figment = figment.merge(Env::prefixed("NODE_AGENT_").split("__"));
        figment
            .extract()
            .map_err(|e| AgentError::ConfigParse(Box::new(e)))
    }
}

fn default_true() -> bool {
    true
}

fn default_heartbeat_interval_secs() -> u64 {
    30
}

fn default_request_timeout_secs() -> u64 {
    10
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn load_falls_back_to_defaults_without_a_file() {
        let cfg = AgentConfig::load(None).expect("defaults alone must extract cleanly");
        assert_eq!(cfg.mode, AgentMode::Edge);
        assert!(cfg.features.connectivity);
        assert!(cfg.features.netsvcs_edge);
        assert_eq!(cfg.heartbeat_interval_secs, 30);
    }

    #[test]
    fn load_merges_a_toml_file_over_defaults() {
        let dir =
            std::env::temp_dir().join(format!("node-agent-config-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("temp dir for config test must be creatable");
        let path = dir.join("config.toml");
        std::fs::write(
            &path,
            r#"
            mode = "daemonset"
            control_plane_url = "https://hub-api.example.internal:50051"
            machine_jwt_path = "/etc/node-agent/machine.pem"

            [features]
            connectivity = true
            netsvcs_edge = false
            "#,
        )
        .expect("writing the test config file must succeed");

        let cfg = AgentConfig::load(Some(&path)).expect("a well-formed TOML file must load");
        assert_eq!(cfg.mode, AgentMode::Daemonset);
        assert_eq!(
            cfg.control_plane_url,
            "https://hub-api.example.internal:50051"
        );
        assert!(!cfg.features.netsvcs_edge);

        let _ = std::fs::remove_dir_all(&dir);
    }
}
