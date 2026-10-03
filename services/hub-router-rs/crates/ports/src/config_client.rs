//! Manager-service port-configuration client — the Rust port of
//! `ConfigClient` (`services/hub-router/proxy/ports/config_client.go`).
//! Fetches the current TCP/UDP port-range configuration for this headend
//! from the Manager/hub-api control plane and validates it.

use async_trait::async_trait;
use reqwest::header::{AUTHORIZATION, USER_AGENT};
use std::sync::Arc;
use std::time::Duration;

/// Detailed per-range record as returned by the Manager API's
/// `tcp_ranges_detail`/`udp_ranges_detail` fields — distinct from
/// [`crate::range::PortRange`] (the lean parsed-config struct); see the
/// `range` module doc for why this port splits the Go source's single
/// conflated `PortRange` type in two.
#[derive(Debug, Clone, PartialEq, Eq, serde::Deserialize, serde::Serialize)]
pub struct PortRangeDetail {
    pub id: String,
    pub start_port: u16,
    pub end_port: u16,
    pub protocol: String,
    pub description: String,
    pub enabled: bool,
    pub created_at: String,
    pub updated_at: String,
}

/// Port configuration payload returned by
/// `GET /api/v1/headend/{headend_id}/ports?cluster_id={cluster_id}`.
#[derive(Debug, Clone, PartialEq, Eq, serde::Deserialize, serde::Serialize)]
pub struct PortConfig {
    pub headend_id: String,
    pub cluster_id: String,
    pub tcp_ranges: String,
    pub udp_ranges: String,
    #[serde(default)]
    pub tcp_ranges_detail: Vec<PortRangeDetail>,
    #[serde(default)]
    pub udp_ranges_detail: Vec<PortRangeDetail>,
    pub updated_at: String,
}

/// Supplies a bearer token for each [`ConfigClient::fetch_config`] call —
/// the Rust equivalent of the Go source's `TokenProvider func(ctx
/// context.Context) (string, error)`, expressed as a trait (via
/// `async-trait`, already a workspace dependency) rather than a boxed
/// async closure type.
#[async_trait]
pub trait TokenProvider: Send + Sync {
    async fn token(&self) -> Result<String, String>;
}

/// Default provider: always returns the client's static configured token,
/// matching `NewConfigClient`'s default closure.
struct StaticTokenProvider(String);

#[async_trait]
impl TokenProvider for StaticTokenProvider {
    async fn token(&self) -> Result<String, String> {
        Ok(self.0.clone())
    }
}

/// Failure fetching or validating a [`PortConfig`] via [`ConfigClient`].
#[derive(Debug, thiserror::Error)]
pub enum ConfigClientError {
    #[error("failed to build http client: {0}")]
    ClientInit(#[source] reqwest::Error),
    #[error("failed to fetch config: {0}")]
    Request(#[source] reqwest::Error),
    #[error("failed to fetch config: status {status}, body: {body}")]
    Status { status: u16, body: String },
    #[error("failed to decode config response: {0}")]
    Decode(#[source] reqwest::Error),
    #[error("headend ID mismatch: expected {expected}, got {got}")]
    HeadendMismatch { expected: String, got: String },
    #[error("no port ranges configured")]
    NoPortRangesConfigured,
}

const USER_AGENT_VALUE: &str = "SASEWaddle-Headend/1.0";
const REQUEST_TIMEOUT: Duration = Duration::from_secs(10);

/// Fetches/validates port configuration from the Manager service for one
/// headend+cluster.
pub struct ConfigClient {
    manager_url: String,
    auth_token: String,
    headend_id: String,
    cluster_id: String,
    http_client: reqwest::Client,
    token_provider: Arc<dyn TokenProvider>,
}

impl ConfigClient {
    /// Builds a client with a static-token fallback provider (mirrors
    /// `NewConfigClient`). Returns an error rather than panicking if the
    /// underlying HTTP client can't be constructed (the Go source can't
    /// fail here — `&http.Client{}` is a plain struct literal — so this
    /// is a Rust-specific, not a Go-mirroring, fallible step).
    pub fn new(
        manager_url: impl Into<String>,
        auth_token: impl Into<String>,
        headend_id: impl Into<String>,
        cluster_id: impl Into<String>,
    ) -> Result<Self, ConfigClientError> {
        let auth_token = auth_token.into();
        let http_client = reqwest::Client::builder()
            .timeout(REQUEST_TIMEOUT)
            .build()
            .map_err(ConfigClientError::ClientInit)?;

        Ok(Self {
            manager_url: manager_url.into(),
            token_provider: Arc::new(StaticTokenProvider(auth_token.clone())),
            auth_token,
            headend_id: headend_id.into(),
            cluster_id: cluster_id.into(),
            http_client,
        })
    }

    /// Installs a custom token provider (e.g. a machine-JWT client),
    /// mirroring `SetTokenProvider`.
    pub fn set_token_provider(&mut self, provider: Arc<dyn TokenProvider>) {
        self.token_provider = provider;
    }

    /// Fetches the current port configuration. On a token-provider
    /// failure, falls back to the static configured token (warning
    /// logged) rather than failing the whole request — mirrors the Go
    /// source's `FetchConfig` fallback exactly.
    #[tracing::instrument(skip(self), fields(headend_id = %self.headend_id, cluster_id = %self.cluster_id))]
    pub async fn fetch_config(&self) -> Result<PortConfig, ConfigClientError> {
        let url = format!(
            "{}/api/v1/headend/{}/ports?cluster_id={}",
            self.manager_url, self.headend_id, self.cluster_id
        );

        let token = match self.token_provider.token().await {
            Ok(t) => t,
            Err(e) => {
                tracing::warn!(error = %e, "failed to get auth token; falling back to static token");
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
            .map_err(ConfigClientError::Request)?;

        let status = resp.status();
        if status != reqwest::StatusCode::OK {
            let body = resp.text().await.unwrap_or_default();
            return Err(ConfigClientError::Status {
                status: status.as_u16(),
                body,
            });
        }

        let config: PortConfig = resp.json().await.map_err(ConfigClientError::Decode)?;
        tracing::debug!(
            tcp_ranges = %config.tcp_ranges,
            udp_ranges = %config.udp_ranges,
            "fetched port configuration"
        );
        Ok(config)
    }

    /// Validates a fetched [`PortConfig`] against this client's own
    /// `headend_id` and checks that at least one of `tcp_ranges`/
    /// `udp_ranges` is non-empty.
    ///
    /// Fix-while-porting: the Go source's `ValidateConfig` compares
    /// `TCPRanges == "" && UDPRanges == ""` with no trimming, so a
    /// whitespace-only value (`" "`) passes this check even though
    /// `parseRangeString` treats it identically to an empty string (no
    /// ranges at all) — a config that looks "configured" but parses to
    /// nothing. This port trims both fields before the emptiness check so
    /// the two validations agree.
    pub fn validate_config(&self, config: &PortConfig) -> Result<(), ConfigClientError> {
        if config.headend_id != self.headend_id {
            return Err(ConfigClientError::HeadendMismatch {
                expected: self.headend_id.clone(),
                got: config.headend_id.clone(),
            });
        }

        if config.tcp_ranges.trim().is_empty() && config.udp_ranges.trim().is_empty() {
            return Err(ConfigClientError::NoPortRangesConfigured);
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use wiremock::matchers::{header, method, path, query_param};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    fn sample_config(headend_id: &str) -> PortConfig {
        PortConfig {
            headend_id: headend_id.to_string(),
            cluster_id: "cluster-1".to_string(),
            tcp_ranges: "8000-8100".to_string(),
            udp_ranges: "9000".to_string(),
            tcp_ranges_detail: vec![],
            udp_ranges_detail: vec![],
            updated_at: "2026-01-01T00:00:00Z".to_string(),
        }
    }

    #[tokio::test]
    async fn fetch_config_success_parses_response_and_sets_headers() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/api/v1/headend/headend-1/ports"))
            .and(query_param("cluster_id", "cluster-1"))
            .and(header("authorization", "Bearer static-token"))
            .and(header("user-agent", USER_AGENT_VALUE))
            .respond_with(ResponseTemplate::new(200).set_body_json(sample_config("headend-1")))
            .mount(&server)
            .await;

        let client =
            ConfigClient::new(server.uri(), "static-token", "headend-1", "cluster-1").unwrap();
        let config = client.fetch_config().await.unwrap();
        assert_eq!(config, sample_config("headend-1"));
    }

    #[tokio::test]
    async fn fetch_config_uses_custom_token_provider() {
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
            .respond_with(ResponseTemplate::new(200).set_body_json(sample_config("headend-1")))
            .mount(&server)
            .await;

        let mut client =
            ConfigClient::new(server.uri(), "static-token", "headend-1", "cluster-1").unwrap();
        client.set_token_provider(Arc::new(Custom));
        client.fetch_config().await.unwrap();
    }

    #[tokio::test]
    async fn fetch_config_falls_back_to_static_token_when_provider_fails() {
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
            .respond_with(ResponseTemplate::new(200).set_body_json(sample_config("headend-1")))
            .mount(&server)
            .await;

        let mut client =
            ConfigClient::new(server.uri(), "static-token", "headend-1", "cluster-1").unwrap();
        client.set_token_provider(Arc::new(Failing));
        // Should still succeed by falling back to the static token.
        client.fetch_config().await.unwrap();
    }

    #[tokio::test]
    async fn fetch_config_non_200_status_is_an_error() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .respond_with(ResponseTemplate::new(500).set_body_string("boom"))
            .mount(&server)
            .await;

        let client = ConfigClient::new(server.uri(), "t", "headend-1", "cluster-1").unwrap();
        let err = client.fetch_config().await.unwrap_err();
        match err {
            ConfigClientError::Status { status, body } => {
                assert_eq!(status, 500);
                assert_eq!(body, "boom");
            }
            other => panic!("expected Status error, got {other:?}"),
        }
    }

    #[tokio::test]
    async fn fetch_config_malformed_json_is_a_decode_error() {
        let server = MockServer::start().await;
        Mock::given(method("GET"))
            .respond_with(ResponseTemplate::new(200).set_body_string("not json"))
            .mount(&server)
            .await;

        let client = ConfigClient::new(server.uri(), "t", "headend-1", "cluster-1").unwrap();
        let err = client.fetch_config().await.unwrap_err();
        assert!(matches!(err, ConfigClientError::Decode(_)));
    }

    #[tokio::test]
    async fn fetch_config_connection_failure_is_a_request_error() {
        // Port 1 on localhost: a reserved, essentially-always-closed port,
        // giving a reliable connection-refused without binding anything.
        let client =
            ConfigClient::new("http://127.0.0.1:1", "t", "headend-1", "cluster-1").unwrap();
        let err = client.fetch_config().await.unwrap_err();
        assert!(matches!(err, ConfigClientError::Request(_)));
    }

    #[test]
    fn validate_config_rejects_headend_mismatch() {
        let client =
            ConfigClient::new("http://example.invalid", "t", "headend-1", "cluster-1").unwrap();
        let err = client
            .validate_config(&sample_config("headend-2"))
            .unwrap_err();
        assert!(matches!(err, ConfigClientError::HeadendMismatch { .. }));
    }

    #[test]
    fn validate_config_rejects_empty_ranges() {
        let client =
            ConfigClient::new("http://example.invalid", "t", "headend-1", "cluster-1").unwrap();
        let mut config = sample_config("headend-1");
        config.tcp_ranges = String::new();
        config.udp_ranges = String::new();
        assert!(matches!(
            client.validate_config(&config).unwrap_err(),
            ConfigClientError::NoPortRangesConfigured
        ));
    }

    /// Fix-while-porting regression: whitespace-only range fields must be
    /// treated as empty, unlike the Go source's unconditioned `== ""`
    /// check (see [`ConfigClient::validate_config`]'s doc).
    #[test]
    fn validate_config_rejects_whitespace_only_ranges() {
        let client =
            ConfigClient::new("http://example.invalid", "t", "headend-1", "cluster-1").unwrap();
        let mut config = sample_config("headend-1");
        config.tcp_ranges = "   ".to_string();
        config.udp_ranges = "\t".to_string();
        assert!(matches!(
            client.validate_config(&config).unwrap_err(),
            ConfigClientError::NoPortRangesConfigured
        ));
    }

    #[test]
    fn validate_config_accepts_one_non_empty_range_field() {
        let client =
            ConfigClient::new("http://example.invalid", "t", "headend-1", "cluster-1").unwrap();
        let mut config = sample_config("headend-1");
        config.udp_ranges = String::new();
        assert!(client.validate_config(&config).is_ok());
    }
}
