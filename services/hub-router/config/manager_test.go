package config

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"
)

// ─── NewManager ───────────────────────────────────────────────────────────────

func TestNewManager_StoresFields(t *testing.T) {
	cm := NewManager("http://manager:8080", "my-api-key")
	if cm == nil {
		t.Fatal("expected non-nil manager")
	}
	if cm.managerURL != "http://manager:8080" {
		t.Errorf("unexpected managerURL: %s", cm.managerURL)
	}
	if cm.apiKey != "my-api-key" {
		t.Errorf("unexpected apiKey: %s", cm.apiKey)
	}
	if cm.config != nil {
		t.Error("config should be nil on creation")
	}
}

func TestNewManager_HttpClientSet(t *testing.T) {
	cm := NewManager("http://manager:8080", "key")
	if cm.httpClient == nil {
		t.Error("httpClient should be initialized")
	}
}

// ─── FetchConfig ─────────────────────────────────────────────────────────────

func makeValidConfig() HeadendConfig {
	return HeadendConfig{
		HTTPPort:    "8080",
		TCPPort:     "8443",
		UDPPort:     "8444",
		MetricsPort: "9090",
		Auth: AuthConfig{
			Type:       "jwt",
			ManagerURL: "http://manager:8080",
		},
		WireGuard: WireGuardConfig{
			Interface:  "wg0",
			ListenPort: 51820,
			Network:    "10.200.0.0/16",
		},
	}
}

func TestFetchConfig_RequiresClusterID(t *testing.T) {
	os.Unsetenv("CLUSTER_ID")
	cm := NewManager("http://manager:8080", "key")
	_, err := cm.FetchConfig()
	if err == nil {
		t.Error("expected error when CLUSTER_ID not set")
	}
}

func TestFetchConfig_Success(t *testing.T) {
	cfg := makeValidConfig()

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-key" {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(cfg)
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_ID", "cluster-1")
	defer os.Unsetenv("CLUSTER_ID")

	cm := NewManager(ts.URL, "test-key")
	result, err := cm.FetchConfig()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.HTTPPort != "8080" {
		t.Errorf("unexpected HTTPPort: %s", result.HTTPPort)
	}
	if result.Auth.Type != "jwt" {
		t.Errorf("unexpected auth type: %s", result.Auth.Type)
	}
}

func TestFetchConfig_HTTPError(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal server error", http.StatusInternalServerError)
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_ID", "cluster-1")
	defer os.Unsetenv("CLUSTER_ID")

	cm := NewManager(ts.URL, "key")
	_, err := cm.FetchConfig()
	if err == nil {
		t.Error("expected error for 500 response")
	}
}

func TestFetchConfig_ConnectionRefused(t *testing.T) {
	os.Setenv("CLUSTER_ID", "cluster-1")
	defer os.Unsetenv("CLUSTER_ID")

	cm := NewManager("http://127.0.0.1:1", "key")
	_, err := cm.FetchConfig()
	if err == nil {
		t.Error("expected error for connection refused")
	}
}

func TestFetchConfig_InvalidJSON(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("not-json"))
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_ID", "cluster-1")
	defer os.Unsetenv("CLUSTER_ID")

	cm := NewManager(ts.URL, "key")
	_, err := cm.FetchConfig()
	if err == nil {
		t.Error("expected error for invalid JSON")
	}
}

func TestFetchConfig_SetsLastUpdate(t *testing.T) {
	cfg := makeValidConfig()
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(cfg)
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_ID", "cluster-1")
	defer os.Unsetenv("CLUSTER_ID")

	before := time.Now()
	cm := NewManager(ts.URL, "key")
	_, err := cm.FetchConfig()
	after := time.Now()

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cm.lastUpdate.Before(before) || cm.lastUpdate.After(after) {
		t.Error("lastUpdate not in expected range")
	}
}

func TestFetchConfig_CachesConfig(t *testing.T) {
	cfg := makeValidConfig()
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(cfg)
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_ID", "cluster-1")
	defer os.Unsetenv("CLUSTER_ID")

	cm := NewManager(ts.URL, "key")
	_, err := cm.FetchConfig()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cm.config == nil {
		t.Error("expected config to be cached after fetch")
	}
}

func TestFetchConfig_URLBuilding(t *testing.T) {
	var gotPath string
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		json.NewEncoder(w).Encode(makeValidConfig())
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_ID", "my-cluster")
	defer os.Unsetenv("CLUSTER_ID")

	cm := NewManager(ts.URL, "key")
	cm.FetchConfig()

	expected := "/api/v1/clusters/my-cluster/headend-config"
	if gotPath != expected {
		t.Errorf("unexpected path: %s, want %s", gotPath, expected)
	}
}

func TestFetchConfig_SendsAuthHeader(t *testing.T) {
	var gotAuth string
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		json.NewEncoder(w).Encode(makeValidConfig())
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_ID", "cluster-1")
	defer os.Unsetenv("CLUSTER_ID")

	cm := NewManager(ts.URL, "secret-api-key")
	cm.FetchConfig()

	if gotAuth != "Bearer secret-api-key" {
		t.Errorf("unexpected auth header: %s", gotAuth)
	}
}

// ─── applyEnvOverrides ────────────────────────────────────────────────────────

func TestApplyEnvOverrides_HTTPPort(t *testing.T) {
	os.Setenv("HEADEND_HTTP_PORT", "9090")
	defer os.Unsetenv("HEADEND_HTTP_PORT")

	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{HTTPPort: "8080"}
	cm.applyEnvOverrides(cfg)

	if cfg.HTTPPort != "9090" {
		t.Errorf("expected HTTPPort=9090, got %s", cfg.HTTPPort)
	}
}

func TestApplyEnvOverrides_TCPPort(t *testing.T) {
	os.Setenv("HEADEND_TCP_PORT", "9443")
	defer os.Unsetenv("HEADEND_TCP_PORT")

	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{TCPPort: "8443"}
	cm.applyEnvOverrides(cfg)

	if cfg.TCPPort != "9443" {
		t.Errorf("expected TCPPort=9443, got %s", cfg.TCPPort)
	}
}

func TestApplyEnvOverrides_UDPPort(t *testing.T) {
	os.Setenv("HEADEND_UDP_PORT", "9444")
	defer os.Unsetenv("HEADEND_UDP_PORT")

	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{UDPPort: "8444"}
	cm.applyEnvOverrides(cfg)

	if cfg.UDPPort != "9444" {
		t.Errorf("expected UDPPort=9444, got %s", cfg.UDPPort)
	}
}

func TestApplyEnvOverrides_AuthType(t *testing.T) {
	os.Setenv("HEADEND_AUTH_TYPE", "oauth2")
	defer os.Unsetenv("HEADEND_AUTH_TYPE")

	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{Auth: AuthConfig{Type: "jwt"}}
	cm.applyEnvOverrides(cfg)

	if cfg.Auth.Type != "oauth2" {
		t.Errorf("expected auth type=oauth2, got %s", cfg.Auth.Type)
	}
}

func TestApplyEnvOverrides_MirrorEnabled_True(t *testing.T) {
	os.Setenv("HEADEND_MIRROR_ENABLED", "true")
	defer os.Unsetenv("HEADEND_MIRROR_ENABLED")

	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{Mirror: MirrorConfig{Enabled: false}}
	cm.applyEnvOverrides(cfg)

	if !cfg.Mirror.Enabled {
		t.Error("expected mirror enabled=true")
	}
}

func TestApplyEnvOverrides_MirrorEnabled_False(t *testing.T) {
	os.Setenv("HEADEND_MIRROR_ENABLED", "false")
	defer os.Unsetenv("HEADEND_MIRROR_ENABLED")

	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{Mirror: MirrorConfig{Enabled: true}}
	cm.applyEnvOverrides(cfg)

	if cfg.Mirror.Enabled {
		t.Error("expected mirror enabled=false")
	}
}

func TestApplyEnvOverrides_NoEnvVars_NoChange(t *testing.T) {
	// Ensure no env vars are set
	for _, k := range []string{"HEADEND_HTTP_PORT", "HEADEND_TCP_PORT", "HEADEND_UDP_PORT",
		"HEADEND_AUTH_TYPE", "HEADEND_MIRROR_ENABLED"} {
		os.Unsetenv(k)
	}

	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{
		HTTPPort: "8080",
		TCPPort:  "8443",
		Auth:     AuthConfig{Type: "jwt"},
		Mirror:   MirrorConfig{Enabled: true},
	}
	cm.applyEnvOverrides(cfg)

	if cfg.HTTPPort != "8080" {
		t.Error("HTTPPort should not change")
	}
	if cfg.Auth.Type != "jwt" {
		t.Error("auth type should not change")
	}
	if !cfg.Mirror.Enabled {
		t.Error("mirror enabled should not change")
	}
}

// ─── GetConfig ────────────────────────────────────────────────────────────────

func TestGetConfig_FetchesWhenNil(t *testing.T) {
	cfg := makeValidConfig()
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(cfg)
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_ID", "cluster-1")
	defer os.Unsetenv("CLUSTER_ID")

	cm := NewManager(ts.URL, "key")
	result, err := cm.GetConfig()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result == nil {
		t.Fatal("expected non-nil config")
	}
}

func TestGetConfig_UsesCacheWhenFresh(t *testing.T) {
	callCount := 0
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		json.NewEncoder(w).Encode(makeValidConfig())
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_ID", "cluster-1")
	defer os.Unsetenv("CLUSTER_ID")

	cm := NewManager(ts.URL, "key")

	// First call fetches
	cm.GetConfig()

	// Second call within 5 minutes should use cache
	cm.GetConfig()

	if callCount != 1 {
		t.Errorf("expected 1 HTTP call (cached), got %d", callCount)
	}
}

func TestGetConfig_RefetchesWhenStale(t *testing.T) {
	callCount := 0
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		json.NewEncoder(w).Encode(makeValidConfig())
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_ID", "cluster-1")
	defer os.Unsetenv("CLUSTER_ID")

	cm := NewManager(ts.URL, "key")

	// First fetch
	cm.GetConfig()

	// Set last update to >5 minutes ago to force a refresh
	cm.lastUpdate = time.Now().Add(-6 * time.Minute)

	// Should re-fetch
	cm.GetConfig()

	if callCount != 2 {
		t.Errorf("expected 2 HTTP calls (stale cache), got %d", callCount)
	}
}

// ─── RefreshConfig ────────────────────────────────────────────────────────────

func TestRefreshConfig_AlwaysFetches(t *testing.T) {
	callCount := 0
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		json.NewEncoder(w).Encode(makeValidConfig())
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_ID", "cluster-1")
	defer os.Unsetenv("CLUSTER_ID")

	cm := NewManager(ts.URL, "key")
	cm.GetConfig()   // fetch once
	cm.RefreshConfig() // force refresh

	if callCount != 2 {
		t.Errorf("expected 2 HTTP calls, got %d", callCount)
	}
}

// ─── ValidateConfig ───────────────────────────────────────────────────────────

func TestValidateConfig_Valid(t *testing.T) {
	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{
		HTTPPort: "8080",
		Auth: AuthConfig{
			Type:       "jwt",
			ManagerURL: "http://manager:8080",
		},
		WireGuard: WireGuardConfig{
			Interface:  "wg0",
			ListenPort: 51820,
		},
	}
	if err := cm.ValidateConfig(cfg); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestValidateConfig_MissingHTTPPort(t *testing.T) {
	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{
		Auth: AuthConfig{
			Type:       "jwt",
			ManagerURL: "http://manager:8080",
		},
		WireGuard: WireGuardConfig{
			Interface:  "wg0",
			ListenPort: 51820,
		},
	}
	if err := cm.ValidateConfig(cfg); err == nil {
		t.Error("expected error for missing HTTPPort")
	}
}

func TestValidateConfig_MissingAuthType(t *testing.T) {
	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{
		HTTPPort: "8080",
		WireGuard: WireGuardConfig{
			Interface:  "wg0",
			ListenPort: 51820,
		},
	}
	if err := cm.ValidateConfig(cfg); err == nil {
		t.Error("expected error for missing auth type")
	}
}

func TestValidateConfig_JWTMissingManagerURL(t *testing.T) {
	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{
		HTTPPort: "8080",
		Auth: AuthConfig{
			Type: "jwt",
			// ManagerURL intentionally missing
		},
		WireGuard: WireGuardConfig{
			Interface:  "wg0",
			ListenPort: 51820,
		},
	}
	if err := cm.ValidateConfig(cfg); err == nil {
		t.Error("expected error for JWT missing manager URL")
	}
}

func TestValidateConfig_OAuth2DoesNotRequireManagerURL(t *testing.T) {
	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{
		HTTPPort: "8080",
		Auth: AuthConfig{
			Type: "oauth2",
			// no ManagerURL
		},
		WireGuard: WireGuardConfig{
			Interface:  "wg0",
			ListenPort: 51820,
		},
	}
	if err := cm.ValidateConfig(cfg); err != nil {
		t.Errorf("unexpected error for oauth2 without manager URL: %v", err)
	}
}

func TestValidateConfig_MissingWireGuardInterface(t *testing.T) {
	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{
		HTTPPort: "8080",
		Auth: AuthConfig{
			Type:       "jwt",
			ManagerURL: "http://manager",
		},
		WireGuard: WireGuardConfig{
			// Interface intentionally missing
			ListenPort: 51820,
		},
	}
	if err := cm.ValidateConfig(cfg); err == nil {
		t.Error("expected error for missing WireGuard interface")
	}
}

func TestValidateConfig_MissingWireGuardListenPort(t *testing.T) {
	cm := NewManager("http://manager", "key")
	cfg := &HeadendConfig{
		HTTPPort: "8080",
		Auth: AuthConfig{
			Type:       "jwt",
			ManagerURL: "http://manager",
		},
		WireGuard: WireGuardConfig{
			Interface: "wg0",
			// ListenPort intentionally zero
		},
	}
	if err := cm.ValidateConfig(cfg); err == nil {
		t.Error("expected error for zero WireGuard listen port")
	}
}

// ─── HeadendConfig JSON ───────────────────────────────────────────────────────

func TestHeadendConfig_JSONRoundTrip(t *testing.T) {
	original := makeValidConfig()
	original.Mirror = MirrorConfig{
		Enabled:      true,
		Destinations: []string{"192.168.1.1:4789"},
		Protocol:     "vxlan",
		BufferSize:   1024,
		SampleRate:   100,
	}
	original.Proxy = ProxyConfig{
		SkipTLSVerify: true,
		Timeout:       30,
		MaxIdleConns:  100,
	}

	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}

	var decoded HeadendConfig
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}

	if decoded.HTTPPort != original.HTTPPort {
		t.Errorf("HTTPPort mismatch")
	}
	if decoded.Mirror.Protocol != "vxlan" {
		t.Errorf("Mirror.Protocol mismatch: %s", decoded.Mirror.Protocol)
	}
	if !decoded.Proxy.SkipTLSVerify {
		t.Error("Proxy.SkipTLSVerify mismatch")
	}
}

func TestAuthConfig_OAuth2Fields(t *testing.T) {
	auth := AuthConfig{
		Type: "oauth2",
		OAuth2: OAuth2Config{
			Issuer:       "https://auth.example.com",
			ClientID:     "my-client",
			ClientSecret: "my-secret",
			RedirectURL:  "https://app.example.com/callback",
		},
	}
	data, _ := json.Marshal(auth)
	var decoded AuthConfig
	json.Unmarshal(data, &decoded)

	if decoded.OAuth2.Issuer != "https://auth.example.com" {
		t.Errorf("OAuth2.Issuer mismatch: %s", decoded.OAuth2.Issuer)
	}
	if decoded.OAuth2.ClientID != "my-client" {
		t.Errorf("OAuth2.ClientID mismatch: %s", decoded.OAuth2.ClientID)
	}
}

func TestAuthConfig_SAML2Fields(t *testing.T) {
	auth := AuthConfig{
		Type: "saml2",
		SAML2: SAML2Config{
			IDPMetadataURL: "https://idp.example.com/metadata",
			SPEntityID:     "https://sp.example.com",
			SSOURL:         "https://idp.example.com/sso",
		},
	}
	data, _ := json.Marshal(auth)
	var decoded AuthConfig
	json.Unmarshal(data, &decoded)

	if decoded.SAML2.IDPMetadataURL != "https://idp.example.com/metadata" {
		t.Errorf("SAML2.IDPMetadataURL mismatch: %s", decoded.SAML2.IDPMetadataURL)
	}
}

func TestWireGuardConfig_Peers(t *testing.T) {
	cfg := WireGuardConfig{
		Interface:  "wg0",
		ListenPort: 51820,
		Peers: []WireGuardPeer{
			{NodeID: "n1", NodeType: "client", PublicKey: "key1", AllowedIPs: "10.1.0.1/32"},
			{NodeID: "n2", NodeType: "client", PublicKey: "key2", AllowedIPs: "10.1.0.2/32", Endpoint: "1.2.3.4:51820"},
		},
	}
	data, _ := json.Marshal(cfg)
	var decoded WireGuardConfig
	json.Unmarshal(data, &decoded)

	if len(decoded.Peers) != 2 {
		t.Fatalf("expected 2 peers, got %d", len(decoded.Peers))
	}
	if decoded.Peers[1].Endpoint != "1.2.3.4:51820" {
		t.Errorf("unexpected endpoint: %s", decoded.Peers[1].Endpoint)
	}
}

func TestWireGuardPeer_OmitEmptyEndpoint(t *testing.T) {
	peer := WireGuardPeer{
		NodeID:     "n1",
		NodeType:   "client",
		PublicKey:  "key1",
		AllowedIPs: "10.0.0.1/32",
	}
	data, _ := json.Marshal(peer)
	var m map[string]interface{}
	json.Unmarshal(data, &m)
	if _, exists := m["endpoint"]; exists {
		t.Error("endpoint should be omitted when empty")
	}
}

// ─── WatchConfig ─────────────────────────────────────────────────────────────

func TestWatchConfig_DoesNotPanic(t *testing.T) {
	callCount := 0
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		json.NewEncoder(w).Encode(makeValidConfig())
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_ID", "cluster-1")
	defer os.Unsetenv("CLUSTER_ID")

	cm := NewManager(ts.URL, "key")

	// WatchConfig starts a background goroutine with the given interval.
	// We use a very long interval so it won't actually fire during the test.
	// The point is to verify it launches without panicking.
	cm.WatchConfig(24 * time.Hour)

	// Give it a moment to start
	time.Sleep(10 * time.Millisecond)

	// callCount should be 0 since the ticker hasn't fired yet
	if callCount != 0 {
		t.Errorf("expected 0 HTTP calls, got %d", callCount)
	}
}
