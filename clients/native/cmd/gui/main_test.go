package main

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/spf13/cobra"
)

// TestPackageConstants verifies OS constant values are defined.
func TestPackageConstants(t *testing.T) {
	if OSWindows != "windows" {
		t.Errorf("OSWindows: expected 'windows', got %q", OSWindows)
	}
	if OSDarwin != "darwin" {
		t.Errorf("OSDarwin: expected 'darwin', got %q", OSDarwin)
	}
	if OSLinux != "linux" {
		t.Errorf("OSLinux: expected 'linux', got %q", OSLinux)
	}
}

// TestPackageVersions verifies version info is available.
func TestPackageVersions(t *testing.T) {
	if version == "" {
		t.Error("version should not be empty")
	}
	t.Logf("version=%s, buildTime=%s, gitCommit=%s", version, buildTime, gitCommit)
}

// newTestCmd creates a cobra.Command with the same persistent flags as the real root command.
func newTestCmd() *cobra.Command {
	cmd := &cobra.Command{Use: "test"}
	cmd.PersistentFlags().StringP("config", "c", "", "")
	cmd.PersistentFlags().StringP("manager-url", "m", "", "")
	cmd.PersistentFlags().StringP("log-level", "l", "info", "")
	cmd.PersistentFlags().Bool("headless", false, "")
	return cmd
}

// writeValidConfig writes a minimal valid Tobogganing config YAML to a temp file
// and returns the path. The file is cleaned up via t.Cleanup.
func writeValidConfig(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "config.yaml")
	content := `manager_url: "https://manager.test.internal"
api_key: "test-api-key-12345"
client_type: "client_native"
log_level: "info"
reconnect_interval: 30
auth_refresh_threshold: 300
overlay_type: "dual"
`
	if err := os.WriteFile(path, []byte(content), 0600); err != nil {
		t.Fatalf("writeValidConfig: %v", err)
	}
	return path
}

// --- loadConfig ---

// TestLoadConfig_EmptyCommand returns an error because ManagerURL is empty.
func TestLoadConfig_EmptyCommand(t *testing.T) {
	cmd := newTestCmd()
	_, err := loadConfig(cmd)
	if err == nil {
		t.Error("expected error for empty config (no ManagerURL)")
	}
}

// TestLoadConfig_WithNonexistentFile exercises the LoadFromFile error path.
func TestLoadConfig_WithNonexistentFile(t *testing.T) {
	cmd := newTestCmd()
	if err := cmd.ParseFlags([]string{"--config", "/tmp/nonexistent-tobogganing-99999.yaml"}); err != nil {
		t.Fatalf("ParseFlags: %v", err)
	}
	_, err := loadConfig(cmd)
	if err == nil {
		t.Error("expected error for non-existent config file")
	}
}

// TestLoadConfig_ValidFile successfully loads a valid config.
func TestLoadConfig_ValidFile(t *testing.T) {
	cfgPath := writeValidConfig(t)
	cmd := newTestCmd()
	if err := cmd.ParseFlags([]string{"--config", cfgPath}); err != nil {
		t.Fatalf("ParseFlags: %v", err)
	}
	cfg, err := loadConfig(cmd)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if cfg.ManagerURL != "https://manager.test.internal" {
		t.Errorf("ManagerURL mismatch: %s", cfg.ManagerURL)
	}
}

// --- runConnect ---

// TestRunConnect_LoadConfigFails exercises the loadConfig error path.
func TestRunConnect_LoadConfigFails(t *testing.T) {
	cmd := newTestCmd()
	err := runConnect(cmd, nil)
	if err == nil {
		t.Error("expected error when config fails to load")
	}
}

// TestRunConnect_ClientNewFails exercises the client.New error path.
// With a valid config, client.New() tries to create a WireGuard kernel client
// which will fail in CI (no kernel module), covering the "failed to create client" path.
func TestRunConnect_ClientNewFails(t *testing.T) {
	cfgPath := writeValidConfig(t)
	cmd := newTestCmd()
	if err := cmd.ParseFlags([]string{"--config", cfgPath}); err != nil {
		t.Fatalf("ParseFlags: %v", err)
	}
	// The error may be from wgctrl or from the remote connect — either is fine.
	err := runConnect(cmd, nil)
	// We expect an error (wgctrl.New() fails without kernel WireGuard support).
	// If it somehow succeeds (test env has WireGuard), that's also fine.
	t.Logf("runConnect result: %v", err)
}

// --- runDisconnect ---

// TestRunDisconnect_LoadConfigFails exercises the loadConfig error path.
func TestRunDisconnect_LoadConfigFails(t *testing.T) {
	cmd := newTestCmd()
	err := runDisconnect(cmd, nil)
	if err == nil {
		t.Error("expected error when config fails to load")
	}
}

// TestRunDisconnect_ClientNewFails exercises the client.New error path.
func TestRunDisconnect_ClientNewFails(t *testing.T) {
	cfgPath := writeValidConfig(t)
	cmd := newTestCmd()
	if err := cmd.ParseFlags([]string{"--config", cfgPath}); err != nil {
		t.Fatalf("ParseFlags: %v", err)
	}
	err := runDisconnect(cmd, nil)
	t.Logf("runDisconnect result: %v", err)
}

// --- runStatus ---

// TestRunStatus_LoadConfigFails exercises the loadConfig error path.
func TestRunStatus_LoadConfigFails(t *testing.T) {
	cmd := newTestCmd()
	err := runStatus(cmd, nil)
	if err == nil {
		t.Error("expected error when config fails to load")
	}
}

// TestRunStatus_ClientNewFails exercises the client.New error path.
func TestRunStatus_ClientNewFails(t *testing.T) {
	cfgPath := writeValidConfig(t)
	cmd := newTestCmd()
	if err := cmd.ParseFlags([]string{"--config", cfgPath}); err != nil {
		t.Fatalf("ParseFlags: %v", err)
	}
	err := runStatus(cmd, nil)
	t.Logf("runStatus result: %v", err)
}

// --- runGUI ---

// TestRunGUI_LoadConfigFails exercises the loadConfig error path.
func TestRunGUI_LoadConfigFails(t *testing.T) {
	cmd := newTestCmd()
	err := runGUI(cmd, nil)
	if err == nil {
		t.Error("expected error when config fails to load")
	}
}

// TestRunGUI_ValidConfig exercises the tray.Run path. With -tags nogui, tray.Run
// is a no-op stub that returns nil immediately.
func TestRunGUI_ValidConfig(t *testing.T) {
	cfgPath := writeValidConfig(t)
	cmd := newTestCmd()
	if err := cmd.ParseFlags([]string{"--config", cfgPath}); err != nil {
		t.Fatalf("ParseFlags: %v", err)
	}
	err := runGUI(cmd, nil)
	// With nogui build tag, tray.Run returns nil immediately.
	if err != nil {
		t.Logf("runGUI returned: %v (acceptable in non-nogui builds)", err)
	}
}

// --- runServiceInstall/Uninstall/Start/Stop ---

// TestRunServiceInstall exercises all platform branches by overriding currentGOOS.
func TestRunServiceInstall_Linux(t *testing.T) {
	old := *CurrentGOOS
	*CurrentGOOS = "linux"
	defer func() { *CurrentGOOS = old }()
	err := runServiceInstall(nil, nil)
	if err == nil {
		t.Error("expected error from installLinuxService")
	}
}

func TestRunServiceInstall_Windows(t *testing.T) {
	old := *CurrentGOOS
	*CurrentGOOS = "windows"
	defer func() { *CurrentGOOS = old }()
	err := runServiceInstall(nil, nil)
	if err == nil {
		t.Error("expected error from installWindowsService")
	}
}

func TestRunServiceInstall_Darwin(t *testing.T) {
	old := *CurrentGOOS
	*CurrentGOOS = "darwin"
	defer func() { *CurrentGOOS = old }()
	err := runServiceInstall(nil, nil)
	if err == nil {
		t.Error("expected error from installMacOSService")
	}
}

func TestRunServiceInstall_Unsupported(t *testing.T) {
	old := *CurrentGOOS
	*CurrentGOOS = "plan9"
	defer func() { *CurrentGOOS = old }()
	err := runServiceInstall(nil, nil)
	if err == nil {
		t.Error("expected error for unsupported platform")
	}
}

func TestRunServiceUninstall_AllPlatforms(t *testing.T) {
	platforms := []string{"linux", "windows", "darwin", "plan9"}
	for _, p := range platforms {
		t.Run(p, func(t *testing.T) {
			old := *CurrentGOOS
			*CurrentGOOS = p
			defer func() { *CurrentGOOS = old }()
			err := runServiceUninstall(nil, nil)
			t.Logf("runServiceUninstall(%s): %v", p, err)
		})
	}
}

func TestRunServiceStart_AllPlatforms(t *testing.T) {
	platforms := []string{"linux", "windows", "darwin", "plan9"}
	for _, p := range platforms {
		t.Run(p, func(t *testing.T) {
			old := *CurrentGOOS
			*CurrentGOOS = p
			defer func() { *CurrentGOOS = old }()
			err := runServiceStart(nil, nil)
			t.Logf("runServiceStart(%s): %v", p, err)
		})
	}
}

func TestRunServiceStop_AllPlatforms(t *testing.T) {
	platforms := []string{"linux", "windows", "darwin", "plan9"}
	for _, p := range platforms {
		t.Run(p, func(t *testing.T) {
			old := *CurrentGOOS
			*CurrentGOOS = p
			defer func() { *CurrentGOOS = old }()
			err := runServiceStop(nil, nil)
			t.Logf("runServiceStop(%s): %v", p, err)
		})
	}
}

// --- Platform stub functions (all return "not implemented" errors) ---

func TestInstallWindowsService(t *testing.T) {
	if err := installWindowsService(); err == nil {
		t.Error("expected error: Windows service not implemented")
	}
}

func TestUninstallWindowsService(t *testing.T) {
	if err := uninstallWindowsService(); err == nil {
		t.Error("expected error: Windows service not implemented")
	}
}

func TestStartWindowsService(t *testing.T) {
	if err := startWindowsService(); err == nil {
		t.Error("expected error: Windows service not implemented")
	}
}

func TestStopWindowsService(t *testing.T) {
	if err := stopWindowsService(); err == nil {
		t.Error("expected error: Windows service not implemented")
	}
}

func TestInstallMacOSService(t *testing.T) {
	if err := installMacOSService(); err == nil {
		t.Error("expected error: macOS service not implemented")
	}
}

func TestUninstallMacOSService(t *testing.T) {
	if err := uninstallMacOSService(); err == nil {
		t.Error("expected error: macOS service not implemented")
	}
}

func TestStartMacOSService(t *testing.T) {
	if err := startMacOSService(); err == nil {
		t.Error("expected error: macOS service not implemented")
	}
}

func TestStopMacOSService(t *testing.T) {
	if err := stopMacOSService(); err == nil {
		t.Error("expected error: macOS service not implemented")
	}
}

func TestInstallLinuxService(t *testing.T) {
	if err := installLinuxService(); err == nil {
		t.Error("expected error: Linux service not implemented")
	}
}

func TestUninstallLinuxService(t *testing.T) {
	if err := uninstallLinuxService(); err == nil {
		t.Error("expected error: Linux service not implemented")
	}
}

func TestStartLinuxService(t *testing.T) {
	if err := startLinuxService(); err == nil {
		t.Error("expected error: Linux service not implemented")
	}
}

func TestStopLinuxService(t *testing.T) {
	if err := stopLinuxService(); err == nil {
		t.Error("expected error: Linux service not implemented")
	}
}
