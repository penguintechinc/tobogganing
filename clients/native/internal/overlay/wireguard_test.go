package overlay

import (
	"context"
	"testing"
)

func TestClientWireGuardName(t *testing.T) {
	p := NewWireGuardProvider(nil, nil)
	if p.Name() != "wireguard" {
		t.Fatalf("expected 'wireguard', got %q", p.Name())
	}
}

func TestClientWireGuardDialReturnsNil(t *testing.T) {
	p := NewWireGuardProvider(nil, nil)
	conn, err := p.Dial(context.Background(), "test")
	if conn != nil || err != nil {
		t.Fatalf("expected (nil, nil), got (%v, %v)", conn, err)
	}
}

func TestClientWireGuardConnectDisconnect(t *testing.T) {
	setupCalled := false
	teardownCalled := false

	p := NewWireGuardProvider(
		func() error { setupCalled = true; return nil },
		func() error { teardownCalled = true; return nil },
	)

	if err := p.Connect(context.Background()); err != nil {
		t.Fatalf("Connect failed: %v", err)
	}
	if !setupCalled {
		t.Fatal("setup function not called")
	}
	if !p.IsConnected() {
		t.Fatal("expected connected")
	}

	if err := p.Disconnect(); err != nil {
		t.Fatalf("Disconnect failed: %v", err)
	}
	if !teardownCalled {
		t.Fatal("teardown function not called")
	}
	if p.IsConnected() {
		t.Fatal("expected disconnected")
	}
}
