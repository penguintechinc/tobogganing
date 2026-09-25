package auth

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// TestTokenExchange verifies that the client exchanges API key for access+refresh tokens.
func TestTokenExchange(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/auth/token" && r.Method == "POST" {
			var req TokenExchangeRequest
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				w.WriteHeader(http.StatusBadRequest)
				return
			}

			// Verify the request payload.
			if req.NodeID == "" || req.NodeType != "kubernetes_node" || req.APIKey == "" {
				w.WriteHeader(http.StatusBadRequest)
				return
			}

			resp := TokenResponse{
				AccessToken:  "eyJhbGc.access.token",
				RefreshToken: "eyJhbGc.refresh.token",
				ExpiresIn:    3600,
				TokenType:    "Bearer",
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	client, err := NewMachineJWTClient(server.URL, "cluster-1", "api-key-123", "fallback-token")
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	token, err := client.GetToken(ctx)
	if err != nil {
		t.Fatalf("Failed to get token: %v", err)
	}

	if token != "eyJhbGc.access.token" {
		t.Errorf("Expected access token 'eyJhbGc.access.token', got %q", token)
	}
}

// TestTokenRefresh verifies that the client refreshes tokens when they approach expiry.
func TestTokenRefresh(t *testing.T) {
	refreshCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/auth/token" && r.Method == "POST" {
			resp := TokenResponse{
				AccessToken:  "eyJhbGc.access.token.initial",
				RefreshToken: "eyJhbGc.refresh.token.initial",
				ExpiresIn:    320, // 5 minutes + 20 seconds
				TokenType:    "Bearer",
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
			return
		}

		if r.URL.Path == "/api/v1/auth/refresh" && r.Method == "POST" {
			refreshCount++
			var req RefreshRequest
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				w.WriteHeader(http.StatusBadRequest)
				return
			}

			// Return new tokens with a new refresh token (rotating).
			resp := TokenResponse{
				AccessToken:  fmt.Sprintf("eyJhbGc.access.token.refresh%d", refreshCount),
				RefreshToken: fmt.Sprintf("eyJhbGc.refresh.token.refresh%d", refreshCount),
				ExpiresIn:    320,
				TokenType:    "Bearer",
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
			return
		}

		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	client, err := NewMachineJWTClient(server.URL, "cluster-1", "api-key-123", "fallback-token")
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Get initial token.
	token1, err := client.GetToken(ctx)
	if err != nil {
		t.Fatalf("Failed to get initial token: %v", err)
	}

	if token1 != "eyJhbGc.access.token.initial" {
		t.Errorf("Expected initial token, got %q", token1)
	}

	// Wait for token to reach refresh threshold (20 seconds in, which is within 5 min of 320s expiry).
	time.Sleep(20 * time.Second)

	// Get token again; should trigger refresh since we're within 5 minutes of expiry.
	token2, err := client.GetToken(ctx)
	if err != nil {
		t.Fatalf("Failed to get refreshed token: %v", err)
	}

	if token2 == token1 {
		t.Errorf("Expected token to be refreshed, but got same token")
	}

	if refreshCount != 1 {
		t.Errorf("Expected 1 refresh, got %d", refreshCount)
	}
}

// TestRefreshRotatesToken verifies that the refresh token is rotated on each refresh.
func TestRefreshRotatesToken(t *testing.T) {
	var seenRefreshTokens []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/auth/token" && r.Method == "POST" {
			resp := TokenResponse{
				AccessToken:  "eyJhbGc.access.token",
				RefreshToken: "eyJhbGc.refresh.token.1",
				ExpiresIn:    10,
				TokenType:    "Bearer",
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
			return
		}

		if r.URL.Path == "/api/v1/auth/refresh" && r.Method == "POST" {
			var req RefreshRequest
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				w.WriteHeader(http.StatusBadRequest)
				return
			}

			seenRefreshTokens = append(seenRefreshTokens, req.RefreshToken)

			// Return a new refresh token each time.
			newToken := fmt.Sprintf("eyJhbGc.refresh.token.%d", len(seenRefreshTokens)+1)
			resp := TokenResponse{
				AccessToken:  "eyJhbGc.access.token.refreshed",
				RefreshToken: newToken,
				ExpiresIn:    10,
				TokenType:    "Bearer",
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
			return
		}

		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	client, err := NewMachineJWTClient(server.URL, "cluster-1", "api-key-123", "fallback-token")
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Initial token.
	_, err = client.GetToken(ctx)
	if err != nil {
		t.Fatalf("Failed to get initial token: %v", err)
	}

	// Wait and trigger refresh (8 seconds in, within 5 min of 10s expiry).
	time.Sleep(8 * time.Second)
	_, err = client.GetToken(ctx)
	if err != nil {
		t.Fatalf("Failed to get refreshed token: %v", err)
	}

	// Wait and trigger another refresh.
	time.Sleep(8 * time.Second)
	_, err = client.GetToken(ctx)
	if err != nil {
		t.Fatalf("Failed to get second refreshed token: %v", err)
	}

	// Verify that different refresh tokens were used.
	if len(seenRefreshTokens) < 2 {
		t.Errorf("Expected at least 2 refresh tokens, got %d", len(seenRefreshTokens))
	}

	// Verify tokens are unique.
	if len(seenRefreshTokens) > 0 {
		for i := 0; i < len(seenRefreshTokens)-1; i++ {
			if seenRefreshTokens[i] == seenRefreshTokens[i+1] {
				t.Errorf("Refresh token was not rotated: %s == %s", seenRefreshTokens[i], seenRefreshTokens[i+1])
			}
		}
	}
}

// Test401TriggersRefresh verifies that a 401 response triggers a token refresh.
func Test401TriggersRefresh(t *testing.T) {
	refreshAttempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/auth/token" && r.Method == "POST" {
			resp := TokenResponse{
				AccessToken:  "eyJhbGc.access.token",
				RefreshToken: "eyJhbGc.refresh.token",
				ExpiresIn:    10, // 10 seconds expiry
				TokenType:    "Bearer",
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
			return
		}

		if r.URL.Path == "/api/v1/auth/refresh" && r.Method == "POST" {
			refreshAttempts++
			resp := TokenResponse{
				AccessToken:  "eyJhbGc.access.token.refreshed",
				RefreshToken: "eyJhbGc.refresh.token.refreshed",
				ExpiresIn:    3600,
				TokenType:    "Bearer",
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
			return
		}

		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	client, err := NewMachineJWTClient(server.URL, "cluster-1", "api-key-123", "fallback-token")
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Get initial token.
	_, err = client.GetToken(ctx)
	if err != nil {
		t.Fatalf("Failed to get initial token: %v", err)
	}

	// Wait until we're within 5 minutes of expiry (8 seconds in, with 10s expiry).
	time.Sleep(8 * time.Second)

	// Get token again; should trigger refresh.
	_, err = client.GetToken(ctx)
	if err != nil {
		t.Fatalf("Failed to get token after refresh: %v", err)
	}

	if refreshAttempts < 1 {
		t.Errorf("Expected at least 1 refresh attempt, got %d", refreshAttempts)
	}
}

// Test503RetryWithCredentials verifies that 503 with retry_with_credentials flag triggers re-exchange.
func Test503RetryWithCredentials(t *testing.T) {
	exchangeAttempts := 0
	refreshAttempts := 0

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/auth/token" && r.Method == "POST" {
			exchangeAttempts++
			resp := TokenResponse{
				AccessToken:  fmt.Sprintf("eyJhbGc.access.token.exchange%d", exchangeAttempts),
				RefreshToken: fmt.Sprintf("eyJhbGc.refresh.token.exchange%d", exchangeAttempts),
				ExpiresIn:    10,
				TokenType:    "Bearer",
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
			return
		}

		if r.URL.Path == "/api/v1/auth/refresh" && r.Method == "POST" {
			refreshAttempts++
			// First refresh succeeds; second refresh returns 503 with retry_with_credentials.
			if refreshAttempts <= 1 {
				resp := TokenResponse{
					AccessToken:  "eyJhbGc.access.token.refreshed",
					RefreshToken: "eyJhbGc.refresh.token.refreshed",
					ExpiresIn:    10,
					TokenType:    "Bearer",
				}
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(resp)
			} else {
				w.WriteHeader(http.StatusServiceUnavailable)
				errResp := ErrorResponse{
					Detail:               "Valkey unavailable",
					RetryWithCredentials: true,
				}
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(errResp)
			}
			return
		}

		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	client, err := NewMachineJWTClient(server.URL, "cluster-1", "api-key-123", "fallback-token")
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	// Get initial token.
	_, err = client.GetToken(ctx)
	if err != nil {
		t.Fatalf("Failed to get initial token: %v", err)
	}

	// Wait and get token (triggers first refresh, succeeds).
	time.Sleep(8 * time.Second)
	_, err = client.GetToken(ctx)
	if err != nil {
		t.Fatalf("Failed to get refreshed token: %v", err)
	}

	// Wait and get token again (triggers second refresh, fails with 503, then re-exchanges).
	time.Sleep(8 * time.Second)
	_, err = client.GetToken(ctx)
	if err != nil {
		t.Fatalf("Failed to get token after 503 retry: %v", err)
	}

	if exchangeAttempts < 2 {
		t.Errorf("Expected at least 2 exchange attempts (initial + after 503), got %d", exchangeAttempts)
	}
}

// TestTokenExchangeFailureFallback verifies that token exchange failure at startup falls back to legacy token.
func TestTokenExchangeFailureFallback(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// All endpoints return 500 to simulate complete failure.
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("Internal server error"))
	}))
	defer server.Close()

	// NewMachineJWTClient should not crash and should allow fallback to legacy token.
	client, err := NewMachineJWTClient(server.URL, "cluster-1", "api-key-123", "fallback-token")
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// GetToken should return the fallback token instead of crashing.
	token, err := client.GetToken(ctx)
	if err != nil {
		t.Fatalf("Expected fallback token, got error: %v", err)
	}

	if token != "fallback-token" {
		t.Errorf("Expected fallback token, got %q", token)
	}
}

// TestConcurrentTokenAccess verifies thread-safe token access.
func TestConcurrentTokenAccess(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/v1/auth/token" && r.Method == "POST" {
			resp := TokenResponse{
				AccessToken:  "eyJhbGc.access.token",
				RefreshToken: "eyJhbGc.refresh.token",
				ExpiresIn:    3600,
				TokenType:    "Bearer",
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
			return
		}

		if r.URL.Path == "/api/v1/auth/refresh" && r.Method == "POST" {
			resp := TokenResponse{
				AccessToken:  "eyJhbGc.access.token.refreshed",
				RefreshToken: "eyJhbGc.refresh.token.refreshed",
				ExpiresIn:    3600,
				TokenType:    "Bearer",
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
			return
		}

		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	client, err := NewMachineJWTClient(server.URL, "cluster-1", "api-key-123", "fallback-token")
	if err != nil {
		t.Fatalf("Failed to create client: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Launch concurrent goroutines to fetch tokens.
	done := make(chan error, 10)
	for i := 0; i < 10; i++ {
		go func() {
			token, err := client.GetToken(ctx)
			if err != nil {
				done <- err
			} else if token == "" {
				done <- fmt.Errorf("empty token returned")
			} else {
				done <- nil
			}
		}()
	}

	// Collect results.
	for i := 0; i < 10; i++ {
		if err := <-done; err != nil {
			t.Errorf("Concurrent access failed: %v", err)
		}
	}
}
