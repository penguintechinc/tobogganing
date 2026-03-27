package config

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

// --- DefaultConfig ---

func TestDefaultConfig_ReturnsNonNil(t *testing.T) {
	cfg := DefaultConfig()
	if cfg == nil {
		t.Fatal("DefaultConfig() returned nil")
	}
}

func TestDefaultConfig_ClientType(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.ClientType != "client_native" {
		t.Errorf("ClientType: want %q, got %q", "client_native", cfg.ClientType)
	}
}

func TestDefaultConfig_AutoConnect_False(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.AutoConnect {
		t.Error("AutoConnect should default to false")
	}
}

func TestDefaultConfig_ReconnectInterval(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.ReconnectInterval != 30 {
		t.Errorf("ReconnectInterval: want 30, got %d", cfg.ReconnectInterval)
	}
}

func TestDefaultConfig_LogLevel(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.LogLevel != "info" {
		t.Errorf("LogLevel: want %q, got %q", "info", cfg.LogLevel)
	}
}

func TestDefaultConfig_Headless_False(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.Headless {
		t.Error("Headless should default to false")
	}
}

func TestDefaultConfig_ServiceMode_False(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.ServiceMode {
		t.Error("ServiceMode should default to false")
	}
}

func TestDefaultConfig_OverlayType(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.OverlayType != "dual" {
		t.Errorf("OverlayType: want %q, got %q", "dual", cfg.OverlayType)
	}
}

func TestDefaultConfig_DNSServers(t *testing.T) {
	cfg := DefaultConfig()
	if len(cfg.DNSServers) == 0 {
		t.Error("DNSServers should not be empty")
	}
}

func TestDefaultConfig_AuthRefreshThreshold(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.AuthRefreshThreshold != 300 {
		t.Errorf("AuthRefreshThreshold: want 300, got %d", cfg.AuthRefreshThreshold)
	}
}

// --- Validate ---

func TestValidate_ValidConfig_NoError(t *testing.T) {
	cfg := &Config{
		ManagerURL:           "https://manager.example.com",
		APIKey:               "secret-api-key",
		ClientType:           "client_native",
		LogLevel:             "info",
		ReconnectInterval:    30,
		AuthRefreshThreshold: 300,
		OverlayType:          "dual",
	}
	if err := cfg.Validate(); err != nil {
		t.Errorf("expected valid config to pass, got: %v", err)
	}
}

func TestValidate_MissingManagerURL(t *testing.T) {
	cfg := &Config{
		APIKey:               "key",
		ClientType:           "client_native",
		LogLevel:             "info",
		ReconnectInterval:    30,
		AuthRefreshThreshold: 300,
		OverlayType:          "dual",
	}
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for missing ManagerURL")
	}
}

func TestValidate_MissingAPIKey(t *testing.T) {
	cfg := &Config{
		ManagerURL:           "https://manager.example.com",
		ClientType:           "client_native",
		LogLevel:             "info",
		ReconnectInterval:    30,
		AuthRefreshThreshold: 300,
		OverlayType:          "dual",
	}
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for missing APIKey")
	}
}

func TestValidate_InvalidClientType(t *testing.T) {
	cfg := &Config{
		ManagerURL:           "https://manager.example.com",
		APIKey:               "key",
		ClientType:           "invalid_type",
		LogLevel:             "info",
		ReconnectInterval:    30,
		AuthRefreshThreshold: 300,
		OverlayType:          "dual",
	}
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for invalid ClientType")
	}
}

func TestValidate_InvalidLogLevel(t *testing.T) {
	cfg := &Config{
		ManagerURL:           "https://manager.example.com",
		APIKey:               "key",
		ClientType:           "client_native",
		LogLevel:             "verbose",
		ReconnectInterval:    30,
		AuthRefreshThreshold: 300,
		OverlayType:          "dual",
	}
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for invalid LogLevel")
	}
}

func TestValidate_ValidLogLevels(t *testing.T) {
	levels := []string{"debug", "info", "warn", "error"}
	for _, level := range levels {
		cfg := &Config{
			ManagerURL:           "https://manager.example.com",
			APIKey:               "key",
			ClientType:           "client_native",
			LogLevel:             level,
			ReconnectInterval:    30,
			AuthRefreshThreshold: 300,
			OverlayType:          "dual",
		}
		if err := cfg.Validate(); err != nil {
			t.Errorf("level %q: unexpected error: %v", level, err)
		}
	}
}

func TestValidate_ReconnectIntervalTooLow(t *testing.T) {
	cfg := &Config{
		ManagerURL:           "https://manager.example.com",
		APIKey:               "key",
		ClientType:           "client_native",
		LogLevel:             "info",
		ReconnectInterval:    5,
		AuthRefreshThreshold: 300,
		OverlayType:          "dual",
	}
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for ReconnectInterval < 10")
	}
}

func TestValidate_ReconnectIntervalMinimum(t *testing.T) {
	cfg := &Config{
		ManagerURL:           "https://manager.example.com",
		APIKey:               "key",
		ClientType:           "client_native",
		LogLevel:             "info",
		ReconnectInterval:    10,
		AuthRefreshThreshold: 300,
		OverlayType:          "dual",
	}
	if err := cfg.Validate(); err != nil {
		t.Errorf("ReconnectInterval=10 should be valid: %v", err)
	}
}

func TestValidate_AuthRefreshThresholdTooLow(t *testing.T) {
	cfg := &Config{
		ManagerURL:           "https://manager.example.com",
		APIKey:               "key",
		ClientType:           "client_native",
		LogLevel:             "info",
		ReconnectInterval:    30,
		AuthRefreshThreshold: 30,
		OverlayType:          "dual",
	}
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for AuthRefreshThreshold < 60")
	}
}

func TestValidate_AuthRefreshThresholdMinimum(t *testing.T) {
	cfg := &Config{
		ManagerURL:           "https://manager.example.com",
		APIKey:               "key",
		ClientType:           "client_native",
		LogLevel:             "info",
		ReconnectInterval:    30,
		AuthRefreshThreshold: 60,
		OverlayType:          "dual",
	}
	if err := cfg.Validate(); err != nil {
		t.Errorf("AuthRefreshThreshold=60 should be valid: %v", err)
	}
}

func TestValidate_ValidOverlayTypes(t *testing.T) {
	types := []string{"wireguard", "openziti", "dual"}
	for _, ot := range types {
		cfg := &Config{
			ManagerURL:           "https://manager.example.com",
			APIKey:               "key",
			ClientType:           "client_native",
			LogLevel:             "info",
			ReconnectInterval:    30,
			AuthRefreshThreshold: 300,
			OverlayType:          ot,
		}
		if err := cfg.Validate(); err != nil {
			t.Errorf("overlay type %q: unexpected error: %v", ot, err)
		}
	}
}

func TestValidate_InvalidOverlayType(t *testing.T) {
	cfg := &Config{
		ManagerURL:           "https://manager.example.com",
		APIKey:               "key",
		ClientType:           "client_native",
		LogLevel:             "info",
		ReconnectInterval:    30,
		AuthRefreshThreshold: 300,
		OverlayType:          "ipsec",
	}
	if err := cfg.Validate(); err == nil {
		t.Error("expected error for invalid OverlayType")
	}
}

// --- GetConfigDir ---

func TestGetConfigDir_NonEmpty(t *testing.T) {
	dir := GetConfigDir()
	if dir == "" {
		t.Error("GetConfigDir() returned empty string")
	}
}

func TestGetConfigDir_ContainsTobogganing(t *testing.T) {
	dir := GetConfigDir()
	// All platforms should have "tobogganing" or "Tobogganing" in the path.
	lower := filepath.Base(dir)
	if lower != "tobogganing" && lower != "Tobogganing" {
		t.Errorf("GetConfigDir() base should be tobogganing, got %q (full: %q)", lower, dir)
	}
}

func TestGetConfigDir_PlatformSpecific(t *testing.T) {
	dir := GetConfigDir()
	switch runtime.GOOS {
	case "linux":
		// Should contain "tobogganing" under XDG or HOME.
		if dir == "" {
			t.Error("Linux config dir should not be empty")
		}
	case "darwin":
		home := os.Getenv("HOME")
		if home != "" && dir != home+"/.tobogganing" {
			t.Errorf("Darwin: expected %q, got %q", home+"/.tobogganing", dir)
		}
	case "windows":
		appdata := os.Getenv("APPDATA")
		if appdata != "" && dir != appdata+"\\Tobogganing" {
			t.Errorf("Windows: expected %q, got %q", appdata+"\\Tobogganing", dir)
		}
	}
}

// --- GetDefaultConfigFile ---

func TestGetDefaultConfigFile_NonEmpty(t *testing.T) {
	f := GetDefaultConfigFile()
	if f == "" {
		t.Error("GetDefaultConfigFile() returned empty string")
	}
}

func TestGetDefaultConfigFile_HasYamlExtension(t *testing.T) {
	f := GetDefaultConfigFile()
	ext := filepath.Ext(f)
	if ext != ".yaml" {
		t.Errorf("expected .yaml extension, got %q", ext)
	}
}

// --- GetWireGuardConfigPath ---

func TestGetWireGuardConfigPath_NonEmpty(t *testing.T) {
	cfg := &Config{}
	p := cfg.GetWireGuardConfigPath()
	if p == "" {
		t.Error("GetWireGuardConfigPath() returned empty string")
	}
}

// --- WriteFile ---

func TestWriteFile_CreatesFileWithContent(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "subdir", "test.conf")
	data := []byte("test content")

	cfg := &Config{}
	if err := cfg.WriteFile(path, data); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(got) != string(data) {
		t.Errorf("content mismatch: want %q, got %q", data, got)
	}
}

func TestWriteFile_CreatesDirectoryIfNotExist(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "deep", "nested", "file.yaml")

	cfg := &Config{}
	if err := cfg.WriteFile(path, []byte("data")); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	if _, err := os.Stat(filepath.Dir(path)); err != nil {
		t.Errorf("expected directory to be created: %v", err)
	}
}

func TestWriteFile_FilePermissions(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("file permission test not applicable on Windows")
	}

	dir := t.TempDir()
	path := filepath.Join(dir, "secret.conf")

	cfg := &Config{}
	if err := cfg.WriteFile(path, []byte("secret")); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("Stat: %v", err)
	}

	perm := info.Mode().Perm()
	if perm != 0600 {
		t.Errorf("expected file permissions 0600, got %o", perm)
	}
}

// --- LoadFromFile ---

func TestLoadFromFile_ValidYAML(t *testing.T) {
	dir := t.TempDir()
	cfgFile := filepath.Join(dir, "config.yaml")

	content := `manager_url: "https://example.com"
api_key: "testkey"
client_name: "testclient"
client_type: "client_native"
log_level: "debug"
reconnect_interval: 30
auth_refresh_threshold: 300
overlay_type: "dual"
`
	if err := os.WriteFile(cfgFile, []byte(content), 0600); err != nil {
		t.Fatalf("write temp config: %v", err)
	}

	cfg := DefaultConfig()
	if err := LoadFromFile(cfg, cfgFile); err != nil {
		t.Fatalf("LoadFromFile: %v", err)
	}

	if cfg.ManagerURL != "https://example.com" {
		t.Errorf("ManagerURL: want %q, got %q", "https://example.com", cfg.ManagerURL)
	}
	if cfg.APIKey != "testkey" {
		t.Errorf("APIKey: want %q, got %q", "testkey", cfg.APIKey)
	}
	if cfg.ClientName != "testclient" {
		t.Errorf("ClientName: want %q, got %q", "testclient", cfg.ClientName)
	}
	if cfg.LogLevel != "debug" {
		t.Errorf("LogLevel: want %q, got %q", "debug", cfg.LogLevel)
	}
}

func TestLoadFromFile_NonExistentFile_ReturnsError(t *testing.T) {
	cfg := DefaultConfig()
	err := LoadFromFile(cfg, "/nonexistent/path/config.yaml")
	if err == nil {
		t.Error("expected error loading nonexistent config file")
	}
}

// --- LoadFromDefaults ---

func TestLoadFromDefaults_SetsDefaults(t *testing.T) {
	// Unset any env that might interfere.
	os.Unsetenv("TOBOGGANING_MANAGER_URL")
	os.Unsetenv("TOBOGGANING_API_KEY")

	cfg := &Config{}
	if err := LoadFromDefaults(cfg); err != nil {
		t.Fatalf("LoadFromDefaults: %v", err)
	}

	// Defaults should be applied even when no config file found.
	// Note: a pre-existing config file on the machine may override defaults;
	// we only assert fields that are not overridable by typical local configs.
	if cfg.ClientType != "client_native" {
		t.Errorf("ClientType: want %q, got %q", "client_native", cfg.ClientType)
	}
	if cfg.ReconnectInterval == 0 {
		t.Error("ReconnectInterval should be non-zero")
	}
	// LogLevel may be overridden by a local config file; just verify it's non-empty.
	if cfg.LogLevel == "" {
		t.Error("LogLevel should not be empty")
	}
	if cfg.OverlayType == "" {
		t.Error("OverlayType should not be empty")
	}
}

func TestLoadFromDefaults_EnvVarOverride(t *testing.T) {
	t.Setenv("TOBOGGANING_MANAGER_URL", "https://env-override.example.com")
	defer os.Unsetenv("TOBOGGANING_MANAGER_URL")

	cfg := &Config{}
	if err := LoadFromDefaults(cfg); err != nil {
		t.Fatalf("LoadFromDefaults: %v", err)
	}

	if cfg.ManagerURL != "https://env-override.example.com" {
		t.Errorf("ManagerURL from env: want %q, got %q", "https://env-override.example.com", cfg.ManagerURL)
	}
}

// --- Save ---

func TestSave_WritesFile(t *testing.T) {
	dir := t.TempDir()
	cfgFile := filepath.Join(dir, "saved_config.yaml")

	cfg := &Config{
		ManagerURL:           "https://save.example.com",
		APIKey:               "saved-key",
		ClientName:           "saved-client",
		ClientType:           "client_native",
		AutoConnect:          true,
		ReconnectInterval:    45,
		LogLevel:             "warn",
		AuthRefreshThreshold: 120,
		DNSServers:           []string{"8.8.8.8"},
	}

	if err := cfg.Save(cfgFile); err != nil {
		t.Fatalf("Save: %v", err)
	}

	// File should exist.
	if _, err := os.Stat(cfgFile); err != nil {
		t.Errorf("config file should exist after Save: %v", err)
	}
}
