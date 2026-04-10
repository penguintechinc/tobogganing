package vpn

import (
	"errors"
	"os"
	"strings"
	"testing"

	"golang.zx2c4.com/wireguard/conn"
	"golang.zx2c4.com/wireguard/device"
	"golang.zx2c4.com/wireguard/tun"
	"golang.zx2c4.com/wireguard/tun/tuntest"
)

// --- Mock TunnelBackend helpers ---

// channelTunnelBackend is a test TunnelBackend backed by tuntest.ChannelTUN.
// It creates a real *device.Device so Start/Stop/configureDevice execute fully.
type channelTunnelBackend struct {
	ch *tuntest.ChannelTUN
}

func newChannelTunnelBackend() *channelTunnelBackend {
	return &channelTunnelBackend{ch: tuntest.NewChannelTUN()}
}

func (b *channelTunnelBackend) CreateTUN(_ string, _ int) (tun.Device, error) {
	return b.ch.TUN(), nil
}

func (b *channelTunnelBackend) NewDevice(tunDev tun.Device, bind conn.Bind, logger *device.Logger) *device.Device {
	return device.NewDevice(tunDev, bind, logger)
}

// failTunnelBackend always fails CreateTUN.
type failTunnelBackend struct{ err error }

func (b *failTunnelBackend) CreateTUN(_ string, _ int) (tun.Device, error) {
	return nil, b.err
}

func (b *failTunnelBackend) NewDevice(tunDev tun.Device, bind conn.Bind, logger *device.Logger) *device.Device {
	return device.NewDevice(tunDev, bind, logger)
}

// noopTUN implements tun.Device doing nothing (for cleanup tests).
type noopTUN struct {
	events chan tun.Event
	closed bool
}

func newNoopTUN() *noopTUN {
	ch := make(chan tun.Event, 1)
	ch <- tun.EventUp
	return &noopTUN{events: ch}
}

func (t *noopTUN) File() *os.File                               { return nil }
func (t *noopTUN) Read(_ [][]byte, _ []int, _ int) (int, error) { return 0, errors.New("closed") }
func (t *noopTUN) Write(_ [][]byte, _ int) (int, error)         { return 0, nil }
func (t *noopTUN) MTU() (int, error)                            { return 1420, nil }
func (t *noopTUN) Name() (string, error)                        { return "mock0", nil }
func (t *noopTUN) Events() <-chan tun.Event                     { return t.events }
func (t *noopTUN) Close() error                                 { t.closed = true; return nil }
func (t *noopTUN) BatchSize() int                               { return 1 }

// validWGConfig uses hex-encoded keys (IPC format) so IpcSetOperation succeeds.
// The PrivateKey/PublicKey here are 64-char hex strings (32 bytes).
const validWGConfig = `[Interface]
PrivateKey = e84b3b49e3e6ff15e84b3b49e3e6ff15e84b3b49e3e6ff15e84b3b49e3e6ff15
Address = 10.99.99.2/24
DNS = 8.8.8.8

[Peer]
PublicKey = a3f1c2d4e5b6a7f8a3f1c2d4e5b6a7f8a3f1c2d4e5b6a7f8a3f1c2d4e5b6a7f8
Endpoint = 192.0.2.1:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
`

// configWithoutAddress is missing the Address field to trigger configureNetworking error.
// Uses valid hex keys so IpcSetOperation passes and we reach configureNetworking.
const configWithoutAddress = `[Interface]
PrivateKey = e84b3b49e3e6ff15e84b3b49e3e6ff15e84b3b49e3e6ff15e84b3b49e3e6ff15

[Peer]
PublicKey = a3f1c2d4e5b6a7f8a3f1c2d4e5b6a7f8a3f1c2d4e5b6a7f8a3f1c2d4e5b6a7f8
Endpoint = 192.0.2.1:51820
AllowedIPs = 0.0.0.0/0
`

// --- NewEmbeddedWireGuard ---

func TestNewEmbeddedWireGuard_ReturnsNonNil(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	if ew == nil {
		t.Fatal("NewEmbeddedWireGuard returned nil")
	}
}

func TestNewEmbeddedWireGuard_InterfaceName(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg-test")
	if ew.GetInterfaceName() != "wg-test" {
		t.Errorf("GetInterfaceName: want %q, got %q", "wg-test", ew.GetInterfaceName())
	}
}

func TestNewEmbeddedWireGuard_NotRunningInitially(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	if ew.IsRunning() {
		t.Error("expected IsRunning=false initially")
	}
}

func TestNewEmbeddedWireGuard_EmptyConfigInitially(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	if ew.GetConfig() != "" {
		t.Errorf("expected empty config initially, got %q", ew.GetConfig())
	}
}

// --- NewEmbeddedWireGuardWithBackend ---

func TestNewEmbeddedWireGuardWithBackend_ReturnsNonNil(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)
	if ew == nil {
		t.Fatal("NewEmbeddedWireGuardWithBackend returned nil")
	}
}

func TestNewEmbeddedWireGuardWithBackend_StoresInterfaceName(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg-inject", be)
	if ew.GetInterfaceName() != "wg-inject" {
		t.Errorf("expected wg-inject, got %q", ew.GetInterfaceName())
	}
}

// --- GetInterfaceName ---

func TestEmbeddedWireGuard_GetInterfaceName(t *testing.T) {
	tests := []string{"wg0", "wg1", "wg-custom", "Tobogganing"}
	for _, name := range tests {
		ew := NewEmbeddedWireGuard(name)
		if got := ew.GetInterfaceName(); got != name {
			t.Errorf("GetInterfaceName(%q): want %q, got %q", name, name, got)
		}
	}
}

// --- IsRunning ---

func TestEmbeddedWireGuard_IsRunning_FalseBeforeStart(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	if ew.IsRunning() {
		t.Error("IsRunning should be false before Start")
	}
}

// --- GetConfig ---

func TestEmbeddedWireGuard_GetConfig_EmptyBeforeStart(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	if ew.GetConfig() != "" {
		t.Error("config should be empty before Start")
	}
}

// --- Stop (when not running) ---

func TestEmbeddedWireGuard_Stop_WhenNotRunning_NoError(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	if err := ew.Stop(); err != nil {
		t.Errorf("Stop when not running: %v", err)
	}
}

func TestEmbeddedWireGuard_Stop_IsIdempotent(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	// Multiple stops should not error.
	for i := 0; i < 3; i++ {
		if err := ew.Stop(); err != nil {
			t.Errorf("Stop #%d: %v", i, err)
		}
	}
}

// --- Start: CreateTUN error ---

func TestEmbeddedWireGuard_Start_CreateTUNError_ReturnsError(t *testing.T) {
	be := &failTunnelBackend{err: errors.New("no kernel access")}
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	err := ew.Start(validWGConfig)
	if err == nil {
		t.Fatal("expected error when CreateTUN fails")
	}
	if !strings.Contains(err.Error(), "failed to create TUN interface") {
		t.Errorf("unexpected error message: %v", err)
	}
	if ew.IsRunning() {
		t.Error("should not be running after CreateTUN failure")
	}
}

// --- Start: already running ---

func TestEmbeddedWireGuard_Start_AlreadyRunning_ReturnsError(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	// Force isRunning = true without actual device start.
	ew.mutex.Lock()
	ew.isRunning = true
	ew.mutex.Unlock()

	err := ew.Start(validWGConfig)
	if err == nil {
		t.Fatal("expected error when already running")
	}
	if !strings.Contains(err.Error(), "already running") {
		t.Errorf("unexpected error: %v", err)
	}
}

// --- Start: IpcSetOperation error (bad key) ---

func TestEmbeddedWireGuard_Start_BadIPCKey_ReturnsError(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	// PrivateKey must be 64 hex chars (32 bytes). Use 60 hex chars to trigger IPC error.
	badKeyConfig := `[Interface]
PrivateKey = deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbe
Address = 10.0.0.2/24
`
	err := ew.Start(badKeyConfig)
	if err == nil {
		// If somehow it succeeded, clean up.
		_ = ew.Stop()
		t.Fatal("expected IPC configuration error for bad key")
	}
	if !strings.Contains(err.Error(), "failed to configure device") {
		t.Errorf("unexpected error: %v", err)
	}
	if ew.IsRunning() {
		t.Error("should not be running after IPC error")
	}
}

// --- Start: missing Address → configureNetworking error → cleanup ---

func TestEmbeddedWireGuard_Start_MissingAddress_ReturnsError(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	err := ew.Start(configWithoutAddress)
	if err == nil {
		t.Fatal("expected error when Address is missing from config")
	}
	if !strings.Contains(err.Error(), "failed to configure device") {
		t.Errorf("unexpected error message: %v", err)
	}
	// cleanup should have run — device and tun should be nil.
	if ew.IsRunning() {
		t.Error("should not be running after configure failure")
	}
}

// --- Start/Stop: success path via mock backend ---

func TestEmbeddedWireGuard_StartStop_Success(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("Start: %v", err)
	}
	if !ew.IsRunning() {
		t.Error("expected IsRunning=true after Start")
	}
	if ew.GetConfig() != validWGConfig {
		t.Error("expected config to be stored after Start")
	}

	if err := ew.Stop(); err != nil {
		t.Fatalf("Stop: %v", err)
	}
	if ew.IsRunning() {
		t.Error("expected IsRunning=false after Stop")
	}
	// Config is not cleared on Stop — that's intentional.
}

func TestEmbeddedWireGuard_Start_SetsIsRunningTrue(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = ew.Stop() }()

	if !ew.IsRunning() {
		t.Error("IsRunning should be true after successful Start")
	}
}

func TestEmbeddedWireGuard_Stop_SetsIsRunningFalse(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("Start: %v", err)
	}
	if err := ew.Stop(); err != nil {
		t.Fatalf("Stop: %v", err)
	}
	if ew.IsRunning() {
		t.Error("IsRunning should be false after Stop")
	}
}

// --- Double Start ---

func TestEmbeddedWireGuard_DoubleStart_SecondFails(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("first Start: %v", err)
	}
	defer func() { _ = ew.Stop() }()

	err := ew.Start(validWGConfig)
	if err == nil {
		t.Fatal("expected error on second Start while running")
	}
}

// --- Stop after Stop ---

func TestEmbeddedWireGuard_StopAfterStop_Idempotent(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("Start: %v", err)
	}
	if err := ew.Stop(); err != nil {
		t.Fatalf("first Stop: %v", err)
	}
	if err := ew.Stop(); err != nil {
		t.Errorf("second Stop should be no-op: %v", err)
	}
}

// --- IsRunning state transitions ---

func TestEmbeddedWireGuard_IsRunning_TransitionsCorrectly(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	// initial
	if ew.IsRunning() {
		t.Error("expected false initially")
	}

	// after start
	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("Start: %v", err)
	}
	if !ew.IsRunning() {
		t.Error("expected true after Start")
	}

	// after stop
	if err := ew.Stop(); err != nil {
		t.Fatalf("Stop: %v", err)
	}
	if ew.IsRunning() {
		t.Error("expected false after Stop")
	}
}

// --- GetConfig after Start ---

func TestEmbeddedWireGuard_GetConfig_AfterStart(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = ew.Stop() }()

	if ew.GetConfig() != validWGConfig {
		t.Errorf("GetConfig: want original config, got %q", ew.GetConfig())
	}
}

// --- parseConfig ---

func TestEmbeddedWireGuard_ParseConfig_PrivateKey(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := `[Interface]
PrivateKey = testPrivateKeyValue
Address = 10.0.0.2/24
`
	result := ew.parseConfig(config)
	if !strings.Contains(result, "private_key=testPrivateKeyValue") {
		t.Errorf("parseConfig should include private_key, got: %q", result)
	}
}

func TestEmbeddedWireGuard_ParseConfig_PublicKey(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := `[Peer]
PublicKey = peerPublicKeyValue
Endpoint = server.example.com:51820
`
	result := ew.parseConfig(config)
	if !strings.Contains(result, "public_key=peerPublicKeyValue") {
		t.Errorf("parseConfig should include public_key, got: %q", result)
	}
}

func TestEmbeddedWireGuard_ParseConfig_Endpoint(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := `[Peer]
PublicKey = key
Endpoint = server.example.com:51820
`
	result := ew.parseConfig(config)
	if !strings.Contains(result, "endpoint=server.example.com:51820") {
		t.Errorf("parseConfig should include endpoint, got: %q", result)
	}
}

func TestEmbeddedWireGuard_ParseConfig_AllowedIPs(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := `[Peer]
PublicKey = key
AllowedIPs = 0.0.0.0/0, ::/0
`
	result := ew.parseConfig(config)
	if !strings.Contains(result, "allowed_ip=") {
		t.Errorf("parseConfig should include allowed_ip, got: %q", result)
	}
}

func TestEmbeddedWireGuard_ParseConfig_PersistentKeepalive(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := `[Peer]
PublicKey = key
PersistentKeepalive = 25
`
	result := ew.parseConfig(config)
	if !strings.Contains(result, "persistent_keepalive_interval=25") {
		t.Errorf("parseConfig should include persistent_keepalive_interval, got: %q", result)
	}
}

func TestEmbeddedWireGuard_ParseConfig_SkipsComments(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := `# This is a comment
[Interface]
# Another comment
PrivateKey = testkey
`
	result := ew.parseConfig(config)
	if strings.Contains(result, "#") {
		t.Errorf("parseConfig should skip comments, got: %q", result)
	}
}

func TestEmbeddedWireGuard_ParseConfig_SkipsSectionHeaders(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := `[Interface]
PrivateKey = key
[Peer]
PublicKey = peerkey
`
	result := ew.parseConfig(config)
	if strings.Contains(result, "[Interface]") || strings.Contains(result, "[Peer]") {
		t.Errorf("parseConfig should skip section headers, got: %q", result)
	}
}

func TestEmbeddedWireGuard_ParseConfig_SkipsUnknownKeys(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := `[Interface]
PrivateKey = key
UnknownField = somevalue
Address = 10.0.0.2/24
`
	result := ew.parseConfig(config)
	// Address is not in the switch, so it should NOT appear.
	if strings.Contains(result, "unknownfield") || strings.Contains(result, "address") {
		t.Errorf("parseConfig should skip unknown fields, got: %q", result)
	}
}

func TestEmbeddedWireGuard_ParseConfig_EmptyInput(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	result := ew.parseConfig("")
	// Empty config = empty IPC config.
	if result != "" {
		t.Errorf("parseConfig with empty input: want empty, got %q", result)
	}
}

// --- extractConfigValue ---

func TestEmbeddedWireGuard_ExtractConfigValue_Found(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := "Address=10.0.0.2/24\nDNS=8.8.8.8\n"

	got := ew.extractConfigValue(config, "Address")
	if got != "10.0.0.2/24" {
		t.Errorf("extractConfigValue(Address): want %q, got %q", "10.0.0.2/24", got)
	}
}

func TestEmbeddedWireGuard_ExtractConfigValue_NotFound(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := "Address=10.0.0.2/24\n"

	got := ew.extractConfigValue(config, "DNS")
	if got != "" {
		t.Errorf("extractConfigValue(DNS): expected empty, got %q", got)
	}
}

func TestEmbeddedWireGuard_ExtractConfigValue_CaseInsensitive(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := "ADDRESS=10.0.0.1/24\n"

	got := ew.extractConfigValue(config, "Address")
	if got != "10.0.0.1/24" {
		t.Errorf("extractConfigValue should be case-insensitive: got %q", got)
	}
}

// --- configureInterfaceIP ---

func TestEmbeddedWireGuard_ConfigureInterfaceIP_ValidCIDR(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	err := ew.configureInterfaceIP("10.0.0.2/24")
	if err != nil {
		t.Errorf("configureInterfaceIP with valid CIDR: %v", err)
	}
}

func TestEmbeddedWireGuard_ConfigureInterfaceIP_InvalidCIDR(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	err := ew.configureInterfaceIP("not-an-ip")
	if err == nil {
		t.Error("expected error for invalid CIDR")
	}
}

// --- configureDNS ---

func TestEmbeddedWireGuard_ConfigureDNS_MultipleServers(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	err := ew.configureDNS("8.8.8.8, 1.1.1.1")
	if err != nil {
		t.Errorf("configureDNS: %v", err)
	}
}

func TestEmbeddedWireGuard_ConfigureDNS_SingleServer(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	err := ew.configureDNS("8.8.8.8")
	if err != nil {
		t.Errorf("configureDNS single server: %v", err)
	}
}

// --- configureNetworking ---

func TestEmbeddedWireGuard_ConfigureNetworking_NoAddress_ReturnsError(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	// configureNetworking requires ew.device to be set for IpcSetOperation; we only need
	// to reach configureNetworking itself (it doesn't use ew.device). Call directly.
	err := ew.configureNetworking(configWithoutAddress)
	if err == nil {
		t.Fatal("expected error when Address is missing")
	}
	if !strings.Contains(err.Error(), "no Address specified") {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestEmbeddedWireGuard_ConfigureNetworking_InvalidCIDR_ReturnsError(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := "Address=not-a-cidr\n"
	err := ew.configureNetworking(config)
	if err == nil {
		t.Fatal("expected error for invalid CIDR in Address")
	}
	if !strings.Contains(err.Error(), "failed to configure interface IP") {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestEmbeddedWireGuard_ConfigureNetworking_WithDNS_NoError(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := "Address=10.0.0.2/24\nDNS=8.8.8.8\n"
	err := ew.configureNetworking(config)
	if err != nil {
		t.Errorf("configureNetworking with DNS: %v", err)
	}
}

// --- cleanup ---

func TestEmbeddedWireGuard_Cleanup_WhenNilDevice_NoPanic(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	// device and tun are nil — cleanup should not panic.
	ew.cleanup()
}

func TestEmbeddedWireGuard_Cleanup_ClosesDeviceAndTun(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("Start: %v", err)
	}
	// Access fields directly (same package).
	if ew.device == nil || ew.tun == nil {
		t.Fatal("device/tun should be set after Start")
	}

	// cleanup clears device and tun.
	ew.cleanup()
	if ew.device != nil {
		t.Error("device should be nil after cleanup")
	}
	if ew.tun != nil {
		t.Error("tun should be nil after cleanup")
	}
}

// --- Additional state/accessor tests ---

func TestEmbeddedWireGuard_GetInterfaceNameExtra(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg-custom")
	if ew.GetInterfaceName() != "wg-custom" {
		t.Errorf("expected wg-custom, got %q", ew.GetInterfaceName())
	}
}

func TestEmbeddedWireGuard_GetConfig_BeforeStart(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	if ew.GetConfig() != "" {
		t.Error("expected empty config before Start")
	}
}

func TestEmbeddedWireGuard_IsRunning_BeforeStart(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	if ew.IsRunning() {
		t.Error("expected IsRunning=false before Start")
	}
}

func TestEmbeddedWireGuard_Stop_BeforeStart(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	err := ew.Stop()
	if err != nil {
		t.Errorf("Stop before Start: %v", err)
	}
}

func TestEmbeddedWireGuard_Stop_Twice(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	_ = ew.Stop()
	err := ew.Stop()
	if err != nil {
		t.Errorf("second Stop: %v", err)
	}
}

// --- Additional edge case coverage ---

func TestEmbeddedWireGuard_ConfigureInterfaceIP_NoMask(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	// IP without netmask should fail
	err := ew.configureInterfaceIP("10.0.0.2")
	if err == nil {
		t.Error("expected error for IP without netmask")
	}
}

func TestEmbeddedWireGuard_ExtractConfigValue_WithSpaces(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := "  Address  =  10.0.0.2/24  \n"

	got := ew.extractConfigValue(config, "Address")
	if got != "10.0.0.2/24" {
		t.Errorf("extractConfigValue with spaces: want %q, got %q", "10.0.0.2/24", got)
	}
}

func TestEmbeddedWireGuard_ExtractConfigValue_EmptyValue(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := "Address = \n"

	got := ew.extractConfigValue(config, "Address")
	if got != "" {
		t.Errorf("extractConfigValue with empty value: want empty, got %q", got)
	}
}

func TestEmbeddedWireGuard_ExtractConfigValue_MultipleOccurrences(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := "PrivateKey = first\nPrivateKey = second\n"

	// Should return the first occurrence
	got := ew.extractConfigValue(config, "PrivateKey")
	if got != "first" {
		t.Errorf("extractConfigValue first occurrence: want %q, got %q", "first", got)
	}
}

func TestEmbeddedWireGuard_ParseConfig_CaseInsensitiveKeys(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := `[Interface]
PRIVATEKEY = testkey
publickey = peerkey
ENDPOINT = 192.0.2.1:51820
`
	result := ew.parseConfig(config)
	if !strings.Contains(result, "private_key=testkey") {
		t.Errorf("should handle uppercase PRIVATEKEY: %q", result)
	}
	if !strings.Contains(result, "public_key=peerkey") {
		t.Errorf("should handle lowercase publickey: %q", result)
	}
}

func TestEmbeddedWireGuard_ParseConfig_NoEqualsSign(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := `[Interface]
PrivateKey = testkey
NoEquals should be ignored
`
	result := ew.parseConfig(config)
	// Should not panic and should include the valid key
	if !strings.Contains(result, "private_key=testkey") {
		t.Error("should have private_key in result")
	}
}

func TestEmbeddedWireGuard_ConfigureNetworking_WithValidDNS(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := "Address=10.0.0.2/24\nDNS=8.8.8.8,1.1.1.1\n"

	err := ew.configureNetworking(config)
	if err != nil {
		t.Errorf("configureNetworking with DNS: %v", err)
	}
}

func TestEmbeddedWireGuard_Start_ContextInitialized(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	if ew.ctx == nil {
		t.Error("context should be initialized after creation")
	}

	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = ew.Stop() }()

	// Context should not be cancelled while running
	select {
	case <-ew.ctx.Done():
		t.Error("context should not be cancelled while running")
	default:
		t.Log("context is active (expected)")
	}
}

func TestEmbeddedWireGuard_Start_CleanupOnFailure(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	// Use bad config to trigger configureNetworking error
	err := ew.Start(configWithoutAddress)
	if err == nil {
		t.Fatal("expected error")
	}

	// After cleanup, device and tun should be nil
	if ew.device != nil {
		t.Error("device should be nil after failed Start")
	}
	if ew.tun != nil {
		t.Error("tun should be nil after failed Start")
	}
}

func TestEmbeddedWireGuard_Cleanup_WithActiveDevice(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("Start: %v", err)
	}

	// Store original device/tun
	origDevice := ew.device
	origTun := ew.tun

	// cleanup should close device
	ew.cleanup()

	if ew.device != nil {
		t.Error("device should be nil after cleanup")
	}
	if ew.tun != nil {
		t.Error("tun should be nil after cleanup")
	}

	// Original device should have been closed
	_ = origDevice
	_ = origTun
}

func TestEmbeddedWireGuard_GetConfig_NotModifiable(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = ew.Stop() }()

	config1 := ew.GetConfig()
	config2 := ew.GetConfig()

	if config1 != config2 {
		t.Error("GetConfig should return the same value each time")
	}
}

func TestEmbeddedWireGuard_IsRunning_ThreadSafe(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer func() { _ = ew.Stop() }()

	done := make(chan struct{})
	for i := 0; i < 10; i++ {
		go func() {
			_ = ew.IsRunning()
			done <- struct{}{}
		}()
	}

	for i := 0; i < 10; i++ {
		<-done
	}
}

// --- parseHandshakeLine edge cases ---

func TestEmbeddedWireGuard_ParseHandshakeLine_NoColon(t *testing.T) {
	// Simulate parsing a line with no colon (malformed)
	line := "latest handshake 2024-01-15 10:30:00"
	stats := &InterfaceStatistics{}
	// parseHandshakeLine handles this gracefully (won't split correctly)
	// Just verify it doesn't crash and stats remain zero
	m := &Manager{}
	m.parseHandshakeLine(line, stats)
	if !stats.LastHandshake.IsZero() {
		t.Error("line without colon should not parse time")
	}
}

// --- parseHandshakeLine with whitespace variation ---

func TestEmbeddedWireGuard_ParseHandshakeLine_ExtraWhitespace(t *testing.T) {
	m := &Manager{}
	stats := &InterfaceStatistics{}
	// Extra whitespace around colon causes the date value to have leading spaces,
	// which doesn't match the expected time format — LastHandshake stays zero.
	line := "latest handshake  :   2024-01-15 10:30:00"
	m.parseHandshakeLine(line, stats)
	if !stats.LastHandshake.IsZero() {
		t.Error("extra whitespace around colon prevents time parsing — expected zero")
	}
}

// --- parseHandshakeLine with never handshake ---

func TestEmbeddedWireGuard_ParseHandshakeLine_Never(t *testing.T) {
	m := &Manager{}
	stats := &InterfaceStatistics{}
	line := "latest handshake: never"
	m.parseHandshakeLine(line, stats)
	// "never" cannot parse as a date, so LastHandshake should remain zero
	if !stats.LastHandshake.IsZero() {
		t.Error("'never' should not parse as a valid timestamp")
	}
}

// --- extractConfigValue with no equals sign ---

func TestEmbeddedWireGuard_ExtractConfigValue_LineWithoutEquals(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := "Address\nDNS=8.8.8.8\n"
	got := ew.extractConfigValue(config, "Address")
	if got != "" {
		t.Errorf("line without '=' should not match: got %q", got)
	}
}

// --- extractConfigValue with empty value after equals ---

func TestEmbeddedWireGuard_ExtractConfigValue_EmptyValueAfterEquals(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := "PrivateKey=\nAddress=10.0.0.2/24\n"
	got := ew.extractConfigValue(config, "PrivateKey")
	if got != "" {
		t.Errorf("empty value should return empty string: got %q", got)
	}
}

// --- configureNetworking with valid but minimal config ---

func TestEmbeddedWireGuard_ConfigureNetworking_MinimalValid(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	config := "Address=10.0.0.2/24"
	err := ew.configureNetworking(config)
	if err != nil {
		t.Errorf("configureNetworking with minimal valid config should not error: %v", err)
	}
}

// --- NewEmbeddedWireGuardWithBackend error scenario ---

func TestNewEmbeddedWireGuardWithBackend_ErrorBackend(t *testing.T) {
	be := &failTunnelBackend{err: errors.New("backend failed")}
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)
	if ew == nil {
		t.Error("constructor should not return nil even with failing backend")
	}
	// Try to start with the failing backend
	err := ew.Start(validWGConfig)
	if err == nil {
		t.Fatal("Start should fail with failing backend")
	}
	if !strings.Contains(err.Error(), "failed to create TUN interface") {
		t.Errorf("unexpected error message: %v", err)
	}
}

// --- Stop when already stopped (idempotent) ---

func TestEmbeddedWireGuard_Stop_AlreadyStopped_Idempotent(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	err := ew.Stop()
	if err != nil {
		t.Errorf("first Stop when never started: %v", err)
	}
	// Call again
	err = ew.Stop()
	if err != nil {
		t.Errorf("second Stop should be idempotent: %v", err)
	}
}

// --- Stop after Start then Stop (normal lifecycle) ---

func TestEmbeddedWireGuard_Stop_AfterStart_ClearsResources(t *testing.T) {
	be := newChannelTunnelBackend()
	ew := NewEmbeddedWireGuardWithBackend("wg0", be)

	if err := ew.Start(validWGConfig); err != nil {
		t.Fatalf("Start: %v", err)
	}

	if err := ew.Stop(); err != nil {
		t.Fatalf("Stop: %v", err)
	}

	// After Stop, device and tun should be nil
	if ew.device != nil {
		t.Error("device should be nil after Stop")
	}
	if ew.tun != nil {
		t.Error("tun should be nil after Stop")
	}
}
