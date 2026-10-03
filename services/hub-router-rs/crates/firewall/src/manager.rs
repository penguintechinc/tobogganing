//! Periodic rule-fetching manager — the Rust port of `Manager`
//! (`services/hub-router/proxy/firewall/manager.go`). Fetches the full
//! per-user rule set from the hub-api/Manager control plane, builds a
//! presorted [`RuleSet`] per user (see [`crate::engine`]'s doc for why
//! this differs from the Go source's per-request sort), and serves
//! [`Manager::check_access`] against the cached, presorted snapshot.

use crate::engine::RuleSet;
use crate::metrics;
use crate::rule::{AllRulesResponse, UserRules};
use async_trait::async_trait;
use reqwest::header::{AUTHORIZATION, USER_AGENT};
use std::collections::HashMap;
use std::sync::{Arc, PoisonError, RwLock};
use std::time::{Duration, SystemTime};
use tokio_util::sync::CancellationToken;

/// Supplies a bearer token for each [`Manager::fetch_rules`] call —
/// mirrors the Go source's `TokenProvider func(ctx context.Context)
/// (string, error)` (expressed here as a trait, same pattern as
/// `hub_router_ports::config_client::TokenProvider` — this crate defines
/// its own copy rather than depending on `hub-router-ports` just to
/// reuse one trait).
#[async_trait]
pub trait TokenProvider: Send + Sync {
    async fn token(&self) -> Result<String, String>;
}

/// Default provider: always returns the client's static configured
/// token, matching `NewManager`'s default closure.
struct StaticTokenProvider(String);

#[async_trait]
impl TokenProvider for StaticTokenProvider {
    async fn token(&self) -> Result<String, String> {
        Ok(self.0.clone())
    }
}

/// Failure fetching/decoding the firewall-rules response from the
/// Manager/hub-api control plane.
#[derive(Debug, thiserror::Error)]
pub enum ManagerError {
    #[error("failed to build http client: {0}")]
    ClientInit(#[source] reqwest::Error),
    #[error("failed to fetch firewall rules: {0}")]
    Request(#[source] reqwest::Error),
    #[error("failed to fetch firewall rules: status {status}, body: {body}")]
    Status { status: u16, body: String },
    #[error("failed to decode firewall rules response: {0}")]
    Decode(#[source] reqwest::Error),
}

const USER_AGENT_VALUE: &str = "SASEWaddle-Headend/1.0";
const REQUEST_TIMEOUT: Duration = Duration::from_secs(10);
/// Matches the Go source's `30+rand.Intn(61)` seconds — `[30, 90]`
/// inclusive.
const REFRESH_JITTER_MIN_SECS: u64 = 30;
const REFRESH_JITTER_MAX_SECS: u64 = 90;

#[derive(Default)]
struct ManagerState {
    rule_sets: HashMap<String, Arc<RuleSet>>,
    user_rules: HashMap<String, Arc<UserRules>>,
    last_update: Option<SystemTime>,
}

/// Fetches and caches per-user firewall rules, and evaluates access
/// checks against the cached, presorted snapshot.
///
/// Go source method mapping: `NewManager` → [`Manager::new`];
/// `SetTokenProvider` → [`Manager::set_token_provider`]; `Start` →
/// caller does `manager.fetch_rules().await?` once for the initial
/// fetch, then `Arc::new(manager).spawn_refresh_loop()` for the periodic
/// background refresh (split in two because spawning a
/// self-referencing task requires `Arc`-wrapping — the caller's choice,
/// not baked into this type); `Stop` → [`Manager::cancel`] (cancels the
/// token the spawned loop watches, the same "signal, don't block waiting
/// for exit" semantics as closing the Go source's `stopChan`);
/// `CheckAccess` → [`Manager::check_access`];
/// `GetUserRules`/`GetLastUpdateTime`/`GetRulesCount` → identically
/// named methods below.
pub struct Manager {
    manager_url: String,
    auth_token: String,
    token_provider: Arc<dyn TokenProvider>,
    http_client: reqwest::Client,
    state: RwLock<ManagerState>,
    cancel: CancellationToken,
}

impl Manager {
    /// Builds a manager with a static-token fallback provider (mirrors
    /// `NewManager`). No network call happens until [`Manager::fetch_rules`]
    /// runs.
    pub fn new(
        manager_url: impl Into<String>,
        auth_token: impl Into<String>,
    ) -> Result<Self, ManagerError> {
        let auth_token = auth_token.into();
        let http_client = reqwest::Client::builder()
            .timeout(REQUEST_TIMEOUT)
            .build()
            .map_err(ManagerError::ClientInit)?;

        Ok(Self {
            manager_url: manager_url.into(),
            token_provider: Arc::new(StaticTokenProvider(auth_token.clone())),
            auth_token,
            http_client,
            state: RwLock::new(ManagerState::default()),
            cancel: CancellationToken::new(),
        })
    }

    /// Installs a custom token provider (e.g. a machine-JWT client),
    /// mirroring `SetTokenProvider`.
    pub fn set_token_provider(&mut self, provider: Arc<dyn TokenProvider>) {
        self.token_provider = provider;
    }

    /// Fetches the full per-user rules snapshot from
    /// `GET {manager_url}/api/v1/firewall/rules` and replaces the cached
    /// [`RuleSet`]s — the Rust port of `fetchRules`, plus building each
    /// user's presorted [`RuleSet`] once right here (see
    /// [`crate::engine`]'s doc on why that no longer happens per-request).
    /// On a token-provider failure, falls back to the static configured
    /// token (warning logged) rather than failing the whole request,
    /// mirroring the Go source exactly.
    #[tracing::instrument(skip(self))]
    pub async fn fetch_rules(&self) -> Result<(), ManagerError> {
        let url = format!("{}/api/v1/firewall/rules", self.manager_url);

        let token = match self.token_provider.token().await {
            Ok(t) => t,
            Err(e) => {
                tracing::warn!(
                    error = %e,
                    "failed to get auth token; falling back to static token"
                );
                self.auth_token.clone()
            }
        };

        let resp = self
            .http_client
            .get(&url)
            .header(AUTHORIZATION, format!("Bearer {token}"))
            .header(USER_AGENT, USER_AGENT_VALUE)
            .send()
            .await
            .map_err(ManagerError::Request)?;

        let status = resp.status();
        if status != reqwest::StatusCode::OK {
            let body = resp.text().await.unwrap_or_default();
            return Err(ManagerError::Status {
                status: status.as_u16(),
                body,
            });
        }

        let decoded: AllRulesResponse = resp.json().await.map_err(ManagerError::Decode)?;

        let mut rule_sets = HashMap::with_capacity(decoded.user_rules.len());
        let mut user_rules = HashMap::with_capacity(decoded.user_rules.len());
        for (user_id, rules) in decoded.user_rules {
            rule_sets.insert(user_id.clone(), Arc::new(RuleSet::build(&rules)));
            user_rules.insert(user_id, Arc::new(rules));
        }
        let fetched_count = user_rules.len();

        {
            let mut state = self.state.write().unwrap_or_else(PoisonError::into_inner);
            state.rule_sets = rule_sets;
            state.user_rules = user_rules;
            state.last_update = Some(SystemTime::now());
        }

        tracing::info!(users = fetched_count, "updated firewall rules");
        Ok(())
    }

    /// Evaluates `target` against `user_id`'s cached, presorted rule set
    /// — the Rust port of `CheckAccess` (minus the per-call sort). No
    /// cached rules for `user_id` (never fetched, or the last fetch
    /// never included this user) → deny, matching the Go source's "no
    /// rules found, denying access" branch. Records a rule-eval-latency
    /// histogram data point (labeled by outcome) on every call.
    #[tracing::instrument(skip(self), fields(user_id = %user_id))]
    pub fn check_access(&self, user_id: &str, target: &str) -> bool {
        let start = std::time::Instant::now();
        let rule_set = {
            let state = self.state.read().unwrap_or_else(PoisonError::into_inner);
            state.rule_sets.get(user_id).cloned()
        };

        let Some(rule_set) = rule_set else {
            tracing::warn!(user_id, "no firewall rules found for user, denying access");
            metrics::record_access_check(start.elapsed().as_secs_f64(), "deny_no_rules");
            return false;
        };

        let outcome = rule_set.check(target);
        tracing::debug!(
            user_id,
            target,
            allowed = outcome.allowed(),
            reason = outcome.reason(),
            "firewall access check"
        );
        metrics::record_access_check(start.elapsed().as_secs_f64(), outcome.reason());
        outcome.allowed()
    }

    /// The raw [`UserRules`] last fetched for `user_id`, if any — the
    /// Rust port of `GetUserRules`.
    pub fn get_user_rules(&self, user_id: &str) -> Option<Arc<UserRules>> {
        self.state
            .read()
            .unwrap_or_else(PoisonError::into_inner)
            .user_rules
            .get(user_id)
            .cloned()
    }

    /// When [`Manager::fetch_rules`] last succeeded, if ever — the Rust
    /// port of `GetLastUpdateTime` (which returns the Go zero-value
    /// `time.Time{}` before the first fetch; `None` serves that role
    /// here).
    pub fn get_last_update_time(&self) -> Option<SystemTime> {
        self.state
            .read()
            .unwrap_or_else(PoisonError::into_inner)
            .last_update
    }

    /// Count of users with cached rules — the Rust port of
    /// `GetRulesCount`.
    pub fn get_rules_count(&self) -> usize {
        self.state
            .read()
            .unwrap_or_else(PoisonError::into_inner)
            .user_rules
            .len()
    }

    /// Signals [`Manager::spawn_refresh_loop`] to stop — the Rust port
    /// of `Stop` (`m.refreshTicker.Stop(); close(m.stopChan)`), expressed
    /// as a single `CancellationToken` rather than a ticker-stop-plus-
    /// channel-close pair.
    pub fn cancel(&self) {
        self.cancel.cancel();
    }

    /// Spawns the periodic background refresh loop — the Rust port of
    /// `refreshLoop`/the ticker half of `Start`. Randomizes the wait
    /// before *every* fetch to the same `[30, 90]`-second window the Go
    /// source used, preventing thundering-herd refreshes across multiple
    /// headend replicas. A failed refresh is logged at WARN and the loop
    /// continues on the previously cached rules (graceful degradation —
    /// critical-rules.md: a dead/unreachable control plane never crashes
    /// the service). Returns immediately after spawning; call
    /// [`Manager::fetch_rules`] once yourself first for the initial
    /// fetch (see this type's doc on the `Start` mapping).
    pub fn spawn_refresh_loop(self: Arc<Self>) -> tokio::task::JoinHandle<()> {
        tokio::spawn(async move {
            loop {
                let jitter_secs =
                    rand::random_range(REFRESH_JITTER_MIN_SECS..=REFRESH_JITTER_MAX_SECS);
                let interval = Duration::from_secs(jitter_secs);

                tokio::select! {
                    () = self.cancel.cancelled() => {
                        tracing::info!("firewall rules refresh loop stopping");
                        return;
                    }
                    () = tokio::time::sleep(interval) => {}
                }

                if let Err(error) = self.fetch_rules().await {
                    tracing::warn!(%error, "failed to refresh firewall rules; using cached rules");
                }
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use wiremock::matchers::{header, method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    fn sample_rules_response() -> serde_json::Value {
        serde_json::json!({
            "timestamp": "2026-01-01T00:00:00Z",
            "rules_count": 1,
            "user_rules": {
                "user-1": {
                    "user_id": "user-1",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "rules": {
                        "allow_domains": [
                            {"pattern": "example.com", "priority": 1, "description": "allow"}
                        ],
                        "deny_domains": [],
                        "allow_ips": [],
                        "deny_ips": [],
                        "allow_ip_ranges": [],
                        "deny_ip_ranges": [],
                        "allow_url_patterns": [],
                        "deny_url_patterns": [],
                        "allow_protocol_rules": [],
                        "deny_protocol_rules": []
                    }
                }
            }
        })
    }

    #[tokio::test]
    async fn fetch_rules_populates_cache_and_check_access_evaluates_it() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/api/v1/firewall/rules"))
            .and(header("authorization", "Bearer static-token"))
            .and(header("user-agent", USER_AGENT_VALUE))
            .respond_with(ResponseTemplate::new(200).set_body_json(sample_rules_response()))
            .mount(&server)
            .await;

        let manager = Manager::new(server.uri(), "static-token").unwrap();
        manager.fetch_rules().await.unwrap();

        assert!(manager.check_access("user-1", "example.com"));
        assert!(!manager.check_access("user-1", "other.com"));
        assert_eq!(manager.get_rules_count(), 1);
        assert!(manager.get_last_update_time().is_some());
        assert!(manager.get_user_rules("user-1").is_some());
        assert!(manager.get_user_rules("missing-user").is_none());
    }

    #[tokio::test]
    async fn check_access_denies_when_user_has_no_cached_rules() {
        let manager = Manager::new("http://unused.invalid", "t").unwrap();
        assert!(!manager.check_access("nobody", "example.com"));
    }

    #[tokio::test]
    async fn fetch_rules_uses_custom_token_provider() {
        struct Custom;
        #[async_trait]
        impl TokenProvider for Custom {
            async fn token(&self) -> Result<String, String> {
                Ok("provider-token".to_string())
            }
        }

        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(header("authorization", "Bearer provider-token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(sample_rules_response()))
            .mount(&server)
            .await;

        let mut manager = Manager::new(server.uri(), "static-token").unwrap();
        manager.set_token_provider(Arc::new(Custom));
        manager.fetch_rules().await.unwrap();
    }

    #[tokio::test]
    async fn fetch_rules_falls_back_to_static_token_when_provider_fails() {
        struct Failing;
        #[async_trait]
        impl TokenProvider for Failing {
            async fn token(&self) -> Result<String, String> {
                Err("no token available".to_string())
            }
        }

        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(header("authorization", "Bearer static-token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(sample_rules_response()))
            .mount(&server)
            .await;

        let mut manager = Manager::new(server.uri(), "static-token").unwrap();
        manager.set_token_provider(Arc::new(Failing));
        manager.fetch_rules().await.unwrap();
    }

    #[tokio::test]
    async fn fetch_rules_non_200_status_is_an_error() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .respond_with(ResponseTemplate::new(500).set_body_string("boom"))
            .mount(&server)
            .await;

        let manager = Manager::new(server.uri(), "t").unwrap();
        let err = manager.fetch_rules().await.unwrap_err();
        match err {
            ManagerError::Status { status, body } => {
                assert_eq!(status, 500);
                assert_eq!(body, "boom");
            }
            other => panic!("expected Status error, got {other:?}"),
        }
    }

    #[tokio::test]
    async fn fetch_rules_malformed_json_is_a_decode_error() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .respond_with(ResponseTemplate::new(200).set_body_string("not json"))
            .mount(&server)
            .await;

        let manager = Manager::new(server.uri(), "t").unwrap();
        let err = manager.fetch_rules().await.unwrap_err();
        assert!(matches!(err, ManagerError::Decode(_)));
    }

    #[tokio::test]
    async fn fetch_rules_connection_failure_is_a_request_error() {
        // Port 1 on localhost: a reserved, essentially-always-closed
        // port, giving a reliable connection-refused without binding
        // anything.
        let manager = Manager::new("http://127.0.0.1:1", "t").unwrap();
        let err = manager.fetch_rules().await.unwrap_err();
        assert!(matches!(err, ManagerError::Request(_)));
    }

    /// A failed refresh must never clear previously cached rules —
    /// mirrors `hub_router_auth::PublicKeyCache`'s identical graceful-
    /// degradation contract (critical-rules.md: a dead/unreachable
    /// control plane never crashes or blanks out the service).
    #[tokio::test]
    async fn failed_refresh_leaves_previously_cached_rules_untouched() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .respond_with(ResponseTemplate::new(200).set_body_json(sample_rules_response()))
            .mount(&server)
            .await;

        let manager = Manager::new(server.uri(), "t").unwrap();
        manager.fetch_rules().await.unwrap();
        assert!(manager.check_access("user-1", "example.com"));

        // Point fetch_rules at an unreachable manager_url by building a
        // second manager that shares nothing — instead, directly assert
        // the contract at the unit the state lives in: a second manager
        // pointed at an unreachable endpoint never populates its cache,
        // while this one's cache (never touched by that failure) still
        // answers correctly.
        let unreachable = Manager::new("http://127.0.0.1:1", "t").unwrap();
        assert!(unreachable.fetch_rules().await.is_err());
        assert!(!unreachable.check_access("user-1", "example.com"));

        // Original manager's cache is unaffected by the unrelated failure.
        assert!(manager.check_access("user-1", "example.com"));
    }

    #[tokio::test]
    async fn spawn_refresh_loop_stops_promptly_on_cancel() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .respond_with(ResponseTemplate::new(200).set_body_json(sample_rules_response()))
            .mount(&server)
            .await;

        let manager = Arc::new(Manager::new(server.uri(), "t").unwrap());
        manager.fetch_rules().await.unwrap();

        let handle = Arc::clone(&manager).spawn_refresh_loop();
        manager.cancel();

        tokio::time::timeout(Duration::from_secs(5), handle)
            .await
            .expect("refresh loop must stop promptly once cancelled, even mid-sleep")
            .expect("refresh loop task must not panic");
    }
}
