package vpn

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/tobogganing/clients/native/internal/config"
)

// buildTestConfig creates a Config suitable for tests.
func buildTestConfig(t *testing.T) *config.Config {
	t.Helper()
	cfg := config.DefaultConfig()
	cfg.ManagerURL = "https://manager.example.com"
	cfg.ClientName = "test-client"
	return cfg
}

// --- NewManager ---

func TestNewManager_ReturnsNonNil(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	if m == nil {
		t.Fatal("NewManager returned nil")
	}
}

func TestNewManager_NotConnectedInitially(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	if m.IsConnected() {
		t.Error("expected IsConnected=false initially")
	}
}

func TestNewManager_HasEmbeddedWireGuard(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	if m.embeddedWG == nil {
		t.Error("expected embeddedWG to be initialized")
	}
}

func TestNewManager_InterfaceName(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	if m.interfaceName == "" {
		t.Error("expected interfaceName to be set")
	}
}

// --- IsConnected ---

func TestManager_IsConnected_FalseByDefault(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	if m.IsConnected() {
		t.Error("IsConnected should be false by default")
	}
}

// --- GetStatusString ---

func TestManager_GetStatusString_Disconnected(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	s := m.GetStatusString()
	if s != "Disconnected" {
		t.Errorf("GetStatusString: want %q, got %q", "Disconnected", s)
	}
}

// --- GetStatus ---

func TestManager_GetStatus_Disconnected_StateField(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	status := m.GetStatus()
	if status.State != "" && status.State != "disconnected" {
		t.Errorf("GetStatus.State unexpected: %q", status.State)
	}
}

// --- GetStatistics ---

func TestManager_GetStatistics_ReturnsMap(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	stats := m.GetStatistics()
	if stats == nil {
		t.Fatal("GetStatistics returned nil")
	}
}

func TestManager_GetStatistics_ConnectedField_False(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	stats := m.GetStatistics()
	if connected, ok := stats["connected"]; ok {
		if connected.(bool) {
			t.Error("expected connected=false in statistics when not connected")
		}
	}
	_ = m.Stop() // Clean up
}

func TestManager_GetStatistics_StatusField_Present(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	stats := m.GetStatistics()
	if _, ok := stats["status"]; !ok {
		t.Error("expected 'status' key in statistics map")
	}
}

// --- Stop ---

func TestManager_Stop_WhenNotConnected_NoError(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	if err := m.Stop(); err != nil {
		t.Errorf("Stop when not connected: %v", err)
	}
}

// --- Connect --- (requires valid WireGuard config file)

func TestManager_Connect_WithMissingConfigFile_ReturnsError(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	// configPath points to nonexistent file.
	m.configPath = "/nonexistent/wireguard.conf"

	err := m.Connect()
	if err == nil {
		t.Error("expected error when WireGuard config file doesn't exist")
	}
}

func TestManager_Connect_AlreadyConnected_ReturnsError(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	// Manually set connected state.
	m.mutex.Lock()
	m.isConnected = true
	m.mutex.Unlock()

	err := m.Connect()
	if err == nil {
		t.Error("expected error when already connected")
	}
	if !strings.Contains(err.Error(), "already connected") {
		t.Errorf("expected 'already connected' error, got: %v", err)
	}
}

// --- Disconnect ---

func TestManager_Disconnect_WhenNotConnected_ReturnsError(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)

	err := m.Disconnect()
	if err == nil {
		t.Error("expected error when disconnecting while not connected")
	}
	if !strings.Contains(err.Error(), "not connected") {
		t.Errorf("expected 'not connected' error, got: %v", err)
	}
}

// --- validateConfig ---

func TestManager_ValidateConfig_EmptyPath_ReturnsError(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.configPath = ""

	err := m.validateConfig()
	if err == nil {
		t.Error("expected error for empty configPath")
	}
}

func TestManager_ValidateConfig_NonExistentFile_ReturnsError(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.configPath = "/nonexistent/path/wg.conf"

	err := m.validateConfig()
	if err == nil {
		t.Error("expected error for nonexistent config file")
	}
}

func TestManager_ValidateConfig_ValidFile_NoError(t *testing.T) {
	dir := t.TempDir()
	cfgPath := filepath.Join(dir, "wg0.conf")

	content := `[Interface]
PrivateKey = ABC123
Address = 10.0.0.2/24

[Peer]
PublicKey = XYZ789
Endpoint = server.example.com:51820
`
	if err := os.WriteFile(cfgPath, []byte(content), 0600); err != nil {
		t.Fatalf("write test config: %v", err)
	}

	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.configPath = cfgPath
	m.useEmbedded = false // avoid trying to actually start WG

	if err := m.validateConfig(); err != nil {
		t.Errorf("validateConfig with valid file: %v", err)
	}
}

func TestManager_ValidateConfig_InvalidFormat_ReturnsError(t *testing.T) {
	dir := t.TempDir()
	cfgPath := filepath.Join(dir, "invalid.conf")

	if err := os.WriteFile(cfgPath, []byte("not a wireguard config"), 0600); err != nil {
		t.Fatalf("write test config: %v", err)
	}

	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.configPath = cfgPath

	if err := m.validateConfig(); err == nil {
		t.Error("expected error for invalid WireGuard format")
	}
}

// --- parseWireGuardOutput / parseTransferLine / parseHandshakeLine ---

func TestManager_ParseWireGuardOutput_Empty(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	stats := &InterfaceStatistics{}
	m.parseWireGuardOutput("", stats)
	// No panic, stats unchanged.
	if stats.BytesSent != 0 || stats.BytesReceived != 0 {
		t.Error("empty output should leave stats at zero")
	}
}

func TestManager_ParseTransferLine_ValidTransfer(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	stats := &InterfaceStatistics{}

	// wg show output format: "  transfer: 1.50 MiB received, 2.25 MiB sent"
	line := "transfer: 1.50 MiB received, 2.25 MiB sent"
	m.parseTransferLine(line, stats)

	if stats.BytesReceived == 0 {
		t.Error("expected BytesReceived to be parsed")
	}
	if stats.BytesSent == 0 {
		t.Error("expected BytesSent to be parsed")
	}
}

func TestManager_ParseTransferLine_NoTransfer(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	stats := &InterfaceStatistics{}

	m.parseTransferLine("interface: wg0", stats)
	if stats.BytesReceived != 0 || stats.BytesSent != 0 {
		t.Error("non-transfer line should not modify stats")
	}
}

func TestManager_ParseTransferLine_TooFewFields(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	stats := &InterfaceStatistics{}

	// Fewer than 6 parts after splitting.
	m.parseTransferLine("transfer: 1.5", stats)
	if stats.BytesReceived != 0 || stats.BytesSent != 0 {
		t.Error("malformed transfer line should not crash or set stats")
	}
}

func TestManager_ParseHandshakeLine_ValidHandshake(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	stats := &InterfaceStatistics{}

	line := "latest handshake: 2024-01-15 10:30:00"
	m.parseHandshakeLine(line, stats)

	if stats.LastHandshake.IsZero() {
		t.Error("expected LastHandshake to be parsed")
	}
}

func TestManager_ParseHandshakeLine_InvalidFormat(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	stats := &InterfaceStatistics{}

	m.parseHandshakeLine("latest handshake: not-a-date", stats)
	if !stats.LastHandshake.IsZero() {
		t.Error("invalid date should leave LastHandshake zero")
	}
}

func TestManager_ParseHandshakeLine_NotHandshakeLine(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	stats := &InterfaceStatistics{}

	m.parseHandshakeLine("public key: ABC123", stats)
	if !stats.LastHandshake.IsZero() {
		t.Error("non-handshake line should not set LastHandshake")
	}
}

// --- parseTransferAmount ---

func TestManager_ParseTransferAmount_Bytes(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)

	tests := []struct {
		input string
		want  uint64
	}{
		{"1.00 KiB", 1024},
		{"1.00 MiB", 1024 * 1024},
		{"1.00 GiB", 1024 * 1024 * 1024},
		{"0.00 KiB", 0},
		{"2.50 KiB", 2560}, // 2.5 * 1024 = 2560
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := m.parseTransferAmount(tt.input)
			if got != tt.want {
				t.Errorf("parseTransferAmount(%q): want %d, got %d", tt.input, tt.want, got)
			}
		})
	}
}

func TestManager_ParseTransferAmount_UnknownUnit(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)

	// Unknown unit = multiplier 1.
	got := m.parseTransferAmount("100 B")
	if got != 100 {
		t.Errorf("unknown unit: want 100, got %d", got)
	}
}

func TestManager_ParseTransferAmount_MalformedInput(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)

	got := m.parseTransferAmount("notanumber")
	if got != 0 {
		t.Errorf("malformed input: want 0, got %d", got)
	}
}

// --- InterfaceStatistics ---

func TestInterfaceStatistics_ZeroValue(t *testing.T) {
	var s InterfaceStatistics
	if s.BytesSent != 0 {
		t.Error("BytesSent should default to 0")
	}
	if s.BytesReceived != 0 {
		t.Error("BytesReceived should default to 0")
	}
	if !s.LastHandshake.IsZero() {
		t.Error("LastHandshake should default to zero time")
	}
}

// --- readWireGuardConfig ---

func TestReadWireGuardConfig_ValidFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "wg.conf")
	content := []byte("test content")

	if err := os.WriteFile(path, content, 0600); err != nil {
		t.Fatalf("write file: %v", err)
	}

	got, err := readWireGuardConfig(path)
	if err != nil {
		t.Fatalf("readWireGuardConfig: %v", err)
	}
	if string(got) != string(content) {
		t.Errorf("content mismatch: want %q, got %q", content, got)
	}
}

func TestReadWireGuardConfig_NonExistentFile_ReturnsError(t *testing.T) {
	_, err := readWireGuardConfig("/nonexistent/path.conf")
	if err == nil {
		t.Error("expected error for nonexistent file")
	}
}

// --- stopMonitoring ---

func TestManager_StopMonitoring_WhenNotMonitoring_NoPanic(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	// Should not panic when monitorTicker is nil.
	m.stopMonitoring()
}

// --- startMonitoring / stopMonitoring integration ---

func TestManager_StartStop_Monitoring(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)

	m.startMonitoring()
	time.Sleep(10 * time.Millisecond)
	m.stopMonitoring()
	// No panic.
}

// --- getLocalIP ---

func TestManager_GetLocalIP_NonExistentInterface(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.interfaceName = "wg-nonexistent-9999"

	// Should return "unknown" for nonexistent interface.
	ip := m.getLocalIP()
	if ip != statusUnknown {
		t.Errorf("expected %q for nonexistent interface, got %q", statusUnknown, ip)
	}
}

// --- getWireGuardOutput ---

func TestManager_GetWireGuardOutput_NonExistentInterface(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.interfaceName = "wg-nonexistent-9999"

	// wg show will fail — should return error.
	_, err := m.getWireGuardOutput()
	if err == nil {
		t.Log("wg show succeeded (WireGuard tools present on system)")
	}
	// Either success or error is acceptable — we just test it doesn't panic.
}

// --- getInterfaceStatistics ---

func TestManager_GetInterfaceStatistics_NonExistentInterface(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.interfaceName = "wg-nonexistent-9999"

	// Should return zero stats gracefully.
	stats := m.getInterfaceStatistics()
	// No panic, zero stats.
	_ = stats
}

// --- checkConnection ---

func TestManager_CheckConnection_NonExistentInterface(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.interfaceName = "wg-nonexistent-9999"
	m.mutex.Lock()
	m.isConnected = true
	m.mutex.Unlock()

	// Should detect interface missing and set disconnected.
	m.checkConnection()

	if m.IsConnected() {
		t.Error("expected IsConnected=false after checkConnection with missing interface")
	}
}

// --- connectWireGuard (falls through to platform-specific or embedded) ---

func TestManager_ConnectWireGuard_EmbeddedDisabled_InvalidConfig(t *testing.T) {
	dir := t.TempDir()
	cfgPath := filepath.Join(dir, "wg.conf")
	if err := os.WriteFile(cfgPath, []byte("not-valid-config"), 0600); err != nil {
		t.Fatal(err)
	}

	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.useEmbedded = false
	m.configPath = cfgPath

	// connectWireGuard will try platform-specific (wg-quick) which should fail.
	err := m.connectWireGuard()
	if err == nil {
		t.Log("connectWireGuard succeeded (wg-quick available and ran)")
	} else {
		t.Logf("connectWireGuard error (expected without wg-quick): %v", err)
	}
}

// --- disconnectWireGuard ---

func TestManager_DisconnectWireGuard_EmbeddedNotRunning(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	// useEmbedded = true but embeddedWG is not running.
	err := m.disconnectWireGuard()
	// Should return nil (Stop on non-running EmbeddedWG is a no-op).
	if err != nil {
		t.Errorf("disconnectWireGuard when embedded not running: %v", err)
	}
}

func TestManager_DisconnectWireGuard_NonEmbedded(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.useEmbedded = false

	// Will try wg-quick down which will fail.
	err := m.disconnectWireGuard()
	// Error is acceptable (no wg-quick in test env).
	if err == nil {
		t.Log("disconnectWireGuard succeeded (wg-quick present)")
	}
}

// --- GetStatus when connected ---

func TestManager_GetStatus_Connected(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.mutex.Lock()
	m.isConnected = true
	m.currentStatus.State = "connected"
	m.mutex.Unlock()

	// getInterfaceStatistics is called internally; it will fail gracefully.
	status := m.GetStatus()
	if status.State != "connected" {
		t.Errorf("GetStatus.State: want %q, got %q", "connected", status.State)
	}
}

// --- GetStatusString when connected ---

func TestManager_GetStatusString_Connected(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.mutex.Lock()
	m.isConnected = true
	m.mutex.Unlock()

	s := m.GetStatusString()
	if s != "Connected" {
		t.Errorf("GetStatusString: want %q, got %q", "Connected", s)
	}
}

// --- GetStatistics when connected ---

func TestManager_GetStatistics_Connected(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.mutex.Lock()
	m.isConnected = true
	m.interfaceName = "wg-nonexistent-9999" //nolint:goconst
	m.mutex.Unlock()

	stats := m.GetStatistics()
	if connected, ok := stats["connected"]; ok {
		if !connected.(bool) {
			t.Error("expected connected=true in stats")
		}
	}
	_ = m.Stop() // Clean up
}

// --- Stop when connected ---

func TestManager_Stop_WhenConnected_Disconnects(t *testing.T) {
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.mutex.Lock()
	m.isConnected = true
	m.mutex.Unlock()

	// Stop should call Disconnect first, which will return "not connected" error
	// because the VPN wasn't really connected. But Stop should not propagate that error.
	err := m.Stop()
	if err != nil {
		t.Errorf("Stop: %v", err)
	}
}

// --- Platform-specific connect/disconnect (non-embedded) ---

func TestManager_ConnectLinux_InvalidConfig(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping platform-specific test in short mode")
	}
	cfg := buildTestConfig(t)
	m := NewManager(cfg)

	// connectLinux calls sudo wg-quick up — will fail without root or wg-quick.
	err := m.connectLinux()
	if err == nil {
		t.Log("connectLinux succeeded (wg-quick and root available)")
	} else {
		t.Logf("connectLinux error (expected): %v", err)
	}
}

func TestManager_DisconnectLinux_InvalidInterface(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping platform-specific test in short mode")
	}
	cfg := buildTestConfig(t)
	m := NewManager(cfg)
	m.interfaceName = "wg-nonexistent-9999" //nolint:goconst

	err := m.disconnectLinux()
	if err == nil {
		t.Log("disconnectLinux succeeded")
	} else {
		t.Logf("disconnectLinux error (expected): %v", err)
	}
	_ = m.Stop() // Clean up
}
