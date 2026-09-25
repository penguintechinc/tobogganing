//! `healthz` subcommand: a lightweight, dependency-free liveness check
//! wired as the container `HEALTHCHECK` command. Runs as a fresh process
//! invocation, so it validates the binary and its configuration rather
//! than querying a running daemon's in-memory state.

use node_agent_core::{AgentConfig, Result};
use std::path::Path;

/// Validates that configuration loads cleanly — the failure mode a broken
/// image or misconfigured rollout hits most often. A liveness probe against
/// the running daemon (local status file or loopback probe) lands with
/// Stage I packaging.
pub async fn healthz(config_path: Option<&Path>) -> Result<()> {
    let _ = AgentConfig::load(config_path)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use node_agent_core::AgentError;

    #[tokio::test]
    async fn succeeds_with_no_config_file_via_built_in_defaults() {
        healthz(None)
            .await
            .expect("defaults alone must load cleanly");
    }

    #[tokio::test]
    async fn succeeds_with_a_well_formed_config_file() {
        let dir =
            std::env::temp_dir().join(format!("node-agent-healthz-test-ok-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("temp dir must be creatable");
        let path = dir.join("config.toml");
        std::fs::write(
            &path,
            r#"
            mode = "edge"
            control_plane_url = "https://hub-api.example.internal:8443"
            machine_jwt_path = "/etc/node-agent/machine.pem"
            "#,
        )
        .expect("writing the test config file must succeed");

        healthz(Some(&path))
            .await
            .expect("a well-formed config file must pass the health check");

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[tokio::test]
    async fn fails_with_a_malformed_config_file() {
        let dir = std::env::temp_dir().join(format!(
            "node-agent-healthz-test-bad-{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).expect("temp dir must be creatable");
        let path = dir.join("config.toml");
        std::fs::write(&path, "mode = 12345\nnot valid = = toml{{{").expect("write must succeed");

        let err = healthz(Some(&path))
            .await
            .expect_err("a malformed config file must fail the health check");
        assert!(matches!(err, AgentError::ConfigParse(_)));

        let _ = std::fs::remove_dir_all(&dir);
    }
}
