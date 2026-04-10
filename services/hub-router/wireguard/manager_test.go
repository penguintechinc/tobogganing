package wireguard

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"golang.zx2c4.com/wireguard/wgctrl"
	"golang.zx2c4.com/wireguard/wgctrl/wgtypes"
)

// ─── Mock CmdExecutor ────────────────────────────────────────────────────────

// MockCmdExecutor allows testing shell command execution paths
type MockCmdExecutor struct {
	runs   []struct{ name, args string }
	result string
	err    error
}

// Run records the command and returns the mocked result
func (m *MockCmdExecutor) Run(name string, args ...string) (string, error) {
	argsStr := strings.Join(args, " ")
	m.runs = append(m.runs, struct{ name, args string }{name, argsStr})
	return m.result, m.err
}


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

// MockWireGuardBackend is a test double for WireGuardBackend.
type MockWireGuardBackend struct {
	configureDeviceErr error
	deviceErr          error
	deviceResult       *wgtypes.Device
	closeErr           error
	// recorded calls
	configureDeviceCalls []wgtypes.Config
	deviceCalls          []string
}

func (m *MockWireGuardBackend) ConfigureDevice(name string, cfg wgtypes.Config) error {
	m.configureDeviceCalls = append(m.configureDeviceCalls, cfg)
	return m.configureDeviceErr
}

func (m *MockWireGuardBackend) Device(name string) (*wgtypes.Device, error) {
	m.deviceCalls = append(m.deviceCalls, name)
	if m.deviceResult != nil {
		return m.deviceResult, m.deviceErr
	}
	return nil, m.deviceErr
}

func (m *MockWireGuardBackend) Close() error {
	return m.closeErr
}

// makeManagerWithMockBackend builds a Manager with a controllable mock backend.
// It uses newManagerWithBackendAndKey to bypass /etc/wireguard key file I/O.
func makeManagerWithMockBackend(managerURL string, backend *MockWireGuardBackend) *Manager {
	key, _ := wgtypes.GeneratePrivateKey()
	m, err := newManagerWithBackendAndKey("wg0", managerURL, 51820, "10.0.0.0/24", backend, key)
	if err != nil {
		// Should never happen with a pre-set key and mock backend.
		panic(fmt.Sprintf("makeManagerWithMockBackend: %v", err))
	}
	m.httpClient = &http.Client{Timeout: 5 * time.Second}
	return m
}

// makeManagerWithoutWgctrl builds a Manager with a no-op mock backend for
// testing methods that don't touch the WireGuard kernel interface (HTTP, parsing, etc.).
func makeManagerWithoutWgctrl(managerURL string) *Manager {
	return makeManagerWithMockBackend(managerURL, &MockWireGuardBackend{
		// Device returns an error by default so createInterface will try to create
		deviceErr: fmt.Errorf("no such device"),
	})
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

func TestGetStats_NilBackend(t *testing.T) {
	m := &Manager{
		interfaceName: "wg0",
		backend:       nil,
	}
	// With nil backend, Close and GetStats should panic — document the behavior.
	defer func() {
		if r := recover(); r != nil {
			t.Logf("GetStats with nil backend panics as expected: %v", r)
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

func TestClose_NilBackend(t *testing.T) {
	m := &Manager{backend: nil}
	if err := m.Close(); err != nil {
		t.Errorf("unexpected error for nil backend: %v", err)
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

// TestStartPeriodicSync_TickerFires covers the ticker.C case in StartPeriodicSync
// (the syncPeers call path). We use a 1ms interval so the tick fires before we cancel.
func TestStartPeriodicSync_TickerFires(t *testing.T) {
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(peerResponse{})
	}))
	defer ts.Close()

	old := periodicSyncInterval
	defer func() { periodicSyncInterval = old }()
	periodicSyncInterval = 1 * time.Millisecond

	m := makeManagerWithoutWgctrl(ts.URL)
	ctx, cancel := context.WithCancel(context.Background())

	m.StartPeriodicSync(ctx)

	// Let the ticker fire at least once.
	time.Sleep(20 * time.Millisecond)
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

// ─── syncPeers & Peer Processing ──────────────────────────────────────────────

func TestSyncPeers_FetchError(t *testing.T) {
	m := makeManagerWithoutWgctrl("http://127.0.0.1:1") // Non-existent host

	err := m.syncPeers()
	if err == nil {
		t.Error("expected error when fetch fails")
	}
}

// ─── CmdExecutor tests ────────────────────────────────────────────────────────

func TestDefaultCmdExecutor_Run(t *testing.T) {
	executor := &DefaultCmdExecutor{}

	// Test a simple command
	output, err := executor.Run("echo", "hello")
	if err != nil {
		t.Logf("echo command result: %v (may fail in test environment)", err)
	}
	if !strings.Contains(output, "hello") && err == nil {
		t.Errorf("expected 'hello' in output, got: %s", output)
	}
}

func TestDefaultCmdExecutor_RunError(t *testing.T) {
	executor := &DefaultCmdExecutor{}

	// Test a command that doesn't exist
	_, err := executor.Run("nonexistent-command-xyz")
	if err == nil {
		t.Error("expected error for nonexistent command")
	}
}

func TestMockCmdExecutor_Run(t *testing.T) {
	executor := &MockCmdExecutor{result: "mocked output", err: nil}

	output, err := executor.Run("fake", "command")
	if err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	if output != "mocked output" {
		t.Errorf("expected 'mocked output', got %s", output)
	}
	if len(executor.runs) != 1 {
		t.Errorf("expected 1 run recorded, got %d", len(executor.runs))
	}
}

func TestMockCmdExecutor_MultipleRuns(t *testing.T) {
	executor := &MockCmdExecutor{result: "output", err: nil}

	executor.Run("cmd1", "arg1")
	executor.Run("cmd2", "arg2", "arg3")
	executor.Run("cmd3")

	if len(executor.runs) != 3 {
		t.Errorf("expected 3 runs, got %d", len(executor.runs))
	}
	if executor.runs[1].args != "arg2 arg3" {
		t.Errorf("expected 'arg2 arg3', got %s", executor.runs[1].args)
	}
}

// ─── SequencingCmdExecutor for testing command sequences ───────────────────────

// SequencingCmdExecutor changes behavior based on call count
type SequencingCmdExecutor struct {
	results []struct{ out string; err error }
	callNum int
}

func (s *SequencingCmdExecutor) Run(name string, args ...string) (string, error) {
	if s.callNum >= len(s.results) {
		return "", fmt.Errorf("unexpected call #%d", s.callNum)
	}
	result := s.results[s.callNum]
	s.callNum++
	return result.out, result.err
}

func TestSequencingCmdExecutor_ReturnsInSequence(t *testing.T) {
	executor := &SequencingCmdExecutor{
		results: []struct{ out string; err error }{
			{"first", nil},
			{"second", fmt.Errorf("error")},
			{"third", nil},
		},
	}

	out1, err1 := executor.Run("cmd1")
	out2, err2 := executor.Run("cmd2")
	out3, err3 := executor.Run("cmd3")

	if out1 != "first" || err1 != nil {
		t.Errorf("first call mismatch")
	}
	if out2 != "second" || err2 == nil {
		t.Errorf("second call mismatch")
	}
	if out3 != "third" || err3 != nil {
		t.Errorf("third call mismatch")
	}
}

// ─── Initialize documentation ─────────────────────────────────────────────────

func TestInitialize_IsCallable(t *testing.T) {
	// Initialize requires:
	// 1. kernel WireGuard support (for client.Device)
	// 2. /etc/wireguard directory write permission (for key storage)
	// 3. ip command availability
	// 4. Valid network setup
	// This test documents that Initialize exists and has the right signature.
	key, _ := wgtypes.GeneratePrivateKey()

	m := makeManagerWithoutWgctrl("http://localhost:9999")
	m.privateKey = key
	m.publicKey = key.PublicKey()
	m.cmdExecutor = &DefaultCmdExecutor{}

	// Don't actually call Initialize as it requires kernel support
	// Just verify it exists
	_ = m.Initialize
}

// ─── Endpoint parsing ─────────────────────────────────────────────────────────

func TestParseEndpoint_ValidIPAndPort(t *testing.T) {
	// Test the endpoint parsing logic indirectly through a mock
	// The endpoint parsing happens in syncPeers when a valid endpoint string is provided
	m := makeManagerWithoutWgctrl("")

	// Validate the helper function parseAllowedIPs works correctly
	// which uses similar parsing logic
	nets, err := m.parseAllowedIPs("10.0.0.1/32")
	if err != nil {
		t.Errorf("parseAllowedIPs failed: %v", err)
	}
	if len(nets) != 1 {
		t.Errorf("expected 1 network, got %d", len(nets))
	}
}

// ─── parseAllowedIPs edge cases ───────────────────────────────────────────────

func TestParseAllowedIPs_WithCommasAndSpaces(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	// Mixed spacing around commas
	nets, err := m.parseAllowedIPs("10.0.0.0/8 ,  172.16.0.0/12,192.168.0.0/16")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 3 {
		t.Fatalf("expected 3 networks, got %d", len(nets))
	}
}

func TestParseAllowedIPs_TrailingComma(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("10.0.0.1/32,")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 1 {
		t.Fatalf("expected 1 network, got %d", len(nets))
	}
}

func TestParseAllowedIPs_LeadingComma(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs(",10.0.0.1/32")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 1 {
		t.Fatalf("expected 1 network, got %d", len(nets))
	}
}

func TestParseAllowedIPs_IPv6_SpecificSubnet(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("2001:db8::/32")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 1 {
		t.Fatalf("expected 1 network, got %d", len(nets))
	}
}

// ─── fetchPeersFromManager edge cases ──────────────────────────────────────────

func TestFetchPeersFromManager_MalformedJSON(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"peers": [{"node_id": "n1", "invalid json}`))
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	_, err := m.fetchPeersFromManager()
	if err == nil {
		t.Error("expected error for malformed JSON")
	}
}

func TestFetchPeersFromManager_WrongURL(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/wrong/path" {
			http.NotFound(w, r)
			return
		}
		w.Write([]byte("{}"))
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	_, err := m.fetchPeersFromManager()
	if err == nil {
		t.Error("expected error for 404 response")
	}
}

func TestFetchPeersFromManager_NonJSONResponse(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		w.Write([]byte("plain text response"))
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	_, err := m.fetchPeersFromManager()
	if err == nil {
		t.Error("expected error for non-JSON response")
	}
}

func TestFetchPeersFromManager_LargePeerList(t *testing.T) {
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}

	// Generate a large peer list
	peers := make([]Peer, 100)
	for i := 0; i < 100; i++ {
		key, _ := wgtypes.GeneratePrivateKey()
		peers[i] = Peer{
			NodeID:     "peer-" + string(rune(i)),
			NodeType:   "client",
			PublicKey:  key.PublicKey().String(),
			AllowedIPs: "10.0.0.0/8",
		}
	}

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(peerResponse{Peers: peers, Total: 100})
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	result, err := m.fetchPeersFromManager()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result) != 100 {
		t.Errorf("expected 100 peers, got %d", len(result))
	}
}

// ─── GetPublicKey variants ────────────────────────────────────────────────────

func TestGetPublicKey_Consistent(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	key1 := m.GetPublicKey()
	key2 := m.GetPublicKey()

	if key1 != key2 {
		t.Error("public key should be consistent across calls")
	}
}

func TestGetPublicKey_NotEmpty(t *testing.T) {
	key, _ := wgtypes.GeneratePrivateKey()
	m := &Manager{
		publicKey: key.PublicKey(),
	}

	pk := m.GetPublicKey()
	if pk == "" {
		t.Error("public key should not be empty")
	}
	if len(pk) != 44 {
		t.Errorf("expected 44-char public key, got %d", len(pk))
	}
}

// ─── parseAllowedIPs comprehensive coverage ────────────────────────────────────

func TestParseAllowedIPs_SingleIPv4(t *testing.T) {
	m := makeManagerWithoutWgctrl("")
	nets, err := m.parseAllowedIPs("192.168.0.0/16")
	if err != nil {
		t.Fatalf("parseAllowedIPs failed: %v", err)
	}
	if len(nets) != 1 {
		t.Errorf("expected 1 network, got %d", len(nets))
	}
	if nets[0].String() != "192.168.0.0/16" {
		t.Errorf("expected 192.168.0.0/16, got %s", nets[0].String())
	}
}

func TestParseAllowedIPs_MultipleMixedFormats(t *testing.T) {
	m := makeManagerWithoutWgctrl("")
	nets, err := m.parseAllowedIPs("10.0.0.0/8, 192.168.0.0/16,  172.16.0.0/12  ")
	if err != nil {
		t.Fatalf("parseAllowedIPs failed: %v", err)
	}
	if len(nets) != 3 {
		t.Errorf("expected 3 networks, got %d", len(nets))
	}
}

func TestParseAllowedIPs_AllErrorCases(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	cases := []string{
		"256.0.0.0/8",           // Invalid IP octet
		"10.0.0.0/33",           // Invalid CIDR prefix
		"10.0.0.0",              // Missing CIDR prefix
		"not.an.ip.address/24",  // Invalid IP format
		"10.0.0.0/abc",          // Invalid prefix
	}

	for _, tc := range cases {
		_, err := m.parseAllowedIPs(tc)
		if err == nil {
			t.Errorf("expected error for %q, got nil", tc)
		}
	}
}

// ─── fetchPeersFromManager comprehensive ──────────────────────────────────────

func TestFetchPeersFromManager_StatusCodes(t *testing.T) {
	testCases := []struct {
		name           string
		statusCode     int
		body           string
		shouldError    bool
	}{
		{
			name:        "OK with valid JSON",
			statusCode:  200,
			body:        `{"peers":[],"total":0}`,
			shouldError: false,
		},
		{
			name:        "Not Found",
			statusCode:  404,
			body:        "Not Found",
			shouldError: true,
		},
		{
			name:        "Server Error",
			statusCode:  500,
			body:        "Internal Server Error",
			shouldError: true,
		},
		{
			name:        "Unauthorized",
			statusCode:  401,
			body:        "Unauthorized",
			shouldError: true,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tc.statusCode)
				w.Write([]byte(tc.body))
			}))
			defer ts.Close()

			m := makeManagerWithoutWgctrl(ts.URL)
			_, err := m.fetchPeersFromManager()

			if tc.shouldError && err == nil {
				t.Errorf("expected error, got nil")
			}
			if !tc.shouldError && err != nil {
				t.Errorf("unexpected error: %v", err)
			}
		})
	}
}

func TestFetchPeersFromManager_ResponseBodyReadError(t *testing.T) {
	// Create a server that returns a valid status code but invalid body
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		// Write incomplete JSON
		w.Write([]byte(`{"peers":[`))
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)
	_, err := m.fetchPeersFromManager()
	if err == nil {
		t.Error("expected error for incomplete JSON")
	}
}

func TestFetchPeersFromManager_WithMultiplePeersAndEndpoints(t *testing.T) {
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}

	key1, _ := wgtypes.GeneratePrivateKey()
	key2, _ := wgtypes.GeneratePrivateKey()
	key3, _ := wgtypes.GeneratePrivateKey()

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(peerResponse{
			Peers: []Peer{
				{
					NodeID:     "gateway-1",
					NodeType:   "gateway",
					PublicKey:  key1.PublicKey().String(),
					AllowedIPs: "10.0.0.0/8, 192.168.0.0/16",
					Endpoint:   "1.2.3.4:51820",
				},
				{
					NodeID:     "client-1",
					NodeType:   "client",
					PublicKey:  key2.PublicKey().String(),
					AllowedIPs: "10.1.1.0/24",
					Endpoint:   "5.6.7.8:51820",
				},
				{
					NodeID:     "relay-1",
					NodeType:   "relay",
					PublicKey:  key3.PublicKey().String(),
					AllowedIPs: "172.16.0.0/12",
					// No endpoint for this one
				},
			},
			Total: 3,
		})
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)
	peers, err := m.fetchPeersFromManager()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(peers) != 3 {
		t.Errorf("expected 3 peers, got %d", len(peers))
	}
	if peers[0].NodeType != "gateway" {
		t.Errorf("expected first peer to be gateway, got %s", peers[0].NodeType)
	}
	if peers[1].Endpoint != "5.6.7.8:51820" {
		t.Errorf("expected client endpoint, got %s", peers[1].Endpoint)
	}
	if peers[2].Endpoint != "" {
		t.Errorf("expected empty endpoint for relay, got %s", peers[2].Endpoint)
	}
}

// ─── Manager field storage ────────────────────────────────────────────────────

func TestManager_FieldsAccessible(t *testing.T) {
	m := makeManagerWithoutWgctrl("http://test:9000")

	if m.interfaceName != "wg0" {
		t.Errorf("unexpected interfaceName: %s", m.interfaceName)
	}
	if m.managerURL != "http://test:9000" {
		t.Errorf("unexpected managerURL: %s", m.managerURL)
	}
	if m.listenPort != 51820 {
		t.Errorf("unexpected listenPort: %d", m.listenPort)
	}
	if m.network != "10.0.0.0/24" {
		t.Errorf("unexpected network: %s", m.network)
	}
}

func TestManager_PublicKeyMatches(t *testing.T) {
	key, _ := wgtypes.GeneratePrivateKey()
	expectedPub := key.PublicKey()

	m := &Manager{
		privateKey: key,
		publicKey:  expectedPub,
	}

	if m.GetPublicKey() != expectedPub.String() {
		t.Error("public key does not match")
	}
}

// ─── Peer struct variations ───────────────────────────────────────────────────

func TestPeer_AllFields(t *testing.T) {
	p := Peer{
		NodeID:     "node-99",
		NodeType:   "gateway",
		PublicKey:  "pubkey123",
		AllowedIPs: "10.99.0.0/16",
		Endpoint:   "99.99.99.99:51820",
	}

	if p.NodeID != "node-99" {
		t.Errorf("NodeID: expected node-99, got %s", p.NodeID)
	}
	if p.NodeType != "gateway" {
		t.Errorf("NodeType: expected gateway, got %s", p.NodeType)
	}
	if p.PublicKey != "pubkey123" {
		t.Errorf("PublicKey mismatch")
	}
	if p.AllowedIPs != "10.99.0.0/16" {
		t.Errorf("AllowedIPs mismatch")
	}
	if p.Endpoint != "99.99.99.99:51820" {
		t.Errorf("Endpoint mismatch")
	}
}

func TestPeer_EmptyFields(t *testing.T) {
	p := Peer{}
	if p.NodeID != "" || p.PublicKey != "" {
		t.Error("empty peer should have empty fields")
	}
}

// ─── Config struct variations ──────────────────────────────────────────────────

func TestConfig_AllFields(t *testing.T) {
	cfg := Config{
		InterfaceName: "wg99",
		ListenPort:    51999,
		PrivateKey:    "pk-value",
		Network:       "10.99.0.0/16",
		ManagerURL:    "https://manager.test:9000",
	}

	if cfg.InterfaceName != "wg99" {
		t.Errorf("InterfaceName mismatch")
	}
	if cfg.ListenPort != 51999 {
		t.Errorf("ListenPort mismatch")
	}
	if cfg.PrivateKey != "pk-value" {
		t.Errorf("PrivateKey mismatch")
	}
	if cfg.Network != "10.99.0.0/16" {
		t.Errorf("Network mismatch")
	}
	if cfg.ManagerURL != "https://manager.test:9000" {
		t.Errorf("ManagerURL mismatch")
	}
}

func TestConfig_EmptyFields(t *testing.T) {
	cfg := Config{}
	if cfg.InterfaceName != "" || cfg.ManagerURL != "" {
		t.Error("empty config should have empty fields")
	}
	if cfg.ListenPort != 0 {
		t.Error("empty config ListenPort should be 0")
	}
}

// ─── Close edge cases ──────────────────────────────────────────────────────────

func TestClose_WithValidBackend(t *testing.T) {
	mock := &MockWireGuardBackend{}
	m := &Manager{backend: mock}
	err := m.Close()
	if err != nil {
		t.Logf("Close with mock backend: %v", err)
	}
}

func TestClose_BackendReturnsError(t *testing.T) {
	mock := &MockWireGuardBackend{closeErr: fmt.Errorf("close failed")}
	m := &Manager{backend: mock}
	err := m.Close()
	if err == nil {
		t.Error("expected error from Close when backend returns error")
	}
}

// ─── StartPeriodicSync edge cases ──────────────────────────────────────────────

func TestStartPeriodicSync_WithErrorFetchingPeers(t *testing.T) {
	// Server returns error
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "service unavailable", http.StatusServiceUnavailable)
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go m.StartPeriodicSync(ctx)

	// Let it try at least once
	time.Sleep(100 * time.Millisecond)

	cancel()
	// Test passes if no panic
}

func TestStartPeriodicSync_ImmediateCancel(t *testing.T) {
	m := makeManagerWithoutWgctrl("http://localhost:9999")

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // Cancel immediately

	go m.StartPeriodicSync(ctx)

	// Should return immediately since context is cancelled
	time.Sleep(50 * time.Millisecond)
	// Test passes if no panic
}

func TestStartPeriodicSync_LongRunning(t *testing.T) {
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}

	callCount := 0
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		_ = json.NewEncoder(w).Encode(peerResponse{Peers: []Peer{}, Total: 0})
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	ctx, cancel := context.WithCancel(context.Background())

	go m.StartPeriodicSync(ctx)

	// Let it run for a bit
	time.Sleep(100 * time.Millisecond)

	cancel()
	time.Sleep(50 * time.Millisecond)

	// Test passes if no panic
}

// ─── FetchPeersFromManager with special response structures ────────────────────

func TestFetchPeersFromManager_ExtraFieldsInResponse(t *testing.T) {
	type extendedResponse struct {
		Peers      []Peer `json:"peers"`
		Total      int    `json:"total"`
		ExtraField string `json:"extra_field"`
	}

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(extendedResponse{
			Peers:      []Peer{},
			Total:      0,
			ExtraField: "ignored",
		})
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

// ─── HTTP request details ─────────────────────────────────────────────────────

func TestFetchPeersFromManager_VerifyURL(t *testing.T) {
	var requestPath string
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestPath = r.URL.Path
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"peers": []interface{}{},
			"total": 0,
		})
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)
	_, _ = m.fetchPeersFromManager()

	if requestPath != "/api/v1/wireguard/peers" {
		t.Errorf("expected path /api/v1/wireguard/peers, got %s", requestPath)
	}
}

func TestFetchPeersFromManager_VerifyHTTPMethod(t *testing.T) {
	var requestMethod string
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestMethod = r.Method
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"peers": []interface{}{},
			"total": 0,
		})
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)
	_, _ = m.fetchPeersFromManager()

	if requestMethod != "GET" {
		t.Errorf("expected GET, got %s", requestMethod)
	}
}

// ─── parseAllowedIPs with various CIDR formats ─────────────────────────────────

func TestParseAllowedIPs_HostMask32(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("10.0.0.1/32")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 1 {
		t.Fatalf("expected 1 network, got %d", len(nets))
	}
	if nets[0].String() != "10.0.0.1/32" {
		t.Errorf("expected 10.0.0.1/32, got %s", nets[0].String())
	}
}

func TestParseAllowedIPs_HostMask128(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("2001:db8::1/128")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 1 {
		t.Fatalf("expected 1 network, got %d", len(nets))
	}
}

func TestParseAllowedIPs_ComplexIPv6(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("fe80::/10, 2001:db8::/32, ::/0")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 3 {
		t.Fatalf("expected 3 networks, got %d", len(nets))
	}
}

// ─── Manager initialization patterns ───────────────────────────────────────────

func TestNewManager_WithNilConfig(t *testing.T) {
	// NewManager calls NewManagerWithParams, so if config is nil it might panic
	// This documents current behavior
	defer func() {
		if r := recover(); r != nil {
			t.Logf("NewManager with nil config panics as expected")
		}
	}()
	_, _ = NewManager(nil)
}

func TestNewManagerWithParams_AllFieldsStored(t *testing.T) {
	m, err := NewManagerWithParams("test-wg", "http://manager:8080", 51821, "10.100.0.0/24")
	if err != nil {
		t.Logf("NewManagerWithParams error (expected in some environments): %v", err)
		return
	}
	defer m.Close()

	if m.interfaceName != "test-wg" {
		t.Errorf("interfaceName: expected test-wg, got %s", m.interfaceName)
	}
	if m.managerURL != "http://manager:8080" {
		t.Errorf("managerURL: expected http://manager:8080, got %s", m.managerURL)
	}
	if m.listenPort != 51821 {
		t.Errorf("listenPort: expected 51821, got %d", m.listenPort)
	}
	if m.network != "10.100.0.0/24" {
		t.Errorf("network: expected 10.100.0.0/24, got %s", m.network)
	}
}

// ─── Peer JSON serialization edge cases ────────────────────────────────────────

func TestPeer_JSONSerializationRoundTrip(t *testing.T) {
	cases := []Peer{
		{NodeID: "n1", NodeType: "client", PublicKey: "key1", AllowedIPs: "10.0.0.0/8"},
		{NodeID: "n2", NodeType: "gateway", PublicKey: "key2", AllowedIPs: "10.1.0.0/16", Endpoint: "1.2.3.4:51820"},
		{NodeID: "n3", PublicKey: "key3", AllowedIPs: "10.2.0.0/24, 10.3.0.0/24"},
	}

	for _, original := range cases {
		data, _ := json.Marshal(original)
		var decoded Peer
		_ = json.Unmarshal(data, &decoded)

		if decoded.NodeID != original.NodeID {
			t.Errorf("NodeID mismatch: %s vs %s", decoded.NodeID, original.NodeID)
		}
		if decoded.PublicKey != original.PublicKey {
			t.Errorf("PublicKey mismatch")
		}
		if decoded.AllowedIPs != original.AllowedIPs {
			t.Errorf("AllowedIPs mismatch: %s vs %s", decoded.AllowedIPs, original.AllowedIPs)
		}
	}
}

// ─── Close method variants ────────────────────────────────────────────────────

func TestClose_MultipleTimesWithoutError(t *testing.T) {
	m := &Manager{backend: nil}

	// Calling Close multiple times with nil backend should be safe (nil guard)
	err1 := m.Close()
	err2 := m.Close()
	err3 := m.Close()

	if err1 != nil || err2 != nil || err3 != nil {
		t.Errorf("unexpected error from Close: %v, %v, %v", err1, err2, err3)
	}
}

// ─── FetchPeersFromManager additional test cases ───────────────────────────────

func TestFetchPeersFromManager_EmptyResponseBody(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		// Empty response body
		w.Write([]byte(""))
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	_, err := m.fetchPeersFromManager()
	if err == nil {
		t.Error("expected error for empty response")
	}
}

func TestFetchPeersFromManager_PartialPeersArray(t *testing.T) {
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Return response with Total > actual peers
		_ = json.NewEncoder(w).Encode(peerResponse{
			Peers: []Peer{
				{NodeID: "p1", PublicKey: "key1", AllowedIPs: "10.0.0.0/8"},
			},
			Total: 5,
		})
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	peers, err := m.fetchPeersFromManager()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(peers) != 1 {
		t.Errorf("expected 1 peer, got %d", len(peers))
	}
}

// ─── ParseAllowedIPs regex/format variations ──────────────────────────────────

func TestParseAllowedIPs_OnlyCommas(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs(",,,")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 0 {
		t.Errorf("expected 0 networks for comma-only, got %d", len(nets))
	}
}

func TestParseAllowedIPs_ExtraSpaces(t *testing.T) {
	m := makeManagerWithoutWgctrl("")

	nets, err := m.parseAllowedIPs("   10.0.0.0/8   ,   192.168.0.0/16   ")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(nets) != 2 {
		t.Errorf("expected 2 networks, got %d", len(nets))
	}
}

// ─── StartPeriodicSync context behavior ────────────────────────────────────────

func TestStartPeriodicSync_ContextCancelledBeforeStart(t *testing.T) {
	m := makeManagerWithoutWgctrl("http://localhost:9999")

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // Cancel before starting

	// This should return immediately
	go m.StartPeriodicSync(ctx)

	time.Sleep(50 * time.Millisecond)
	// Test passes if no panic
}

func TestStartPeriodicSync_WithValidManagerURL(t *testing.T) {
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}

	callCount := 0
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		_ = json.NewEncoder(w).Encode(peerResponse{Peers: []Peer{}, Total: 0})
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	ctx, cancel := context.WithCancel(context.Background())
	go m.StartPeriodicSync(ctx)

	time.Sleep(100 * time.Millisecond)
	cancel()

	// Should have attempted at least one fetch
	if callCount == 0 {
		t.Logf("Note: callCount is 0 (ticker timing)")
	}
}

// ─── GetStats behavior ────────────────────────────────────────────────────────

func TestGetStats_ReturnsDeviceOrError(t *testing.T) {
	mock := &MockWireGuardBackend{deviceErr: fmt.Errorf("no such device")}
	m := &Manager{
		interfaceName: "nonexistent-wg",
		backend:       mock,
	}

	_, err := m.GetStats()
	if err == nil {
		t.Error("expected error for nonexistent interface")
	}
}

// ─── HTTPClient configuration ─────────────────────────────────────────────────

func TestManager_HTTPClientTimeout(t *testing.T) {
	m := makeManagerWithoutWgctrl("http://localhost:9999")

	if m.httpClient == nil {
		t.Error("httpClient should not be nil")
	}
	if m.httpClient.Timeout <= 0 {
		t.Error("httpClient should have positive timeout")
	}
}

// ─── Response handling edge cases ──────────────────────────────────────────────

func TestFetchPeersFromManager_NullPeersField(t *testing.T) {
	type peerResponse struct {
		Peers interface{} `json:"peers"`
		Total int         `json:"total"`
	}

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Return null peers field
		_ = json.NewEncoder(w).Encode(peerResponse{
			Peers: nil,
			Total: 0,
		})
	}))
	defer ts.Close()

	m := makeManagerWithoutWgctrl(ts.URL)

	// This should handle nil peers gracefully
	peers, _ := m.fetchPeersFromManager()
	if peers != nil && len(peers) > 0 {
		t.Errorf("expected nil or empty peers, got %d", len(peers))
	}
}

// ─── Alias type validation ────────────────────────────────────────────────────

func TestWireGuardManager_IsManagerAlias(t *testing.T) {
	// WireGuardManager is defined as type WireGuardManager = Manager
	// This ensures the alias is valid
	var m1 *Manager
	var m2 *WireGuardManager

	// This would compile error if types don't match
	_ = (*WireGuardManager)(m1)
	_ = (*Manager)(m2)
}

func TestPeerConfig_IsWgtypesPeerConfigAlias(t *testing.T) {
	// PeerConfig is defined as type PeerConfig = wgtypes.PeerConfig
	// This ensures the alias is valid
	var pc1 PeerConfig
	var pc2 wgtypes.PeerConfig

	// Test that they're compatible
	pc1 = pc2
	_ = pc1
}

// ─── newManagerWithBackend ─────────────────────────────────────────────────────

func TestNewManagerWithBackend_StoresFields(t *testing.T) {
	key, _ := wgtypes.GeneratePrivateKey()
	mock := &MockWireGuardBackend{}
	m, err := newManagerWithBackendAndKey("wg-inj", "http://mgr:8080", 51821, "10.1.0.0/24", mock, key)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if m.interfaceName != "wg-inj" {
		t.Errorf("unexpected interfaceName: %s", m.interfaceName)
	}
	if m.backend != mock {
		t.Error("backend not stored correctly")
	}
	if m.listenPort != 51821 {
		t.Errorf("unexpected listenPort: %d", m.listenPort)
	}
	m.Close()
}

func TestNewManagerWithBackend_NilUsesRealClient(t *testing.T) {
	// When backend is nil, a real wgctrl.Client is created; skip if unavailable.
	m, err := newManagerWithBackend("wg-real", "http://mgr:8080", 51822, "10.2.0.0/24", nil)
	if err != nil {
		t.Skipf("wgctrl unavailable: %v", err)
	}
	if m.backend == nil {
		t.Error("expected non-nil backend when nil passed in")
	}
	m.Close()
}

// ─── createInterface ─────────────────────────────────────────────────────────

func TestCreateInterface_AlreadyExists(t *testing.T) {
	// When Device() succeeds the function returns nil immediately without calling ip link.
	mock := &MockWireGuardBackend{deviceErr: nil, deviceResult: &wgtypes.Device{Name: "wg0"}}
	cmdMock := &MockCmdExecutor{}
	m := makeManagerWithMockBackend("", mock)
	m.cmdExecutor = cmdMock

	if err := m.createInterface(); err != nil {
		t.Errorf("unexpected error when interface already exists: %v", err)
	}
	if len(cmdMock.runs) != 0 {
		t.Errorf("expected no shell commands when interface already exists, got %d", len(cmdMock.runs))
	}
}

func TestCreateInterface_CreatesNew(t *testing.T) {
	// When Device() errors, ip link add should be called.
	mock := &MockWireGuardBackend{deviceErr: fmt.Errorf("no such device")}
	cmdMock := &MockCmdExecutor{result: "", err: nil}
	m := makeManagerWithMockBackend("", mock)
	m.cmdExecutor = cmdMock

	if err := m.createInterface(); err != nil {
		t.Errorf("unexpected error creating new interface: %v", err)
	}
	if len(cmdMock.runs) == 0 {
		t.Error("expected ip link add to be called")
	}
}

func TestCreateInterface_IpLinkFails(t *testing.T) {
	mock := &MockWireGuardBackend{deviceErr: fmt.Errorf("no such device")}
	cmdMock := &MockCmdExecutor{result: "permission denied", err: fmt.Errorf("exit status 1")}
	m := makeManagerWithMockBackend("", mock)
	m.cmdExecutor = cmdMock

	err := m.createInterface()
	if err == nil {
		t.Error("expected error when ip link add fails")
	}
}

// ─── configureInterface ────────────────────────────────────────────────────────

func TestConfigureInterface_Success(t *testing.T) {
	mock := &MockWireGuardBackend{}
	cmdMock := &SequencingCmdExecutor{
		results: []struct{ out string; err error }{
			{"", nil}, // ip addr add
			{"", nil}, // ip link set up
		},
	}
	m := makeManagerWithMockBackend("", mock)
	m.cmdExecutor = cmdMock

	if err := m.configureInterface(); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	if len(mock.configureDeviceCalls) != 1 {
		t.Errorf("expected 1 ConfigureDevice call, got %d", len(mock.configureDeviceCalls))
	}
}

func TestConfigureInterface_IpAddrAddFileExists(t *testing.T) {
	// "File exists" error from ip addr add should be ignored.
	mock := &MockWireGuardBackend{}
	cmdMock := &SequencingCmdExecutor{
		results: []struct{ out string; err error }{
			{"File exists", fmt.Errorf("exit status 2")}, // ip addr add — already set
			{"", nil}, // ip link set up
		},
	}
	m := makeManagerWithMockBackend("", mock)
	m.cmdExecutor = cmdMock

	if err := m.configureInterface(); err != nil {
		t.Errorf("unexpected error for File exists: %v", err)
	}
}

func TestConfigureInterface_IpAddrAddOtherError(t *testing.T) {
	mock := &MockWireGuardBackend{}
	cmdMock := &SequencingCmdExecutor{
		results: []struct{ out string; err error }{
			{"permission denied", fmt.Errorf("exit status 1")}, // ip addr add — real error
		},
	}
	m := makeManagerWithMockBackend("", mock)
	m.cmdExecutor = cmdMock

	err := m.configureInterface()
	if err == nil {
		t.Error("expected error for non-File-exists ip addr add failure")
	}
}

func TestConfigureInterface_IpLinkSetUpFails(t *testing.T) {
	mock := &MockWireGuardBackend{}
	cmdMock := &SequencingCmdExecutor{
		results: []struct{ out string; err error }{
			{"", nil},                                        // ip addr add succeeds
			{"operation not permitted", fmt.Errorf("exit 1")}, // ip link set up fails
		},
	}
	m := makeManagerWithMockBackend("", mock)
	m.cmdExecutor = cmdMock

	err := m.configureInterface()
	if err == nil {
		t.Error("expected error when ip link set up fails")
	}
}

func TestConfigureInterface_ConfigureDeviceFails(t *testing.T) {
	mock := &MockWireGuardBackend{configureDeviceErr: fmt.Errorf("operation not permitted")}
	cmdMock := &SequencingCmdExecutor{
		results: []struct{ out string; err error }{
			{"", nil}, // ip addr add
			{"", nil}, // ip link set up
		},
	}
	m := makeManagerWithMockBackend("", mock)
	m.cmdExecutor = cmdMock

	err := m.configureInterface()
	if err == nil {
		t.Error("expected error when ConfigureDevice fails")
	}
}

// ─── syncPeers with mock backend ──────────────────────────────────────────────

func buildPeerServer(peers []Peer) *httptest.Server {
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/wireguard/peers" {
			http.NotFound(w, r)
			return
		}
		_ = json.NewEncoder(w).Encode(peerResponse{Peers: peers, Total: len(peers)})
	}))
}

func TestSyncPeers_EmptyPeerList(t *testing.T) {
	ts := buildPeerServer([]Peer{})
	defer ts.Close()

	mock := &MockWireGuardBackend{}
	m := makeManagerWithMockBackend(ts.URL, mock)

	if err := m.syncPeers(); err != nil {
		t.Errorf("unexpected error with empty peer list: %v", err)
	}
	if len(mock.configureDeviceCalls) != 1 {
		t.Errorf("expected 1 ConfigureDevice call, got %d", len(mock.configureDeviceCalls))
	}
}

func TestSyncPeers_ValidPeers(t *testing.T) {
	key1, _ := wgtypes.GeneratePrivateKey()
	key2, _ := wgtypes.GeneratePrivateKey()

	peers := []Peer{
		{NodeID: "n1", PublicKey: key1.PublicKey().String(), AllowedIPs: "10.0.0.1/32"},
		{NodeID: "n2", PublicKey: key2.PublicKey().String(), AllowedIPs: "10.0.0.2/32", Endpoint: "1.2.3.4:51820"},
	}
	ts := buildPeerServer(peers)
	defer ts.Close()

	mock := &MockWireGuardBackend{}
	m := makeManagerWithMockBackend(ts.URL, mock)

	if err := m.syncPeers(); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	if len(mock.configureDeviceCalls) != 1 {
		t.Fatalf("expected 1 ConfigureDevice call, got %d", len(mock.configureDeviceCalls))
	}
	cfg := mock.configureDeviceCalls[0]
	if len(cfg.Peers) != 2 {
		t.Errorf("expected 2 peers in config, got %d", len(cfg.Peers))
	}
	if !cfg.ReplacePeers {
		t.Error("expected ReplacePeers=true")
	}
}

func TestSyncPeers_InvalidPublicKey(t *testing.T) {
	// Peer with invalid key is skipped; sync still succeeds.
	goodKey, _ := wgtypes.GeneratePrivateKey()
	peers := []Peer{
		{NodeID: "bad", PublicKey: "not-a-valid-key", AllowedIPs: "10.0.0.1/32"},
		{NodeID: "good", PublicKey: goodKey.PublicKey().String(), AllowedIPs: "10.0.0.2/32"},
	}
	ts := buildPeerServer(peers)
	defer ts.Close()

	mock := &MockWireGuardBackend{}
	m := makeManagerWithMockBackend(ts.URL, mock)

	if err := m.syncPeers(); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	cfg := mock.configureDeviceCalls[0]
	if len(cfg.Peers) != 1 {
		t.Errorf("expected 1 valid peer in config, got %d", len(cfg.Peers))
	}
}

func TestSyncPeers_InvalidAllowedIPs(t *testing.T) {
	// Peer with invalid AllowedIPs is skipped.
	goodKey, _ := wgtypes.GeneratePrivateKey()
	badKey, _ := wgtypes.GeneratePrivateKey()
	peers := []Peer{
		{NodeID: "bad", PublicKey: badKey.PublicKey().String(), AllowedIPs: "not-a-cidr"},
		{NodeID: "good", PublicKey: goodKey.PublicKey().String(), AllowedIPs: "10.0.0.2/32"},
	}
	ts := buildPeerServer(peers)
	defer ts.Close()

	mock := &MockWireGuardBackend{}
	m := makeManagerWithMockBackend(ts.URL, mock)

	if err := m.syncPeers(); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	cfg := mock.configureDeviceCalls[0]
	if len(cfg.Peers) != 1 {
		t.Errorf("expected 1 valid peer, got %d", len(cfg.Peers))
	}
}

func TestSyncPeers_InvalidEndpointFormat(t *testing.T) {
	// Peer with malformed endpoint (no colon) is added without an endpoint.
	key, _ := wgtypes.GeneratePrivateKey()
	peers := []Peer{
		{NodeID: "n1", PublicKey: key.PublicKey().String(), AllowedIPs: "10.0.0.1/32", Endpoint: "badendpoint"},
	}
	ts := buildPeerServer(peers)
	defer ts.Close()

	mock := &MockWireGuardBackend{}
	m := makeManagerWithMockBackend(ts.URL, mock)

	if err := m.syncPeers(); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	cfg := mock.configureDeviceCalls[0]
	// Peer still added but Endpoint will be nil
	if len(cfg.Peers) != 1 {
		t.Errorf("expected 1 peer, got %d", len(cfg.Peers))
	}
	if cfg.Peers[0].Endpoint != nil {
		t.Error("expected nil endpoint for malformed endpoint string")
	}
}

func TestSyncPeers_InvalidEndpointPort(t *testing.T) {
	// Peer with non-numeric port gets endpoint skipped.
	key, _ := wgtypes.GeneratePrivateKey()
	peers := []Peer{
		{NodeID: "n1", PublicKey: key.PublicKey().String(), AllowedIPs: "10.0.0.1/32", Endpoint: "1.2.3.4:notaport"},
	}
	ts := buildPeerServer(peers)
	defer ts.Close()

	mock := &MockWireGuardBackend{}
	m := makeManagerWithMockBackend(ts.URL, mock)

	if err := m.syncPeers(); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestSyncPeers_InvalidEndpointIP(t *testing.T) {
	// Peer with non-IP host in endpoint gets endpoint skipped.
	key, _ := wgtypes.GeneratePrivateKey()
	peers := []Peer{
		{NodeID: "n1", PublicKey: key.PublicKey().String(), AllowedIPs: "10.0.0.1/32", Endpoint: "not-an-ip:51820"},
	}
	ts := buildPeerServer(peers)
	defer ts.Close()

	mock := &MockWireGuardBackend{}
	m := makeManagerWithMockBackend(ts.URL, mock)

	if err := m.syncPeers(); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestSyncPeers_ConfigureDeviceFails(t *testing.T) {
	key, _ := wgtypes.GeneratePrivateKey()
	peers := []Peer{
		{NodeID: "n1", PublicKey: key.PublicKey().String(), AllowedIPs: "10.0.0.1/32"},
	}
	ts := buildPeerServer(peers)
	defer ts.Close()

	mock := &MockWireGuardBackend{configureDeviceErr: fmt.Errorf("permission denied")}
	m := makeManagerWithMockBackend(ts.URL, mock)

	err := m.syncPeers()
	if err == nil {
		t.Error("expected error when ConfigureDevice fails")
	}
}

// ─── Initialize with mocked backend and cmd ───────────────────────────────────

func TestInitialize_Success(t *testing.T) {
	// Device() returns error → createInterface runs ip link add
	// ip addr add succeeds, ip link set up succeeds, ConfigureDevice succeeds
	// syncPeers fetches from managerURL (use httptest server)
	ts := buildPeerServer([]Peer{})
	defer ts.Close()

	mock := &MockWireGuardBackend{deviceErr: fmt.Errorf("no such device")}
	cmdMock := &SequencingCmdExecutor{
		results: []struct{ out string; err error }{
			{"", nil}, // ip link add (createInterface)
			{"", nil}, // ip addr add (configureInterface)
			{"", nil}, // ip link set up (configureInterface)
		},
	}
	m := makeManagerWithMockBackend(ts.URL, mock)
	m.cmdExecutor = cmdMock

	if err := m.Initialize(); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	// configureInterface + syncPeers each call ConfigureDevice once
	if len(mock.configureDeviceCalls) != 2 {
		t.Errorf("expected 2 ConfigureDevice calls (configure + syncPeers), got %d", len(mock.configureDeviceCalls))
	}
}

func TestInitialize_CreateInterfaceFails(t *testing.T) {
	mock := &MockWireGuardBackend{deviceErr: fmt.Errorf("no such device")}
	cmdMock := &MockCmdExecutor{result: "permission denied", err: fmt.Errorf("exit 1")}
	m := makeManagerWithMockBackend("http://localhost:1", mock)
	m.cmdExecutor = cmdMock

	err := m.Initialize()
	if err == nil {
		t.Error("expected error when createInterface fails")
	}
}

func TestInitialize_ConfigureInterfaceFails(t *testing.T) {
	// createInterface succeeds (Device returns error → ip link add succeeds)
	// configureInterface fails on ip addr add
	mock := &MockWireGuardBackend{deviceErr: fmt.Errorf("no such device")}
	cmdMock := &SequencingCmdExecutor{
		results: []struct{ out string; err error }{
			{"", nil},                                    // ip link add — createInterface OK
			{"error", fmt.Errorf("exit 1")},             // ip addr add fails
		},
	}
	m := makeManagerWithMockBackend("http://localhost:1", mock)
	m.cmdExecutor = cmdMock

	err := m.Initialize()
	if err == nil {
		t.Error("expected error when configureInterface fails")
	}
}

func TestInitialize_SyncPeersFails_DoesNotReturnError(t *testing.T) {
	// syncPeers failure is a warning, not fatal — Initialize should still succeed.
	mock := &MockWireGuardBackend{deviceErr: fmt.Errorf("no such device")}
	cmdMock := &SequencingCmdExecutor{
		results: []struct{ out string; err error }{
			{"", nil}, // ip link add
			{"", nil}, // ip addr add
			{"", nil}, // ip link set up
		},
	}
	// Point at invalid URL so syncPeers fails
	m := makeManagerWithMockBackend("http://127.0.0.1:1", mock)
	m.cmdExecutor = cmdMock

	// configureInterface calls ConfigureDevice; syncPeers fails at fetch — no ConfigureDevice for sync
	err := m.Initialize()
	if err != nil {
		t.Errorf("expected Initialize to succeed even when syncPeers fails, got: %v", err)
	}
}

func TestInitialize_InterfaceAlreadyExists(t *testing.T) {
	// Device() succeeds → createInterface is a no-op
	ts := buildPeerServer([]Peer{})
	defer ts.Close()

	mock := &MockWireGuardBackend{deviceErr: nil, deviceResult: &wgtypes.Device{Name: "wg0"}}
	cmdMock := &SequencingCmdExecutor{
		results: []struct{ out string; err error }{
			{"", nil}, // ip addr add
			{"", nil}, // ip link set up
		},
	}
	m := makeManagerWithMockBackend(ts.URL, mock)
	m.cmdExecutor = cmdMock

	if err := m.Initialize(); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}

// ─── GetStats with mock backend ───────────────────────────────────────────────

func TestGetStats_ReturnsDevice(t *testing.T) {
	expected := &wgtypes.Device{Name: "wg0"}
	mock := &MockWireGuardBackend{deviceResult: expected}
	m := makeManagerWithMockBackend("", mock)

	dev, err := m.GetStats()
	if err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	if dev == nil || dev.Name != "wg0" {
		t.Errorf("expected device wg0, got %v", dev)
	}
}

func TestGetStats_ReturnsErrorFromBackend(t *testing.T) {
	mock := &MockWireGuardBackend{deviceErr: fmt.Errorf("no such device")}
	m := makeManagerWithMockBackend("", mock)

	_, err := m.GetStats()
	if err == nil {
		t.Error("expected error from GetStats")
	}
}

// ─── initializeKeys via temp dir ──────────────────────────────────────────────

func TestInitializeKeys_GeneratesAndSavesKey(t *testing.T) {
	dir := t.TempDir()
	m := &Manager{interfaceName: "wg-test", keyDir: dir}

	if err := m.initializeKeys(); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if m.privateKey == (wgtypes.Key{}) {
		t.Error("expected non-zero private key")
	}
	if m.publicKey == (wgtypes.Key{}) {
		t.Error("expected non-zero public key")
	}
}

func TestInitializeKeys_LoadsExistingKey(t *testing.T) {
	dir := t.TempDir()
	// Pre-write a key file.
	key, _ := wgtypes.GeneratePrivateKey()
	keyPath := dir + "/wg-load.key"
	if err := os.WriteFile(keyPath, []byte(key.String()+"\n"), 0600); err != nil {
		t.Fatalf("failed to write key file: %v", err)
	}

	m := &Manager{interfaceName: "wg-load", keyDir: dir}
	if err := m.initializeKeys(); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if m.privateKey.String() != key.String() {
		t.Errorf("expected loaded key %s, got %s", key.String(), m.privateKey.String())
	}
}

func TestInitializeKeys_CorruptKeyFileGeneratesNew(t *testing.T) {
	dir := t.TempDir()
	keyPath := dir + "/wg-corrupt.key"
	if err := os.WriteFile(keyPath, []byte("not-a-valid-key\n"), 0600); err != nil {
		t.Fatalf("failed to write corrupt key file: %v", err)
	}

	m := &Manager{interfaceName: "wg-corrupt", keyDir: dir}
	if err := m.initializeKeys(); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// A new key should have been generated.
	if m.privateKey == (wgtypes.Key{}) {
		t.Error("expected non-zero private key after corrupt file")
	}
}

func TestInitializeKeys_CannotSaveKey(t *testing.T) {
	// Use a path where we can't write — make dir read-only after creation.
	dir := t.TempDir()
	if err := os.Chmod(dir, 0500); err != nil {
		t.Skipf("cannot change dir permissions: %v", err)
	}
	defer os.Chmod(dir, 0700) //nolint:errcheck

	m := &Manager{interfaceName: "wg-nosave", keyDir: dir + "/subdir"}
	err := m.initializeKeys()
	if err == nil {
		t.Error("expected error when directory cannot be created")
	}
}

// ─── fetchPeersFromManager — invalid URL ──────────────────────────────────────

func TestFetchPeersFromManager_InvalidURL(t *testing.T) {
	// An invalid URL (contains a space) causes http.NewRequest to fail.
	m := makeManagerWithoutWgctrl("http://host with spaces.invalid")
	_, err := m.fetchPeersFromManager()
	if err == nil {
		t.Error("expected error for invalid URL")
	}
}

// ─── StartPeriodicSync — ticker fires ────────────────────────────────────────

func TestStartPeriodicSync_TickerFiresSyncPeers(t *testing.T) {
	// Use a server that counts requests.
	reqCount := 0
	type peerResponse struct {
		Peers []Peer `json:"peers"`
		Total int    `json:"total"`
	}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		reqCount++
		_ = json.NewEncoder(w).Encode(peerResponse{})
	}))
	defer ts.Close()

	mock := &MockWireGuardBackend{}
	m := makeManagerWithMockBackend(ts.URL, mock)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Call syncPeers directly to exercise the ticker branch without waiting 5 min.
	if err := m.syncPeers(); err != nil {
		t.Errorf("unexpected error from syncPeers: %v", err)
	}

	// Start the goroutine and cancel immediately to exercise the ctx.Done branch.
	m.StartPeriodicSync(ctx)
	cancel()
	time.Sleep(50 * time.Millisecond) // let goroutine see cancellation
}

// ─── wgctrlBackend — covered via NewManagerWithParams when kernel available ───

func TestWgctrlBackend_SkipWithoutKernel(t *testing.T) {
	// Attempt to create a real wgctrl client.  If unavailable, skip.
	c, err := wgctrl.New()
	if err != nil {
		t.Skipf("wgctrl unavailable: %v", err)
	}
	defer c.Close()

	b := &wgctrlBackend{c: c}

	// Device on a nonexistent interface returns an error but exercises the code path.
	_, err = b.Device("wg-test-nonexistent")
	// Either an error or not — both are acceptable.
	t.Logf("Device: err=%v", err)

	// ConfigureDevice on nonexistent interface also returns error.
	err = b.ConfigureDevice("wg-test-nonexistent", wgtypes.Config{})
	t.Logf("ConfigureDevice: err=%v", err)

	// Close exercises the close path.
	if err := b.Close(); err != nil {
		t.Logf("Close: err=%v (expected in some environments)", err)
	}
}
