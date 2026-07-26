package overlay

import "testing"

// TestProviderStatus_ZeroValue checks default values of ProviderStatus.
func TestProviderStatus_ZeroValue(t *testing.T) {
	var s ProviderStatus
	if s.Connected {
		t.Error("zero-value ProviderStatus.Connected should be false")
	}
	if s.Endpoint != "" {
		t.Errorf("zero-value Endpoint should be empty, got %q", s.Endpoint)
	}
	if s.BytesIn != 0 {
		t.Errorf("zero-value BytesIn should be 0, got %d", s.BytesIn)
	}
	if s.BytesOut != 0 {
		t.Errorf("zero-value BytesOut should be 0, got %d", s.BytesOut)
	}
}

// TestProviderStatus_Fields checks all fields can be set.
func TestProviderStatus_Fields(t *testing.T) {
	s := ProviderStatus{
		Connected: true,
		Endpoint:  "10.0.0.1:51820",
		BytesIn:   1024,
		BytesOut:  2048,
	}

	if !s.Connected {
		t.Error("Connected should be true")
	}
	if s.Endpoint != "10.0.0.1:51820" {
		t.Errorf("Endpoint mismatch: got %q", s.Endpoint)
	}
	if s.BytesIn != 1024 {
		t.Errorf("BytesIn: want 1024, got %d", s.BytesIn)
	}
	if s.BytesOut != 2048 {
		t.Errorf("BytesOut: want 2048, got %d", s.BytesOut)
	}
}

// TestOpenZitiConfig_ZeroValue checks defaults.
func TestOpenZitiConfig_ZeroValue(t *testing.T) {
	var cfg OpenZitiConfig
	if cfg.IdentityFile != "" {
		t.Errorf("expected empty IdentityFile, got %q", cfg.IdentityFile)
	}
	if cfg.ServiceName != "" {
		t.Errorf("expected empty ServiceName, got %q", cfg.ServiceName)
	}
}

// TestOpenZitiConfig_Fields verifies fields are set correctly.
func TestOpenZitiConfig_Fields(t *testing.T) {
	cfg := OpenZitiConfig{
		IdentityFile: "/path/to/identity.json",
		ServiceName:  "my-service",
	}

	if cfg.IdentityFile != "/path/to/identity.json" {
		t.Errorf("IdentityFile mismatch: got %q", cfg.IdentityFile)
	}
	if cfg.ServiceName != "my-service" {
		t.Errorf("ServiceName mismatch: got %q", cfg.ServiceName)
	}
}

// TestNewWireGuardProvider_WithValidCallbacks verifies factory function works
func TestNewWireGuardProvider_WithValidCallbacks(t *testing.T) {
	connectCalls := 0
	disconnectCalls := 0

	p := NewWireGuardProvider(
		func() error { connectCalls++; return nil },
		func() error { disconnectCalls++; return nil },
	)

	if p == nil {
		t.Fatal("expected non-nil provider")
	}
}

// TestNewDualProvider_WithValidProviders verifies factory function works
func TestNewDualProvider_WithValidProviders(t *testing.T) {
	primary := NewWireGuardProvider(
		func() error { return nil },
		func() error { return nil },
	)
	secondary := NewOpenZitiProvider(OpenZitiConfig{})

	p := NewDualProvider(primary, secondary)
	if p == nil {
		t.Fatal("expected non-nil dual provider")
	}
}
