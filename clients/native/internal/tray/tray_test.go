//go:build nogui

package tray

import (
	"testing"
	"time"
)

// stubVPNManager satisfies VPNManager for tests.
type stubVPNManager struct {
	connected bool
}

func (s *stubVPNManager) Connect() error           { s.connected = true; return nil }
func (s *stubVPNManager) Disconnect() error        { s.connected = false; return nil }
func (s *stubVPNManager) IsConnected() bool        { return s.connected }
func (s *stubVPNManager) GetStatusString() string  { return "connected" }
func (s *stubVPNManager) GetStatistics() map[string]interface{} {
	return map[string]interface{}{"bytes_in": 0}
}

// stubConfigManager satisfies ConfigManager for tests.
type stubConfigManager struct{}

func (s *stubConfigManager) GetServerURL() string         { return "https://manager.example.com" }
func (s *stubConfigManager) UpdateConfiguration() error   { return nil }
func (s *stubConfigManager) GetUpdateSchedule() time.Duration { return 30 * time.Minute }

// --- NewTrayManager ---

func TestNewTrayManager_ReturnsNonNil(t *testing.T) {
	vpn := &stubVPNManager{}
	cfg := &stubConfigManager{}
	mgr := NewTrayManager(vpn, cfg)
	if mgr == nil {
		t.Fatal("NewTrayManager returned nil")
	}
}

func TestNewTrayManager_StoresVPN(t *testing.T) {
	vpn := &stubVPNManager{}
	cfg := &stubConfigManager{}
	mgr := NewTrayManager(vpn, cfg)
	if mgr.vpn != vpn {
		t.Error("NewTrayManager should store vpn reference")
	}
}

func TestNewTrayManager_StoresConfig(t *testing.T) {
	vpn := &stubVPNManager{}
	cfg := &stubConfigManager{}
	mgr := NewTrayManager(vpn, cfg)
	if mgr.config != cfg {
		t.Error("NewTrayManager should store config reference")
	}
}

func TestNewTrayManager_HasContext(t *testing.T) {
	vpn := &stubVPNManager{}
	cfg := &stubConfigManager{}
	mgr := NewTrayManager(vpn, cfg)
	if mgr.ctx == nil {
		t.Error("NewTrayManager should set context")
	}
	if mgr.cancel == nil {
		t.Error("NewTrayManager should set cancel func")
	}
}

// --- Stop ---

func TestTrayManager_Stop_NoPanic(t *testing.T) {
	vpn := &stubVPNManager{}
	cfg := &stubConfigManager{}
	mgr := NewTrayManager(vpn, cfg)
	// Stop should cancel context without panicking.
	mgr.Stop()
}

func TestTrayManager_Stop_Idempotent(t *testing.T) {
	vpn := &stubVPNManager{}
	cfg := &stubConfigManager{}
	mgr := NewTrayManager(vpn, cfg)
	mgr.Stop()
	// Multiple stops should be safe.
	mgr.Stop()
}

func TestTrayManager_Stop_CancelsContext(t *testing.T) {
	vpn := &stubVPNManager{}
	cfg := &stubConfigManager{}
	mgr := NewTrayManager(vpn, cfg)
	mgr.Stop()
	select {
	case <-mgr.ctx.Done():
		// context was cancelled — expected
	default:
		t.Error("context should be cancelled after Stop")
	}
}

// --- Run (package-level) ---

func TestRun_NoError(t *testing.T) {
	err := Run(nil)
	if err != nil {
		t.Errorf("Run(nil): %v", err)
	}
}

func TestRun_WithConfig_NoError(t *testing.T) {
	err := Run(map[string]string{"key": "value"})
	if err != nil {
		t.Errorf("Run with config: %v", err)
	}
}

// --- Run (TrayManager method) ---
// TrayManager.Run blocks until the context is done, so we need to stop it.

func TestTrayManager_Run_StopsOnCancel(t *testing.T) {
	vpn := &stubVPNManager{}
	cfg := &stubConfigManager{}
	mgr := NewTrayManager(vpn, cfg)

	done := make(chan error, 1)
	go func() {
		done <- mgr.Run()
	}()

	// Give Run a moment to start, then stop it.
	time.Sleep(10 * time.Millisecond)
	mgr.Stop()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("Run returned error: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Error("Run did not return after Stop was called")
	}
}
