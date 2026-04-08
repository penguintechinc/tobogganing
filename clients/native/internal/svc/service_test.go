package svc

import (
	"fmt"
	"strings"
	"testing"

	"github.com/kardianos/service"
)

// --- Config ---

func TestConfig_ZeroValue(t *testing.T) {
	var cfg Config
	if cfg.Name != "" {
		t.Errorf("zero-value Config.Name should be empty, got %q", cfg.Name)
	}
}

func TestConfig_Fields(t *testing.T) {
	cfg := Config{
		Name:        "test-service",
		DisplayName: "Test Service",
		Description: "A test service",
		Executable:  "/usr/bin/test",
		Arguments:   []string{"--flag", "value"},
	}

	if cfg.Name != "test-service" {
		t.Errorf("Name: got %q", cfg.Name)
	}
	if cfg.DisplayName != "Test Service" {
		t.Errorf("DisplayName: got %q", cfg.DisplayName)
	}
	if cfg.Description != "A test service" {
		t.Errorf("Description: got %q", cfg.Description)
	}
	if cfg.Executable != "/usr/bin/test" {
		t.Errorf("Executable: got %q", cfg.Executable)
	}
	if len(cfg.Arguments) != 2 {
		t.Errorf("Arguments length: want 2, got %d", len(cfg.Arguments))
	}
}

// --- NewManager ---

func TestNewManager_ValidConfig_ReturnsManager(t *testing.T) {
	m, err := NewManager(Config{
		Name:        "test-svc",
		DisplayName: "Test Svc",
		Description: "test",
	})
	if err != nil {
		t.Fatalf("NewManager with valid config returned error: %v", err)
	}
	if m == nil {
		t.Fatal("NewManager returned nil manager")
	}
}

func TestNewManager_WithExecutable(t *testing.T) {
	m, err := NewManager(Config{
		Name:        "test-svc",
		DisplayName: "Test Svc",
		Description: "test",
		Executable:  "/usr/bin/test-executable",
	})
	if err != nil {
		t.Fatalf("NewManager with Executable returned error: %v", err)
	}
	if m == nil {
		t.Fatal("NewManager returned nil manager")
	}
}

func TestNewManager_WithArguments(t *testing.T) {
	m, err := NewManager(Config{
		Name:        "test-svc",
		DisplayName: "Test Svc",
		Description: "test",
		Arguments:   []string{"--config", "/etc/test.yaml"},
	})
	if err != nil {
		t.Fatalf("NewManager with Arguments returned error: %v", err)
	}
	if m == nil {
		t.Fatal("NewManager returned nil manager")
	}
}

func TestNewManager_EmptyName_Behavior(t *testing.T) {
	// Empty Name may or may not error depending on kardianos/service.
	// We just verify it doesn't panic.
	_, _ = NewManager(Config{
		Name: "",
	})
}

func TestNewManager_MinimalConfig(t *testing.T) {
	// Minimal valid config with just a name.
	m, err := NewManager(Config{Name: "minimal-svc"})
	if err != nil {
		t.Logf("NewManager minimal config error (may be platform specific): %v", err)
	} else if m == nil {
		t.Error("expected non-nil manager")
	}
}

// --- Install / Uninstall / Start / Stop / Status ---
// These require OS service manager access (e.g., systemd on Linux).
// We verify they return appropriate errors when run without privileges.

func TestManager_Install_ReturnsErrorOrSucceeds(t *testing.T) {
	m, err := NewManager(Config{
		Name:        "tobogganing-test-install",
		DisplayName: "Tobogganing Test Install",
		Description: "test",
	})
	if err != nil {
		t.Skipf("NewManager failed (service platform issue): %v", err)
	}

	err = m.Install()
	// Either success (unlikely without root) or a meaningful error.
	if err != nil {
		// Error message should be wrapped.
		if !strings.Contains(err.Error(), "install service") {
			t.Errorf("expected error to mention 'install service', got: %v", err)
		}
	}
}

func TestManager_Uninstall_ReturnsErrorOrSucceeds(t *testing.T) {
	m, err := NewManager(Config{
		Name:        "tobogganing-test-uninstall",
		DisplayName: "Tobogganing Test Uninstall",
		Description: "test",
	})
	if err != nil {
		t.Skipf("NewManager failed: %v", err)
	}

	err = m.Uninstall()
	if err != nil {
		if !strings.Contains(err.Error(), "uninstall service") {
			t.Errorf("expected error to mention 'uninstall service', got: %v", err)
		}
	}
}

func TestManager_Start_ReturnsErrorOrSucceeds(t *testing.T) {
	m, err := NewManager(Config{
		Name:        "tobogganing-test-start",
		DisplayName: "Tobogganing Test Start",
		Description: "test",
	})
	if err != nil {
		t.Skipf("NewManager failed: %v", err)
	}

	err = m.Start()
	if err != nil {
		if !strings.Contains(err.Error(), "start service") {
			t.Errorf("expected error to mention 'start service', got: %v", err)
		}
	}
}

func TestManager_Stop_ReturnsErrorOrSucceeds(t *testing.T) {
	m, err := NewManager(Config{
		Name:        "tobogganing-test-stop",
		DisplayName: "Tobogganing Test Stop",
		Description: "test",
	})
	if err != nil {
		t.Skipf("NewManager failed: %v", err)
	}

	err = m.Stop()
	if err != nil {
		if !strings.Contains(err.Error(), "stop service") {
			t.Errorf("expected error to mention 'stop service', got: %v", err)
		}
	}
}

func TestManager_Status_ReturnsStringOrError(t *testing.T) {
	m, err := NewManager(Config{
		Name:        "tobogganing-test-status",
		DisplayName: "Tobogganing Test Status",
		Description: "test",
	})
	if err != nil {
		t.Skipf("NewManager failed: %v", err)
	}

	status, err := m.Status()
	if err != nil {
		if !strings.Contains(err.Error(), "service status") {
			t.Errorf("expected error to mention 'service status', got: %v", err)
		}
		return
	}

	// Status should be one of the known strings.
	validStatuses := map[string]bool{
		"running": true,
		"stopped": true,
		"unknown": true,
	}
	if !validStatuses[status] {
		t.Errorf("unexpected status string %q (want running|stopped|unknown)", status)
	}
}

// --- program ---

func TestProgram_Start_NoError(t *testing.T) {
	p := &program{}
	err := p.Start(nil)
	if err != nil {
		t.Errorf("program.Start: %v", err)
	}
}

func TestProgram_Stop_NoError(t *testing.T) {
	p := &program{}
	err := p.Stop(nil)
	if err != nil {
		t.Errorf("program.Stop: %v", err)
	}
}

// --- Manager error path coverage (mock-based) ---

// mockLogger implements service.Logger for testing
type mockLogger struct{}

func (m *mockLogger) Error(args ...interface{}) error {
	return nil
}
func (m *mockLogger) Warning(args ...interface{}) error {
	return nil
}
func (m *mockLogger) Info(args ...interface{}) error {
	return nil
}
func (m *mockLogger) Errorf(format string, a ...interface{}) error {
	return nil
}
func (m *mockLogger) Warningf(format string, a ...interface{}) error {
	return nil
}
func (m *mockLogger) Infof(format string, a ...interface{}) error {
	return nil
}

// mockService implements a mock of kardianos/service.Service for testing error paths
type mockService struct {
	installErr    error
	uninstallErr  error
	startErr      error
	stopErr       error
	restartErr    error
	statusErr     error
	statusValue   service.Status
}

func (m *mockService) Start() error               { return m.startErr }
func (m *mockService) Stop() error                { return m.stopErr }
func (m *mockService) Restart() error             { return m.restartErr }
func (m *mockService) Install() error             { return m.installErr }
func (m *mockService) Uninstall() error           { return m.uninstallErr }
func (m *mockService) Status() (service.Status, error) { return m.statusValue, m.statusErr }
func (m *mockService) Run() error                 { return nil }
func (m *mockService) Logger(errs chan<- error) (service.Logger, error) {
	return &mockLogger{}, nil
}
func (m *mockService) SystemLogger(errs chan<- error) (service.Logger, error) {
	return &mockLogger{}, nil
}
func (m *mockService) String() string {
	return "mock-service"
}
func (m *mockService) Platform() string {
	return "mock"
}

// injectMockService replaces m.svc with a mock for error testing
func injectMockService(m *Manager, mock *mockService) {
	m.svc = mock
}

func TestManager_Install_WrapsError(t *testing.T) {
	m := &Manager{svc: &mockService{installErr: fmt.Errorf("permission denied")}}
	err := m.Install()
	if err == nil {
		t.Error("expected error")
	}
	if !strings.Contains(err.Error(), "install service") {
		t.Errorf("error should mention 'install service', got: %v", err)
	}
}

func TestManager_Uninstall_WrapsError(t *testing.T) {
	m := &Manager{svc: &mockService{uninstallErr: fmt.Errorf("not installed")}}
	err := m.Uninstall()
	if err == nil {
		t.Error("expected error")
	}
	if !strings.Contains(err.Error(), "uninstall service") {
		t.Errorf("error should mention 'uninstall service', got: %v", err)
	}
}

func TestManager_Start_WrapsError(t *testing.T) {
	m := &Manager{svc: &mockService{startErr: fmt.Errorf("service not found")}}
	err := m.Start()
	if err == nil {
		t.Error("expected error")
	}
	if !strings.Contains(err.Error(), "start service") {
		t.Errorf("error should mention 'start service', got: %v", err)
	}
}

func TestManager_Stop_WrapsError(t *testing.T) {
	m := &Manager{svc: &mockService{stopErr: fmt.Errorf("timeout")}}
	err := m.Stop()
	if err == nil {
		t.Error("expected error")
	}
	if !strings.Contains(err.Error(), "stop service") {
		t.Errorf("error should mention 'stop service', got: %v", err)
	}
}

func TestManager_Status_ReturnsRunning(t *testing.T) {
	// Simulate running status
	m := &Manager{svc: &mockService{statusValue: service.StatusRunning}}
	status, err := m.Status()
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status != "running" {
		t.Errorf("expected 'running', got %q", status)
	}
}

func TestManager_Status_ReturnsStopped(t *testing.T) {
	// Simulate stopped status
	m := &Manager{svc: &mockService{statusValue: service.StatusStopped}}
	status, err := m.Status()
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status != "stopped" {
		t.Errorf("expected 'stopped', got %q", status)
	}
}

func TestManager_Status_ReturnsUnknown(t *testing.T) {
	// Simulate unknown status (use a value > 1)
	m := &Manager{svc: &mockService{statusValue: service.Status(99)}}
	status, err := m.Status()
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status != "unknown" {
		t.Errorf("expected 'unknown', got %q", status)
	}
}

func TestManager_Status_WrapsError(t *testing.T) {
	m := &Manager{svc: &mockService{statusErr: fmt.Errorf("failed to query status")}}
	status, err := m.Status()
	if err == nil {
		t.Error("expected error")
	}
	if status != "" {
		t.Errorf("status should be empty on error, got %q", status)
	}
	if !strings.Contains(err.Error(), "service status") {
		t.Errorf("error should mention 'service status', got: %v", err)
	}
}

// --- Success paths (no system access) ---

func TestManager_Install_Success(t *testing.T) {
	m := &Manager{svc: &mockService{installErr: nil}}
	err := m.Install()
	if err != nil {
		t.Errorf("expected success, got: %v", err)
	}
}

func TestManager_Uninstall_Success(t *testing.T) {
	m := &Manager{svc: &mockService{uninstallErr: nil}}
	err := m.Uninstall()
	if err != nil {
		t.Errorf("expected success, got: %v", err)
	}
}

func TestManager_Start_Success(t *testing.T) {
	m := &Manager{svc: &mockService{startErr: nil}}
	err := m.Start()
	if err != nil {
		t.Errorf("expected success, got: %v", err)
	}
}

func TestManager_Stop_Success(t *testing.T) {
	m := &Manager{svc: &mockService{stopErr: nil}}
	err := m.Stop()
	if err != nil {
		t.Errorf("expected success, got: %v", err)
	}
}
