//! The transport-agnostic control-plane contract. `node-agent-transport`
//! provides the gRPC and REST implementations; `connectivity` and
//! `netsvcs-edge` depend only on this trait, never on a concrete transport,
//! so the three can be built in parallel worktrees against a stable
//! interface.

use crate::error::Result;
use crate::types::{
    EnrollRequest, EnrollResponse, Heartbeat, IocVerdict, Metrics, NodeConfig, RefreshResponse,
};
use async_trait::async_trait;

/// Everything a node needs from the control plane: enrollment, heartbeat,
/// config polling, metrics reporting, token refresh, and IOC lookups.
/// Implementations attach a short-lived signed JWT to every call per the
/// universal inter-service auth policy, regardless of transport.
#[async_trait]
pub trait ControlPlaneClient: Send + Sync {
    /// Registers this node with the control plane using a machine-JWT,
    /// returning the assigned identity, initial access/refresh tokens, and
    /// starting node config.
    async fn enroll(&self, req: EnrollRequest) -> Result<EnrollResponse>;

    /// Sends a liveness signal; the control plane may use the response to
    /// signal that this node's config is stale (handled by `get_config`).
    async fn heartbeat(&self, hb: Heartbeat) -> Result<()>;

    /// Fetches the node's current config if it differs from
    /// `current_version`; returns `Ok(None)` when already up to date.
    async fn get_config(&self, node_id: &str, current_version: i64) -> Result<Option<NodeConfig>>;

    /// Pushes a batch of metric samples for this node.
    async fn report_metrics(&self, m: Metrics) -> Result<()>;

    /// Exchanges a single-use `refresh_token` for a new access/refresh
    /// token pair. Reuse of an already-spent token is treated by the
    /// server as compromise and revokes the whole chain.
    async fn refresh_token(&self, refresh_token: &str) -> Result<RefreshResponse>;

    /// Looks up an indicator (domain or IP) against the control plane's
    /// threat-intel feed.
    async fn check_ioc(&self, indicator: &str) -> Result<IocVerdict>;
}
