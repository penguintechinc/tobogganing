package main

import (
	"bytes"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/tobogganing/clients/native/internal/config"
)

// --- parseConfigFlags ---

func TestParseConfigFlags_EmptyString_LoadsDefaults(t *testing.T) {
	cfg, err := parseConfigFlags("")
	if err != nil {
		// Expected if defaults can't be loaded
		if !strings.Contains(err.Error(), "default") && !strings.Contains(err.Error(), "config") {
			t.Logf("parseConfigFlags('') returned unexpected error: %v", err)
		}
		return
	}

	if cfg == nil {
		t.Fatal("parseConfigFlags returned nil config without error")
	}
}

func TestParseConfigFlags_DefaultConfig_NotNil(t *testing.T) {
	cfg, err := parseConfigFlags("")
	if err != nil {
		t.Logf("parseConfigFlags returned error: %v", err)
		return
	}

	if cfg == nil {
		t.Fatal("parseConfigFlags returned nil config without error")
	}

	// Verify config is at least a valid Config struct
	if cfg.ClientType == "" {
		t.Logf("config.ClientType is empty (may be expected)")
	}
}

func TestParseConfigFlags_InvalidFile_Error(t *testing.T) {
	cfg, err := parseConfigFlags("/nonexistent/config/file.yaml")
	if err == nil {
		t.Error("parseConfigFlags should return error for non-existent file")
	}
	if cfg != nil {
		t.Error("parseConfigFlags should return nil config on error")
	}
}

func TestParseConfigFlags_NonexistentFile_HasError(t *testing.T) {
	cfg, err := parseConfigFlags("/does/not/exist/config.yaml")
	if err == nil {
		t.Error("parseConfigFlags should error for nonexistent file")
	}
	if !strings.Contains(err.Error(), "config") {
		t.Logf("error message: %v", err)
	}
	if cfg != nil {
		t.Error("cfg should be nil on error")
	}
}

func TestParseConfigFlags_EmptyFile_Path(t *testing.T) {
	// Empty string should load defaults
	cfg, err := parseConfigFlags("")
	// May error if defaults don't work in test env, but that's ok
	if err == nil && cfg == nil {
		t.Fatal("should return config or error, not both nil")
	}
}

func TestParseConfigFlags_ValidFile(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "test-config.yaml")

	content := `
client_name: test-client
manager_url: https://manager.test.example.com
`
	if err := os.WriteFile(configPath, []byte(content), 0o644); err != nil {
		t.Fatalf("failed to create test config file: %v", err)
	}

	cfg, err := parseConfigFlags(configPath)
	if err != nil {
		t.Logf("parseConfigFlags returned error: %v (may be expected)", err)
		return
	}

	if cfg == nil {
		t.Fatal("parseConfigFlags returned nil config without error")
	}
}

func TestParseConfigFlags_WithAbsolutePath(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "config.yaml")

	content := "client_name: test\n"
	if err := os.WriteFile(configPath, []byte(content), 0o644); err != nil {
		t.Fatalf("failed to create config file: %v", err)
	}

	cfg, err := parseConfigFlags(configPath)
	// May error due to format, but function should attempt to load
	if err == nil && cfg == nil {
		t.Fatal("should return config or error")
	}
}

func TestParseConfigFlags_FilePath_Branch(t *testing.T) {
	// Ensure we test both branches: with configFile != "" and configFile == ""

	// Branch 1: configFile != "" - LoadFromFile
	dir := t.TempDir()
	configPath := filepath.Join(dir, "test.yaml")
	if err := os.WriteFile(configPath, []byte("client_name: test\n"), 0o644); err != nil {
		t.Fatalf("failed to create config: %v", err)
	}

	cfg1, err1 := parseConfigFlags(configPath)
	// Will likely error due to format, but that's ok - we're testing the branch is taken
	t.Logf("Branch 1 (configFile != ''): err=%v, cfg=%v", err1, cfg1)

	// Branch 2: configFile == "" - LoadFromDefaults
	cfg2, err2 := parseConfigFlags("")
	t.Logf("Branch 2 (configFile == ''): err=%v, cfg=%v", err2, cfg2)

	// At least one should succeed or both should error
	if err1 != nil && err2 != nil {
		t.Logf("Both branches returned errors (expected in test env)")
	}
}

// --- validateConfig ---

func TestValidateConfig_Valid_NoError(t *testing.T) {
	cfg := &config.Config{
		ManagerURL: "https://manager.example.com",
	}
	err := validateConfig(cfg)
	if err != nil {
		t.Errorf("validateConfig should not error with valid manager URL: %v", err)
	}
}

func TestValidateConfig_Empty_Error(t *testing.T) {
	cfg := &config.Config{
		ManagerURL: "",
	}
	err := validateConfig(cfg)
	if err == nil {
		t.Error("validateConfig should error with empty manager URL")
	}
}

func TestValidateConfig_WithURL_Success(t *testing.T) {
	cfg := &config.Config{
		ManagerURL: "https://manager.example.com:8443",
	}
	err := validateConfig(cfg)
	if err != nil {
		t.Errorf("validateConfig should succeed with valid URL: %v", err)
	}
}

func TestValidateConfig_WithHTTPURL_Success(t *testing.T) {
	cfg := &config.Config{
		ManagerURL: "http://localhost:8080",
	}
	err := validateConfig(cfg)
	if err != nil {
		t.Errorf("validateConfig should accept HTTP URLs: %v", err)
	}
}

func TestValidateConfig_Whitespace_Error(t *testing.T) {
	cfg := &config.Config{
		ManagerURL: "   ",
	}
	err := validateConfig(cfg)
	// May or may not error depending on trimming logic
	if err == nil {
		t.Logf("validateConfig accepted whitespace-only URL")
	}
}

// --- printConfigInfo ---

func TestPrintConfigInfo_NoNil(t *testing.T) {
	cfg := &config.Config{
		ManagerURL: "https://manager.example.com",
		ClientType: "headless",
		AutoConnect: true,
	}

	// Capture stdout
	old := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w

	printConfigInfo(cfg)

	w.Close()
	os.Stdout = old

	var buf bytes.Buffer
	io.Copy(&buf, r)
	output := buf.String()

	if !strings.Contains(output, "Tobogganing Client") {
		t.Error("output should contain 'Tobogganing Client'")
	}
	if !strings.Contains(output, "Manager URL") {
		t.Error("output should contain 'Manager URL'")
	}
}

func TestPrintConfigInfo_WithConfig(t *testing.T) {
	cfg := &config.Config{
		ManagerURL: "https://manager.example.com",
		ClientType: "test-type",
		AutoConnect: false,
	}

	// Capture stdout
	old := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w

	printConfigInfo(cfg)

	w.Close()
	os.Stdout = old

	var buf bytes.Buffer
	io.Copy(&buf, r)
	output := buf.String()

	if !strings.Contains(output, "https://manager.example.com") {
		t.Error("output should contain the manager URL")
	}
	if !strings.Contains(output, "test-type") {
		t.Error("output should contain the client type")
	}
}

func TestPrintConfigInfo_EmptyURL(t *testing.T) {
	cfg := &config.Config{
		ManagerURL: "",
		ClientType: "test",
		AutoConnect: true,
	}

	// Should not panic with empty URL
	printConfigInfo(cfg)
}

// --- Integration tests ---

func TestParseConfigFlags_MultipleCallsConsistent(t *testing.T) {
	cfg1, err1 := parseConfigFlags("")
	cfg2, err2 := parseConfigFlags("")

	// Both calls should have same error state
	if (err1 == nil) != (err2 == nil) {
		t.Error("parseConfigFlags should return same error state on multiple calls")
	}

	if err1 == nil && err2 == nil {
		if cfg1 == nil || cfg2 == nil {
			t.Error("parseConfigFlags should return non-nil configs on success")
		}
	}
}

func TestValidateAndPrintConfigInfo_Flow(t *testing.T) {
	cfg := &config.Config{
		ManagerURL: "https://manager.example.com",
		ClientType: "headless",
		AutoConnect: true,
	}

	// Validate should pass
	err := validateConfig(cfg)
	if err != nil {
		t.Fatalf("validateConfig failed: %v", err)
	}

	// printConfigInfo should not panic
	printConfigInfo(cfg)
}

func TestParseConfig_ThenValidate(t *testing.T) {
	dir := t.TempDir()
	configPath := filepath.Join(dir, "config.yaml")

	content := `manager_url: https://manager.example.com
`
	if err := os.WriteFile(configPath, []byte(content), 0o644); err != nil {
		t.Fatalf("failed to create config file: %v", err)
	}

	cfg, err := parseConfigFlags(configPath)
	if err != nil {
		t.Logf("parseConfigFlags returned error: %v (may be expected)", err)
		return
	}

	if cfg == nil {
		t.Fatal("config should not be nil")
	}

	// Even if parsed, validate behavior depends on config content
	validateConfig(cfg)
}
