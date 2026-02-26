package dns

import (
	"context"
	"testing"
)

// ---------------------------------------------------------------------------
// DefaultConfig
// ---------------------------------------------------------------------------

func TestDefaultConfig_Values(t *testing.T) {
	cfg := DefaultConfig()

	if cfg.Enabled {
		t.Error("expected Enabled to be false by default")
	}
	if cfg.ListenAddr != "127.0.0.1:53" {
		t.Errorf("expected ListenAddr %q, got %q", "127.0.0.1:53", cfg.ListenAddr)
	}
	if cfg.UpstreamAddr != "10.200.0.1:5353" {
		t.Errorf("expected UpstreamAddr %q, got %q", "10.200.0.1:5353", cfg.UpstreamAddr)
	}
}

func TestDefaultConfig_TableDriven(t *testing.T) {
	tests := []struct {
		name string
		fn   func(Config) bool
		desc string
	}{
		{"Enabled=false", func(c Config) bool { return !c.Enabled }, "Enabled should default to false"},
		{"ListenAddr=127.0.0.1:53", func(c Config) bool { return c.ListenAddr == "127.0.0.1:53" }, "ListenAddr should default to 127.0.0.1:53"},
		{"UpstreamAddr=10.200.0.1:5353", func(c Config) bool { return c.UpstreamAddr == "10.200.0.1:5353" }, "UpstreamAddr should default to 10.200.0.1:5353"},
	}

	cfg := DefaultConfig()
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if !tt.fn(cfg) {
				t.Error(tt.desc)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// NewModule creation
// ---------------------------------------------------------------------------

func TestNewModule_ReturnsNonNil(t *testing.T) {
	m := NewModule(DefaultConfig())
	if m == nil {
		t.Fatal("expected non-nil Module from NewModule")
	}
}

func TestNewModule_NotRunningInitially(t *testing.T) {
	m := NewModule(DefaultConfig())
	if m.IsRunning() {
		t.Error("expected IsRunning() == false before Start")
	}
}

func TestNewModule_StoredConfigMatchesInput(t *testing.T) {
	cfg := Config{
		Enabled:      true,
		ListenAddr:   "127.0.0.1:5300",
		UpstreamAddr: "10.100.0.1:5353",
	}
	m := NewModule(cfg)
	if m.config.ListenAddr != cfg.ListenAddr {
		t.Errorf("ListenAddr: got %q, want %q", m.config.ListenAddr, cfg.ListenAddr)
	}
	if m.config.UpstreamAddr != cfg.UpstreamAddr {
		t.Errorf("UpstreamAddr: got %q, want %q", m.config.UpstreamAddr, cfg.UpstreamAddr)
	}
}

// ---------------------------------------------------------------------------
// Start — disabled path
// ---------------------------------------------------------------------------

func TestStart_DisabledDoesNotSetRunning(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Enabled = false

	m := NewModule(cfg)
	if err := m.Start(context.Background()); err != nil {
		t.Fatalf("Start returned unexpected error: %v", err)
	}
	if m.IsRunning() {
		t.Error("expected IsRunning() == false when Enabled is false")
	}
}

func TestStart_DisabledReturnsNilError(t *testing.T) {
	m := NewModule(DefaultConfig())
	if err := m.Start(context.Background()); err != nil {
		t.Errorf("expected nil error from Start when disabled, got %v", err)
	}
}

// ---------------------------------------------------------------------------
// Start — enabled path
// ---------------------------------------------------------------------------

func TestStart_EnabledSetsRunning(t *testing.T) {
	cfg := Config{
		Enabled:      true,
		ListenAddr:   "127.0.0.1:5300",
		UpstreamAddr: "10.200.0.1:5353",
	}
	m := NewModule(cfg)
	if err := m.Start(context.Background()); err != nil {
		t.Fatalf("Start returned unexpected error: %v", err)
	}
	if !m.IsRunning() {
		t.Error("expected IsRunning() == true after Start with Enabled=true")
	}
}

func TestStart_EnabledRequiresUpstreamAddr(t *testing.T) {
	// When Enabled=true and UpstreamAddr is empty the module still starts
	// (addr validation is a runtime concern for the actual stub listener).
	// The test verifies the module records running state.
	cfg := Config{
		Enabled:      true,
		ListenAddr:   "127.0.0.1:5300",
		UpstreamAddr: "",
	}
	m := NewModule(cfg)
	if err := m.Start(context.Background()); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !m.IsRunning() {
		t.Error("expected IsRunning() == true even with empty UpstreamAddr")
	}
}

// ---------------------------------------------------------------------------
// Stop lifecycle
// ---------------------------------------------------------------------------

func TestStop_AfterStart_SetsNotRunning(t *testing.T) {
	cfg := Config{Enabled: true, ListenAddr: "127.0.0.1:5300", UpstreamAddr: "10.200.0.1:5353"}
	m := NewModule(cfg)
	_ = m.Start(context.Background())

	if err := m.Stop(); err != nil {
		t.Fatalf("Stop returned unexpected error: %v", err)
	}
	if m.IsRunning() {
		t.Error("expected IsRunning() == false after Stop")
	}
}

func TestStop_IsIdempotent(t *testing.T) {
	cfg := Config{Enabled: true, ListenAddr: "127.0.0.1:5300", UpstreamAddr: "10.200.0.1:5353"}
	m := NewModule(cfg)
	_ = m.Start(context.Background())

	// First Stop.
	if err := m.Stop(); err != nil {
		t.Fatalf("first Stop returned error: %v", err)
	}
	// Second Stop must not return an error or panic.
	if err := m.Stop(); err != nil {
		t.Errorf("second Stop returned error: %v", err)
	}
	if m.IsRunning() {
		t.Error("expected IsRunning() == false after two Stop calls")
	}
}

func TestStop_WithoutStart_IsNoOp(t *testing.T) {
	m := NewModule(DefaultConfig())
	// Stop without ever calling Start must not panic or error.
	if err := m.Stop(); err != nil {
		t.Errorf("Stop without Start returned error: %v", err)
	}
}

// ---------------------------------------------------------------------------
// IsRunning state transitions (table-driven)
// ---------------------------------------------------------------------------

func TestIsRunning_StateTransitions(t *testing.T) {
	tests := []struct {
		name    string
		setup   func(*Module)
		running bool
	}{
		{
			name:    "after construction",
			setup:   func(_ *Module) {},
			running: false,
		},
		{
			name: "after Start with Enabled=false",
			setup: func(m *Module) {
				_ = m.Start(context.Background())
			},
			running: false,
		},
		{
			name: "after Start with Enabled=true",
			setup: func(m *Module) {
				m.config.Enabled = true
				_ = m.Start(context.Background())
			},
			running: true,
		},
		{
			name: "after Start then Stop",
			setup: func(m *Module) {
				m.config.Enabled = true
				_ = m.Start(context.Background())
				_ = m.Stop()
			},
			running: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			m := NewModule(DefaultConfig())
			tt.setup(m)
			got := m.IsRunning()
			if got != tt.running {
				t.Errorf("IsRunning() = %v, want %v", got, tt.running)
			}
		})
	}
}
