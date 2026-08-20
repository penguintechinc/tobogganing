//! The connectivity module's own control-plane loop, authored fresh per the
//! squawk-P4 design: bootstrap a capability-scoped machine-JWT, enroll
//! (advertising the WireGuard public key generated in [`crate::keys`]),
//! then supervise heartbeat + config-poll + single-use refresh-token
//! rotation against the injected [`ControlPlaneClient`] until shutdown.
//!
//! This loop is independent of the top-level agent's own enroll/heartbeat
//! in `crates/agent/src/run.rs` — it exists because `run()`'s fixed
//! signature (`ConnectivityConfig`, client, shutdown token) carries no node
//! identity or WireGuard public key for the top-level enrollment to have
//! advertised, so connectivity registers itself under `node_type =
//! "connectivity"` to obtain one.

use jsonwebtoken::Algorithm;
use node_agent_core::{
    AgentError, ControlPlaneClient, EnrollRequest, Heartbeat, MachineJwtSigner, NodeConfig,
    RefreshResponse, Result, WireguardConfig,
};
use serde::Deserialize;
#[cfg(test)]
use serde::Serialize;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::sync::mpsc::UnboundedSender;
use tokio_util::sync::CancellationToken;

/// Default cadence for heartbeat + config-poll + refresh-check ticks, per
/// the spec's "~30s" heartbeat interval.
pub const DEFAULT_TICK_INTERVAL: Duration = Duration::from_secs(30);

/// Refresh the access token once fewer than this many seconds remain before
/// its `exp` claim, so a slow refresh round-trip never races expiry.
const REFRESH_MARGIN_SECS: i64 = 60;

/// Default location of the machine-JWT signing key — the same convention
/// `AgentConfig::machine_jwt_path` defaults to, since connectivity's
/// capability-scoped enrollment bootstraps independently of (and before)
/// the top-level agent's own enroll call.
const DEFAULT_MACHINE_JWT_PATH: &str = "/etc/node-agent/machine.pem";

/// Overrides the signing-key path, mirroring the `NODE_AGENT_`-prefixed
/// environment convention `AgentConfig::load` uses for every other setting.
const MACHINE_JWT_PATH_ENV: &str = "NODE_AGENT_MACHINE_JWT_PATH";

const HOSTNAME_ENV: &str = "HOSTNAME";
const MACHINE_JWT_TTL: Duration = Duration::from_secs(300);
const MACHINE_JWT_SCOPE: &str = "dns:config:read metrics:write ioc:read connectivity:config:read";

/// Everything the connectivity control loop needs to bootstrap: the signed
/// machine JWT proving this node's identity, its hostname, and the base64
/// WireGuard public key to advertise at enrollment.
#[derive(Debug, Clone)]
pub struct BootstrapIdentity {
    pub machine_jwt: String,
    pub hostname: String,
    pub public_key: String,
}

/// Signs a fresh machine JWT from the conventional key path (overridable
/// via `NODE_AGENT_MACHINE_JWT_PATH`) and reads `HOSTNAME`, producing the
/// [`BootstrapIdentity`] connectivity's own `enroll()` call needs. Returns
/// `Err` when the signing key isn't present — callers should treat that as
/// a capability gap to log and degrade from (run WireGuard with only a
/// statically supplied [`WireguardConfig`], no control-plane loop), not a
/// reason to crash the agent.
pub fn bootstrap_identity(public_key_b64: &str) -> Result<BootstrapIdentity> {
    let hostname = std::env::var(HOSTNAME_ENV).map_err(|_| {
        AgentError::Config(format!("{HOSTNAME_ENV} environment variable is not set"))
    })?;
    let key_path = std::env::var(MACHINE_JWT_PATH_ENV)
        .unwrap_or_else(|_| DEFAULT_MACHINE_JWT_PATH.to_string());
    let signer = MachineJwtSigner::from_pem_file(&key_path, Algorithm::ES256)?;
    let machine_jwt = signer.sign(
        "node-agent-connectivity",
        &hostname,
        "connectivity",
        MACHINE_JWT_SCOPE,
        MACHINE_JWT_TTL,
    )?;
    Ok(BootstrapIdentity {
        machine_jwt,
        hostname,
        public_key: public_key_b64.to_string(),
    })
}

/// Mutable session state tracked across ticks: the control-plane-assigned
/// node id, the current single-use refresh token, the last-applied config
/// version, and when the current access token expires.
#[derive(Debug, Clone, PartialEq, Eq)]
struct Session {
    node_id: String,
    refresh_token: String,
    config_version: i64,
    access_token_exp: i64,
}

#[derive(Debug, Default, Deserialize)]
#[cfg_attr(test, derive(Serialize))]
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

fn unix_now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or_default()
}

/// Performs the capability-scoped enrollment step: registers `node_type =
/// "connectivity"` with `identity.public_key` attached, returning the
/// resulting session state plus the node's starting [`NodeConfig`].
async fn enroll(
    client: &dyn ControlPlaneClient,
    identity: &BootstrapIdentity,
) -> Result<(Session, NodeConfig)> {
    let resp = client
        .enroll(EnrollRequest {
            machine_jwt: identity.machine_jwt.clone(),
            node_type: "connectivity".to_string(),
            hostname: identity.hostname.clone(),
            public_key: Some(identity.public_key.clone()),
        })
        .await?;

    let session = Session {
        node_id: resp.node_id,
        refresh_token: resp.refresh_token,
        config_version: resp.config.config_version,
        access_token_exp: decode_exp(&resp.access_token),
    };
    Ok((session, resp.config))
}

/// One heartbeat + config-poll + refresh-check tick. Returns `Some(config)`
/// when the control plane reports a newer config than `session` has
/// applied. Individual RPC failures are non-fatal — logged by the caller
/// and retried on the next tick, matching the top-level agent's own
/// heartbeat-loop resilience.
async fn tick(client: &dyn ControlPlaneClient, session: &mut Session) -> Option<NodeConfig> {
    let hb = Heartbeat {
        node_id: session.node_id.clone(),
        timestamp: unix_now(),
        config_version: session.config_version,
    };
    if let Err(err) = client.heartbeat(hb).await {
        tracing::warn!(error = %err, "connectivity heartbeat failed");
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
            tracing::warn!(error = %err, "connectivity config poll failed");
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
            Err(err) => tracing::warn!(error = %err, "connectivity token refresh failed"),
        }
    }

    new_config
}

/// Runs the full control-plane loop: enroll, then tick every
/// `tick_interval` until `shutdown` is cancelled, publishing every
/// WireGuard config the control plane reports (including the one from
/// enrollment itself) on `config_tx`. Publishing rather than calling back
/// directly keeps this loop free of any dependency on `boringtun`/rtnetlink
/// — the receiver (in `lib.rs`) owns applying the config, which is async
/// I/O and shouldn't block this loop's ticking. A closed receiver ends the
/// loop early (treated the same as `shutdown`), so callers never leak this
/// task if the applying side goes away first.
pub async fn run_control_loop(
    client: &dyn ControlPlaneClient,
    identity: BootstrapIdentity,
    tick_interval: Duration,
    shutdown: &CancellationToken,
    config_tx: UnboundedSender<WireguardConfig>,
) -> Result<()> {
    let (mut session, initial_config) = enroll(client, &identity).await?;
    tracing::info!(module = "connectivity", node_id = %session.node_id, "connectivity control loop enrolled");
    if let Some(wg) = initial_config.connectivity.wireguard {
        let _ = config_tx.send(wg);
    }

    let mut interval = tokio::time::interval(tick_interval.max(Duration::from_millis(1)));
    interval.tick().await; // the first tick fires immediately; consume it so we don't double-tick right after enroll

    loop {
        tokio::select! {
            _ = shutdown.cancelled() => return Ok(()),
            _ = interval.tick() => {
                if let Some(cfg) = tick(client, &mut session).await {
                    if let Some(wg) = cfg.connectivity.wireguard {
                        if config_tx.send(wg).is_err() {
                            return Ok(()); // receiver gone; nothing left to drive
                        }
                    }
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use async_trait::async_trait;
    use node_agent_core::{
        ConnectivityConfig, DnsConfig, EnrollResponse, IocVerdict, Metrics, NetsvcsEdgeConfig,
    };
    use std::sync::atomic::{AtomicI64, AtomicUsize, Ordering};
    use std::sync::Mutex;

    /// A fully in-memory [`ControlPlaneClient`] double: canned enroll/config
    /// responses plus call counters, so the control loop's state machine can
    /// be exercised without a live server.
    #[derive(Default)]
    struct MockClient {
        enroll_calls: AtomicUsize,
        heartbeat_calls: AtomicUsize,
        config_poll_calls: AtomicUsize,
        refresh_calls: AtomicUsize,
        enroll_result: Mutex<Option<Result<EnrollResponse>>>,
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
            dns: DnsConfig::default(),
            connectivity: ConnectivityConfig {
                wireguard: wg,
                ..ConnectivityConfig::default()
            },
            edge: NetsvcsEdgeConfig::default(),
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
            self.enroll_result
                .lock()
                .expect("mutex not poisoned")
                .take()
                .unwrap_or_else(|| {
                    Ok(EnrollResponse {
                        node_id: "node-1".to_string(),
                        tenant: "tenant-1".to_string(),
                        access_token: token_with_exp(self.access_token_exp.load(Ordering::SeqCst)),
                        refresh_token: "refresh-0".to_string(),
                        config: node_config(1, Some(wg_config("initial-peer-key"))),
                    })
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

    fn identity() -> BootstrapIdentity {
        BootstrapIdentity {
            machine_jwt: "test-machine-jwt".to_string(),
            hostname: "test-host".to_string(),
            public_key: "test-public-key".to_string(),
        }
    }

    #[tokio::test]
    async fn enroll_maps_response_into_session_and_config() {
        let mock = MockClient {
            access_token_exp: AtomicI64::new(unix_now() + 3600),
            ..Default::default()
        };
        let (session, config) = enroll(&mock, &identity())
            .await
            .expect("enroll must succeed");
        assert_eq!(session.node_id, "node-1");
        assert_eq!(session.refresh_token, "refresh-0");
        assert_eq!(session.config_version, 1);
        assert!(session.access_token_exp > unix_now());
        assert_eq!(
            config
                .connectivity
                .wireguard
                .expect("initial wg config")
                .peer_public_key,
            "initial-peer-key"
        );
        assert_eq!(mock.enroll_calls.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn enroll_propagates_control_plane_errors() {
        let mock = MockClient::default();
        *mock.enroll_result.lock().expect("mutex not poisoned") = Some(Err(
            AgentError::ControlPlane("enrollment denied".to_string()),
        ));
        let err = enroll(&mock, &identity())
            .await
            .expect_err("enroll must fail");
        assert!(matches!(err, AgentError::ControlPlane(_)));
    }

    #[tokio::test]
    async fn tick_sends_heartbeat_and_reports_no_config_change_by_default() {
        let mock = MockClient {
            access_token_exp: AtomicI64::new(unix_now() + 3600),
            ..Default::default()
        };
        let mut session = Session {
            node_id: "node-1".to_string(),
            refresh_token: "refresh-0".to_string(),
            config_version: 1,
            access_token_exp: unix_now() + 3600,
        };
        let result = tick(&mock, &mut session).await;
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
        let mut session = Session {
            node_id: "node-1".to_string(),
            refresh_token: "refresh-0".to_string(),
            config_version: 1,
            access_token_exp: unix_now() + 3600,
        };
        let result = tick(&mock, &mut session)
            .await
            .expect("a newer config must be surfaced");
        assert_eq!(result.config_version, 2);
        assert_eq!(session.config_version, 2);
    }

    #[tokio::test]
    async fn tick_rotates_the_refresh_token_once_within_the_expiry_margin() {
        let mock = MockClient::default();
        let mut session = Session {
            node_id: "node-1".to_string(),
            refresh_token: "refresh-0".to_string(),
            config_version: 1,
            // Already inside REFRESH_MARGIN_SECS of "expiry".
            access_token_exp: unix_now() + 10,
        };
        tick(&mock, &mut session).await;
        assert_eq!(mock.refresh_calls.load(Ordering::SeqCst), 1);
        assert_eq!(session.refresh_token, "refresh-0-rotated");
        assert!(session.access_token_exp > unix_now() + 3000);
    }

    #[tokio::test]
    async fn tick_does_not_refresh_when_well_within_expiry() {
        let mock = MockClient::default();
        let mut session = Session {
            node_id: "node-1".to_string(),
            refresh_token: "refresh-0".to_string(),
            config_version: 1,
            access_token_exp: unix_now() + 3600,
        };
        tick(&mock, &mut session).await;
        assert_eq!(mock.refresh_calls.load(Ordering::SeqCst), 0);
        assert_eq!(session.refresh_token, "refresh-0");
    }

    #[tokio::test]
    async fn run_control_loop_publishes_the_initial_config_then_returns_on_shutdown() {
        let mock = MockClient {
            access_token_exp: AtomicI64::new(unix_now() + 3600),
            ..Default::default()
        };
        let shutdown = CancellationToken::new();
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel();

        shutdown.cancel(); // cancel immediately: exercises enroll + shutdown path without waiting on real ticks
        let result =
            run_control_loop(&mock, identity(), Duration::from_secs(30), &shutdown, tx).await;

        assert!(result.is_ok());
        assert_eq!(mock.enroll_calls.load(Ordering::SeqCst), 1);
        let published = rx.recv().await.expect("initial config must be published");
        assert_eq!(published.peer_public_key, "initial-peer-key");
    }

    #[tokio::test]
    async fn run_control_loop_propagates_enroll_failure() {
        let mock = MockClient::default();
        *mock.enroll_result.lock().expect("mutex not poisoned") =
            Some(Err(AgentError::ControlPlane("denied".to_string())));
        let shutdown = CancellationToken::new();
        let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
        let result =
            run_control_loop(&mock, identity(), Duration::from_secs(30), &shutdown, tx).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn run_control_loop_ticks_and_publishes_updated_configs_before_shutdown() {
        let mock = MockClient {
            access_token_exp: AtomicI64::new(unix_now() + 3600),
            ..Default::default()
        };
        *mock.config_poll_result.lock().expect("mutex not poisoned") =
            Some(node_config(2, Some(wg_config("rotated-peer-key"))));
        let shutdown = CancellationToken::new();
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel();

        let shutdown_clone = shutdown.clone();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(30)).await;
            shutdown_clone.cancel();
        });

        let result =
            run_control_loop(&mock, identity(), Duration::from_millis(5), &shutdown, tx).await;

        assert!(result.is_ok());
        assert!(mock.heartbeat_calls.load(Ordering::SeqCst) >= 1);

        let mut published = Vec::new();
        while let Ok(cfg) = rx.try_recv() {
            published.push(cfg.peer_public_key);
        }
        assert!(published.contains(&"initial-peer-key".to_string()));
        assert!(published.contains(&"rotated-peer-key".to_string()));
    }

    #[tokio::test]
    async fn run_control_loop_ends_early_when_the_receiver_is_dropped() {
        let mock = MockClient {
            access_token_exp: AtomicI64::new(unix_now() + 3600),
            ..Default::default()
        };
        *mock.config_poll_result.lock().expect("mutex not poisoned") =
            Some(node_config(2, Some(wg_config("rotated-peer-key"))));
        let shutdown = CancellationToken::new();
        let (tx, rx) = tokio::sync::mpsc::unbounded_channel();
        drop(rx); // simulate the applying side going away first

        let result =
            run_control_loop(&mock, identity(), Duration::from_millis(5), &shutdown, tx).await;
        assert!(result.is_ok());
    }
}
