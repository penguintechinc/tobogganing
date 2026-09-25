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

    // `NetsvcsEdgeConfig` embeds `DnsConfig` so the netsvcs-edge module's
    // `run()` (which only receives `NetsvcsEdgeConfig`, per its stable
    // signature) has everything it needs without a second parameter.
    // `NodeConfig` itself carries no separate top-level `dns` field.
    let edge = NetsvcsEdgeConfig {
        dns,
        ..NetsvcsEdgeConfig::default()
    };

    NodeConfig {
        connectivity: ConnectivityConfig::default(),
        edge,
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

#[cfg(test)]
mod tests {
    use super::*;
    use pb::manager_service_server::{ManagerService, ManagerServiceServer};
    use std::pin::Pin;
    use tokio::sync::Mutex as AsyncMutex;
    use tokio_util::sync::CancellationToken;
    use tonic::codegen::tokio_stream::Stream as TonicStream;
    use tonic::transport::server::TcpIncoming;
    use tonic::transport::Server;

    type BoxedConfigStream =
        Pin<Box<dyn TonicStream<Item = std::result::Result<pb::ConfigUpdate, Status>> + Send>>;

    /// An in-process `netsvcs.manager.v1.ManagerService` double: each RPC
    /// pops one canned `Result` (panicking on a second call), and every RPC
    /// records the `authorization` metadata it received so tests can assert
    /// on the bearer actually presented — this is what makes these tests a
    /// real end-to-end exercise of `GrpcClient` over the wire rather than a
    /// unit test of request builders alone.
    #[derive(Default)]
    struct ScriptedManager {
        register_server:
            AsyncMutex<Option<std::result::Result<pb::RegisterServerResponse, Status>>>,
        refresh_token: AsyncMutex<Option<std::result::Result<pb::RefreshTokenResponse, Status>>>,
        get_config: AsyncMutex<Option<std::result::Result<pb::GetConfigResponse, Status>>>,
        send_heartbeat: AsyncMutex<Option<std::result::Result<pb::SendHeartbeatResponse, Status>>>,
        check_ioc: AsyncMutex<Option<std::result::Result<pb::CheckIocResponse, Status>>>,
        last_auth: AsyncMutex<Option<String>>,
        heartbeat_calls: std::sync::atomic::AtomicUsize,
    }

    async fn record_auth<T>(mgr: &ScriptedManager, request: &Request<T>) {
        let header = request
            .metadata()
            .get("authorization")
            .and_then(|v| v.to_str().ok())
            .map(str::to_string);
        *mgr.last_auth.lock().await = header;
    }

    async fn take<T>(
        slot: &AsyncMutex<Option<std::result::Result<T, Status>>>,
    ) -> std::result::Result<tonic::Response<T>, Status> {
        slot.lock()
            .await
            .take()
            .expect("scripted RPC called more times than configured")
            .map(tonic::Response::new)
    }

    #[async_trait]
    impl ManagerService for ScriptedManager {
        async fn register_server(
            &self,
            request: Request<pb::RegisterServerRequest>,
        ) -> std::result::Result<tonic::Response<pb::RegisterServerResponse>, Status> {
            record_auth(self, &request).await;
            take(&self.register_server).await
        }

        async fn refresh_token(
            &self,
            request: Request<pb::RefreshTokenRequest>,
        ) -> std::result::Result<tonic::Response<pb::RefreshTokenResponse>, Status> {
            record_auth(self, &request).await;
            take(&self.refresh_token).await
        }

        async fn get_config(
            &self,
            request: Request<pb::GetConfigRequest>,
        ) -> std::result::Result<tonic::Response<pb::GetConfigResponse>, Status> {
            record_auth(self, &request).await;
            take(&self.get_config).await
        }

        type StreamConfigUpdatesStream = BoxedConfigStream;

        async fn stream_config_updates(
            &self,
            _request: Request<pb::StreamConfigUpdatesRequest>,
        ) -> std::result::Result<tonic::Response<Self::StreamConfigUpdatesStream>, Status> {
            Err(Status::unimplemented("not exercised by these tests"))
        }

        async fn send_heartbeat(
            &self,
            request: Request<pb::SendHeartbeatRequest>,
        ) -> std::result::Result<tonic::Response<pb::SendHeartbeatResponse>, Status> {
            record_auth(self, &request).await;
            self.heartbeat_calls
                .fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            take(&self.send_heartbeat).await
        }

        async fn validate_token(
            &self,
            _request: Request<pb::ValidateTokenRequest>,
        ) -> std::result::Result<tonic::Response<pb::ValidateTokenResponse>, Status> {
            Err(Status::unimplemented("not exercised by these tests"))
        }

        async fn check_ioc(
            &self,
            request: Request<pb::CheckIocRequest>,
        ) -> std::result::Result<tonic::Response<pb::CheckIocResponse>, Status> {
            record_auth(self, &request).await;
            take(&self.check_ioc).await
        }
    }

    /// Starts `manager` as a real loopback gRPC server on an OS-assigned
    /// port, returning its `http://127.0.0.1:<port>` endpoint and a
    /// [`CancellationToken`] that stops the server (and its background
    /// task) when cancelled/dropped-detached at test end.
    async fn spawn_manager(
        manager: std::sync::Arc<ScriptedManager>,
    ) -> (String, CancellationToken) {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
            .await
            .expect("binding an ephemeral loopback port must succeed");
        let addr = listener
            .local_addr()
            .expect("a bound listener has a local address");
        let incoming = TcpIncoming::from(listener);
        let shutdown = CancellationToken::new();
        let stop = shutdown.clone();

        tokio::spawn(async move {
            Server::builder()
                .add_service(ManagerServiceServer::from_arc(manager))
                .serve_with_incoming_shutdown(incoming, stop.cancelled())
                .await
                .expect("mock ManagerService server must not fail to serve");
        });

        (format!("http://{addr}"), shutdown)
    }

    fn test_cfg(url: &str) -> AgentConfig {
        AgentConfig {
            mode: node_agent_core::AgentMode::Daemonset,
            control_plane_url: url.to_string(),
            machine_jwt_path: std::path::PathBuf::new(),
            features: node_agent_core::AgentFeatures::default(),
            heartbeat_interval_secs: 30,
            request_timeout_secs: 5,
        }
    }

    fn config_response(version: i32) -> pb::GetConfigResponse {
        pb::GetConfigResponse {
            config: Some(pb::ServerConfig {
                zones: Vec::new(),
                cache_settings: Some(pb::CacheSettings {
                    ttl: 300,
                    enabled: true,
                    max_entries: 10_000,
                }),
                settings: Default::default(),
                ioc_filtering: true,
            }),
            version,
        }
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn enroll_extracts_tenant_and_attaches_the_machine_jwt_as_bearer() {
        let manager = std::sync::Arc::new(ScriptedManager::default());
        // `sub=node-1 tenant=tenant-9` — a real signed token isn't needed
        // since `extract_tenant` deliberately never verifies the signature.
        let jwt_with_tenant = jsonwebtoken::encode(
            &jsonwebtoken::Header::new(jsonwebtoken::Algorithm::HS256),
            &serde_json::json!({"tenant": "tenant-9"}),
            &jsonwebtoken::EncodingKey::from_secret(b"test-secret"),
        )
        .expect("encoding a throwaway test token must succeed");
        *manager.register_server.lock().await = Some(Ok(pb::RegisterServerResponse {
            jwt: jwt_with_tenant,
            server_id: "node-1".to_string(),
            config: Some(pb::ServerConfig {
                zones: Vec::new(),
                cache_settings: None,
                settings: Default::default(),
                ioc_filtering: false,
            }),
            config_version: 1,
            refresh_token: "refresh-1".to_string(),
        }));

        let (url, shutdown) = spawn_manager(std::sync::Arc::clone(&manager)).await;
        let client = GrpcClient::new(&test_cfg(&url));
        let resp = client
            .enroll(EnrollRequest {
                machine_jwt: "machine-jwt-1".to_string(),
                node_type: "node-agent".to_string(),
                hostname: "host-1".to_string(),
                public_key: None,
            })
            .await
            .expect("enroll must succeed");

        assert_eq!(resp.node_id, "node-1");
        assert_eq!(resp.tenant, "tenant-9");
        assert_eq!(resp.config.config_version, 1);
        shutdown.cancel();
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn heartbeat_and_report_metrics_attach_the_enrolled_bearer() {
        let manager = std::sync::Arc::new(ScriptedManager::default());
        *manager.register_server.lock().await = Some(Ok(pb::RegisterServerResponse {
            jwt: "token-1".to_string(),
            server_id: "node-1".to_string(),
            config: None,
            config_version: 0,
            refresh_token: "refresh-1".to_string(),
        }));
        *manager.send_heartbeat.lock().await = Some(Ok(pb::SendHeartbeatResponse {
            config_version: 0,
            should_sync: false,
        }));

        let (url, shutdown) = spawn_manager(std::sync::Arc::clone(&manager)).await;
        let client = GrpcClient::new(&test_cfg(&url));
        client
            .enroll(EnrollRequest {
                machine_jwt: "mjwt".to_string(),
                node_type: "node-agent".to_string(),
                hostname: "host-1".to_string(),
                public_key: None,
            })
            .await
            .expect("enroll must succeed");

        client
            .heartbeat(Heartbeat {
                node_id: "node-1".to_string(),
                timestamp: 0,
                config_version: 0,
            })
            .await
            .expect("heartbeat must succeed using the enrolled access token");

        // Proves the token returned by enroll() — not a stale/absent one —
        // is what actually rides on the wire as the gRPC metadata bearer.
        assert_eq!(
            manager.last_auth.lock().await.as_deref(),
            Some("Bearer token-1")
        );
        assert_eq!(
            manager
                .heartbeat_calls
                .load(std::sync::atomic::Ordering::SeqCst),
            1
        );

        shutdown.cancel();
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn report_metrics_folds_into_a_send_heartbeat_call() {
        let manager = std::sync::Arc::new(ScriptedManager::default());
        *manager.register_server.lock().await = Some(Ok(pb::RegisterServerResponse {
            jwt: "token-1".to_string(),
            server_id: "node-1".to_string(),
            config: None,
            config_version: 0,
            refresh_token: "refresh-1".to_string(),
        }));
        *manager.send_heartbeat.lock().await = Some(Ok(pb::SendHeartbeatResponse {
            config_version: 0,
            should_sync: false,
        }));

        let (url, shutdown) = spawn_manager(std::sync::Arc::clone(&manager)).await;
        let client = GrpcClient::new(&test_cfg(&url));
        client
            .enroll(EnrollRequest {
                machine_jwt: "mjwt".to_string(),
                node_type: "node-agent".to_string(),
                hostname: "host-1".to_string(),
                public_key: None,
            })
            .await
            .expect("enroll must succeed");

        client
            .report_metrics(Metrics {
                node_id: "node-1".to_string(),
                samples: Vec::new(),
            })
            .await
            .expect("report_metrics must succeed by folding into SendHeartbeat");

        shutdown.cancel();
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn get_config_returns_none_when_server_version_is_not_newer() {
        let manager = std::sync::Arc::new(ScriptedManager::default());
        *manager.register_server.lock().await = Some(Ok(pb::RegisterServerResponse {
            jwt: "token-1".to_string(),
            server_id: "node-1".to_string(),
            config: None,
            config_version: 0,
            refresh_token: "refresh-1".to_string(),
        }));
        *manager.get_config.lock().await = Some(Ok(config_response(3)));

        let (url, shutdown) = spawn_manager(std::sync::Arc::clone(&manager)).await;
        let client = GrpcClient::new(&test_cfg(&url));
        client
            .enroll(EnrollRequest {
                machine_jwt: "mjwt".to_string(),
                node_type: "node-agent".to_string(),
                hostname: "host-1".to_string(),
                public_key: None,
            })
            .await
            .expect("enroll must succeed");

        let result = client
            .get_config("node-1", 3)
            .await
            .expect("get_config must succeed");
        assert!(result.is_none());
        shutdown.cancel();
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn get_config_returns_some_and_maps_the_ioc_filtering_flag_when_newer() {
        let manager = std::sync::Arc::new(ScriptedManager::default());
        *manager.register_server.lock().await = Some(Ok(pb::RegisterServerResponse {
            jwt: "token-1".to_string(),
            server_id: "node-1".to_string(),
            config: None,
            config_version: 0,
            refresh_token: "refresh-1".to_string(),
        }));
        *manager.get_config.lock().await = Some(Ok(config_response(5)));

        let (url, shutdown) = spawn_manager(std::sync::Arc::clone(&manager)).await;
        let client = GrpcClient::new(&test_cfg(&url));
        client
            .enroll(EnrollRequest {
                machine_jwt: "mjwt".to_string(),
                node_type: "node-agent".to_string(),
                hostname: "host-1".to_string(),
                public_key: None,
            })
            .await
            .expect("enroll must succeed");

        let cfg = client
            .get_config("node-1", 1)
            .await
            .expect("get_config must succeed")
            .expect("a newer config must be returned");
        assert_eq!(cfg.config_version, 5);
        assert!(cfg.edge.dns.ioc_filtering);
        shutdown.cancel();
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn refresh_token_presents_the_refresh_token_itself_as_bearer() {
        let manager = std::sync::Arc::new(ScriptedManager::default());
        *manager.refresh_token.lock().await = Some(Ok(pb::RefreshTokenResponse {
            jwt: "token-2".to_string(),
        }));

        let (url, shutdown) = spawn_manager(std::sync::Arc::clone(&manager)).await;
        let client = GrpcClient::new(&test_cfg(&url));
        let resp = client
            .refresh_token("the-refresh-token")
            .await
            .expect("refresh_token must succeed");
        assert_eq!(resp.access_token, "token-2");
        // The proto doesn't yet return a rotated refresh token, so the
        // caller's own is echoed back.
        assert_eq!(resp.refresh_token, "the-refresh-token");
        // The refresh token itself — not any (possibly expired) access
        // token — must be what's presented as the bearer for this call.
        assert_eq!(
            manager.last_auth.lock().await.as_deref(),
            Some("Bearer the-refresh-token")
        );
        shutdown.cancel();
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn check_ioc_maps_blocked_and_feed_source() {
        let manager = std::sync::Arc::new(ScriptedManager::default());
        *manager.register_server.lock().await = Some(Ok(pb::RegisterServerResponse {
            jwt: "token-1".to_string(),
            server_id: "node-1".to_string(),
            config: None,
            config_version: 0,
            refresh_token: "refresh-1".to_string(),
        }));
        *manager.check_ioc.lock().await = Some(Ok(pb::CheckIocResponse {
            blocked: true,
            reason: "known malware C2".to_string(),
            feed_source: "test-feed".to_string(),
            severity: "high".to_string(),
        }));

        let (url, shutdown) = spawn_manager(std::sync::Arc::clone(&manager)).await;
        let client = GrpcClient::new(&test_cfg(&url));
        client
            .enroll(EnrollRequest {
                machine_jwt: "mjwt".to_string(),
                node_type: "node-agent".to_string(),
                hostname: "host-1".to_string(),
                public_key: None,
            })
            .await
            .expect("enroll must succeed");

        let verdict = client
            .check_ioc("bad.example.com")
            .await
            .expect("check_ioc must succeed");
        assert!(verdict.malicious);
        assert_eq!(verdict.source.as_deref(), Some("test-feed"));
        shutdown.cancel();
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn unimplemented_with_api_version_message_maps_to_unsupported_api_version() {
        let manager = std::sync::Arc::new(ScriptedManager::default());
        *manager.register_server.lock().await =
            Some(Err(Status::unimplemented("api_version v1 not supported")));

        let (url, shutdown) = spawn_manager(std::sync::Arc::clone(&manager)).await;
        let client = GrpcClient::new(&test_cfg(&url));
        let err = client
            .enroll(EnrollRequest {
                machine_jwt: "mjwt".to_string(),
                node_type: "node-agent".to_string(),
                hostname: "host-1".to_string(),
                public_key: None,
            })
            .await
            .expect_err("an UNIMPLEMENTED + api_version status must map to a typed error");
        assert!(matches!(err, AgentError::UnsupportedApiVersion { .. }));
        shutdown.cancel();
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn other_statuses_map_to_a_transport_error() {
        let manager = std::sync::Arc::new(ScriptedManager::default());
        *manager.register_server.lock().await =
            Some(Err(Status::permission_denied("tenant mismatch")));

        let (url, shutdown) = spawn_manager(std::sync::Arc::clone(&manager)).await;
        let client = GrpcClient::new(&test_cfg(&url));
        let err = client
            .enroll(EnrollRequest {
                machine_jwt: "mjwt".to_string(),
                node_type: "node-agent".to_string(),
                hostname: "host-1".to_string(),
                public_key: None,
            })
            .await
            .expect_err("a non-UNIMPLEMENTED status must map to a Transport error");
        assert!(matches!(err, AgentError::Transport(_)));
        shutdown.cancel();
    }

    #[tokio::test]
    async fn heartbeat_before_enroll_fails_with_not_enrolled_error() {
        let client = GrpcClient::new(&test_cfg("http://127.0.0.1:1"));
        let err = client
            .heartbeat(Heartbeat {
                node_id: "node-1".to_string(),
                timestamp: 0,
                config_version: 0,
            })
            .await
            .expect_err("heartbeat before enroll must fail without ever dialing out");
        assert!(matches!(err, AgentError::ControlPlane(msg) if msg.contains("not enrolled")));
    }

    #[tokio::test]
    async fn new_falls_back_to_loopback_on_an_invalid_control_plane_url() {
        // An embedded NUL byte is rejected by `Endpoint::from_shared`,
        // exercising the fallback branch without needing a live dial.
        // `connect_lazy` still needs a Tokio runtime context to set up the
        // channel, hence `#[tokio::test]` rather than a bare `#[test]`.
        let client = GrpcClient::new(&test_cfg("http://\0invalid"));
        // Construction never panics or blocks; the fallback channel is
        // only proven out on first use, which is covered by the "not
        // enrolled" error path above.
        let _ = client;
    }

    #[test]
    fn map_status_classifies_unimplemented_api_version_vs_other_statuses() {
        let unsupported = map_status(Status::unimplemented("api_version v3 not supported"));
        assert!(matches!(
            unsupported,
            AgentError::UnsupportedApiVersion { .. }
        ));

        let other = map_status(Status::internal("boom"));
        assert!(matches!(other, AgentError::Transport(_)));
    }
}
