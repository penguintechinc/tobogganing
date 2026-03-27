package vpn

import (
	"strings"
	"testing"
)

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
	// extractConfigValue looks for "key=" (no space) as prefix.
	// WireGuard configs often have "Key = value" so this tests the exact format.
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
	// Function lowercases both the line and the key.
	config := "ADDRESS=10.0.0.1/24\n"

	got := ew.extractConfigValue(config, "Address")
	if got != "10.0.0.1/24" {
		t.Errorf("extractConfigValue should be case-insensitive: got %q", got)
	}
}

// --- configureInterfaceIP ---

func TestEmbeddedWireGuard_ConfigureInterfaceIP_ValidCIDR(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	// Should parse the CIDR and print a message but not error.
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
	// Should not error — just prints.
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

// --- cleanup ---

func TestEmbeddedWireGuard_Cleanup_WhenNilDevice_NoPanic(t *testing.T) {
	ew := NewEmbeddedWireGuard("wg0")
	// device and tun are nil — cleanup should not panic.
	ew.cleanup()
}
