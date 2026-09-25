//! REST (`reqwest`) implementation of `ControlPlaneClient`, used by
//! bare-metal edge nodes reaching `hub_api`'s `/api/v1/netsvcs` surface over
//! the public network — the REST fallback transport per `backend.md`.

use async_trait::async_trait;
use node_agent_core::{
    AgentConfig, AgentError, ControlPlaneClient, EnrollRequest, EnrollResponse, Heartbeat,
    IocVerdict, Metrics, NodeConfig, RefreshResponse, Result,
};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;

/// The `api_version` value stamped on every outbound request body, per
/// `backend.md`'s runtime-routing rule.
const API_VERSION: &str = "v1";

/// REST implementation of `ControlPlaneClient` against `hub_api`'s
/// `/api/v1/netsvcs` surface. Caches the most recently issued
/// `access_token` (from `enroll`/`refresh_token`) and attaches it as
/// `Authorization: Bearer` on every other call.
pub struct RestClient {
    http: reqwest::Client,
    base_url: String,
    access_token: RwLock<Option<String>>,
}

impl RestClient {
    /// Builds a REST client for `cfg.control_plane_url`, timing out
    /// requests at `cfg.request_timeout_secs`. Construction never panics:
    /// a client-build failure (rare — only on TLS backend misconfiguration)
    /// falls back to `reqwest::Client::default()` with a logged warning.
    pub fn new(cfg: &AgentConfig) -> Self {
        let http = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(cfg.request_timeout_secs))
            .build()
            .unwrap_or_else(|err| {
                tracing::warn!(error = %err, "failed to build a configured reqwest client; falling back to defaults");
                reqwest::Client::new()
            });
        Self {
            http,
            base_url: cfg.control_plane_url.trim_end_matches('/').to_string(),
            access_token: RwLock::new(None),
        }
    }

    fn url(&self, path: &str) -> String {
        format!("{}/api/v1/netsvcs{path}", self.base_url)
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

    async fn send<B: Serialize, T: DeserializeOwned>(
        &self,
        method: reqwest::Method,
        path: &str,
        bearer: &str,
        body: Option<&B>,
    ) -> Result<T> {
        let mut request = self
            .http
            .request(method, self.url(path))
            .bearer_auth(bearer);
        if let Some(body) = body {
            request = request.json(body);
        }

        let response = request
            .send()
            .await
            .map_err(|e| AgentError::Transport(e.to_string()))?;
        let status = response.status();
        let text = response
            .text()
            .await
            .map_err(|e| AgentError::Transport(e.to_string()))?;

        if status.as_u16() == 501 && text.contains("api_version") {
            return Err(AgentError::UnsupportedApiVersion {
                version: API_VERSION.to_string(),
                reason: text,
            });
        }
        if !status.is_success() {
            return Err(AgentError::ControlPlane(format!(
                "hub_api returned HTTP {status}: {text}"
            )));
        }

        let envelope: Envelope<T> = serde_json::from_str(&text)
            .map_err(|e| AgentError::ControlPlane(format!("malformed response envelope: {e}")))?;
        if envelope.status != "success" {
            return Err(AgentError::ControlPlane(envelope.message.unwrap_or_else(
                || "control-plane returned a non-success status".to_string(),
            )));
        }
        envelope.data.ok_or_else(|| {
            AgentError::ControlPlane("success response missing \"data\"".to_string())
        })
    }
}

/// The `{"status", "data", "meta"}` response envelope mandated by
/// `backend.md`'s API response format.
#[derive(Debug, Deserialize)]
struct Envelope<T> {
    status: String,
    // `Option<T>` fields are implicitly optional to serde (a missing key
    // deserializes to `None`) without needing `#[serde(default)]` — adding
    // it here would make derive(Deserialize) require `T: Default`, which
    // domain types like `NodeConfig` deliberately don't implement.
    data: Option<T>,
    message: Option<String>,
}

#[async_trait]
impl ControlPlaneClient for RestClient {
    async fn enroll(&self, req: EnrollRequest) -> Result<EnrollResponse> {
        #[derive(Serialize)]
        struct Body {
            api_version: &'static str,
            node_type: String,
            hostname: String,
            public_key: Option<String>,
        }
        let body = Body {
            api_version: API_VERSION,
            node_type: req.node_type,
            hostname: req.hostname,
            public_key: req.public_key,
        };
        let resp: EnrollResponse = self
            .send(
                reqwest::Method::POST,
                "/enroll",
                &req.machine_jwt,
                Some(&body),
            )
            .await?;
        self.set_access_token(resp.access_token.clone()).await;
        Ok(resp)
    }

    async fn heartbeat(&self, hb: Heartbeat) -> Result<()> {
        #[derive(Serialize)]
        struct Body {
            api_version: &'static str,
            #[serde(flatten)]
            heartbeat: Heartbeat,
        }
        let token = self.bearer_token().await?;
        let body = Body {
            api_version: API_VERSION,
            heartbeat: hb,
        };
        let _: serde_json::Value = self
            .send(reqwest::Method::POST, "/heartbeat", &token, Some(&body))
            .await?;
        Ok(())
    }

    async fn get_config(&self, node_id: &str, current_version: i64) -> Result<Option<NodeConfig>> {
        // Handled outside the generic `send` helper: the server signals "no
        // update" with HTTP 204 (empty body) rather than `"data": null`,
        // avoiding the `Option<Option<T>>` JSON-null ambiguity.
        let token = self.bearer_token().await?;
        let path = format!(
            "/config?node_id={node_id}&current_version={current_version}&api_version={API_VERSION}"
        );
        let response = self
            .http
            .get(self.url(&path))
            .bearer_auth(&token)
            .send()
            .await
            .map_err(|e| AgentError::Transport(e.to_string()))?;
        let status = response.status();
        if status.as_u16() == 204 {
            return Ok(None);
        }
        let text = response
            .text()
            .await
            .map_err(|e| AgentError::Transport(e.to_string()))?;
        if status.as_u16() == 501 && text.contains("api_version") {
            return Err(AgentError::UnsupportedApiVersion {
                version: API_VERSION.to_string(),
                reason: text,
            });
        }
        if !status.is_success() {
            return Err(AgentError::ControlPlane(format!(
                "hub_api returned HTTP {status}: {text}"
            )));
        }

        let envelope: Envelope<NodeConfig> = serde_json::from_str(&text)
            .map_err(|e| AgentError::ControlPlane(format!("malformed response envelope: {e}")))?;
        if envelope.status != "success" {
            return Err(AgentError::ControlPlane(envelope.message.unwrap_or_else(
                || "control-plane returned a non-success status".to_string(),
            )));
        }
        let config = envelope.data.ok_or_else(|| {
            AgentError::ControlPlane("success response missing \"data\"".to_string())
        })?;
        Ok(Some(config).filter(|c| c.config_version > current_version))
    }

    async fn report_metrics(&self, m: Metrics) -> Result<()> {
        #[derive(Serialize)]
        struct Body {
            api_version: &'static str,
            #[serde(flatten)]
            metrics: Metrics,
        }
        let token = self.bearer_token().await?;
        let body = Body {
            api_version: API_VERSION,
            metrics: m,
        };
        let _: serde_json::Value = self
            .send(reqwest::Method::POST, "/metrics", &token, Some(&body))
            .await?;
        Ok(())
    }

    async fn refresh_token(&self, refresh_token: &str) -> Result<RefreshResponse> {
        #[derive(Serialize)]
        struct Body {
            api_version: &'static str,
            refresh_token: String,
        }
        let body = Body {
            api_version: API_VERSION,
            refresh_token: refresh_token.to_string(),
        };
        let resp: RefreshResponse = self
            .send(
                reqwest::Method::POST,
                "/token/refresh",
                refresh_token,
                Some(&body),
            )
            .await?;
        self.set_access_token(resp.access_token.clone()).await;
        Ok(resp)
    }

    async fn check_ioc(&self, indicator: &str) -> Result<IocVerdict> {
        let token = self.bearer_token().await?;
        let path = format!("/ioc?indicator={indicator}&api_version={API_VERSION}");
        self.send::<(), _>(reqwest::Method::GET, &path, &token, None)
            .await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use node_agent_core::AgentFeatures;
    use serde_json::json;
    use wiremock::matchers::{header, method, path, query_param};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    /// `reqwest`'s `rustls-no-provider` feature requires a process-wide
    /// crypto provider installed before *any* client is built, even for
    /// plain-HTTP mock-server traffic — mirrors the real startup ordering
    /// (`install_crypto_provider` before `build_client`) documented on
    /// [`crate::install_crypto_provider`].
    fn new_client(cfg: &AgentConfig) -> RestClient {
        crate::install_crypto_provider().expect("crypto provider install must not fail");
        RestClient::new(cfg)
    }

    fn test_cfg(base_url: &str) -> AgentConfig {
        AgentConfig {
            mode: node_agent_core::AgentMode::Edge,
            control_plane_url: base_url.to_string(),
            machine_jwt_path: std::path::PathBuf::new(),
            features: AgentFeatures::default(),
            heartbeat_interval_secs: 30,
            request_timeout_secs: 5,
        }
    }

    fn enroll_envelope(access_token: &str) -> serde_json::Value {
        json!({
            "status": "success",
            "data": {
                "node_id": "node-1",
                "tenant": "tenant-1",
                "access_token": access_token,
                "refresh_token": "refresh-1",
                "config": {"connectivity": {}, "edge": {}, "config_version": 1},
            },
            "meta": {"version": 1},
        })
    }

    #[tokio::test]
    async fn enroll_sets_access_token_used_by_the_next_call() {
        let server = MockServer::start().await;
        Mock::given(method("POST"))
            .and(path("/api/v1/netsvcs/enroll"))
            .and(header("authorization", "Bearer machine-jwt-1"))
            .respond_with(ResponseTemplate::new(200).set_body_json(enroll_envelope("token-1")))
            .expect(1)
            .mount(&server)
            .await;
        Mock::given(method("POST"))
            .and(path("/api/v1/netsvcs/heartbeat"))
            .and(header("authorization", "Bearer token-1"))
            .respond_with(
                ResponseTemplate::new(200).set_body_json(json!({"status": "success", "data": {}})),
            )
            .expect(1)
            .mount(&server)
            .await;

        let client = new_client(&test_cfg(&server.uri()));
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
        assert_eq!(resp.access_token, "token-1");

        // Proves the access token from enroll(), not a stale/absent one, is
        // attached as the bearer on the very next call.
        client
            .heartbeat(Heartbeat {
                node_id: "node-1".to_string(),
                timestamp: 0,
                config_version: 1,
            })
            .await
            .expect("heartbeat must succeed using the freshly enrolled token");
    }

    #[tokio::test]
    async fn heartbeat_before_enroll_fails_with_not_enrolled_error() {
        let server = MockServer::start().await;
        let client = new_client(&test_cfg(&server.uri()));
        let err = client
            .heartbeat(Heartbeat {
                node_id: "node-1".to_string(),
                timestamp: 0,
                config_version: 0,
            })
            .await
            .expect_err("heartbeat before enroll must fail");
        assert!(matches!(err, AgentError::ControlPlane(msg) if msg.contains("not enrolled")));
    }

    async fn enrolled_client(server: &MockServer) -> RestClient {
        Mock::given(method("POST"))
            .and(path("/api/v1/netsvcs/enroll"))
            .respond_with(ResponseTemplate::new(200).set_body_json(enroll_envelope("token-1")))
            .mount(server)
            .await;
        let client = new_client(&test_cfg(&server.uri()));
        client
            .enroll(EnrollRequest {
                machine_jwt: "mjwt".to_string(),
                node_type: "node-agent".to_string(),
                hostname: "host-1".to_string(),
                public_key: Some("pubkey".to_string()),
            })
            .await
            .expect("enroll must succeed");
        client
    }

    #[tokio::test]
    async fn get_config_returns_some_when_server_reports_a_newer_version() {
        let server = MockServer::start().await;
        let client = enrolled_client(&server).await;
        Mock::given(method("GET"))
            .and(path("/api/v1/netsvcs/config"))
            .and(query_param("node_id", "node-1"))
            .and(query_param("current_version", "1"))
            .and(header("authorization", "Bearer token-1"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "status": "success",
                "data": {"connectivity": {}, "edge": {}, "config_version": 2},
            })))
            .mount(&server)
            .await;

        let cfg = client
            .get_config("node-1", 1)
            .await
            .expect("get_config must succeed")
            .expect("a newer config must be returned");
        assert_eq!(cfg.config_version, 2);
    }

    #[tokio::test]
    async fn get_config_returns_none_when_server_reports_no_newer_version_via_204() {
        let server = MockServer::start().await;
        let client = enrolled_client(&server).await;
        Mock::given(method("GET"))
            .and(path("/api/v1/netsvcs/config"))
            .respond_with(ResponseTemplate::new(204))
            .mount(&server)
            .await;

        let result = client
            .get_config("node-1", 5)
            .await
            .expect("204 must not be an error");
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn get_config_filters_out_a_stale_version_returned_with_200() {
        let server = MockServer::start().await;
        let client = enrolled_client(&server).await;
        Mock::given(method("GET"))
            .and(path("/api/v1/netsvcs/config"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "status": "success",
                "data": {"connectivity": {}, "edge": {}, "config_version": 1},
            })))
            .mount(&server)
            .await;

        // Server echoed back the same version the caller already has —
        // must be filtered to None even though the envelope carried data.
        let result = client
            .get_config("node-1", 1)
            .await
            .expect("must not error");
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn get_config_maps_unsupported_api_version_to_the_dedicated_error() {
        let server = MockServer::start().await;
        let client = enrolled_client(&server).await;
        Mock::given(method("GET"))
            .and(path("/api/v1/netsvcs/config"))
            .respond_with(
                ResponseTemplate::new(501).set_body_string("api_version v1 not supported"),
            )
            .mount(&server)
            .await;

        let err = client
            .get_config("node-1", 1)
            .await
            .expect_err("501 with api_version text must error");
        assert!(matches!(err, AgentError::UnsupportedApiVersion { .. }));
    }

    #[tokio::test]
    async fn get_config_maps_other_http_errors_to_control_plane_error() {
        let server = MockServer::start().await;
        let client = enrolled_client(&server).await;
        Mock::given(method("GET"))
            .and(path("/api/v1/netsvcs/config"))
            .respond_with(ResponseTemplate::new(500).set_body_string("boom"))
            .mount(&server)
            .await;

        let err = client
            .get_config("node-1", 1)
            .await
            .expect_err("HTTP 500 must error");
        assert!(matches!(err, AgentError::ControlPlane(msg) if msg.contains("500")));
    }

    #[tokio::test]
    async fn report_metrics_succeeds_against_a_success_envelope() {
        let server = MockServer::start().await;
        let client = enrolled_client(&server).await;
        Mock::given(method("POST"))
            .and(path("/api/v1/netsvcs/metrics"))
            .and(header("authorization", "Bearer token-1"))
            .respond_with(
                ResponseTemplate::new(200).set_body_json(json!({"status": "success", "data": {}})),
            )
            .mount(&server)
            .await;

        client
            .report_metrics(Metrics {
                node_id: "node-1".to_string(),
                samples: Vec::new(),
            })
            .await
            .expect("report_metrics must succeed");
    }

    #[tokio::test]
    async fn refresh_token_rotates_the_access_token_used_by_subsequent_calls() {
        let server = MockServer::start().await;
        let client = enrolled_client(&server).await;
        Mock::given(method("POST"))
            .and(path("/api/v1/netsvcs/token/refresh"))
            .and(header("authorization", "Bearer old-refresh"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "status": "success",
                "data": {"access_token": "token-2", "refresh_token": "refresh-2"},
            })))
            .mount(&server)
            .await;
        Mock::given(method("POST"))
            .and(path("/api/v1/netsvcs/heartbeat"))
            .and(header("authorization", "Bearer token-2"))
            .respond_with(
                ResponseTemplate::new(200).set_body_json(json!({"status": "success", "data": {}})),
            )
            .mount(&server)
            .await;

        let resp = client
            .refresh_token("old-refresh")
            .await
            .expect("refresh_token must succeed");
        assert_eq!(resp.access_token, "token-2");
        assert_eq!(resp.refresh_token, "refresh-2");

        client
            .heartbeat(Heartbeat {
                node_id: "node-1".to_string(),
                timestamp: 0,
                config_version: 1,
            })
            .await
            .expect("heartbeat must use the rotated access token");
    }

    #[tokio::test]
    async fn check_ioc_parses_a_malicious_verdict() {
        let server = MockServer::start().await;
        let client = enrolled_client(&server).await;
        Mock::given(method("GET"))
            .and(path("/api/v1/netsvcs/ioc"))
            .and(query_param("indicator", "bad.example.com"))
            .and(header("authorization", "Bearer token-1"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "status": "success",
                "data": {"indicator": "bad.example.com", "malicious": true, "source": "test-feed"},
            })))
            .mount(&server)
            .await;

        let verdict = client
            .check_ioc("bad.example.com")
            .await
            .expect("check_ioc must succeed");
        assert!(verdict.malicious);
        assert_eq!(verdict.source.as_deref(), Some("test-feed"));
    }

    #[tokio::test]
    async fn send_maps_a_non_success_envelope_status_to_control_plane_error() {
        let server = MockServer::start().await;
        let client = enrolled_client(&server).await;
        Mock::given(method("POST"))
            .and(path("/api/v1/netsvcs/heartbeat"))
            .respond_with(ResponseTemplate::new(200).set_body_json(json!({
                "status": "error",
                "message": "tenant mismatch",
            })))
            .mount(&server)
            .await;

        let err = client
            .heartbeat(Heartbeat {
                node_id: "node-1".to_string(),
                timestamp: 0,
                config_version: 1,
            })
            .await
            .expect_err("a non-success envelope status must error");
        assert!(matches!(err, AgentError::ControlPlane(msg) if msg.contains("tenant mismatch")));
    }

    #[tokio::test]
    async fn send_maps_unsupported_api_version_to_the_dedicated_error() {
        let server = MockServer::start().await;
        let client = enrolled_client(&server).await;
        Mock::given(method("POST"))
            .and(path("/api/v1/netsvcs/heartbeat"))
            .respond_with(
                ResponseTemplate::new(501).set_body_string("api_version v1 not supported"),
            )
            .mount(&server)
            .await;

        let err = client
            .heartbeat(Heartbeat {
                node_id: "node-1".to_string(),
                timestamp: 0,
                config_version: 1,
            })
            .await
            .expect_err("501 with api_version text must error");
        assert!(matches!(err, AgentError::UnsupportedApiVersion { .. }));
    }

    #[tokio::test]
    async fn new_falls_back_gracefully_when_configured_normally() {
        // `RestClient::new` never panics — this just exercises the happy
        // construction path (the `unwrap_or_else` fallback branch is not
        // independently triggerable without an invalid TLS backend, which
        // `reqwest::Client::builder()` cannot be forced into from safe code).
        let client = new_client(&test_cfg("http://127.0.0.1:0"));
        let err = client
            .bearer_token()
            .await
            .expect_err("a fresh client has no access token yet");
        assert!(matches!(err, AgentError::ControlPlane(_)));
    }
}
