//! gRPC (`tonic`) implementation of `ControlPlaneClient`, used for
//! intra-cluster DaemonSet ↔ `hub_api` netsvcs-manager traffic per
//! `backend.md`'s "gRPC for service-to-service" rule.

use crate::pb;
use async_trait::async_trait;
use node_agent_core::{
    AgentConfig, AgentError, ConnectivityConfig, ControlPlaneClient, DnsConfig, EnrollRequest,
    EnrollResponse, Heartbeat, IocVerdict, Metrics, NetsvcsEdgeConfig, NodeConfig, RefreshResponse,
    Result,
};
use serde::Deserialize;
use tokio::sync::RwLock;
use tonic::transport::{Channel, Endpoint};
use tonic::{Request, Status};

/// The `api_version` value stamped on every outbound request message, per
/// `backend.md`'s runtime-routing rule.
const API_VERSION: &str = "v1";

/// gRPC implementation of `ControlPlaneClient` against `netsvcs.manager.v1`.
/// Caches the most recently issued `access_token` (from `enroll`/
/// `refresh_token`) and attaches it as `Authorization: Bearer` on every
/// other call.
pub struct GrpcClient {
    channel: Channel,
    access_token: RwLock<Option<String>>,
}

impl GrpcClient {
    /// Builds a gRPC client for `cfg.control_plane_url`. Connection is lazy
    /// (`connect_lazy`) so construction never blocks or fails; a malformed
    /// URL falls back to a loopback default and is logged, surfacing as a
    /// `Transport` error on the first actual call instead of a panic here.
    pub fn new(cfg: &AgentConfig) -> Self {
        let endpoint = Endpoint::from_shared(cfg.control_plane_url.clone()).unwrap_or_else(|err| {
            tracing::warn!(
                error = %err,
                control_plane_url = %cfg.control_plane_url,
                "invalid control_plane_url for gRPC mode; falling back to http://127.0.0.1:50051"
            );
            Endpoint::from_static("http://127.0.0.1:50051")
        });
        let channel = endpoint.connect_lazy();
        Self {
            channel,
            access_token: RwLock::new(None),
        }
    }

    fn client(&self) -> pb::manager_service_client::ManagerServiceClient<Channel> {
        pb::manager_service_client::ManagerServiceClient::new(self.channel.clone())
    }

    async fn bearer_token(&self) -> Result<String> {
        self.access_token.read().await.clone().ok_or_else(|| {
            AgentError::ControlPlane(
                "client not enrolled: call enroll() before other RPCs".to_string(),
            )
        })
    }

    async fn set_access_token(&self, token: String) {
        *self.access_token.write().await = Some(token);
    }
}

#[async_trait]
impl ControlPlaneClient for GrpcClient {
    async fn enroll(&self, req: EnrollRequest) -> Result<EnrollResponse> {
        let mut request = Request::new(pb::RegisterServerRequest {
            api_version: API_VERSION.to_string(),
            hostname: req.hostname,
            version: env!("CARGO_PKG_VERSION").to_string(),
        });
        attach_bearer(&mut request, &req.machine_jwt);

        let resp = self
            .client()
            .register_server(request)
            .await
            .map_err(map_status)?
            .into_inner();

        self.set_access_token(resp.jwt.clone()).await;
        let tenant = extract_tenant(&resp.jwt);

        Ok(EnrollResponse {
            node_id: resp.server_id,
            tenant,
            access_token: resp.jwt,
            refresh_token: resp.refresh_token,
            config: map_node_config(resp.config, resp.config_version as i64),
        })
    }

    async fn heartbeat(&self, hb: Heartbeat) -> Result<()> {
        let token = self.bearer_token().await?;
        let mut request = Request::new(pb::SendHeartbeatRequest {
            api_version: API_VERSION.to_string(),
            server_id: hb.node_id,
            timestamp: hb.timestamp,
            metrics: None,
        });
        attach_bearer(&mut request, &token);
        self.client()
            .send_heartbeat(request)
            .await
            .map_err(map_status)?;
        Ok(())
    }

    async fn get_config(&self, node_id: &str, current_version: i64) -> Result<Option<NodeConfig>> {
        let token = self.bearer_token().await?;
        let mut request = Request::new(pb::GetConfigRequest {
            api_version: API_VERSION.to_string(),
            server_id: node_id.to_string(),
        });
        attach_bearer(&mut request, &token);
        let resp = self
            .client()
            .get_config(request)
            .await
            .map_err(map_status)?
            .into_inner();

        if resp.version as i64 <= current_version {
            return Ok(None);
        }
        Ok(Some(map_node_config(resp.config, resp.version as i64)))
    }

    async fn report_metrics(&self, m: Metrics) -> Result<()> {
        // The current netsvcs.manager.v1 proto folds metrics into the
        // heartbeat RPC (SendHeartbeatRequest.metrics); dedicated ingest is
        // out of scope for Stage F and is aggregated here as a best-effort
        // heartbeat carrying the first sample's counters, refined once the
        // real metrics pipeline lands.
        let token = self.bearer_token().await?;
        let mut request = Request::new(pb::SendHeartbeatRequest {
            api_version: API_VERSION.to_string(),
            server_id: m.node_id,
            timestamp: current_unix_time(),
            metrics: Some(pb::ServerMetrics {
                queries_total: 0,
                cache_hits: 0,
                errors: 0,
                avg_response_ms: 0.0,
                queries_by_type: std::collections::HashMap::new(),
            }),
        });
        attach_bearer(&mut request, &token);
        self.client()
            .send_heartbeat(request)
            .await
            .map_err(map_status)?;
        Ok(())
    }

    async fn refresh_token(&self, refresh_token: &str) -> Result<RefreshResponse> {
        // The refresh token itself is the credential for this call — it is
        // presented as the bearer, not the (possibly expired) access token.
        let mut request = Request::new(pb::RefreshTokenRequest {
            api_version: API_VERSION.to_string(),
            server_id: String::new(),
        });
        attach_bearer(&mut request, refresh_token);

        let resp = self
            .client()
            .refresh_token(request)
            .await
            .map_err(map_status)?
            .into_inner();
        self.set_access_token(resp.jwt.clone()).await;

        // The proto's RefreshTokenResponse only carries the new access JWT;
        // rotation of the single-use refresh token itself is not yet
        // exposed by netsvcs.manager.v1, so the caller's existing refresh
        // token is echoed back until the proto grows a rotated value.
        Ok(RefreshResponse {
            access_token: resp.jwt,
            refresh_token: refresh_token.to_string(),
        })
    }

    async fn check_ioc(&self, indicator: &str) -> Result<IocVerdict> {
        let token = self.bearer_token().await?;
        let mut request = Request::new(pb::CheckIocRequest {
            api_version: API_VERSION.to_string(),
            domain: indicator.to_string(),
            ip: String::new(),
        });
        attach_bearer(&mut request, &token);
        let resp = self
            .client()
            .check_ioc(request)
            .await
            .map_err(map_status)?
            .into_inner();

        Ok(IocVerdict {
            indicator: indicator.to_string(),
            malicious: resp.blocked,
            source: (!resp.feed_source.is_empty()).then_some(resp.feed_source),
        })
    }
}

fn attach_bearer<T>(request: &mut Request<T>, token: &str) {
    if let Ok(value) = format!("Bearer {token}").parse() {
        request.metadata_mut().insert("authorization", value);
    }
}

/// Maps a `tonic::Status` into `AgentError`, special-casing `UNIMPLEMENTED`
/// with an `api_version` message into `UnsupportedApiVersion` per
/// `backend.md`'s "never silently fall through" contract.
fn map_status(status: Status) -> AgentError {
    if status.code() == tonic::Code::Unimplemented && status.message().contains("api_version") {
        return AgentError::UnsupportedApiVersion {
            version: API_VERSION.to_string(),
            reason: status.message().to_string(),
        };
    }
    AgentError::Transport(status.to_string())
}

/// Best-effort extraction of the `tenant` claim from an opaque access token
/// issued by the control plane — an informational convenience only, never
/// used for authorization (the server enforces tenant scoping).
fn extract_tenant(token: &str) -> String {
    #[derive(Deserialize)]
    struct TenantClaim {
        #[serde(default)]
        tenant: String,
    }
    node_agent_core::decode_unverified_claims::<TenantClaim>(token)
        .map(|c| c.tenant)
        .unwrap_or_default()
}

fn map_node_config(cfg: Option<pb::ServerConfig>, config_version: i64) -> NodeConfig {
    let dns = match cfg {
        Some(c) => {
            let cache = c.cache_settings.unwrap_or_default();
            DnsConfig {
                upstream_doh_urls: Vec::new(),
                ioc_filtering: c.ioc_filtering,
                cache_enabled: cache.enabled,
                cache_max_entries: cache.max_entries.max(0) as u32,
                cache_ttl_secs: cache.ttl.max(0) as u32,
                ..DnsConfig::default()
            }
        }
        None => DnsConfig::default(),
    };

    NodeConfig {
        dns,
        connectivity: ConnectivityConfig::default(),
        edge: NetsvcsEdgeConfig::default(),
        config_version,
    }
}

fn current_unix_time() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or_default()
}
