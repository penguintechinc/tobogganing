//! Owns the running userspace WireGuard interface: creates the boringtun
//! TUN device and configures it over the UAPI control protocol carried on
//! an in-process `UnixStream` pair (no dependency on the filesystem
//! `/var/run/wireguard/*.sock` convention). Dropping a [`WireguardDevice`]
//! tears the interface down — `boringtun::device::DeviceHandle`'s own
//! `Drop` signals every worker thread to exit and closing the TUN fd
//! removes the (non-persistent) interface, matching the wg-quick "down"
//! contract without shelling out.

use crate::uapi;
use boringtun::device::{DeviceConfig, DeviceHandle};
use node_agent_core::{AgentError, Result, WireguardConfig};
use std::io::{BufRead, BufReader, Write};
#[cfg(target_os = "linux")]
use std::os::fd::IntoRawFd;
use std::os::unix::net::UnixStream;

/// A running boringtun WireGuard interface plus the control socket used to
/// (re)configure it in place. Requires `CAP_NET_ADMIN` (or root) to
/// construct; callers should treat construction failure as a capability gap
/// to log and degrade from, per the org's runtime-capability-detection
/// policy — never a reason to crash the agent.
pub struct WireguardDevice {
    // Held only to keep the device's worker threads alive; never read
    // directly again after construction, so the field itself is unused by
    // name but load-bearing for the interface's lifetime via `Drop`.
    _handle: DeviceHandle,
    control: UnixStream,
    interface_name: String,
}

impl WireguardDevice {
    /// Creates the named TUN-backed boringtun interface and applies `cfg`
    /// (this node's private key plus the single headend peer) immediately.
    pub fn create(
        interface_name: &str,
        private_key_b64: &str,
        listen_port: u16,
        cfg: &WireguardConfig,
    ) -> Result<Self> {
        let (control, device_side) = UnixStream::pair().map_err(AgentError::Io)?;
        #[cfg(target_os = "linux")]
        let device_fd = device_side.into_raw_fd();
        #[cfg(not(target_os = "linux"))]
        {
            let _ = device_side; // only Linux gets the in-process uapi_fd path
        }

        let device_config = DeviceConfig {
            n_threads: 2,
            use_connected_socket: true,
            #[cfg(target_os = "linux")]
            use_multi_queue: false,
            #[cfg(target_os = "linux")]
            uapi_fd: device_fd,
        };

        let handle = DeviceHandle::new(interface_name, device_config).map_err(|e| {
            AgentError::Task(format!(
                "failed to create WireGuard interface {interface_name} (requires CAP_NET_ADMIN): {e:?}"
            ))
        })?;

        let mut device = Self {
            _handle: handle,
            control,
            interface_name: interface_name.to_string(),
        };
        device.apply(private_key_b64, listen_port, cfg)?;
        Ok(device)
    }

    /// Re-sends the UAPI `set=1` command for `cfg` over the already-open
    /// control socket — used both for the initial configuration in
    /// [`Self::create`] and to apply a control-plane config-poll update to
    /// the running interface in place.
    pub fn apply(
        &mut self,
        private_key_b64: &str,
        listen_port: u16,
        cfg: &WireguardConfig,
    ) -> Result<()> {
        let command = uapi::build_set_command(private_key_b64, listen_port, cfg);
        self.control
            .write_all(command.as_bytes())
            .map_err(AgentError::Io)?;

        let mut reader = BufReader::new(&self.control);
        let mut response = String::new();
        reader.read_line(&mut response).map_err(AgentError::Io)?;
        if !uapi::is_success_response(&response) {
            return Err(AgentError::Task(format!(
                "WireGuard UAPI set failed for {}: {response}",
                self.interface_name
            )));
        }
        Ok(())
    }

    /// The kernel-visible interface name (e.g. `"wg-toboggan"`), used by
    /// [`crate::netconfig`] to look up the link for address/route setup.
    pub fn interface_name(&self) -> &str {
        &self.interface_name
    }
}
