//! Optional XDP inspection tap (cargo feature `xdp`, **not** in the default
//! feature set) — loads and attaches a userspace-managed eBPF program via
//! `aya` to observe traffic on the WireGuard interface for telemetry.
//!
//! This module builds and links on stable Rust with no eBPF toolchain: it
//! loads a *pre-compiled* eBPF object from disk at runtime rather than
//! compiling one itself. The eBPF program's own source (an `aya-ebpf`
//! `#![no_std]` crate targeting `bpfel-unknown-none`) needs a nightly
//! toolchain + `bpf-linker` to build and is intentionally out of scope for
//! this crate — lowest priority per the P4 task scope, and a separate build
//! target so it never taints the default `cargo build`/`clippy` path. Drop
//! the compiled object at the path passed to [`XdpTap::attach`] (convention:
//! `/etc/node-agent/xdp/inspect.o`) once that companion crate exists.

use aya::programs::{Xdp, XdpFlags};
use aya::Ebpf;
use node_agent_core::{AgentError, Result};
use std::path::Path;

/// Name of the XDP program section the loader looks up inside the compiled
/// object — the companion `aya-ebpf` crate must export a program with this
/// name (`#[xdp(name = "xdp_inspect")]`).
pub const PROGRAM_NAME: &str = "xdp_inspect";

/// A running XDP inspection attachment. Dropping this detaches the program
/// via `aya`'s own `Drop` impl on the underlying link, restoring the
/// interface to its unmonitored state.
pub struct XdpTap {
    _bpf: Ebpf,
    interface: String,
}

impl XdpTap {
    /// Loads the eBPF object at `object_path` and attaches its
    /// `xdp_inspect` program to `interface` in SKB (generic) mode — works
    /// without driver-level native XDP support, at a modest throughput cost
    /// appropriate for an inspection tap rather than the wire-speed data
    /// plane itself.
    ///
    /// Requires `NET_ADMIN`/`NET_RAW`, or `CAP_BPF` on kernel 5.8+; callers
    /// should treat failure as a capability/artifact gap to log and degrade
    /// from, never a reason to crash the agent.
    pub fn attach(object_path: &Path, interface: &str) -> Result<Self> {
        let mut bpf = Ebpf::load_file(object_path).map_err(|e| {
            AgentError::Task(format!(
                "failed to load XDP inspection object {object_path:?}: {e}"
            ))
        })?;

        let program: &mut Xdp = bpf
            .program_mut(PROGRAM_NAME)
            .ok_or_else(|| {
                AgentError::Task(format!(
                    "XDP object {object_path:?} has no \"{PROGRAM_NAME}\" program"
                ))
            })?
            .try_into()
            .map_err(|e| {
                AgentError::Task(format!("\"{PROGRAM_NAME}\" is not an XDP program: {e}"))
            })?;

        program.load().map_err(|e| {
            AgentError::Task(format!("failed to load XDP program into the kernel: {e}"))
        })?;
        program.attach(interface, XdpFlags::SKB_MODE).map_err(|e| {
            AgentError::Task(format!("failed to attach XDP program to {interface}: {e}"))
        })?;

        Ok(Self {
            _bpf: bpf,
            interface: interface.to_string(),
        })
    }

    /// The interface this tap is attached to.
    pub fn interface(&self) -> &str {
        &self.interface
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn attach_reports_a_task_error_for_a_missing_object_file() {
        match XdpTap::attach(Path::new("/nonexistent/inspect.o"), "eth0") {
            Err(AgentError::Task(_)) => {}
            Err(other) => panic!("expected AgentError::Task, got a different variant: {other}"),
            Ok(_) => panic!("a missing object file must not panic or succeed"),
        }
    }
}
