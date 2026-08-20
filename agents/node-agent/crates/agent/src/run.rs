//! `run` subcommand: loads config, performs the node's single enrollment
//! with the control plane, and supervises the connectivity/netsvcs-edge
//! data-plane modules plus one node-level lifecycle loop (heartbeat +
//! config-poll + token refresh) until an interrupt is received.
//!
//! This is the *only* place in the workspace that calls
//! [`ControlPlaneClient::enroll`] — a node enrolls exactly once, with its
//! WireGuard public key (if connectivity is enabled) attached from the
//! start, so the control plane never sees two competing registrations for
//! the same physical node. `connectivity` and `netsvcs-edge` are pure
//! data-plane consumers of the config this loop publishes; neither talks
//! to the control plane directly.

use jsonwebtoken::Algorithm;
use node_agent_core::{
    AgentConfig, AgentError, AgentMode, ConnectivityConfig, ControlPlaneClient, EnrollRequest,
    Heartbeat, MachineJwtSigner, NodeConfig, RefreshResponse, Result,
};
use std::path::Path;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::sync::watch;
use tokio_util::sync::CancellationToken;

/// Scope requested on the single bootstrap machine-JWT used at enrollment
/// — the base netsvcs scopes plus `connectivity:config:read` whenever this
/// build carries the `connectivity` module, mirroring the P4 design doc's
/// "`dns:config:read metrics:write ioc:read` + connectivity scopes".
#[cfg(feature = "connectivity")]
const MACHINE_JWT_SCOPE: &str = "dns:config:read metrics:write ioc:read connectivity:config:read";
#[cfg(not(feature = "connectivity"))]
const MACHINE_JWT_SCOPE: &str = "dns:config:read metrics:write ioc:read";

/// Refresh the access token once fewer than this many seconds remain before
/// its `exp` claim, so a slow refresh round-trip never races expiry.
const REFRESH_MARGIN_SECS: i64 = 60;

/// Runs the agent: load config → install the shared TLS crypto provider →
/// build a transport client → generate this node's WireGuard identity (if
/// applicable) → enroll exactly once → spawn the capability modules and
/// the node-level lifecycle loop under a shared [`CancellationToken`] →
/// wait for an interrupt → cancel and join every task.
pub async fn run(
    config_path: Option<&Path>,
    mode_override: Option<AgentMode>,
    control_plane_url_override: Option<String>,
) -> Result<()> {
    let mut cfg = AgentConfig::load(config_path)?;
    if let Some(mode) = mode_override {
        cfg.mode = mode;
    }
    if let Some(url) = control_plane_url_override {
        cfg.control_plane_url = url;
    }

    node_agent_transport::install_crypto_provider()?;
    let client = node_agent_transport::build_client(&cfg);

    let signer = MachineJwtSigner::from_pem_file(&cfg.machine_jwt_path, Algorithm::ES256)?;
    let hostname = local_hostname()?;
    // node_id isn't known until the control plane assigns one in
    // EnrollResponse, so the hostname doubles as the bootstrap JWT subject.
    let machine_jwt = signer.sign(
        "node-agent",
        &hostname,
        "node-agent",
        MACHINE_JWT_SCOPE,
        Duration::from_secs(300),
    )?;

    // Generate this node's WireGuard identity *before* enrolling, so its
    // public key can ride along in the single `EnrollRequest` below and
    // the control plane can hand back a matching peer config in the very
    // first response. The server's own `ConnectivityConfig` isn't known
    // yet at this point (it only arrives *in* the enroll response), so
    // `wireguard_identity` is consulted against `ConnectivityConfig::default()`
    // (which defaults `wireguard_enabled` to `true`) — gated on both the
    // compile-time `connectivity` feature and the runtime
    // `cfg.features.connectivity` toggle.
    #[cfg(feature = "connectivity")]
    let wg_identity = if cfg.features.connectivity {
        node_agent_connectivity::wireguard_identity(&ConnectivityConfig::default())?
    } else {
        None
    };
    #[cfg(feature = "connectivity")]
    let wg_public_key = wg_identity.as_ref().map(|w| w.public_key_b64.clone());
    #[cfg(not(feature = "connectivity"))]
    let wg_public_key: Option<String> = None;

    let enroll_resp = client
        .enroll(EnrollRequest {
            machine_jwt,
            node_type: "node-agent".to_string(),
            hostname: hostname.clone(),
            public_key: wg_public_key,
        })
        .await?;
    tracing::info!(node_id = %enroll_resp.node_id, tenant = %enroll_resp.tenant, "enrolled with control plane");

    let shutdown = CancellationToken::new();
    // Explicit type: with every capability feature compiled out, the only
    // task ever spawned is the lifecycle loop below, whose `Ok(())` alone
    // can't pin the JoinSet's error type parameter — a pre-existing gap
    // this makes unconditionally correct rather than feature-combination
    // dependent.
    let mut tasks: tokio::task::JoinSet<Result<()>> = tokio::task::JoinSet::new();

    // Published by the lifecycle loop below on every config change the
    // control plane reports; `connectivity::run` (when spawned) applies
    // each new value. Always created — cheap, and lets the lifecycle loop
    // stay unconditional — but only ever has an active receiver when the
    // `connectivity` feature is compiled in and enabled at runtime.
    let (conn_tx, conn_rx) = watch::channel(enroll_resp.config.connectivity.clone());

    #[cfg(feature = "connectivity")]
    if cfg.features.connectivity {
        let module_cfg = enroll_resp.config.connectivity.clone();
        let identity = wg_identity;
        let token = shutdown.clone();
        tasks.spawn(async move {
            node_agent_connectivity::run(module_cfg, identity, conn_rx, token).await
        });
    }
    #[cfg(not(feature = "connectivity"))]
    {
        // No connectivity module compiled in — nothing will ever consume
        // config updates, so explicitly drop the receiver rather than
        // leave it idle (silences "unused variable" without a feature-gated
        // `let`, and makes the intent explicit).
        drop(conn_rx);
    }

    #[cfg(feature = "netsvcs-edge")]
    if cfg.features.netsvcs_edge {
        let module_cfg = enroll_resp.config.edge.clone();
        let client = Arc::clone(&client);
        let token = shutdown.clone();
        tasks.spawn(async move { node_agent_netsvcs_edge::run(module_cfg, client, token).await });
    }

    {
        let client = Arc::clone(&client);
        let session = Session {
            node_id: enroll_resp.node_id.clone(),
            refresh_token: enroll_resp.refresh_token.clone(),
            config_version: enroll_resp.config.config_version,
            access_token_exp: decode_exp(&enroll_resp.access_token),
        };
        let interval_secs = cfg.heartbeat_interval_secs;
        let token = shutdown.clone();
        tasks.spawn(async move {
            lifecycle_loop(client, session, interval_secs, conn_tx, token).await;
            Ok(())
        });
    }

    let _ = tokio::signal::ctrl_c().await;
    tracing::info!("received interrupt; shutting down");
    shutdown.cancel();

    while let Some(joined) = tasks.join_next().await {
        match joined {
            Ok(Ok(())) => {}
            Ok(Err(err)) => tracing::error!(error = %err, "a supervised task exited with an error"),
            Err(join_err) => {
                tracing::error!(error = %join_err, "a supervised task panicked or was aborted")
            }
        }
    }

    Ok(())
}

/// Mutable session state tracked across lifecycle-loop ticks: the
/// control-plane-assigned node id, the current single-use refresh token,
/// the last-applied config version, and when the current access token
/// expires. Seeded once from the single [`node_agent_core::EnrollResponse`]
/// and never re-created — this node enrolls exactly once per process
/// lifetime.
#[derive(Debug, Clone, PartialEq, Eq)]
struct Session {
    node_id: String,
    refresh_token: String,
    config_version: i64,
    access_token_exp: i64,
}

#[derive(Debug, Default, serde::Deserialize)]
#[cfg_attr(test, derive(serde::Serialize))]
struct ExpClaim {
    #[serde(default)]
    exp: i64,
}

/// Decodes the `exp` claim from an opaque, already-TLS-authenticated
/// access token — informational only, matching the `extract_tenant`
/// pattern in `transport::grpc`; never used for authorization.
fn decode_exp(token: &str) -> i64 {
    node_agent_core::decode_unverified_claims::<ExpClaim>(token)
        .map(|c| c.exp)
        .unwrap_or_default()
}

/// One heartbeat + config-poll + refresh-check tick. Returns `Some(config)`
/// when the control plane reports a newer config than `session` has
/// applied. Individual RPC failures are non-fatal — logged here and
/// retried on the next tick rather than tearing down the process.
async fn tick(client: &dyn ControlPlaneClient, session: &mut Session) -> Option<NodeConfig> {
    let hb = Heartbeat {
        node_id: session.node_id.clone(),
        timestamp: unix_now(),
        config_version: session.config_version,
    };
    if let Err(err) = client.heartbeat(hb).await {
        tracing::warn!(error = %err, "heartbeat failed");
    }

    let new_config = match client
        .get_config(&session.node_id, session.config_version)
        .await
    {
        Ok(Some(cfg)) => {
            session.config_version = cfg.config_version;
            Some(cfg)
        }
        Ok(None) => None,
        Err(err) => {
            tracing::warn!(error = %err, "config poll failed");
            None
        }
    };

    if unix_now() >= session.access_token_exp - REFRESH_MARGIN_SECS {
        match client.refresh_token(&session.refresh_token).await {
            Ok(RefreshResponse {
                access_token,
                refresh_token,
            }) => {
                session.refresh_token = refresh_token;
                session.access_token_exp = decode_exp(&access_token);
            }
            Err(err) => tracing::warn!(error = %err, "token refresh failed"),
        }
    }

    new_config
}

/// Drives the single node-level lifecycle after enrollment: every
/// `interval_secs`, runs one heartbeat + config-poll + refresh-check tick
/// against `session`; whenever the control plane reports a newer config,
/// publishes its `connectivity` half on `conn_tx` so `connectivity::run`'s
/// apply loop (if spawned) picks it up — a send with no live receiver
/// (connectivity disabled or not compiled in) is silently ignored. Runs
/// until `shutdown` is cancelled, matching the previous heartbeat loop's
/// resilience (a single failed RPC is logged and retried, never fatal).
async fn lifecycle_loop(
    client: Arc<dyn ControlPlaneClient>,
    mut session: Session,
    interval_secs: u64,
    conn_tx: watch::Sender<ConnectivityConfig>,
    shutdown: CancellationToken,
) {
    let mut interval = tokio::time::interval(Duration::from_secs(interval_secs.max(1)));
    loop {
        tokio::select! {
            _ = shutdown.cancelled() => return,
            _ = interval.tick() => {
                if let Some(new_config) = tick(client.as_ref(), &mut session).await {
                    let _ = conn_tx.send(new_config.connectivity);
                }
            }
        }
    }
}

fn unix_now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or_default()
}

/// Resolves this node's hostname from the `HOSTNAME` environment variable
/// (always set inside containers; commonly set by the shell on bare metal)
/// — a dependency-free source for Stage F, avoiding a libc `gethostname`
/// binding for a single startup-time value.
fn local_hostname() -> Result<String> {
    std::env::var("HOSTNAME")
        .map_err(|_| AgentError::Config("HOSTNAME environment variable is not set".to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use async_trait::async_trait;
    use node_agent_core::{
        DnsConfig, EnrollResponse, IocVerdict, Metrics, NetsvcsEdgeConfig, WireguardConfig,
    };
    use std::sync::atomic::{AtomicI64, AtomicUsize, Ordering};
    use std::sync::Mutex;

    /// A fully in-memory [`ControlPlaneClient`] double: canned enroll/config
    /// responses plus call counters, so the lifecycle loop's state machine
    /// can be exercised without a live server.
    #[derive(Default)]
    struct MockClient {
        enroll_calls: AtomicUsize,
        heartbeat_calls: AtomicUsize,
        config_poll_calls: AtomicUsize,
        refresh_calls: AtomicUsize,
        config_poll_result: Mutex<Option<NodeConfig>>,
        access_token_exp: AtomicI64,
    }

    fn wg_config(pubkey: &str) -> WireguardConfig {
        WireguardConfig {
            peer_public_key: pubkey.to_string(),
            peer_endpoint: "headend.example.internal:51820".to_string(),
            interface_address: "10.200.0.5/32".to_string(),
            ..WireguardConfig::default()
        }
    }

    fn node_config(version: i64, wg: Option<WireguardConfig>) -> NodeConfig {
        NodeConfig {
            connectivity: ConnectivityConfig {
                wireguard: wg,
                ..ConnectivityConfig::default()
            },
            edge: NetsvcsEdgeConfig {
                dns: DnsConfig::default(),
                ..NetsvcsEdgeConfig::default()
            },
            config_version: version,
        }
    }

    fn token_with_exp(exp: i64) -> String {
        // `decode_exp` uses unverified decoding, so any structurally valid
        // JWT (three base64url segments) with an `exp` claim round-trips —
        // sign with a throwaway HMAC key, matching `core::jwt`'s own tests.
        let claims = ExpClaim { exp };
        jsonwebtoken::encode(
            &jsonwebtoken::Header::new(Algorithm::HS256),
            &claims,
            &jsonwebtoken::EncodingKey::from_secret(b"test-secret"),
        )
        .expect("encoding a throwaway test token must succeed")
    }

    #[async_trait]
    impl ControlPlaneClient for MockClient {
        async fn enroll(&self, _req: EnrollRequest) -> Result<EnrollResponse> {
            self.enroll_calls.fetch_add(1, Ordering::SeqCst);
            Ok(EnrollResponse {
                node_id: "node-1".to_string(),
                tenant: "tenant-1".to_string(),
                access_token: token_with_exp(self.access_token_exp.load(Ordering::SeqCst)),
                refresh_token: "refresh-0".to_string(),
                config: node_config(1, Some(wg_config("initial-peer-key"))),
            })
        }

        async fn heartbeat(&self, _hb: Heartbeat) -> Result<()> {
            self.heartbeat_calls.fetch_add(1, Ordering::SeqCst);
            Ok(())
        }

        async fn get_config(
            &self,
            _node_id: &str,
            _current_version: i64,
        ) -> Result<Option<NodeConfig>> {
            self.config_poll_calls.fetch_add(1, Ordering::SeqCst);
            Ok(self
                .config_poll_result
                .lock()
                .expect("mutex not poisoned")
                .take())
        }

        async fn report_metrics(&self, _m: Metrics) -> Result<()> {
            Ok(())
        }

        async fn refresh_token(&self, refresh_token: &str) -> Result<RefreshResponse> {
            self.refresh_calls.fetch_add(1, Ordering::SeqCst);
            Ok(RefreshResponse {
                access_token: token_with_exp(unix_now() + 3600),
                refresh_token: format!("{refresh_token}-rotated"),
            })
        }

        async fn check_ioc(&self, indicator: &str) -> Result<IocVerdict> {
            Ok(IocVerdict {
                indicator: indicator.to_string(),
                malicious: false,
                source: None,
            })
        }
    }

    fn session() -> Session {
        Session {
            node_id: "node-1".to_string(),
            refresh_token: "refresh-0".to_string(),
            config_version: 1,
            access_token_exp: unix_now() + 3600,
        }
    }

    #[tokio::test]
    async fn tick_sends_heartbeat_and_reports_no_config_change_by_default() {
        let mock = MockClient {
            access_token_exp: AtomicI64::new(unix_now() + 3600),
            ..Default::default()
        };
        let mut sess = session();
        let result = tick(&mock, &mut sess).await;
        assert!(result.is_none());
        assert_eq!(mock.heartbeat_calls.load(Ordering::SeqCst), 1);
        assert_eq!(mock.config_poll_calls.load(Ordering::SeqCst), 1);
        assert_eq!(mock.refresh_calls.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn tick_surfaces_a_newer_config_and_bumps_the_session_version() {
        let mock = MockClient {
            access_token_exp: AtomicI64::new(unix_now() + 3600),
            ..Default::default()
        };
        *mock.config_poll_result.lock().expect("mutex not poisoned") =
            Some(node_config(2, Some(wg_config("rotated-peer-key"))));
        let mut sess = session();
        let result = tick(&mock, &mut sess)
            .await
            .expect("a newer config must be surfaced");
        assert_eq!(result.config_version, 2);
        assert_eq!(sess.config_version, 2);
    }

    #[tokio::test]
    async fn tick_rotates_the_refresh_token_once_within_the_expiry_margin() {
        let mock = MockClient::default();
        let mut sess = Session {
            // Already inside REFRESH_MARGIN_SECS of "expiry".
            access_token_exp: unix_now() + 10,
            ..session()
        };
        tick(&mock, &mut sess).await;
        assert_eq!(mock.refresh_calls.load(Ordering::SeqCst), 1);
        assert_eq!(sess.refresh_token, "refresh-0-rotated");
        assert!(sess.access_token_exp > unix_now() + 3000);
    }

    #[tokio::test]
    async fn tick_does_not_refresh_when_well_within_expiry() {
        let mock = MockClient::default();
        let mut sess = session();
        tick(&mock, &mut sess).await;
        assert_eq!(mock.refresh_calls.load(Ordering::SeqCst), 0);
        assert_eq!(sess.refresh_token, "refresh-0");
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn lifecycle_loop_publishes_updated_configs_before_shutdown() {
        let mock = Arc::new(MockClient {
            access_token_exp: AtomicI64::new(unix_now() + 3600),
            ..Default::default()
        });
        *mock.config_poll_result.lock().expect("mutex not poisoned") =
            Some(node_config(2, Some(wg_config("rotated-peer-key"))));

        let shutdown = CancellationToken::new();
        let (conn_tx, mut conn_rx) = watch::channel(ConnectivityConfig::default());

        let shutdown_clone = shutdown.clone();
        let client: Arc<dyn ControlPlaneClient> = mock.clone();
        let handle = tokio::spawn(async move {
            lifecycle_loop(client, session(), 0, conn_tx, shutdown_clone).await;
        });

        // Wait for the published config to carry the rotated peer key
        // rather than sleeping a fixed duration.
        loop {
            conn_rx.changed().await.expect("sender must still be alive");
            if let Some(wg) = conn_rx.borrow().wireguard.clone() {
                assert_eq!(wg.peer_public_key, "rotated-peer-key");
                break;
            }
        }

        assert!(mock.heartbeat_calls.load(Ordering::SeqCst) >= 1);
        shutdown.cancel();
        handle.await.expect("lifecycle_loop task must not panic");
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn lifecycle_loop_tolerates_a_dropped_receiver() {
        let mock = Arc::new(MockClient {
            access_token_exp: AtomicI64::new(unix_now() + 3600),
            ..Default::default()
        });
        *mock.config_poll_result.lock().expect("mutex not poisoned") =
            Some(node_config(2, Some(wg_config("rotated-peer-key"))));

        let shutdown = CancellationToken::new();
        let (conn_tx, conn_rx) = watch::channel(ConnectivityConfig::default());
        drop(conn_rx); // simulate connectivity disabled/not compiled in

        let shutdown_clone = shutdown.clone();
        let client: Arc<dyn ControlPlaneClient> = mock.clone();
        let handle = tokio::spawn(async move {
            lifecycle_loop(client, session(), 0, conn_tx, shutdown_clone).await;
        });

        tokio::time::sleep(Duration::from_millis(30)).await;
        shutdown.cancel();
        handle.await.expect("lifecycle_loop task must not panic");
        assert!(mock.heartbeat_calls.load(Ordering::SeqCst) >= 1);
    }

    /// Generates a fresh, throwaway P-256 EC private key as a PKCS#8 PEM
    /// (the only EC format `jsonwebtoken::EncodingKey::from_ec_pem`
    /// accepts), matching `run`'s hardcoded `Algorithm::ES256` — good only
    /// for signing a never-verified-against-anything-real machine JWT in
    /// this test. Generated at test time (never a fixed/committed key
    /// value) so nothing resembling real key material ever lands in
    /// source control.
    fn generate_test_ec_key_pem() -> String {
        use p256::pkcs8::EncodePrivateKey;
        let signing_key = p256::ecdsa::SigningKey::random(&mut rand_core::OsRng);
        signing_key
            .to_pkcs8_pem(p256::pkcs8::LineEnding::LF)
            .expect("encoding a freshly generated P-256 key as PKCS#8 PEM must succeed")
            .to_string()
    }

    /// Exercises `run()` itself end-to-end (config load, crypto-provider
    /// install, client build, machine-JWT signing, hostname resolution,
    /// and the single enrollment call) against a real loopback REST mock
    /// of `hub_api` — the only way to cover that setup sequence, since
    /// `run()` is not otherwise reachable from outside this module.
    ///
    /// Both capability features are disabled at runtime (`[features]`
    /// block below) so the only unconditionally-spawned task is the
    /// lifecycle loop; the whole `run()` future is aborted shortly after
    /// enrollment completes rather than waiting on a real `ctrl_c()`
    /// signal (which would require signaling the entire test process).
    /// `tokio::task::JoinSet`'s `Drop` aborts every task it's tracking, so
    /// aborting `run()` cleanly tears down the lifecycle-loop subtask too.
    #[tokio::test(flavor = "multi_thread")]
    async fn run_loads_config_signs_a_machine_jwt_and_enrolls_before_spawning_tasks() {
        let dir = std::env::temp_dir().join(format!(
            "node-agent-run-integration-test-{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).expect("temp dir must be creatable");
        let key_path = dir.join("machine.pem");
        std::fs::write(&key_path, generate_test_ec_key_pem())
            .expect("writing the test key must succeed");

        let server = wiremock::MockServer::start().await;
        wiremock::Mock::given(wiremock::matchers::method("POST"))
            .and(wiremock::matchers::path("/api/v1/netsvcs/enroll"))
            .respond_with(
                wiremock::ResponseTemplate::new(200).set_body_json(serde_json::json!({
                    "status": "success",
                    "data": {
                        "node_id": "node-run-test",
                        "tenant": "tenant-run-test",
                        "access_token": "token-1",
                        "refresh_token": "refresh-1",
                        "config": {"connectivity": {}, "edge": {}, "config_version": 1},
                    },
                })),
            )
            .mount(&server)
            .await;

        let config_path = dir.join("config.toml");
        std::fs::write(
            &config_path,
            format!(
                r#"
                mode = "edge"
                control_plane_url = "{}"
                machine_jwt_path = "{}"

                [features]
                connectivity = false
                netsvcs_edge = false
                "#,
                server.uri(),
                key_path.display(),
            ),
        )
        .expect("writing the test config file must succeed");

        // SAFETY(test-only): no other test in this binary reads `HOSTNAME`,
        // and this crate's tests never touch it, so a process-wide env
        // mutation here cannot race a concurrent reader.
        unsafe {
            std::env::set_var("HOSTNAME", "node-agent-run-integration-test");
        }

        let handle = tokio::spawn(async move { run(Some(&config_path), None, None).await });

        // Long enough for config load, JWT signing, and the single
        // loopback enroll round-trip to complete and the lifecycle-loop
        // task to be spawned — short enough to keep the test fast.
        tokio::time::sleep(Duration::from_millis(300)).await;
        handle.abort();
        let result = handle.await;
        match &result {
            Err(join_err) if join_err.is_cancelled() => {}
            other => panic!("expected run() to still be mid-flight when aborted, got {other:?}"),
        }

        let requests = server
            .received_requests()
            .await
            .expect("mock server must record requests");
        let paths: Vec<String> = requests.iter().map(|r| r.url.path().to_string()).collect();
        assert_eq!(
            paths.iter().filter(|p| p.ends_with("/enroll")).count(),
            1,
            "enroll must have been called exactly once, got requests: {paths:?}"
        );
        // `tokio::time::interval`'s first tick fires immediately, so the
        // lifecycle loop's very first heartbeat+config-poll+refresh tick
        // also completes inside the 300ms window above — proving `run`
        // reached and spawned the lifecycle-loop task, not just enrolled.
        assert!(
            paths.iter().any(|p| p.ends_with("/heartbeat")),
            "the lifecycle loop's first tick must have sent a heartbeat, got: {paths:?}"
        );

        let _ = std::fs::remove_dir_all(&dir);
    }
}
