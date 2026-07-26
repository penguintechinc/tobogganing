//go:build nogui || !(linux || darwin || windows)

package tray

import (
	"testing"
	"time"
)

// TestNewTrayManager_StoresReferences verifies NewTrayManager stores vpn and config references.
func TestNewTrayManager_StoresReferences(t *testing.T) {
	vpn := &stubVPNManager{}
	cfg := &stubConfigManager{}
	mgr := NewTrayManager(vpn, cfg)

	if mgr.vpn != vpn {
		t.Error("vpn reference not stored")
	}
	if mgr.config != cfg {
		t.Error("config reference not stored")
	}
}

// TestTrayManager_Run_ReturnsQuicklyWhenCancelled verifies Run exits when context is done.
func TestTrayManager_Run_ReturnsQuicklyWhenCancelled(t *testing.T) {
	vpn := &stubVPNManager{}
	cfg := &stubConfigManager{}
	mgr := NewTrayManager(vpn, cfg)

	// Start Run in a goroutine and cancel immediately
	done := make(chan error, 1)
	go func() {
		done <- mgr.Run()
	}()

	mgr.Stop()

	// Should return quickly
	select {
	case err := <-done:
		if err != nil {
			t.Errorf("Run() returned error: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Error("Run() did not return after Stop()")
	}
}
