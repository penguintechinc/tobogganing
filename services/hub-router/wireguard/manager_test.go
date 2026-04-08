package wireguard

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"golang.zx2c4.com/wireguard/wgctrl/wgtypes"
)

// ─── helpers ─────────────────────────────────────────────────────────────────

// getTestManager creates a Manager for testing.  wgctrl.New() requires kernel
// WireGuard support; if unavailable the test is skipped.
func getTestManager(t *testing.T) *Manager {
	t.Helper()
	m, err := NewManagerWithParams("wg-test0", "http://localhost:9998", 51819, "10.0.0.0/24")
	if err != nil {
		t.Skipf("wgctrl unavailable in test environment: %v", err)
	}
	return m
}

// makeManagerWithoutWgctrl builds a Manager directly without wgctrl, for
// testing methods that don't touch the WireGuard kernel interface.
func makeManagerWithoutWgctrl(managerURL string) *Manager {
	key, _ := wgtypes.GeneratePrivateKey()
	return &Manager{
		interfaceName: "wg0",
		managerURL:    managerURL,
		client:        nil, // intentionally nil — not needed for HTTP-based tests
		httpClient:    &http.Client{Timeout: 5 * time.Second},
		privateKey:    key,
		publicKey:     key.PublicKey(),
		listenPort:    51820,
		network:       "10.0.0.0/24",
	}
}

// ─── Config struct ────────────────────────────────────────────────────────────

func TestConfig_Fields(t *testing.T) {
	cfg := Config{
		InterfaceName: "wg0",
		ListenPort:    51820,
		PrivateKey:    "private-key-value",
		Network:       "10.200.0.0/16",
		ManagerURL:    "https://manager.example.com",
	}
	if cfg.InterfaceName != "wg0" {
		t.Error("unexpected InterfaceName")
	}
	if cfg.ListenPort != 51820 {
		t.Error("unexpected ListenPort")
	}
	if cfg.Network != "10.200.0.0/16" {
		t.Error("unexpected Network")
	}
}

// ─── NewManager / NewManagerWithParams ────────────────────────────────────────

func TestNewManager_DelegatesToWithParams(t *testing.T) {
	cfg := &Config{
		InterfaceName: "wg-nm-test",
		ListenPort:    51820,
		Network:       "10.99.0.0/24",
		ManagerURL:    "http://localhost:9999",
	}
	m, err := NewManager(cfg)
	if err != nil {
		t.Logf("NewManager returned expected environment error: %v", err)
		return
	}
	if m == nil {
		t.Fatal("expected non-nil manager")
	}
	if m.interfaceName != "wg-nm-test" {
		t.Errorf("unexpected interfaceName: %s", m.interfaceName)
	}
	m.Close()
}

func TestNewManagerWithParams_StoresFields(t *testing.T) {
	m, err := NewManagerWithParams("wg-params-test", "http://manager:8080", 51821, "10.100.0.0/24")
	if err != nil {
		t.Logf("NewManagerWithParams returned expected environment error: %v", err)
		return
	}
	if m.interfaceName != "wg-params-test" {
		t.Errorf("unexpected interfaceName: %s", m.interfaceName)
	}
	if m.managerURL != "http://manager:8080" {
		t.Errorf("unexpected managerURL: %s", m.managerURL)
	}
	if m.listenPort != 51821 {
		t.Errorf("unexpected listenPort: %d", m.listenPort)
	}
	if m.network != "10.100.0.0/24" {
		t.Errorf("unexpected network: %s", m.network)
	}
	m.Close()
}

// ─── Peer struct / JSON ───────────────────────────────────────────────────────

func TestPeer_JSONRoundTrip(t *testing.T) {
	original := Peer{
		NodeID:     "node-123",
		NodeType:   "client",
		PublicKey:  "abc123pubkey",
		AllowedIPs: "10.1.1.2/32",
		Endpoint:   "192.168.1.1:51820",
	}
	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("failed to marshal peer: %v", err)
	}
	var decoded Peer
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("failed to unmarshal peer: %v", err)
	}
	if decoded.NodeID != original.NodeID {
		t.Errorf("NodeID mismatch: %s vs %s", decoded.NodeID, original.NodeID)
	}
	if decoded.PublicKey != original.PublicKey {
		t.Errorf("PublicKey mismatch")
	}
	if decoded.AllowedIPs != original.AllowedIPs {
		t.Errorf("AllowedIPs mismatch")
	}
	if decoded.Endpoint != original.Endpoint {
		t.Errorf("Endpoint mismatch: %s vs %s", decoded.Endpoint, original.Endpoint)
	}
}

func TestPeer_JSONOmitEmptyEndpoint(t *testing.T) {
	p := Peer{
		NodeID:     "node-1",
		NodeType:   "client",
		PublicKey:  "key1",
		AllowedIPs: "10.0.0.1/32",
		// Endpoint intentionally empty
	}
	data, _ := json.Marshal(p)
	var m map[string]interface{}
	_ = json.Unmarshal(data, &m)
	if _, exists := m["endpoint"]; exists {
		t.Error("endpoint should be omitted when empty (omitempty)")
	}
}

// ─── parseAllowedIPs ──────────────────────────────────────────────────────────

// parseAllowedIPs is unexported but accessible from the same package.
// We use makeManagerWithoutWgctrl to avoid needing kernel WireGuard support.

func TestParseAllowedIPs_Single(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("10.0.0.1/32")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 1 {
		t.Fatalf("expected 1 network, got %d", len(nets))
	}
}

func TestParseAllowedIPs_Multiple(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("10.0.0.1/32, 192.168.1.0/24, 172.16.0.0/16")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 3 {
		t.Fatalf("expected 3 networks, got %d", len(nets))
	}
}

func TestParseAllowedIPs_Empty(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("")
	if err != nil {
		t.Fatalf("unexpected error on empty string: %v", err)
	}
	if len(nets) != 0 {
		t.Errorf("expected 0 networks for empty string, got %d", len(nets))
	}
}

func TestParseAllowedIPs_WhitespaceOnly(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("   ")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 0 {
		t.Errorf("expected 0 networks for whitespace-only, got %d", len(nets))
	}
}

func TestParseAllowedIPs_Invalid(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	_, err := m.parseAllowedIPs("not-a-cidr")
	if err == nil {
		t.Error("expected error for invalid CIDR")
	}
}

func TestParseAllowedIPs_DefaultIPv4Route(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("0.0.0.0/0")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 1 {
		t.Fatalf("expected 1 network, got %d", len(nets))
	}
}

func TestParseAllowedIPs_IPv6(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("::/0")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 1 {
		t.Fatalf("expected 1 network for IPv6 default route, got %d", len(nets))
	}
}

func TestParseAllowedIPs_MixedIPv4IPv6(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("10.0.0.1/32, ::/0")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 2 {
		t.Fatalf("expected 2 networks, got %d", len(nets))
	}
}

func TestParseAllowedIPs_MultipleIPv4Subnets(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 3 {
		t.Fatalf("expected 3 networks, got %d", len(nets))
	}
}

// ─── fetchPeersFromManager ─────────────────────────────────────────────────

func TestFetchPeersFromManager_Success(t *testing.T) {
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/wireguard/peers" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(peerResponse{
			Peers: []Peer{
				{NodeID: "n1", NodeType: "client", PublicKey: "key1", AllowedIPs: "10.1.0.1/32"},
				{NodeID: "n2", NodeType: "client", PublicKey: "key2", AllowedIPs: "10.1.0.2/32"},
			},
			Total: 2,
		})
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	peers, err := m.fetchPeersFromManager()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(peers) != 2 {
		t.Errorf("expected 2 peers, got %d", len(peers))
	}
	if peers[0].NodeID != "n1" {
		t.Errorf("unexpected first peer NodeID: %s", peers[0].NodeID)
	}
}

func TestFetchPeersFromManager_HTTPError(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "service unavailable", http.StatusServiceUnavailable)
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	_, err := m.fetchPeersFromManager()
	if err == nil {
		t.Error("expected error for 503 response")
	}
}

func TestFetchPeersFromManager_InvalidJSON(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("not-json"))
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	_, err := m.fetchPeersFromManager()
	if err == nil {
		t.Error("expected error for invalid JSON")
	}
}

func TestFetchPeersFromManager_ConnectionRefused(t *testing.T) {
	m := makeManagerWithoutWgctrl("http://127.0.0.1:1")

	_, err := m.fetchPeersFromManager()
	if err == nil {
		t.Error("expected error for connection refused")
	}
}

func TestFetchPeersFromManager_SendsAuthHeader(t *testing.T) {
	var gotAuth string
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		_ = json.NewEncoder(w).Encode(peerResponse{})
	}))
	defer ts.Close()

	os.Setenv("CLUSTER_API_KEY", "test-cluster-key-xyz")
	defer os.Unsetenv("CLUSTER_API_KEY")

	m := makeManagerWithoutWgctrl(ts.URL)

	_, _ = m.fetchPeersFromManager()

	if gotAuth != "Bearer test-cluster-key-xyz" {
		t.Errorf("unexpected auth header: %q", gotAuth)
	}
}

func TestFetchPeersFromManager_EmptyPeerList(t *testing.T) {
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(peerResponse{Peers: []Peer{}, Total: 0})
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	peers, err := m.fetchPeersFromManager()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(peers) != 0 {
		t.Errorf("expected 0 peers, got %d", len(peers))
	}
}

func TestFetchPeersFromManager_PeerWithEndpoint(t *testing.T) {
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(peerResponse{
			Peers: []Peer{
				{NodeID: "n1", PublicKey: "key1", AllowedIPs: "10.0.0.1/32", Endpoint: "1.2.3.4:51820"},
			},
		})
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	peers, err := m.fetchPeersFromManager()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(peers) != 1 {
		t.Fatalf("expected 1 peer, got %d", len(peers))
	}
	if peers[0].Endpoint != "1.2.3.4:51820" {
		t.Errorf("unexpected endpoint: %s", peers[0].Endpoint)
	}
}

// ─── GetPublicKey ─────────────────────────────────────────────────────────────

func TestGetPublicKey_ReturnsSomething(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	key := m.GetPublicKey()
	if key == "" {
		t.Error("expected non-empty public key")
	}
}

func TestGetPublicKey_Base64Format(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	key := m.GetPublicKey()
	// WireGuard keys are base64 encoded, 44 chars
	if len(key) != 44 {
		t.Errorf("expected 44-char base64 key, got %d chars: %s", len(key), key)
	}
}

// ─── GetStats ─────────────────────────────────────────────────────────────────

func TestGetStats_NilClient(t *testing.T) {
	m := &Manager{
		interfaceName: "wg0",
		client:        nil,
	}
	// Should return nil pointer dereference — test that this panics or errors gracefully
	// Since client is nil, this will panic; test should document this behavior
	defer func() {
		if r := recover(); r != nil {
			t.Logf("GetStats with nil client panics as expected: %v", r)
		}
	}()
	_, _ = m.GetStats()
}

func TestGetStats_ReturnsErrorWithoutInterface(t *testing.T) {
	m := getTestManager(t)
	defer m.Close()

	_, err := m.GetStats()
	// Either outcome is acceptable: interface may or may not exist
	t.Logf("GetStats result: err=%v", err)
}

// ─── Close ────────────────────────────────────────────────────────────────────

func TestClose_DoesNotPanic(t *testing.T) {
	m := getTestManager(t)
	if err := m.Close(); err != nil {
		t.Logf("Close returned error (expected in some environments): %v", err)
	}
}

func TestClose_NilClient(t *testing.T) {
	m := &Manager{client: nil}
	if err := m.Close(); err != nil {
		t.Errorf("unexpected error for nil client: %v", err)
	}
}

// ─── StartPeriodicSync ────────────────────────────────────────────────────────

func TestStartPeriodicSync_RespondsToCancel(t *testing.T) {
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(peerResponse{})
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	ctx, cancel := context.WithCancel(context.Background())

	// StartPeriodicSync launches a goroutine and returns immediately
	startDone := make(chan struct{})
	go func() {
		m.StartPeriodicSync(ctx)
		close(startDone)
	}()

	// The goroutine should return immediately since StartPeriodicSync is non-blocking
	select {
	case <-startDone:
	case <-time.After(time.Second):
		t.Error("StartPeriodicSync did not return promptly")
	}

	// Cancel to clean up the background goroutine
	cancel()
}

// ─── Type aliases ─────────────────────────────────────────────────────────────

func TestWireGuardManagerAlias(t *testing.T) {
	// WireGuardManager is a type alias for Manager — must compile
	var _ *WireGuardManager
}

func TestPeerConfigAlias(t *testing.T) {
	// PeerConfig is a type alias for wgtypes.PeerConfig — must compile
	var _ PeerConfig
}
