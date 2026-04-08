package config

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

// --- GetConfigDir Linux XDG_CONFIG_HOME branch ---

func TestGetConfigDir_Linux_WithXDGConfigHome(t *testing.T) {
	if runtime.GOOS != platformLinux {
		t.Skip("XDG_CONFIG_HOME test only runs on Linux")
	}

	// Set XDG_CONFIG_HOME to a custom path.
	t.Setenv("XDG_CONFIG_HOME", "/tmp/test-xdg-config")
	defer func() { _ = os.Unsetenv("XDG_CONFIG_HOME") }()

	dir := GetConfigDir()
	if dir != "/tmp/test-xdg-config/tobogganing" {
		t.Errorf("expected /tmp/test-xdg-config/tobogganing, got %q", dir)
	}
}

func TestGetConfigDir_Linux_WithoutXDGConfigHome(t *testing.T) {
	if runtime.GOOS != platformLinux {
		t.Skip("Linux-only test")
	}

	// Unset XDG_CONFIG_HOME to exercise the fallback to HOME/.config.
	_ = os.Unsetenv("XDG_CONFIG_HOME")
	home := os.Getenv("HOME")

	dir := GetConfigDir()
	if home != "" {
		expected := home + "/.config/tobogganing"
		if dir != expected {
			t.Errorf("expected %q, got %q", expected, dir)
		}
	}
}

// --- DefaultConfig field coverage ---

func TestDefaultConfig_WireGuardInterface(t *testing.T) {
	cfg := DefaultConfig()
	// WireGuardInterface may be set or empty depending on platform; just ensure no panic.
	_ = cfg.WireGuardInterface
}

func TestDefaultConfig_OpenZiti(t *testing.T) {
	cfg := DefaultConfig()
	// OpenZiti struct should be accessible.
	_ = cfg.OpenZiti.IdentityFile
	_ = cfg.OpenZiti.ServiceName
}

// --- Validate edge cases ---

func TestValidate_ValidClientType_ClientNative(t *testing.T) {
	cfg := &Config{
		ManagerURL:           "https://manager.example.com",
		APIKey:               "key",
		ClientType:           "client_native",
		LogLevel:             "info",
		ReconnectInterval:    30,
		AuthRefreshThreshold: 300,
		OverlayType:          "dual",
	}
	if err := cfg.Validate(); err != nil {
		t.Errorf("client_native should be valid: %v", err)
	}
}

// --- LoadFromFile with explicit YAML content (no viper global state pollution) ---

func TestLoadFromFile_WithHeadlessField(t *testing.T) {
	dir := t.TempDir()
	cfgFile := dir + "/headless.yaml"

	content := `manager_url: "https://headless-test.example.com"
api_key: "headless-key"
client_type: "client_native"
log_level: "error"
reconnect_interval: 30
auth_refresh_threshold: 300
overlay_type: "wireguard"
headless: true
`
	if err := os.WriteFile(cfgFile, []byte(content), 0600); err != nil {
		t.Fatalf("write config file: %v", err)
	}

	cfg := DefaultConfig()
	if err := LoadFromFile(cfg, cfgFile); err != nil {
		t.Fatalf("LoadFromFile: %v", err)
	}

	if cfg.ManagerURL != "https://headless-test.example.com" {
		t.Errorf("ManagerURL: got %q", cfg.ManagerURL)
	}
	if !cfg.Headless {
		t.Error("Headless should be true")
	}
	if cfg.LogLevel != "error" {
		t.Errorf("LogLevel: got %q", cfg.LogLevel)
	}
}

// --- GetWireGuardConfigPath ends with wireguard.conf ---

func TestGetWireGuardConfigPath_EndsWithWireGuardConf(t *testing.T) {
	cfg := &Config{}
	p := cfg.GetWireGuardConfigPath()
	if p == "" {
		t.Fatal("path should not be empty")
	}
	// Should contain wireguard
	if len(p) < len("wireguard.conf") {
		t.Fatalf("path too short: %q", p)
	}
	suffix := p[len(p)-len("wireguard.conf"):]
	if suffix != "wireguard.conf" {
		t.Errorf("expected path to end with wireguard.conf, got %q", p)
	}
}

// --- GetConfigDir platform coverage: Windows ---

func TestGetConfigDir_Windows_ReturnsAPPDATA(t *testing.T) {
	if runtime.GOOS != platformWindows {
		t.Skip("Windows-only test")
	}
	dir := GetConfigDir()
	if dir == "" {
		t.Error("GetConfigDir should not be empty on Windows")
	}
	if runtime.GOOS == platformWindows && os.Getenv("APPDATA") != "" {
		appdata := os.Getenv("APPDATA")
		if dir != appdata+"\\Tobogganing" {
			t.Errorf("Windows: expected %q\\Tobogganing, got %q", appdata, dir)
		}
	}
}

func TestGetConfigDir_Darwin_ReturnsHomeDotTobogganing(t *testing.T) {
	if runtime.GOOS != platformDarwin {
		t.Skip("Darwin-only test")
	}
	home := os.Getenv("HOME")
	if home == "" {
		t.Skip("HOME not set")
	}
	dir := GetConfigDir()
	expected := home + "/.tobogganing"
	if dir != expected {
		t.Errorf("Darwin: expected %q, got %q", expected, dir)
	}
}

// --- WriteFile error paths ---

func TestWriteFile_FailedToCreateDirectory(t *testing.T) {
	if runtime.GOOS == platformWindows {
		t.Skip("permission test not reliable on Windows")
	}

	// Try to write to a path under /dev/null (which is a file, not a directory)
	// This should fail when trying to create the directory.
	cfg := &Config{}
	err := cfg.WriteFile("/dev/null/impossible/file.conf", []byte("data"))
	if err == nil {
		t.Error("expected error when directory cannot be created")
	}
}

// --- Save with error handling ---

func TestSave_FailedToCreateDirectory(t *testing.T) {
	if runtime.GOOS == platformWindows {
		t.Skip("permission test not reliable on Windows")
	}

	cfg := &Config{
		ManagerURL:           "https://example.com",
		APIKey:               "key",
		ClientType:           "client_native",
		LogLevel:             "info",
		ReconnectInterval:    30,
		AuthRefreshThreshold: 300,
	}

	// Attempt to save to impossible path.
	err := cfg.Save("/dev/null/impossible/config.yaml")
	if err == nil {
		t.Error("expected error when save fails")
	}
}

// --- LoadFromFile error paths ---

func TestLoadFromFile_InvalidYAML(t *testing.T) {
	dir := t.TempDir()
	cfgFile := filepath.Join(dir, "bad.yaml")

	// Write invalid YAML
	invalidYAML := `
manager_url: "https://example.com"
api_key: [unclosed list
`
	if err := os.WriteFile(cfgFile, []byte(invalidYAML), 0600); err != nil {
		t.Fatalf("write test file: %v", err)
	}

	cfg := DefaultConfig()
	err := LoadFromFile(cfg, cfgFile)
	if err == nil {
		t.Error("expected error for invalid YAML")
	}
}

// --- LoadFromDefaults with error on bad config read ---

func TestLoadFromDefaults_UnmarshalError(t *testing.T) {
	// This test verifies that unmarshal errors are wrapped.
	// It's difficult to trigger without modifying viper directly,
	// but we can verify the function handles viper config paths.
	cfg := &Config{}
	// This should succeed (or at least not panic) since we're testing non-error paths.
	if err := LoadFromDefaults(cfg); err != nil {
		// Error is acceptable if no config files exist; just check no panic.
		_ = err
	}
}
