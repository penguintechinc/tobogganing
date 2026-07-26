package xdp

import (
	"testing"
)

func TestNew(t *testing.T) {
	cfg := XDPConfig{
		Enabled:          true,
		Interface:        "eth0",
		RateLimitPPS:     10000,
		SYNRateLimitPPS:  5000,
		UDPRateLimitPPS:  8000,
		BlocklistSyncURL: "https://example.com/blocklist",
	}

	xdp := New(cfg)
	if xdp == nil {
		t.Fatal("New() returned nil")
	}
	if xdp.cfg != cfg {
		t.Errorf("New() did not store config correctly: got %+v, want %+v", xdp.cfg, cfg)
	}
}

func TestNewWithZeroConfig(t *testing.T) {
	cfg := XDPConfig{}

	xdp := New(cfg)
	if xdp == nil {
		t.Fatal("New() returned nil with zero config")
	}
	if xdp.cfg.Enabled != false {
		t.Errorf("New() should preserve zero config: got %+v", xdp.cfg)
	}
}

func TestAttach(t *testing.T) {
	cfg := XDPConfig{
		Enabled:   true,
		Interface: "eth0",
	}
	xdp := New(cfg)

	err := xdp.Attach("eth1")
	if err != nil {
		t.Fatalf("Attach() returned error: %v", err)
	}
}

func TestAttachEmptyInterface(t *testing.T) {
	cfg := XDPConfig{}
	xdp := New(cfg)

	err := xdp.Attach("")
	if err != nil {
		t.Fatalf("Attach() with empty interface should not error: %v", err)
	}
}

func TestSetRateLimit(t *testing.T) {
	cfg := XDPConfig{
		RateLimitPPS: 1000,
	}
	xdp := New(cfg)

	xdp.SetRateLimit(5000)
	if xdp.cfg.RateLimitPPS != 5000 {
		t.Errorf("SetRateLimit() did not update: got %d, want 5000", xdp.cfg.RateLimitPPS)
	}
}

func TestSetRateLimitZero(t *testing.T) {
	cfg := XDPConfig{
		RateLimitPPS: 10000,
	}
	xdp := New(cfg)

	xdp.SetRateLimit(0)
	if xdp.cfg.RateLimitPPS != 0 {
		t.Errorf("SetRateLimit(0) should allow zero: got %d, want 0", xdp.cfg.RateLimitPPS)
	}
}

func TestSetRateLimitNegative(t *testing.T) {
	cfg := XDPConfig{
		RateLimitPPS: 10000,
	}
	xdp := New(cfg)

	xdp.SetRateLimit(-1)
	if xdp.cfg.RateLimitPPS != -1 {
		t.Errorf("SetRateLimit(-1) should allow negative: got %d, want -1", xdp.cfg.RateLimitPPS)
	}
}

func TestSetSYNRateLimit(t *testing.T) {
	cfg := XDPConfig{
		SYNRateLimitPPS: 1000,
	}
	xdp := New(cfg)

	xdp.SetSYNRateLimit(3000)
	if xdp.cfg.SYNRateLimitPPS != 3000 {
		t.Errorf("SetSYNRateLimit() did not update: got %d, want 3000", xdp.cfg.SYNRateLimitPPS)
	}
}

func TestSetSYNRateLimitZero(t *testing.T) {
	cfg := XDPConfig{
		SYNRateLimitPPS: 5000,
	}
	xdp := New(cfg)

	xdp.SetSYNRateLimit(0)
	if xdp.cfg.SYNRateLimitPPS != 0 {
		t.Errorf("SetSYNRateLimit(0) should allow zero: got %d, want 0", xdp.cfg.SYNRateLimitPPS)
	}
}

func TestSetSYNRateLimitNegative(t *testing.T) {
	cfg := XDPConfig{
		SYNRateLimitPPS: 5000,
	}
	xdp := New(cfg)

	xdp.SetSYNRateLimit(-100)
	if xdp.cfg.SYNRateLimitPPS != -100 {
		t.Errorf("SetSYNRateLimit(-100) should allow negative: got %d, want -100", xdp.cfg.SYNRateLimitPPS)
	}
}

func TestSetUDPRateLimit(t *testing.T) {
	cfg := XDPConfig{
		UDPRateLimitPPS: 2000,
	}
	xdp := New(cfg)

	xdp.SetUDPRateLimit(7000)
	if xdp.cfg.UDPRateLimitPPS != 7000 {
		t.Errorf("SetUDPRateLimit() did not update: got %d, want 7000", xdp.cfg.UDPRateLimitPPS)
	}
}

func TestSetUDPRateLimitZero(t *testing.T) {
	cfg := XDPConfig{
		UDPRateLimitPPS: 8000,
	}
	xdp := New(cfg)

	xdp.SetUDPRateLimit(0)
	if xdp.cfg.UDPRateLimitPPS != 0 {
		t.Errorf("SetUDPRateLimit(0) should allow zero: got %d, want 0", xdp.cfg.UDPRateLimitPPS)
	}
}

func TestSetUDPRateLimitNegative(t *testing.T) {
	cfg := XDPConfig{
		UDPRateLimitPPS: 8000,
	}
	xdp := New(cfg)

	xdp.SetUDPRateLimit(-500)
	if xdp.cfg.UDPRateLimitPPS != -500 {
		t.Errorf("SetUDPRateLimit(-500) should allow negative: got %d, want -500", xdp.cfg.UDPRateLimitPPS)
	}
}

func TestMultipleLimitUpdates(t *testing.T) {
	cfg := XDPConfig{
		RateLimitPPS:    10000,
		SYNRateLimitPPS: 5000,
		UDPRateLimitPPS: 8000,
	}
	xdp := New(cfg)

	xdp.SetRateLimit(15000)
	xdp.SetSYNRateLimit(7000)
	xdp.SetUDPRateLimit(10000)

	if xdp.cfg.RateLimitPPS != 15000 {
		t.Errorf("SetRateLimit: got %d, want 15000", xdp.cfg.RateLimitPPS)
	}
	if xdp.cfg.SYNRateLimitPPS != 7000 {
		t.Errorf("SetSYNRateLimit: got %d, want 7000", xdp.cfg.SYNRateLimitPPS)
	}
	if xdp.cfg.UDPRateLimitPPS != 10000 {
		t.Errorf("SetUDPRateLimit: got %d, want 10000", xdp.cfg.UDPRateLimitPPS)
	}
}

func TestDetach(t *testing.T) {
	cfg := XDPConfig{}
	xdp := New(cfg)

	err := xdp.Detach()
	if err != nil {
		t.Fatalf("Detach() returned error: %v", err)
	}
}

func TestDetachMultipleTimes(t *testing.T) {
	cfg := XDPConfig{}
	xdp := New(cfg)

	err1 := xdp.Detach()
	if err1 != nil {
		t.Fatalf("first Detach() returned error: %v", err1)
	}

	err2 := xdp.Detach()
	if err2 != nil {
		t.Fatalf("second Detach() returned error: %v", err2)
	}
}

func TestClose(t *testing.T) {
	cfg := XDPConfig{}
	xdp := New(cfg)

	err := xdp.Close()
	if err != nil {
		t.Fatalf("Close() returned error: %v", err)
	}
}

func TestCloseCallsDetach(t *testing.T) {
	cfg := XDPConfig{}
	xdp := New(cfg)

	err := xdp.Close()
	if err != nil {
		t.Fatalf("Close() returned error: %v", err)
	}

	// Verify Close does not double-error (should be equivalent to Detach)
	err2 := xdp.Detach()
	if err2 != nil {
		t.Fatalf("Detach() after Close() returned error: %v", err2)
	}
}

func TestCloseMultipleTimes(t *testing.T) {
	cfg := XDPConfig{}
	xdp := New(cfg)

	err1 := xdp.Close()
	if err1 != nil {
		t.Fatalf("first Close() returned error: %v", err1)
	}

	err2 := xdp.Close()
	if err2 != nil {
		t.Fatalf("second Close() returned error: %v", err2)
	}
}

func TestAttachAndClose(t *testing.T) {
	cfg := XDPConfig{
		Interface: "eth0",
	}
	xdp := New(cfg)

	if err := xdp.Attach("eth0"); err != nil {
		t.Fatalf("Attach() returned error: %v", err)
	}

	if err := xdp.Close(); err != nil {
		t.Fatalf("Close() returned error: %v", err)
	}
}

func TestConfigPreservation(t *testing.T) {
	cfg := XDPConfig{
		Enabled:          true,
		Interface:        "eth0",
		RateLimitPPS:     10000,
		SYNRateLimitPPS:  5000,
		UDPRateLimitPPS:  8000,
		BlocklistSyncURL: "https://example.com/blocklist",
	}
	xdp := New(cfg)

	// Verify all config fields are preserved
	if xdp.cfg.Enabled != cfg.Enabled {
		t.Errorf("Enabled: got %v, want %v", xdp.cfg.Enabled, cfg.Enabled)
	}
	if xdp.cfg.Interface != cfg.Interface {
		t.Errorf("Interface: got %s, want %s", xdp.cfg.Interface, cfg.Interface)
	}
	if xdp.cfg.RateLimitPPS != cfg.RateLimitPPS {
		t.Errorf("RateLimitPPS: got %d, want %d", xdp.cfg.RateLimitPPS, cfg.RateLimitPPS)
	}
	if xdp.cfg.SYNRateLimitPPS != cfg.SYNRateLimitPPS {
		t.Errorf("SYNRateLimitPPS: got %d, want %d", xdp.cfg.SYNRateLimitPPS, cfg.SYNRateLimitPPS)
	}
	if xdp.cfg.UDPRateLimitPPS != cfg.UDPRateLimitPPS {
		t.Errorf("UDPRateLimitPPS: got %d, want %d", xdp.cfg.UDPRateLimitPPS, cfg.UDPRateLimitPPS)
	}
	if xdp.cfg.BlocklistSyncURL != cfg.BlocklistSyncURL {
		t.Errorf("BlocklistSyncURL: got %s, want %s", xdp.cfg.BlocklistSyncURL, cfg.BlocklistSyncURL)
	}
}

func TestRateLimitLargeValues(t *testing.T) {
	cfg := XDPConfig{}
	xdp := New(cfg)

	xdp.SetRateLimit(1000000000)
	if xdp.cfg.RateLimitPPS != 1000000000 {
		t.Errorf("SetRateLimit with large value: got %d, want 1000000000", xdp.cfg.RateLimitPPS)
	}

	xdp.SetSYNRateLimit(999999999)
	if xdp.cfg.SYNRateLimitPPS != 999999999 {
		t.Errorf("SetSYNRateLimit with large value: got %d, want 999999999", xdp.cfg.SYNRateLimitPPS)
	}

	xdp.SetUDPRateLimit(2147483647)
	if xdp.cfg.UDPRateLimitPPS != 2147483647 {
		t.Errorf("SetUDPRateLimit with large value: got %d, want 2147483647", xdp.cfg.UDPRateLimitPPS)
	}
}
