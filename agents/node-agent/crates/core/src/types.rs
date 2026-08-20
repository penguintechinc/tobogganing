//! Shared domain types passed across the `ControlPlaneClient` boundary.
//! These are the wire-agnostic structs every transport implementation
//! (gRPC, REST) maps to/from, and every capability module (`connectivity`,
//! `netsvcs-edge`) consumes without depending on either transport.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// This node's identity once enrolled: the control-plane-assigned
/// `node_id`, its owning `tenant`, and the static facts supplied at
/// enrollment time (`node_type`, `hostname`).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct NodeIdentity {
    pub node_id: String,
    pub tenant: String,
    pub node_type: String,
    pub hostname: String,
}

/// Request to enroll this node against the control plane's `headend`
/// audience. `machine_jwt` is the short-lived signed JWT proving this node's
/// bootstrap identity; `public_key` is the optional WireGuard/Ziti public
/// key advertised for connectivity-capable nodes.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnrollRequest {
    pub machine_jwt: String,
    pub node_type: String,
    pub hostname: String,
    pub public_key: Option<String>,
}

/// Response to a successful enrollment: the assigned `node_id`/`tenant`,
/// the short-lived `access_token` used to authenticate subsequent calls,
/// a rotating single-use `refresh_token`, and the node's initial config.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnrollResponse {
    pub node_id: String,
    pub tenant: String,
    pub access_token: String,
    pub refresh_token: String,
    pub config: NodeConfig,
}

/// A periodic liveness signal sent to the control plane; `config_version`
/// reports the config version currently applied so the server can decide
/// whether this node needs to sync.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Heartbeat {
    pub node_id: String,
    pub timestamp: i64,
    pub config_version: i64,
}

/// A single named metric observation, labeled for aggregation (mirrors the
/// Prometheus label model used by the `metrics` crate at the API boundary).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MetricSample {
    pub name: String,
    pub value: f64,
    #[serde(default)]
    pub labels: HashMap<String, String>,
    pub timestamp: i64,
}

/// A batch of metric samples reported for a single node in one call.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Metrics {
    pub node_id: String,
    pub samples: Vec<MetricSample>,
}

/// Response to a token refresh: a freshly issued `access_token` and the
/// next single-use `refresh_token` (the one just spent is invalidated on
/// the server per the `jti` replay-protection contract).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RefreshResponse {
    pub access_token: String,
    pub refresh_token: String,
}

/// Verdict for an indicator-of-compromise lookup (domain or IP) against the
/// control plane's threat-intel feed.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IocVerdict {
    pub indicator: String,
    pub malicious: bool,
    pub source: Option<String>,
}

/// Local DNS/DoH-forwarding configuration for the `netsvcs-edge` module —
/// upstream P3 DoH resolver targets, local cache sizing, and whether IOC
/// filtering is enforced on resolutions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DnsConfig {
    #[serde(default)]
    pub upstream_doh_urls: Vec<String>,
    #[serde(default = "default_dns_listen_addr")]
    pub listen_addr: String,
    #[serde(default = "default_true")]
    pub cache_enabled: bool,
    #[serde(default = "default_cache_max_entries")]
    pub cache_max_entries: u32,
    #[serde(default = "default_cache_ttl_secs")]
    pub cache_ttl_secs: u32,
    #[serde(default)]
    pub ioc_filtering: bool,
}

impl Default for DnsConfig {
    fn default() -> Self {
        Self {
            upstream_doh_urls: Vec::new(),
            listen_addr: default_dns_listen_addr(),
            cache_enabled: default_true(),
            cache_max_entries: default_cache_max_entries(),
            cache_ttl_secs: default_cache_ttl_secs(),
            ioc_filtering: false,
        }
    }
}

/// SASE connectivity configuration for the `connectivity` module —
/// WireGuard/Ziti enablement and the optional XDP inspection tap.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConnectivityConfig {
    #[serde(default = "default_true")]
    pub wireguard_enabled: bool,
    #[serde(default)]
    pub ziti_enabled: bool,
    #[serde(default = "default_wireguard_port")]
    pub wireguard_listen_port: u16,
    #[serde(default)]
    pub xdp_tap_enabled: bool,
}

impl Default for ConnectivityConfig {
    fn default() -> Self {
        Self {
            wireguard_enabled: default_true(),
            ziti_enabled: false,
            wireguard_listen_port: default_wireguard_port(),
            xdp_tap_enabled: false,
        }
    }
}

/// DHCP client configuration for the `netsvcs-edge` module — which network
/// interface to bind the client socket to (`None` binds all interfaces) and
/// whether to advertise a hostname in outgoing DISCOVER/REQUEST messages.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DhcpConfig {
    #[serde(default)]
    pub interface: Option<String>,
    #[serde(default)]
    pub hostname: Option<String>,
}

/// NTP client configuration for the `netsvcs-edge` module — the upstream
/// servers to query and how often to poll them.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NtpConfig {
    #[serde(default)]
    pub servers: Vec<String>,
    #[serde(default = "default_ntp_poll_interval_secs")]
    pub poll_interval_secs: u32,
}

impl Default for NtpConfig {
    fn default() -> Self {
        Self {
            servers: Vec::new(),
            poll_interval_secs: default_ntp_poll_interval_secs(),
        }
    }
}

/// Top-level enablement + bind address for the local netsvcs-edge services
/// (`:53` DNS forward, DHCP, NTP), plus the capability-specific sub-configs
/// (`DnsConfig`, `DhcpConfig`, `NtpConfig`) — embedded here (rather than
/// left as NodeConfig siblings) so the single `NetsvcsEdgeConfig` passed to
/// `node_agent_netsvcs_edge::run` carries everything the module needs.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetsvcsEdgeConfig {
    #[serde(default = "default_true")]
    pub dns_enabled: bool,
    #[serde(default)]
    pub dhcp_enabled: bool,
    #[serde(default)]
    pub ntp_enabled: bool,
    #[serde(default = "default_edge_bind_addr")]
    pub bind_addr: String,
    #[serde(default)]
    pub dns: DnsConfig,
    #[serde(default)]
    pub dhcp: Option<DhcpConfig>,
    #[serde(default)]
    pub ntp: Option<NtpConfig>,
}

impl Default for NetsvcsEdgeConfig {
    fn default() -> Self {
        Self {
            dns_enabled: default_true(),
            dhcp_enabled: false,
            ntp_enabled: false,
            bind_addr: default_edge_bind_addr(),
            dns: DnsConfig::default(),
            dhcp: None,
            ntp: None,
        }
    }
}

/// The full node configuration returned by the control plane on enroll and
/// polled thereafter via `get_config` — one sub-config per capability plus
/// the version stamp used for change detection.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeConfig {
    pub dns: DnsConfig,
    pub connectivity: ConnectivityConfig,
    pub edge: NetsvcsEdgeConfig,
    pub config_version: i64,
}

fn default_true() -> bool {
    true
}

fn default_dns_listen_addr() -> String {
    "0.0.0.0:53".to_string()
}

fn default_cache_max_entries() -> u32 {
    10_000
}

fn default_cache_ttl_secs() -> u32 {
    300
}

fn default_wireguard_port() -> u16 {
    51820
}

fn default_edge_bind_addr() -> String {
    "0.0.0.0:53".to_string()
}

fn default_ntp_poll_interval_secs() -> u32 {
    64
}
