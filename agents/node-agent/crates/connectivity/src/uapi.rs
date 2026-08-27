//! Assembles WireGuard UAPI configuration commands
//! (<https://www.wireguard.com/xplatform/#configuration-protocol>) — the
//! same text protocol `wg setconf` and wireguard-go's `IpcSetOperation`
//! speak. Kept as pure string assembly, separate from the socket I/O in
//! [`crate::device`], so it is unit-testable without a real interface.

use node_agent_core::WireguardConfig;

/// Renders a `set=1` command that replaces the device's private key,
/// listen port, and single headend peer with `cfg`. `replace_peers`/
/// `replace_allowed_ips` are always set so re-applying an updated config
/// (control-plane config-poll) fully supersedes the previous peer state
/// rather than merging with it.
pub fn build_set_command(private_key_b64: &str, listen_port: u16, cfg: &WireguardConfig) -> String {
    let mut out = String::from("set=1\n");
    out.push_str(&format!("private_key={private_key_b64}\n"));
    if listen_port != 0 {
        out.push_str(&format!("listen_port={listen_port}\n"));
    }
    out.push_str("replace_peers=true\n");
    out.push_str(&format!("public_key={}\n", cfg.peer_public_key));
    out.push_str("replace_allowed_ips=true\n");
    if !cfg.peer_endpoint.is_empty() {
        out.push_str(&format!("endpoint={}\n", cfg.peer_endpoint));
    }
    if cfg.persistent_keepalive_secs > 0 {
        out.push_str(&format!(
            "persistent_keepalive_interval={}\n",
            cfg.persistent_keepalive_secs
        ));
    }
    for ip in &cfg.allowed_ips {
        out.push_str(&format!("allowed_ip={ip}\n"));
    }
    out.push('\n');
    out
}

/// Reports whether a UAPI response line signals success (`errno=0`) per the
/// protocol's "return an error code as the response, or zero on success"
/// contract.
pub fn is_success_response(response: &str) -> bool {
    response.trim().starts_with("errno=0")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_cfg() -> WireguardConfig {
        WireguardConfig {
            interface_name: "wg-toboggan".to_string(),
            interface_address: "10.200.0.5/32".to_string(),
            peer_public_key: "aGVhZGVuZC1wdWJsaWMta2V5LWJhc2U2NC0hISEhISE=".to_string(),
            peer_endpoint: "headend.example.internal:51820".to_string(),
            allowed_ips: vec!["0.0.0.0/0".to_string(), "::/0".to_string()],
            persistent_keepalive_secs: 25,
            dns: vec!["10.200.0.1".to_string()],
        }
    }

    #[test]
    fn build_set_command_includes_every_configured_field() {
        let cmd = build_set_command("private-key-b64", 51821, &sample_cfg());
        assert!(cmd.starts_with("set=1\n"));
        assert!(cmd.contains("private_key=private-key-b64\n"));
        assert!(cmd.contains("listen_port=51821\n"));
        assert!(cmd.contains("replace_peers=true\n"));
        assert!(cmd.contains("public_key=aGVhZGVuZC1wdWJsaWMta2V5LWJhc2U2NC0hISEhISE=\n"));
        assert!(cmd.contains("endpoint=headend.example.internal:51820\n"));
        assert!(cmd.contains("persistent_keepalive_interval=25\n"));
        assert!(cmd.contains("allowed_ip=0.0.0.0/0\n"));
        assert!(cmd.contains("allowed_ip=::/0\n"));
        assert!(cmd.ends_with('\n'));
    }

    #[test]
    fn build_set_command_omits_listen_port_when_zero() {
        let cmd = build_set_command("k", 0, &sample_cfg());
        assert!(!cmd.contains("listen_port="));
    }

    #[test]
    fn build_set_command_omits_keepalive_when_zero() {
        let mut cfg = sample_cfg();
        cfg.persistent_keepalive_secs = 0;
        let cmd = build_set_command("k", 51820, &cfg);
        assert!(!cmd.contains("persistent_keepalive_interval="));
    }

    #[test]
    fn build_set_command_omits_endpoint_when_empty() {
        let mut cfg = sample_cfg();
        cfg.peer_endpoint = String::new();
        let cmd = build_set_command("k", 51820, &cfg);
        assert!(!cmd.contains("endpoint="));
    }

    #[test]
    fn is_success_response_accepts_errno_zero() {
        assert!(is_success_response("errno=0\n\n"));
        assert!(is_success_response("  errno=0  "));
    }

    #[test]
    fn is_success_response_rejects_nonzero_errno() {
        assert!(!is_success_response("errno=22\n\n"));
        assert!(!is_success_response(""));
    }
}
