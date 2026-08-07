// Package auth implements authentication mechanisms for the SASEWaddle headend.
//
// The machine JWT client exchanges the cluster API key for a machine-JWT token
// and handles token refresh, expiration, and fallback scenarios. All credentials
// are masked in logs to prevent accidental exposure.
package auth

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"

	log "github.com/sirupsen/logrus"
)

// TokenResponse represents the response from the token exchange endpoint.
type TokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int    `json:"expires_in,omitempty"`
	TokenType    string `json:"token_type,omitempty"`
}

// RefreshRequest is the payload sent to the refresh endpoint.
type RefreshRequest struct {
	RefreshToken string `json:"refresh_token"`
}

// TokenExchangeRequest is the payload sent to the token exchange endpoint.
type TokenExchangeRequest struct {
	NodeID   string `json:"node_id"`
	NodeType string `json:"node_type"`
	APIKey   string `json:"api_key"`
}

// ErrorResponse is a generic error response from the brain API.
type ErrorResponse struct {
	Detail             string `json:"detail,omitempty"`
	RetryWithCredentials bool `json:"retry_with_credentials,omitempty"`
}

// MachineJWTClient manages the machine JWT token lifecycle.
type MachineJWTClient struct {
	managerURL    string
	clusterID     string
	apiKey        string
	httpClient    *http.Client
	tokenCache    *tokenState
	cacheMutex    sync.RWMutex
	fallbackToken string // legacy static token for fallback
}

// tokenState holds the current access and refresh tokens with expiry.
type tokenState struct {
	AccessToken  string
	RefreshToken string
	ExpiresAt    time.Time
}

// NewMachineJWTClient creates a new machine JWT client with fallback to a legacy static token.
// If token exchange fails at startup, the client will use the fallback token and log a warning.
func NewMachineJWTClient(managerURL, clusterID, apiKey, fallbackToken string) (*MachineJWTClient, error) {
	client := &MachineJWTClient{
		managerURL:    managerURL,
		clusterID:     clusterID,
		apiKey:        apiKey,
		fallbackToken: fallbackToken,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		tokenCache: &tokenState{},
	}

	// Try to exchange the API key for a token at startup.
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err := client.exchangeToken(ctx); err != nil {
		// Fall back to legacy token if exchange fails.
		log.Warnf("Failed to exchange API key for machine JWT: %v; falling back to legacy token", err)
		client.cacheMutex.Lock()
		client.tokenCache.AccessToken = fallbackToken
		client.tokenCache.ExpiresAt = time.Now().Add(24 * time.Hour) // Fallback token validity period
		client.cacheMutex.Unlock()
		// Continue without crashing so the headend can still operate with legacy fallback.
	}

	return client, nil
}

// GetToken returns the current valid access token.
// If the token has expired or is close to expiry, it attempts to refresh it first.
func (c *MachineJWTClient) GetToken(ctx context.Context) (string, error) {
	c.cacheMutex.RLock()
	token := c.tokenCache.AccessToken
	expiresAt := c.tokenCache.ExpiresAt
	refreshToken := c.tokenCache.RefreshToken
	c.cacheMutex.RUnlock()

	// Check if token is expired or will expire within 5 minutes.
	if time.Now().After(expiresAt.Add(-5 * time.Minute)) {
		// Token is expiring soon; try to refresh.
		if err := c.refreshToken(ctx, refreshToken); err != nil {
			// If refresh fails with 503 and retry_with_credentials flag, do full re-exchange.
			if isRetryWithCredentialsError(err) {
				if err := c.exchangeToken(ctx); err != nil {
					log.Errorf("Failed to re-exchange token: %v", err)
					// Return the existing token as fallback; caller will retry.
					return token, err
				}
			} else {
				log.Errorf("Failed to refresh token: %v", err)
				return token, err
			}
		}
		// Refresh succeeded; get the new token.
		c.cacheMutex.RLock()
		token = c.tokenCache.AccessToken
		c.cacheMutex.RUnlock()
	}

	if token == "" {
		return "", fmt.Errorf("no valid token available")
	}

	return token, nil
}

// exchangeToken performs the initial token exchange using the API key.
func (c *MachineJWTClient) exchangeToken(ctx context.Context) error {
	url := c.managerURL + "/api/v1/auth/token"

	payload := TokenExchangeRequest{
		NodeID:   c.clusterID,
		NodeType: "kubernetes_node",
		APIKey:   c.apiKey,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal token exchange request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("failed to create token exchange request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "SASEWaddle-Headend/1.0")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to exchange token: %w", err)
	}
	defer func() {
		if err := resp.Body.Close(); err != nil {
			log.Warnf("Failed to close response body: %v", err)
		}
	}()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read token exchange response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("token exchange failed with status %d: %s", resp.StatusCode, string(respBody))
	}

	var tokenResp TokenResponse
	if err := json.Unmarshal(respBody, &tokenResp); err != nil {
		return fmt.Errorf("failed to unmarshal token response: %w", err)
	}

	// Store the tokens with expiry calculated from expires_in (default to 1 hour if not provided).
	expiresIn := 3600 // default 1 hour
	if tokenResp.ExpiresIn > 0 {
		expiresIn = tokenResp.ExpiresIn
	}

	c.cacheMutex.Lock()
	c.tokenCache.AccessToken = tokenResp.AccessToken
	c.tokenCache.RefreshToken = tokenResp.RefreshToken
	c.tokenCache.ExpiresAt = time.Now().Add(time.Duration(expiresIn) * time.Second)
	c.cacheMutex.Unlock()

	log.Infof("Successfully exchanged API key for machine JWT (expires in %d seconds)", expiresIn)
	return nil
}

// refreshToken attempts to refresh the access token using the refresh token.
// Refresh tokens are single-use and rotating; each refresh response contains a new refresh token.
func (c *MachineJWTClient) refreshToken(ctx context.Context, currentRefreshToken string) error {
	if currentRefreshToken == "" {
		return fmt.Errorf("no refresh token available")
	}

	url := c.managerURL + "/api/v1/auth/refresh"

	payload := RefreshRequest{
		RefreshToken: currentRefreshToken,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal refresh request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("failed to create refresh request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "SASEWaddle-Headend/1.0")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to refresh token: %w", err)
	}
	defer func() {
		if err := resp.Body.Close(); err != nil {
			log.Warnf("Failed to close response body: %v", err)
		}
	}()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read refresh response: %w", err)
	}

	// Check for 503 with retry_with_credentials flag (fail-closed scenario).
	if resp.StatusCode == http.StatusServiceUnavailable {
		var errResp ErrorResponse
		if err := json.Unmarshal(respBody, &errResp); err == nil && errResp.RetryWithCredentials {
			return &RetryWithCredentialsError{
				StatusCode: resp.StatusCode,
				Message:    errResp.Detail,
			}
		}
		return fmt.Errorf("refresh failed with status %d: %s", resp.StatusCode, string(respBody))
	}

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("refresh failed with status %d: %s", resp.StatusCode, string(respBody))
	}

	var tokenResp TokenResponse
	if err := json.Unmarshal(respBody, &tokenResp); err != nil {
		return fmt.Errorf("failed to unmarshal refresh response: %w", err)
	}

	// Update tokens with new access and refresh tokens (refresh token is rotated).
	expiresIn := 3600 // default 1 hour
	if tokenResp.ExpiresIn > 0 {
		expiresIn = tokenResp.ExpiresIn
	}

	c.cacheMutex.Lock()
	c.tokenCache.AccessToken = tokenResp.AccessToken
	c.tokenCache.RefreshToken = tokenResp.RefreshToken // Store the new rotating refresh token
	c.tokenCache.ExpiresAt = time.Now().Add(time.Duration(expiresIn) * time.Second)
	c.cacheMutex.Unlock()

	log.Debugf("Successfully refreshed machine JWT (expires in %d seconds)", expiresIn)
	return nil
}

// isRetryWithCredentialsError checks if an error is a RetryWithCredentialsError.
func isRetryWithCredentialsError(err error) bool {
	_, ok := err.(*RetryWithCredentialsError)
	return ok
}

// RetryWithCredentialsError is returned when the brain's Valkey is down (fail-closed).
// The caller should re-authenticate with the API key.
type RetryWithCredentialsError struct {
	StatusCode int
	Message    string
}

func (e *RetryWithCredentialsError) Error() string {
	return fmt.Sprintf("refresh failed with retry_with_credentials flag (status %d): %s", e.StatusCode, e.Message)
}
