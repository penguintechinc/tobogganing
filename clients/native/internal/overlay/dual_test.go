package overlay

import (
	"context"
	"testing"
)

func TestDualProviderName(t *testing.T) {
	wg := NewWireGuardProvider(func() error { return nil }, func() error { return nil })
	ziti := NewOpenZitiProvider(OpenZitiConfig{})
	d := NewDualProvider(wg, ziti)
	if d.Name() != "dual" {
		t.Fatalf("expected 'dual', got %q", d.Name())
	}
}

func TestDualProviderConnectStartsBothWGActive(t *testing.T) {
	wgSetup := false
	wg := NewWireGuardProvider(
		func() error { wgSetup = true; return nil },
		func() error { return nil },
	)
	// OpenZiti will fail (no identity file), but WG should still work
	ziti := NewOpenZitiProvider(OpenZitiConfig{})
	d := NewDualProvider(wg, ziti)

	if err := d.Connect(context.Background()); err != nil {
		t.Fatalf("Connect failed: %v", err)
	}

	if !wgSetup {
		t.Fatal("WireGuard setup not called")
	}
	if !d.IsConnected() {
		t.Fatal("expected connected (WG active)")
	}
}

func TestDualProviderDialFallsThrough(t *testing.T) {
	wg := NewWireGuardProvider(func() error { return nil }, func() error { return nil })
	ziti := NewOpenZitiProvider(OpenZitiConfig{}) // not connected
	d := NewDualProvider(wg, ziti)

	conn, err := d.Dial(context.Background(), "test")
	if conn != nil || err != nil {
		t.Fatalf("expected (nil, nil) fallthrough, got (%v, %v)", conn, err)
	}
}

func TestDualProviderDisconnect(t *testing.T) {
	wgDown := false
	wg := NewWireGuardProvider(
		func() error { return nil },
		func() error { wgDown = true; return nil },
	)
	ziti := NewOpenZitiProvider(OpenZitiConfig{})
	d := NewDualProvider(wg, ziti)
	d.Connect(context.Background())

	if err := d.Disconnect(); err != nil {
		t.Fatalf("Disconnect failed: %v", err)
	}

	if !wgDown {
		t.Fatal("WireGuard teardown not called")
	}
	if d.IsConnected() {
		t.Fatal("expected disconnected")
	}
}
