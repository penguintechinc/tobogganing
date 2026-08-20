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
