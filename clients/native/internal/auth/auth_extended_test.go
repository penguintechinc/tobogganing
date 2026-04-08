package auth

import (
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"
)

// Additional tests extending auth_test.go

func TestManager_GetToken_ConnectionRefused(t *testing.T) {
	manager, err := New("http://127.0.0.1:19999") // no server at this port
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	// Reduce timeout to make test fast.
	manager.httpClient.Timeout = 1 * time.Second

	_, err = manager.GetToken("node", "client", "key")
	if err == nil {
		t.Error("expected error when server is unavailable")
	}
}

func TestManager_RefreshToken_HTTPError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte(`{"error": "forbidden"}`))
	}))
	defer server.Close()

	manager, err := New(server.URL)
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	_, err = manager.RefreshToken("bad-refresh-token")
	if err == nil {
		t.Error("expected error for 403 response")
	}
}

func TestManager_RefreshToken_InvalidJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`not-valid-json{{{`))
	}))
	defer server.Close()

	manager, err := New(server.URL)
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	_, err = manager.RefreshToken("refresh-token")
	if err == nil {
		t.Error("expected error for invalid JSON response")
	}
}

func TestManager_GetToken_InvalidJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`not-valid-json`))
	}))
	defer server.Close()

	manager, err := New(server.URL)
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	_, err = manager.GetToken("node", "client", "key")
	if err == nil {
		t.Error("expected error for invalid JSON response")
	}
}

func TestManager_ValidateToken_ConnectionRefused(t *testing.T) {
	manager, err := New("http://127.0.0.1:19998") // no server
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	manager.httpClient.Timeout = 1 * time.Second

	_, err = manager.ValidateToken("some-token")
	if err == nil {
		t.Error("expected error when server is unavailable")
	}
}

func TestManager_RevokeToken_NoJTI_ReturnsError(t *testing.T) {
	manager := &Manager{}

	// A valid-format JWT with no "jti" claim.
	// Header: {"alg":"none"}, Payload: {"sub":"user"}, no signature.
	// This is a degenerate JWT; parser will parse claims but jti is absent.
	err := manager.RevokeToken("eyJhbGciOiJub25lIn0.eyJzdWIiOiJ1c2VyIn0.")
	if err == nil {
		t.Error("expected error for JWT without jti claim")
	}
}

func TestManager_RevokeToken_MalformedToken_ReturnsError(t *testing.T) {
	manager := &Manager{}
	err := manager.RevokeToken("definitely-not-a-jwt")
	if err == nil {
		t.Error("expected error for completely malformed token")
	}
}

func TestManager_IsTokenExpired_ValidExpiredToken(t *testing.T) {
	manager := &Manager{}

	// JWT with exp in the past (Unix epoch 1).
	// Header: {"alg":"HS256","typ":"JWT"}
	// Payload: {"exp":1,"sub":"user"}
	// This is unsigned but ParseUnverified will still parse claims.
	pastToken := "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjEsInN1YiI6InVzZXIifQ.signature"

	expired := manager.IsTokenExpired(pastToken, time.Minute)
	if !expired {
		t.Error("expected token with past exp to be expired")
	}
}

func TestManager_IsTokenExpired_FutureToken(t *testing.T) {
	manager := &Manager{}

	// JWT with exp in the far future (year 2100 = Unix 4102444800).
	futureToken := "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjQxMDI0NDQ4MDAsInN1YiI6InVzZXIifQ.signature" //nolint:goconst

	expired := manager.IsTokenExpired(futureToken, time.Minute)
	if expired {
		t.Error("expected token with future exp to not be expired")
	}
}

func TestManager_GetToken_Concurrent(t *testing.T) {
	// Run with -race to detect data races.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{
			"access_token": "concurrent-token",
			"refresh_token": "concurrent-refresh",
			"token_type": "Bearer"
		}`))
	}))
	defer server.Close()

	manager, err := New(server.URL)
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	const goroutines = 10
	var wg sync.WaitGroup
	wg.Add(goroutines)
	errs := make(chan error, goroutines)

	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			_, err := manager.GetToken("node", "client", "key")
			if err != nil {
				errs <- err
			}
		}()
	}

	wg.Wait()
	close(errs)

	for err := range errs {
		t.Errorf("concurrent GetToken error: %v", err)
	}
}

func TestManager_New_EmptyURL(t *testing.T) {
	// Even with an empty URL, New should succeed (it only validates at request time).
	m, err := New("")
	if err != nil {
		t.Fatalf("New with empty URL: %v", err)
	}
	if m == nil {
		t.Fatal("expected non-nil manager")
	}
}

func TestManager_New_HTTPClientTimeout(t *testing.T) {
	m, err := New("http://example.com")
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	if m.httpClient.Timeout != 30*time.Second {
		t.Errorf("expected 30s timeout, got %v", m.httpClient.Timeout)
	}
}

func TestManager_GetToken_WithJWTExpiry(t *testing.T) {
	// Return a token that contains an exp claim so getTokenExpiry path is exercised.
	// JWT: {"alg":"HS256"}.{"exp":4102444800}.sig
	futureJWT := "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjQxMDI0NDQ4MDAsInN1YiI6InVzZXIifQ.signature"

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		// Note: ExpiresAt is zero (not set), so code falls through to parse from JWT.
		_, _ = w.Write([]byte(`{
			"access_token": "` + futureJWT + `",
			"refresh_token": "refresh",
			"token_type": "Bearer"
		}`))
	}))
	defer server.Close()

	manager, err := New(server.URL)
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	tokenInfo, err := manager.GetToken("node", "client", "key")
	if err != nil {
		t.Fatalf("GetToken: %v", err)
	}

	// ExpiresAt should have been parsed from the JWT claims.
	if tokenInfo.ExpiresAt.IsZero() {
		t.Error("expected ExpiresAt to be set from JWT exp claim")
	}
}

func TestManager_RefreshToken_WithJWTExpiry(t *testing.T) {
	futureJWT := "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjQxMDI0NDQ4MDAsInN1YiI6InVzZXIifQ.signature"

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{
			"access_token": "` + futureJWT + `",
			"refresh_token": "new-refresh",
			"token_type": "Bearer"
		}`))
	}))
	defer server.Close()

	manager, err := New(server.URL)
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	tokenInfo, err := manager.RefreshToken("old-refresh")
	if err != nil {
		t.Fatalf("RefreshToken: %v", err)
	}

	if tokenInfo.ExpiresAt.IsZero() {
		t.Error("expected ExpiresAt to be parsed from JWT exp claim")
	}
}

// TestManager_RevokeToken_WithJTI tests the full RevokeToken happy path.
// The JWT payload is {"sub":"user","jti":"test-jti-12345"} — base64url encoded.
// Header: {"alg":"HS256","typ":"JWT"} — base64url encoded.
func TestManager_RevokeToken_WithJTI_Success(t *testing.T) {
	var receivedJTI string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/auth/revoke" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		// Record request for assertion; ignore body read errors.
		buf := make([]byte, 1024)
		n, _ := r.Body.Read(buf)
		receivedJTI = string(buf[:n])

		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	manager, err := New(server.URL)
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	// JWT with jti claim: {"alg":"HS256","typ":"JWT"}.{"sub":"user","jti":"test-jti-12345"}.sig
	// Payload base64url: eyJzdWIiOiJ1c2VyIiwianRpIjoidGVzdC1qdGktMTIzNDUifQ
	tokenWithJTI := "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyIiwianRpIjoidGVzdC1qdGktMTIzNDUifQ.signature"

	err = manager.RevokeToken(tokenWithJTI)
	if err != nil {
		t.Errorf("RevokeToken with valid JTI: %v", err)
	}
	if receivedJTI == "" {
		t.Error("server should have received a request body")
	}
}

// TestManager_GetTokenExpiry_NoExpClaim exercises the "no expiry" branch of getTokenExpiry.
func TestManager_GetTokenExpiry_NoExpClaim(t *testing.T) {
	manager := &Manager{}
	// JWT with no exp claim: payload {"sub":"user","jti":"abc"} only.
	tokenNoExp := "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyIiwianRpIjoiYWJjIn0.signature"

	_, err := manager.getTokenExpiry(tokenNoExp)
	if err == nil {
		t.Error("expected error for JWT with no exp claim")
	}
}

func TestManager_RevokeToken_ServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	manager, err := New(server.URL)
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	tokenWithJTI := "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyIiwianRpIjoidGVzdC1qdGktMTIzNDUifQ.signature"
	err = manager.RevokeToken(tokenWithJTI)
	if err == nil {
		t.Error("expected error for 500 response")
	}
}
