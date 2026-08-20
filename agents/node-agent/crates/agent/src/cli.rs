//! Command-line surface for the `node-agent` binary: `run` (load config,
//! enroll, and run the configured capability modules until shutdown) and
//! `healthz` (exit 0/1, wired as the container `HEALTHCHECK`).

use clap::{Parser, Subcommand};
use node_agent_core::AgentMode;
use std::path::PathBuf;

/// Top-level CLI: the unified tobogganing node-agent, delivering SASE
/// connectivity and local netsvcs-edge services from one binary.
#[derive(Debug, Parser)]
#[command(name = "node-agent", version, about = "Unified tobogganing node-agent")]
pub struct Cli {
    /// Optional TOML config file, layered under defaults and above by
    /// `NODE_AGENT_`-prefixed environment variables.
    #[arg(long, global = true)]
    pub config: Option<PathBuf>,

    #[command(subcommand)]
    pub command: Command,
}

/// The two subcommands this binary supports.
#[derive(Debug, Subcommand)]
pub enum Command {
    /// Loads config, enrolls with the control plane, and runs the
    /// configured capability modules until an interrupt is received.
    Run {
        /// Overrides `AgentConfig.mode` from the loaded config.
        #[arg(long, value_enum)]
        mode: Option<AgentMode>,
        /// Overrides `AgentConfig.control_plane_url` from the loaded config.
        #[arg(long)]
        control_plane_url: Option<String>,
    },
    /// Validates the binary and its configuration are structurally sound;
    /// exits 0 on success, 1 on failure. Intended as the container
    /// `HEALTHCHECK` command.
    Healthz,
}
