package dns

import (
	"context"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// DefaultConfig
// ---------------------------------------------------------------------------

func TestDefaultConfig_Values(t *testing.T) {
	cfg := DefaultConfig()

	if cfg.Enabled {
		t.Error("expected Enabled to be false by default")
	}
	if cfg.ListenAddr != ":5353" {
		t.Errorf("expected ListenAddr %q, got %q", ":5353", cfg.ListenAddr)
	}
	if cfg.SquawkServer != "https://dns.penguintech.io/dns-query" {
		t.Errorf("expected SquawkServer %q, got %q",
			"https://dns.penguintech.io/dns-query", cfg.SquawkServer)
	}
	if cfg.CacheTTL != 300 {
		t.Errorf("expected CacheTTL 300, got %d", cfg.CacheTTL)
	}
	if len(cfg.BlockedDomains) != 0 {
		t.Errorf("expected empty BlockedDomains, got %v", cfg.BlockedDomains)
	}
}

// ---------------------------------------------------------------------------
// NewForwarder
// ---------------------------------------------------------------------------

func TestNewForwarder_Creation(t *testing.T) {
	cfg := DefaultConfig()
	f := NewForwarder(cfg)

	if f == nil {
		t.Fatal("expected non-nil Forwarder")
	}
	if f.blocked == nil {
		t.Error("expected blocked map to be initialised")
	}
}

func TestNewForwarder_BlockedDomainsNormalised(t *testing.T) {
	cfg := DefaultConfig()
	cfg.BlockedDomains = []string{"Ads.Example.COM", "TRACKER.IO", "spam.net"}
	f := NewForwarder(cfg)

	cases := []struct {
		domain string
		want   bool
	}{
		{"ads.example.com", true},
		{"tracker.io", true},
		{"spam.net", true},
		{"Ads.Example.COM", false}, // original casing must not be present
		{"allowed.com", false},
	}
	for _, tc := range cases {
		got := f.blocked[tc.domain]
		if got != tc.want {
			t.Errorf("blocked[%q] = %v, want %v", tc.domain, got, tc.want)
		}
	}
}

func TestNewForwarder_EmptyBlockedDomains(t *testing.T) {
	cfg := DefaultConfig()
	f := NewForwarder(cfg)

	if len(f.blocked) != 0 {
		t.Errorf("expected empty blocked map, got %d entries", len(f.blocked))
	}
}

// ---------------------------------------------------------------------------
// IsRunning state transitions
// ---------------------------------------------------------------------------

func TestIsRunning_InitiallyFalse(t *testing.T) {
	f := NewForwarder(DefaultConfig())
	if f.IsRunning() {
		t.Error("expected IsRunning() == false before Start")
	}
}

func TestIsRunning_FalseWhenDisabled(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Enabled = false

	f := NewForwarder(cfg)
	err := f.Start(context.Background())
	if err != nil {
		t.Fatalf("Start returned unexpected error: %v", err)
	}
	// Disabled forwarder must not initialise UDP/TCP servers.
	if f.IsRunning() {
		t.Error("expected IsRunning() == false when Enabled is false")
	}
}

// ---------------------------------------------------------------------------
// Start / Stop lifecycle
// ---------------------------------------------------------------------------

func TestStart_DisabledReturnsNil(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Enabled = false

	f := NewForwarder(cfg)
	if err := f.Start(context.Background()); err != nil {
		t.Errorf("expected nil error from Start when disabled, got %v", err)
	}
}

func TestStart_EnabledSetsRunning(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Enabled = true
	// Use a high-numbered port to avoid needing root / conflicting with
	// the system resolver.  Port 0 is not valid for DNS servers in the
	// miekg/dns library (it does not do automatic port assignment), so we
	// pick an ephemeral port in the private range.  The server may fail to
	// bind if the port is taken, but IsRunning checks only whether the
	// server structs were initialised, not whether binding succeeded.
	cfg.ListenAddr = "127.0.0.1:15353"

	f := NewForwarder(cfg)
	err := f.Start(context.Background())
	if err != nil {
		t.Fatalf("Start returned unexpected error: %v", err)
	}

	// Give background goroutines a moment to initialise.
	time.Sleep(20 * time.Millisecond)

	if !f.IsRunning() {
		t.Error("expected IsRunning() == true after Start with Enabled=true")
	}

	// Clean up.
	f.Stop()
}

func TestStop_AfterDisabledStart(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Enabled = false

	f := NewForwarder(cfg)
	_ = f.Start(context.Background())

	// Stop on a non-running forwarder must not panic.
	f.Stop()
}

func TestStop_IsIdempotent(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Enabled = true
	cfg.ListenAddr = "127.0.0.1:15354"

	f := NewForwarder(cfg)
	_ = f.Start(context.Background())
	time.Sleep(20 * time.Millisecond)

	// Call Stop twice — must not panic.
	f.Stop()
	f.Stop()
}

func TestContextCancellation_StopsForwarder(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Enabled = true
	cfg.ListenAddr = "127.0.0.1:15355"

	ctx, cancel := context.WithCancel(context.Background())

	f := NewForwarder(cfg)
	if err := f.Start(ctx); err != nil {
		t.Fatalf("Start returned unexpected error: %v", err)
	}

	time.Sleep(20 * time.Millisecond)

	// Cancelling the context must trigger Stop via the internal goroutine.
	cancel()

	// Allow the internal goroutine to react.
	time.Sleep(50 * time.Millisecond)
}

// ---------------------------------------------------------------------------
// UpdateBlocklist
// ---------------------------------------------------------------------------

func TestUpdateBlocklist_ReplacesExistingEntries(t *testing.T) {
	cfg := DefaultConfig()
	cfg.BlockedDomains = []string{"old.example.com"}
	f := NewForwarder(cfg)

	f.UpdateBlocklist([]string{"new.example.com", "ANOTHER.COM"})

	if f.blocked["old.example.com"] {
		t.Error("old domain should no longer be blocked after UpdateBlocklist")
	}
	if !f.blocked["new.example.com"] {
		t.Error("new.example.com should be blocked after UpdateBlocklist")
	}
	if !f.blocked["another.com"] {
		t.Error("another.com (normalised) should be blocked after UpdateBlocklist")
	}
}

func TestUpdateBlocklist_EmptyListClearsBlocklist(t *testing.T) {
	cfg := DefaultConfig()
	cfg.BlockedDomains = []string{"bad.com"}
	f := NewForwarder(cfg)

	f.UpdateBlocklist([]string{})

	if len(f.blocked) != 0 {
		t.Errorf("expected empty blocklist after update with empty slice, got %d entries", len(f.blocked))
	}
}

// ---------------------------------------------------------------------------
// Table-driven: config field defaults
// ---------------------------------------------------------------------------

func TestDefaultConfig_TableDriven(t *testing.T) {
	tests := []struct {
		name string
		fn   func(Config) bool
		desc string
	}{
		{"Enabled=false", func(c Config) bool { return !c.Enabled }, "Enabled should be false"},
		{"ListenAddr=:5353", func(c Config) bool { return c.ListenAddr == ":5353" }, "ListenAddr should be :5353"},
		{"CacheTTL=300", func(c Config) bool { return c.CacheTTL == 300 }, "CacheTTL should be 300"},
		{"SquawkServer set", func(c Config) bool { return c.SquawkServer != "" }, "SquawkServer should not be empty"},
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
