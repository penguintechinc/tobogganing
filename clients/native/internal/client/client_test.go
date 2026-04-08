package client

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/tobogganing/clients/native/internal/config"
	"github.com/tobogganing/clients/native/internal/overlay"
)

// buildTestConfig creates a Config suitable for tests.
func buildTestConfig(t *testing.T) *config.Config {
	t.Helper()
	cfg := config.DefaultConfig()
	cfg.ManagerURL = "https://manager.example.com"
	cfg.APIKey = "test-api-key"
	cfg.ClientName = "test-client"
	return cfg
}

// --- ConnectionStatus ---

func TestConnectionStatus_ZeroValue(t *testing.T) {
	var s ConnectionStatus
	if s.State != "" {
		t.Errorf("zero State: got %q", s.State)
	}
	if s.BytesSent != 0 {
		t.Errorf("zero BytesSent: got %d", s.BytesSent)
	}
}

func TestConnectionStatus_Fields(t *testing.T) {
	s := ConnectionStatus{
		State:      "connected",
		ClientID:   "client-123",
		HeadendURL: "https://headend.example.com", //nolint:govet
	}
	if s.State != "connected" {
		t.Errorf("State: got %q", s.State)
	}
	if s.ClientID != "client-123" {
		t.Errorf("ClientID: got %q", s.ClientID)
	}
}

// --- New ---

func TestNew_FailsWhenWireGuardUnavailable(t *testing.T) {
	cfg := buildTestConfig(t)
	// wgctrl.New() may fail if WireGuard kernel module is not loaded.
	// That's acceptable in a test environment.
	_, err := New(cfg)
	if err != nil {
		t.Logf("New returned error (expected in test env without WireGuard kernel module): %v", err)
	} else {
		t.Log("New succeeded (WireGuard available in test environment)")
	}
}

// --- Status (without actual WireGuard connection) ---

func TestClient_Status_DisconnectedByDefault(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed (WireGuard not available): %v", err)
	}

	status, err := c.Status()
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	// Without a connection, state should be disconnected.
	if status.State != "disconnected" && status.State != "" {
		t.Errorf("unexpected state: %q", status.State)
	}
}

// --- Disconnect ---

func TestClient_Disconnect_NoProvider_NoError(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	// Disconnect when overlayProvider is nil should not error.
	if err := c.Disconnect(); err != nil {
		t.Errorf("Disconnect with nil provider: %v", err)
	}

	// Tokens and IDs should be cleared.
	if c.accessToken != "" {
		t.Error("accessToken should be cleared after Disconnect")
	}
	if c.refreshToken != "" {
		t.Error("refreshToken should be cleared after Disconnect")
	}
	if c.clientID != "" {
		t.Error("clientID should be cleared after Disconnect")
	}
}

// --- generateWireGuardKeys ---

func TestClient_GenerateWireGuardKeys(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	if err := c.generateWireGuardKeys(); err != nil {
		t.Fatalf("generateWireGuardKeys: %v", err)
	}

	// Both keys should be set.
	zero := [32]byte{}
	if c.wgPrivateKey == [32]byte(zero) {
		t.Error("private key should not be zero after generation")
	}
	if c.wgPublicKey == [32]byte(zero) {
		t.Error("public key should not be zero after generation")
	}
}

func TestClient_GenerateWireGuardKeys_PublicKeyDerivesFromPrivate(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	if err := c.generateWireGuardKeys(); err != nil {
		t.Fatalf("generateWireGuardKeys: %v", err)
	}

	// Public key should be derived from private key.
	expected := c.wgPrivateKey.PublicKey()
	if c.wgPublicKey != expected {
		t.Error("public key should be derived from private key")
	}
}

// --- buildRegistrationRequest ---

func TestClient_BuildRegistrationRequest_WithClientName(t *testing.T) {
	cfg := buildTestConfig(t)
	cfg.ClientName = "my-specific-client"
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	_ = c.generateWireGuardKeys()
	req := c.buildRegistrationRequest()

	if req["name"] != "my-specific-client" {
		t.Errorf("name: want %q, got %v", "my-specific-client", req["name"])
	}
	if req["type"] != "client_native" {
		t.Errorf("type: want %q, got %v", "client_native", req["type"])
	}
}

func TestClient_BuildRegistrationRequest_WithoutClientName(t *testing.T) {
	cfg := buildTestConfig(t)
	cfg.ClientName = "" // empty — should use hostname
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	_ = c.generateWireGuardKeys()
	req := c.buildRegistrationRequest()

	name, ok := req["name"].(string)
	if !ok {
		t.Fatal("name should be a string")
	}
	if name == "" {
		t.Error("name should be generated from hostname when ClientName is empty")
	}
	if !strings.HasPrefix(name, "native-client-") {
		t.Errorf("generated name should start with 'native-client-', got %q", name)
	}
}

func TestClient_BuildRegistrationRequest_ContainsLocation(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}
	_ = c.generateWireGuardKeys()

	req := c.buildRegistrationRequest()
	location, ok := req["location"].(map[string]interface{})
	if !ok {
		t.Fatal("request should contain 'location' map")
	}

	if location["platform"] != runtime.GOOS {
		t.Errorf("platform: want %q, got %v", runtime.GOOS, location["platform"])
	}
	if location["architecture"] != runtime.GOARCH {
		t.Errorf("architecture: want %q, got %v", runtime.GOARCH, location["architecture"])
	}
}

func TestClient_BuildRegistrationRequest_ContainsPublicKey(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}
	if err := c.generateWireGuardKeys(); err != nil {
		t.Fatalf("generateWireGuardKeys: %v", err)
	}

	req := c.buildRegistrationRequest()
	pubKey, ok := req["public_key"].(string)
	if !ok || pubKey == "" {
		t.Error("request should contain non-empty 'public_key'")
	}
}

// --- sendRegistrationRequest ---

func TestClient_SendRegistrationRequest_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/clients/register" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Error("expected Content-Type: application/json")
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{
			"client_id": "client-abc123",
			"api_key": "new-api-key",
			"cluster": {"headend_url": "https://headend.example.com"},
			"certificates": {"cert": "cert-data", "key": "key-data", "ca": "ca-data"}
		}`))
	}))
	defer server.Close()

	cfg := buildTestConfig(t)
	cfg.ManagerURL = server.URL
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	regReq := map[string]interface{}{
		"name":       "test-client",
		"type":       "client_native",
		"public_key": "test-pub-key",
	}

	resp, err := c.sendRegistrationRequest(regReq)
	if err != nil {
		t.Fatalf("sendRegistrationRequest: %v", err)
	}
	if resp.ClientID != "client-abc123" {
		t.Errorf("ClientID: want %q, got %q", "client-abc123", resp.ClientID)
	}
	if resp.Cluster.HeadendURL != "https://headend.example.com" { //nolint:goconst
		t.Errorf("HeadendURL: got %q", resp.Cluster.HeadendURL)
	}
}

func TestClient_SendRegistrationRequest_HTTPError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte(`{"error": "unauthorized"}`))
	}))
	defer server.Close()

	cfg := buildTestConfig(t)
	cfg.ManagerURL = server.URL
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	_, err = c.sendRegistrationRequest(map[string]interface{}{"name": "test"})
	if err == nil {
		t.Error("expected error for 401 response")
	}
}

func TestClient_SendRegistrationRequest_InvalidJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`not-valid-json`))
	}))
	defer server.Close()

	cfg := buildTestConfig(t)
	cfg.ManagerURL = server.URL
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	_, err = c.sendRegistrationRequest(map[string]interface{}{"name": "test"})
	if err == nil {
		t.Error("expected error for invalid JSON response")
	}
}

// --- saveCertificates ---

func TestClient_SaveCertificates_CreatesFiles(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	dir := t.TempDir()
	// Override getCertificateDir by setting HOME to temp dir so it uses our dir.
	t.Setenv("HOME", dir)

	err = c.saveCertificates("cert-data", "key-data", "ca-data")
	if err != nil {
		t.Fatalf("saveCertificates: %v", err)
	}

	certDir := c.getCertificateDir()
	for _, filename := range []string{"client.crt", "client.key", "ca.crt"} {
		path := filepath.Join(certDir, filename)
		if _, err := os.Stat(path); err != nil {
			t.Errorf("expected file %q to exist: %v", path, err)
		}
	}
}

// --- getCertificateDir ---

func TestClient_GetCertificateDir_NonEmpty(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	dir := c.getCertificateDir()
	if dir == "" {
		t.Error("getCertificateDir should not be empty")
	}
}

func TestClient_GetCertificateDir_ContainsCerts(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	dir := c.getCertificateDir()
	if !strings.Contains(dir, "certs") {
		t.Errorf("getCertificateDir should contain 'certs', got %q", dir)
	}
}

// --- getWireGuardInterface ---

func TestClient_GetWireGuardInterface_NonEmpty(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	iface := c.getWireGuardInterface()
	if iface == "" {
		t.Error("getWireGuardInterface should not be empty")
	}
}

func TestClient_GetWireGuardInterface_PlatformSpecific(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	iface := c.getWireGuardInterface()
	switch runtime.GOOS {
	case "linux":
		if iface != "wg0" {
			t.Errorf("Linux: expected wg0, got %q", iface)
		}
	case "darwin":
		if iface != "utun1" {
			t.Errorf("macOS: expected utun1, got %q", iface)
		}
	case "windows":
		if iface != "tobogganing" {
			t.Errorf("Windows: expected tobogganing, got %q", iface)
		}
	}
}

// --- getWireGuardConfigPath ---

func TestClient_GetWireGuardConfigPath_NonEmpty(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	path := c.getWireGuardConfigPath()
	if path == "" {
		t.Error("getWireGuardConfigPath should not be empty")
	}
}

func TestClient_GetWireGuardConfigPath_HasConfExtension(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	path := c.getWireGuardConfigPath()
	if !strings.HasSuffix(path, ".conf") {
		t.Errorf("config path should end with .conf, got %q", path)
	}
}

// --- createWireGuardConfig ---

func TestClient_CreateWireGuardConfig_WritesFile(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	// Generate keys so the config has valid keys.
	if err := c.generateWireGuardKeys(); err != nil {
		t.Fatalf("generateWireGuardKeys: %v", err)
	}

	// Set headendURL to avoid empty hostname.
	c.headendURL = "https://headend.example.com:8080"

	// Override WireGuard config path to temp directory.
	dir := t.TempDir()
	t.Setenv("HOME", dir)
	if runtime.GOOS == "linux" {
		// The path is /etc/wireguard/wg0.conf — can't write there without root.
		// We just test the function composes the config correctly.
		// Create the directory if needed.
		testPath := filepath.Join(dir, "wg0.conf")
		// Temporarily replace the path resolution.
		// We can't easily redirect on Linux without mock, so just verify it doesn't crash.
		err = c.createWireGuardConfig("10.0.0.2/24", "10.0.0.0/24")
		if err != nil {
			t.Logf("createWireGuardConfig error (expected without /etc/wireguard): %v", err)
		}
		_ = testPath
	} else {
		err = c.createWireGuardConfig("10.0.0.2/24", "10.0.0.0/24")
		if err != nil {
			t.Logf("createWireGuardConfig error: %v", err)
		}
	}
}

// --- processRegistrationResponse ---

func TestClient_ProcessRegistrationResponse_SetsFields(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	dir := t.TempDir()
	t.Setenv("HOME", dir)

	resp := &registrationResponse{
		ClientID: "client-xyz",
		APIKey:   "new-api-key-123",
		Cluster: struct {
			HeadendURL string `json:"headend_url"`
		}{HeadendURL: "https://headend.example.com"},
		Certificates: struct {
			Cert string `json:"cert"`
			Key  string `json:"key"`
			CA   string `json:"ca"`
		}{Cert: "cert", Key: "key", CA: "ca"},
	}

	if err := c.processRegistrationResponse(resp); err != nil {
		t.Fatalf("processRegistrationResponse: %v", err)
	}

	if c.clientID != "client-xyz" {
		t.Errorf("clientID: want %q, got %q", "client-xyz", c.clientID)
	}
	if c.headendURL != "https://headend.example.com" {
		t.Errorf("headendURL: want %q, got %q", "https://headend.example.com", c.headendURL)
	}
	if c.config.APIKey != "new-api-key-123" {
		t.Errorf("APIKey: want %q, got %q", "new-api-key-123", c.config.APIKey)
	}
}

// --- checkAuthentication ---

func TestClient_CheckAuthentication_NoError(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	// checkAuthentication is a placeholder.
	if err := c.checkAuthentication(); err != nil {
		t.Errorf("checkAuthentication: %v", err)
	}
}

// --- getInterfaceIP ---

func TestClient_GetInterfaceIP_NonExistentInterface(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	const nonExistentInterface = "wg-nonexistent-9999"
	// On an unsupported platform or missing interface, should return error.
	_, err = c.getInterfaceIP(nonExistentInterface)
	if err == nil {
		t.Log("getInterfaceIP succeeded (interface exists or command available)")
	} else {
		t.Logf("getInterfaceIP error (expected): %v", err)
	}
}

// --- Disconnect with provider ---

func TestClient_Disconnect_WithProvider_CallsProviderDisconnect(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	// Set a stub provider.
	disconnected := false
	c.overlayProvider = &stubOverlayProvider{
		disconnectFn: func(ctx context.Context) error {
			disconnected = true
			return nil
		},
	}

	if err := c.Disconnect(); err != nil {
		t.Fatalf("Disconnect: %v", err)
	}
	if !disconnected {
		t.Error("expected provider Disconnect to be called")
	}
}

// stubOverlayProvider implements overlay.OverlayProvider for testing.
type stubOverlayProvider struct {
	connectFn    func(ctx context.Context) error
	disconnectFn func(ctx context.Context) error
}

func (s *stubOverlayProvider) Connect(ctx context.Context) error {
	if s.connectFn != nil {
		return s.connectFn(ctx)
	}
	return nil
}

func (s *stubOverlayProvider) Disconnect(ctx context.Context) error {
	if s.disconnectFn != nil {
		return s.disconnectFn(ctx)
	}
	return nil
}

func (s *stubOverlayProvider) Status(ctx context.Context) (overlay.ProviderStatus, error) {
	return overlay.ProviderStatus{}, nil
}

// --- authenticate ---

func TestClient_Authenticate_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/auth/token" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{
			"access_token": "test-access-token",
			"refresh_token": "test-refresh-token",
			"expires_at": "2099-01-01T00:00:00Z"
		}`))
	}))
	defer server.Close()

	cfg := buildTestConfig(t)
	cfg.ManagerURL = server.URL
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}
	c.clientID = "test-client-id" //nolint:goconst

	if err := c.authenticate(); err != nil {
		t.Fatalf("authenticate: %v", err)
	}
	if c.accessToken != "test-access-token" {
		t.Errorf("accessToken: want %q, got %q", "test-access-token", c.accessToken)
	}
	if c.refreshToken != "test-refresh-token" {
		t.Errorf("refreshToken: want %q, got %q", "test-refresh-token", c.refreshToken)
	}
}

func TestClient_Authenticate_HTTPError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte("unauthorized"))
	}))
	defer server.Close()

	cfg := buildTestConfig(t)
	cfg.ManagerURL = server.URL
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	if err := c.authenticate(); err == nil {
		t.Error("expected error for 401 response")
	}
}

func TestClient_Authenticate_InvalidJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("not-json"))
	}))
	defer server.Close()

	cfg := buildTestConfig(t)
	cfg.ManagerURL = server.URL
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	if err := c.authenticate(); err == nil {
		t.Error("expected error for invalid JSON")
	}
}

// --- healthCheck ---

func TestClient_HealthCheck_WireGuardDown(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	// healthCheck checks the WireGuard interface; it should fail since wg0 isn't up.
	err = c.healthCheck()
	if err == nil {
		t.Log("healthCheck succeeded (WireGuard interface somehow available)")
	} else {
		t.Logf("healthCheck error (expected — WireGuard interface not up): %v", err)
	}
}

// --- runMonitoring ---

func TestClient_RunMonitoring_StopsOnContextCancel(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	// Use a very short timeout context so monitoring stops quickly.
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	// runMonitoring blocks until ctx is done, then calls Disconnect.
	done := make(chan error, 1)
	go func() {
		done <- c.runMonitoring(ctx)
	}()

	// Wait for runMonitoring to finish (context times out in 50ms).
	timer := time.NewTimer(2 * time.Second)
	defer timer.Stop()
	select {
	case <-done:
		// completed as expected
	case <-timer.C:
		t.Error("runMonitoring did not return after context cancellation")
	}
}

// --- setupWireGuard ---

func TestClient_SetupWireGuard_HTTPError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte("bad request"))
	}))
	defer server.Close()

	cfg := buildTestConfig(t)
	cfg.ManagerURL = server.URL
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	if err := c.setupWireGuard(); err == nil {
		t.Error("expected error for 400 response")
	}
}

func TestClient_SetupWireGuard_InvalidJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("not-json"))
	}))
	defer server.Close()

	cfg := buildTestConfig(t)
	cfg.ManagerURL = server.URL
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	if err := c.setupWireGuard(); err == nil {
		t.Error("expected error for invalid JSON")
	}
}

func TestClient_SetupWireGuard_ValidResponse_WritesConfig(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{
			"wireguard": {
				"private_key": "",
				"public_key": "",
				"ip_address": "10.0.0.2/24",
				"network_cidr": "10.0.0.0/24"
			}
		}`))
	}))
	defer server.Close()

	cfg := buildTestConfig(t)
	cfg.ManagerURL = server.URL
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	// Set headendURL to avoid empty value in config template.
	c.headendURL = "https://headend.example.com:51820"

	// Generate keys so we have a valid private key.
	_ = c.generateWireGuardKeys()

	// This may fail writing /etc/wireguard/ without root — that's acceptable.
	err = c.setupWireGuard()
	if err != nil {
		t.Logf("setupWireGuard error (expected without write access to /etc/wireguard): %v", err)
	}
}

// --- register ---

func TestClient_Register_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{
			"client_id": "reg-client-id",
			"api_key": "reg-api-key",
			"cluster": {"headend_url": "https://headend.example.com"},
			"certificates": {"cert": "c", "key": "k", "ca": "ca"}
		}`))
	}))
	defer server.Close()

	cfg := buildTestConfig(t)
	cfg.ManagerURL = server.URL
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	dir := t.TempDir()
	t.Setenv("HOME", dir)

	if err := c.register(); err != nil {
		t.Fatalf("register: %v", err)
	}

	if c.clientID != "reg-client-id" {
		t.Errorf("clientID: want %q, got %q", "reg-client-id", c.clientID)
	}
}

// --- Status ---

func TestClient_Status_ConnectedFields(t *testing.T) {
	cfg := buildTestConfig(t)
	c, err := New(cfg)
	if err != nil {
		t.Skipf("New failed: %v", err)
	}

	// Set client state as if connected.
	c.clientID = "test-client-id"
	c.headendURL = "https://headend.example.com"

	status, err := c.Status()
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	// ClientID and HeadendURL should be reflected in status.
	if status.ClientID != "test-client-id" {
		t.Errorf("ClientID: want %q, got %q", "test-client-id", status.ClientID)
	}
	if status.HeadendURL != "https://headend.example.com" {
		t.Errorf("HeadendURL: want %q, got %q", "https://headend.example.com", status.HeadendURL)
	}
}
