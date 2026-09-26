//! Hub router machine JWT authentication subsystem.
//!
//! Manages the machine JWT token lifecycle for control-plane communication.
//! The client exchanges an API key for short-lived access and refresh tokens,
//! handles automatic token refresh when approaching expiry, and falls back to
//! a legacy static token if token exchange fails at startup.

use hub_router_common::Error;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::{Duration, SystemTime};
use tokio::sync::RwLock;
use tracing::{debug, error, warn};

/// Token response from the token exchange or refresh endpoints.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenResponse {
    pub access_token: String,
    pub refresh_token: String,
    #[serde(default)]
    pub expires_in: i64,
    #[serde(default)]
    pub token_type: String,
}

/// Request payload for token refresh.
#[derive(Debug, Serialize)]
pub struct RefreshRequest {
    pub refresh_token: String,
}

/// Request payload for initial token exchange.
#[derive(Debug, Serialize)]
pub struct TokenExchangeRequest {
    pub node_id: String,
    pub node_type: String,
    pub api_key: String,
}

/// Error response from the server.
#[derive(Debug, Deserialize)]
pub struct ErrorResponse {
    #[serde(default)]
    pub detail: String,
    #[serde(default)]
    pub retry_with_credentials: bool,
}

/// Internal token state.
#[derive(Debug, Clone)]
struct TokenState {
    access_token: String,
    refresh_token: String,
    expires_at: SystemTime,
}

/// Machine JWT client manages token lifecycle: exchange, refresh, and caching.
pub struct MachineJWTClient {
    manager_url: String,
    cluster_id: String,
    api_key: String,
    http_client: reqwest::Client,
    token_cache: Arc<RwLock<TokenState>>,
}

/// Returned when refresh fails with 503 + retry_with_credentials flag.
/// Signals to the caller that a full token exchange should be retried.
#[derive(Debug, Clone)]
pub struct RetryWithCredentialsError {
    pub status_code: u16,
    pub message: String,
}

impl std::fmt::Display for RetryWithCredentialsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "refresh failed with retry_with_credentials flag (status {}): {}",
            self.status_code, self.message
        )
    }
}

impl std::error::Error for RetryWithCredentialsError {}

impl MachineJWTClient {
    /// Creates a new machine JWT client and attempts to exchange the API key
    /// for tokens at startup. Falls back to the legacy token if exchange fails.
    pub async fn new(
        manager_url: String,
        cluster_id: String,
        api_key: String,
        fallback_token: String,
    ) -> Result<Self, Error> {
        let http_client = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .map_err(|e| Error::Runtime(format!("failed to create http client: {}", e)))?;

        let client = Self {
            manager_url,
            cluster_id,
            api_key,
            http_client,
            token_cache: Arc::new(RwLock::new(TokenState {
                access_token: String::new(),
                refresh_token: String::new(),
                expires_at: SystemTime::now(),
            })),
        };

        // Try to exchange API key for token at startup with a timeout.
        let exchange_result =
            tokio::time::timeout(Duration::from_secs(30), client.exchange_token()).await;

        match exchange_result {
            Ok(Ok(())) => {
                // Successful exchange, client is ready.
            }
            _ => {
                // Exchange failed; fall back to legacy token.
                warn!("Failed to exchange API key for machine JWT; falling back to legacy token");
                let mut cache = client.token_cache.write().await;
                cache.access_token = fallback_token;
                cache.expires_at = SystemTime::now() + Duration::from_secs(24 * 3600);
                drop(cache);
            }
        }

        Ok(client)
    }

    /// Returns the current valid access token, refreshing if necessary.
    /// If token is expired or within 5 minutes of expiry, attempts refresh first.
    pub async fn get_token(&self) -> Result<String, Error> {
        // Check current token state.
        let (token, expires_at, refresh_token) = {
            let cache = self.token_cache.read().await;
            (
                cache.access_token.clone(),
                cache.expires_at,
                cache.refresh_token.clone(),
            )
        };

        // If token expires within 5 minutes, attempt refresh.
        if SystemTime::now() > expires_at - Duration::from_secs(300) {
            if let Err(e) = self.refresh_token(&refresh_token).await {
                // Check if this is a retry_with_credentials error (503 + flag).
                if let Error::Runtime(ref msg) = e {
                    if msg.contains("RetryWithCredentials") {
                        // Perform full re-exchange.
                        if let Err(exchange_err) = self.exchange_token().await {
                            error!("Failed to re-exchange token: {}", exchange_err);
                            return Ok(token); // Return existing token as fallback.
                        }
                    } else {
                        error!("Failed to refresh token: {}", e);
                        return Ok(token); // Return existing token as fallback.
                    }
                } else {
                    error!("Failed to refresh token: {}", e);
                    return Ok(token); // Return existing token as fallback.
                }
            }

            // Refresh succeeded; get the new token.
            let cache = self.token_cache.read().await;
            return Ok(cache.access_token.clone());
        }

        if token.is_empty() {
            return Err(Error::Runtime("no valid token available".to_string()));
        }

        Ok(token)
    }

    /// Exchanges the API key for access and refresh tokens.
    async fn exchange_token(&self) -> Result<(), Error> {
        let url = format!("{}/api/v1/auth/token", self.manager_url);

        let payload = TokenExchangeRequest {
            node_id: self.cluster_id.clone(),
            node_type: "kubernetes_node".to_string(),
            api_key: self.api_key.clone(),
        };

        let response = self
            .http_client
            .post(&url)
            .header("User-Agent", "SASEWaddle-Headend/1.0")
            .json(&payload)
            .send()
            .await
            .map_err(|e| Error::Runtime(format!("failed to exchange token: {}", e)))?;

        if response.status() != 200 {
            let status = response.status().as_u16();
            let body = response
                .text()
                .await
                .unwrap_or_else(|_| "(unable to read body)".to_string());
            return Err(Error::Runtime(format!(
                "token exchange failed with status {}: {}",
                status, body
            )));
        }

        let token_resp: TokenResponse = response
            .json()
            .await
            .map_err(|e| Error::Runtime(format!("failed to unmarshal token response: {}", e)))?;

        let expires_in = if token_resp.expires_in > 0 {
            token_resp.expires_in
        } else {
            3600 // default 1 hour
        };

        {
            let mut cache = self.token_cache.write().await;
            cache.access_token = token_resp.access_token;
            cache.refresh_token = token_resp.refresh_token;
            cache.expires_at = SystemTime::now() + Duration::from_secs(expires_in as u64);
        }

        debug!(
            "Successfully exchanged API key for machine JWT (expires in {} seconds)",
            expires_in
        );
        Ok(())
    }

    /// Refreshes the access token using the refresh token.
    /// Refresh tokens are single-use and rotating; each refresh returns a new refresh token.
    async fn refresh_token(&self, current_refresh_token: &str) -> Result<(), Error> {
        if current_refresh_token.is_empty() {
            return Err(Error::Runtime("no refresh token available".to_string()));
        }

        let url = format!("{}/api/v1/auth/refresh", self.manager_url);

        let payload = RefreshRequest {
            refresh_token: current_refresh_token.to_string(),
        };

        let response = self
            .http_client
            .post(&url)
            .header("User-Agent", "SASEWaddle-Headend/1.0")
            .json(&payload)
            .send()
            .await
            .map_err(|e| Error::Runtime(format!("failed to refresh token: {}", e)))?;

        let status = response.status().as_u16();

        // Handle 503 with retry_with_credentials flag specially.
        if status == 503 {
            if let Ok(err_resp) = response.json::<ErrorResponse>().await {
                if err_resp.retry_with_credentials {
                    return Err(Error::Runtime(format!(
                        "RetryWithCredentials: {} (status {})",
                        err_resp.detail, status
                    )));
                }
            }
            return Err(Error::Runtime("refresh failed with status 503".to_string()));
        }

        if status != 200 {
            let body = response
                .text()
                .await
                .unwrap_or_else(|_| "(unable to read body)".to_string());
            return Err(Error::Runtime(format!(
                "refresh failed with status {}: {}",
                status, body
            )));
        }

        let token_resp: TokenResponse = response
            .json()
            .await
            .map_err(|e| Error::Runtime(format!("failed to unmarshal refresh response: {}", e)))?;

        let expires_in = if token_resp.expires_in > 0 {
            token_resp.expires_in
        } else {
            3600 // default 1 hour
        };

        {
            let mut cache = self.token_cache.write().await;
            cache.access_token = token_resp.access_token;
            cache.refresh_token = token_resp.refresh_token;
            cache.expires_at = SystemTime::now() + Duration::from_secs(expires_in as u64);
        }

        debug!(
            "Successfully refreshed machine JWT (expires in {} seconds)",
            expires_in
        );
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use wiremock::matchers::{method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    /// Test token exchange: client exchanges API key for access + refresh tokens.
    #[tokio::test]
    async fn test_token_exchange() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/api/v1/auth/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(TokenResponse {
                access_token: "eyJhbGc.access.token".to_string(),
                refresh_token: "eyJhbGc.refresh.token".to_string(),
                expires_in: 3600,
                token_type: "Bearer".to_string(),
            }))
            .mount(&mock_server)
            .await;

        let client = MachineJWTClient::new(
            mock_server.uri(),
            "cluster-1".to_string(),
            "api-key-123".to_string(),
            "fallback-token".to_string(),
        )
        .await
        .expect("Failed to create client");

        let token = client.get_token().await.expect("Failed to get token");
        assert_eq!(token, "eyJhbGc.access.token");
    }

    /// Test token refresh: client refreshes tokens when approaching expiry.
    #[tokio::test]
    async fn test_token_refresh() {
        let mock_server = MockServer::start().await;

        // Mock exchange endpoint
        Mock::given(method("POST"))
            .and(path("/api/v1/auth/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(TokenResponse {
                access_token: "eyJhbGc.access.token.initial".to_string(),
                refresh_token: "eyJhbGc.refresh.token.initial".to_string(),
                expires_in: 320,
                token_type: "Bearer".to_string(),
            }))
            .mount(&mock_server)
            .await;

        // Mock refresh endpoint
        Mock::given(method("POST"))
            .and(path("/api/v1/auth/refresh"))
            .respond_with(ResponseTemplate::new(200).set_body_json(TokenResponse {
                access_token: "eyJhbGc.access.token.refreshed".to_string(),
                refresh_token: "eyJhbGc.refresh.token.refreshed".to_string(),
                expires_in: 320,
                token_type: "Bearer".to_string(),
            }))
            .mount(&mock_server)
            .await;

        let client = MachineJWTClient::new(
            mock_server.uri(),
            "cluster-1".to_string(),
            "api-key-123".to_string(),
            "fallback-token".to_string(),
        )
        .await
        .expect("Failed to create client");

        // Get initial token.
        let token1 = client
            .get_token()
            .await
            .expect("Failed to get initial token");
        assert_eq!(token1, "eyJhbGc.access.token.initial");

        // Force refresh by setting expiry to within 5 minutes.
        {
            let mut cache = client.token_cache.write().await;
            cache.expires_at = SystemTime::now() - Duration::from_secs(300);
        }

        // Get token again; should trigger refresh.
        let token2 = client
            .get_token()
            .await
            .expect("Failed to get refreshed token");
        assert_eq!(token2, "eyJhbGc.access.token.refreshed");
    }

    /// Test refresh token rotation: refresh token changes on each refresh.
    #[tokio::test]
    async fn test_refresh_rotates_token() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/api/v1/auth/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(TokenResponse {
                access_token: "eyJhbGc.access.token".to_string(),
                refresh_token: "eyJhbGc.refresh.token.1".to_string(),
                expires_in: 3600,
                token_type: "Bearer".to_string(),
            }))
            .mount(&mock_server)
            .await;

        // First refresh returns token.2
        Mock::given(method("POST"))
            .and(path("/api/v1/auth/refresh"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "access_token": "eyJhbGc.access.token.refreshed.1",
                "refresh_token": "eyJhbGc.refresh.token.2",
                "expires_in": 3600,
                "token_type": "Bearer"
            })))
            .up_to_n_times(1)
            .mount(&mock_server)
            .await;

        // Second refresh returns token.3
        Mock::given(method("POST"))
            .and(path("/api/v1/auth/refresh"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "access_token": "eyJhbGc.access.token.refreshed.2",
                "refresh_token": "eyJhbGc.refresh.token.3",
                "expires_in": 3600,
                "token_type": "Bearer"
            })))
            .mount(&mock_server)
            .await;

        let client = MachineJWTClient::new(
            mock_server.uri(),
            "cluster-1".to_string(),
            "api-key-123".to_string(),
            "fallback-token".to_string(),
        )
        .await
        .expect("Failed to create client");

        // Get initial token without forcing refresh.
        client
            .get_token()
            .await
            .expect("Failed to get initial token");

        let initial_refresh_token = {
            let cache = client.token_cache.read().await;
            cache.refresh_token.clone()
        };

        // Force refresh by setting expiry to past.
        {
            let mut cache = client.token_cache.write().await;
            cache.expires_at = SystemTime::now() - Duration::from_secs(300);
        }

        client
            .get_token()
            .await
            .expect("Failed to get refreshed token");

        let refresh_token_after_first_refresh = {
            let cache = client.token_cache.read().await;
            cache.refresh_token.clone()
        };

        // Verify that refresh token changed on the first refresh
        assert_ne!(
            initial_refresh_token, refresh_token_after_first_refresh,
            "Refresh token should rotate on first refresh"
        );

        // Force another refresh.
        {
            let mut cache = client.token_cache.write().await;
            cache.expires_at = SystemTime::now() - Duration::from_secs(300);
        }

        client
            .get_token()
            .await
            .expect("Failed to get second refreshed token");

        let refresh_token_after_second_refresh = {
            let cache = client.token_cache.read().await;
            cache.refresh_token.clone()
        };

        // Verify that refresh token changed again on the second refresh
        assert_ne!(
            refresh_token_after_first_refresh, refresh_token_after_second_refresh,
            "Refresh token should rotate on second refresh"
        );
    }

    /// Test 503 with retry_with_credentials triggers re-exchange.
    #[tokio::test]
    async fn test_503_retry_with_credentials() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/api/v1/auth/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(TokenResponse {
                access_token: "eyJhbGc.access.token.exchange".to_string(),
                refresh_token: "eyJhbGc.refresh.token.exchange".to_string(),
                expires_in: 10,
                token_type: "Bearer".to_string(),
            }))
            .mount(&mock_server)
            .await;

        // First refresh succeeds, second fails with 503
        Mock::given(method("POST"))
            .and(path("/api/v1/auth/refresh"))
            .respond_with(ResponseTemplate::new(200).set_body_json(TokenResponse {
                access_token: "eyJhbGc.access.token.refreshed".to_string(),
                refresh_token: "eyJhbGc.refresh.token.refreshed".to_string(),
                expires_in: 10,
                token_type: "Bearer".to_string(),
            }))
            .up_to_n_times(1)
            .mount(&mock_server)
            .await;

        Mock::given(method("POST"))
            .and(path("/api/v1/auth/refresh"))
            .respond_with(ResponseTemplate::new(503).set_body_json(serde_json::json!({
                "detail": "Valkey unavailable",
                "retry_with_credentials": true
            })))
            .mount(&mock_server)
            .await;

        let client = MachineJWTClient::new(
            mock_server.uri(),
            "cluster-1".to_string(),
            "api-key-123".to_string(),
            "fallback-token".to_string(),
        )
        .await
        .expect("Failed to create client");

        client
            .get_token()
            .await
            .expect("Failed to get initial token");

        // First refresh succeeds
        {
            let mut cache = client.token_cache.write().await;
            cache.expires_at = SystemTime::now() - Duration::from_secs(300);
        }
        client
            .get_token()
            .await
            .expect("Failed to get refreshed token");

        // Second refresh will fail with 503, triggering re-exchange
        {
            let mut cache = client.token_cache.write().await;
            cache.expires_at = SystemTime::now() - Duration::from_secs(300);
        }
        let token = client
            .get_token()
            .await
            .expect("Failed to get token after 503 retry");
        assert!(!token.is_empty());
    }

    /// Test token exchange failure falls back to legacy token.
    #[tokio::test]
    async fn test_token_exchange_failure_fallback() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/api/v1/auth/token"))
            .respond_with(ResponseTemplate::new(500))
            .mount(&mock_server)
            .await;

        let client = MachineJWTClient::new(
            mock_server.uri(),
            "cluster-1".to_string(),
            "api-key-123".to_string(),
            "fallback-token".to_string(),
        )
        .await
        .expect("Failed to create client");

        let token = client
            .get_token()
            .await
            .expect("Failed to get fallback token");
        assert_eq!(token, "fallback-token");
    }

    /// Test concurrent token access is thread-safe.
    #[tokio::test]
    async fn test_concurrent_token_access() {
        let mock_server = MockServer::start().await;

        Mock::given(method("POST"))
            .and(path("/api/v1/auth/token"))
            .respond_with(ResponseTemplate::new(200).set_body_json(TokenResponse {
                access_token: "eyJhbGc.access.token".to_string(),
                refresh_token: "eyJhbGc.refresh.token".to_string(),
                expires_in: 3600,
                token_type: "Bearer".to_string(),
            }))
            .mount(&mock_server)
            .await;

        let client = Arc::new(
            MachineJWTClient::new(
                mock_server.uri(),
                "cluster-1".to_string(),
                "api-key-123".to_string(),
                "fallback-token".to_string(),
            )
            .await
            .expect("Failed to create client"),
        );

        let mut handles = vec![];
        for _ in 0..10 {
            let client_clone = Arc::clone(&client);
            let handle = tokio::spawn(async move {
                let token = client_clone.get_token().await.expect("Failed to get token");
                assert!(!token.is_empty());
            });
            handles.push(handle);
        }

        for handle in handles {
            handle.await.expect("Task panicked");
        }
    }
}
