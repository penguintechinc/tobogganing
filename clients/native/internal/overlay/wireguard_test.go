package overlay

import (
	"context"
	"errors"
	"testing"
)

func TestNewWireGuardProvider_ReturnsNonNil(t *testing.T) {
	p := NewWireGuardProvider(
		func() error { return nil },
		func() error { return nil },
	)
	if p == nil {
		t.Fatal("expected non-nil provider")
	}
}

func TestWireGuardProvider_Connect_Success(t *testing.T) {
	called := false
	p := NewWireGuardProvider(
		func() error { called = true; return nil },
		func() error { return nil },
	)

	if err := p.Connect(context.Background()); err != nil {
		t.Fatalf("Connect returned unexpected error: %v", err)
	}
	if !called {
		t.Error("connectFn was not called")
	}
}

func TestWireGuardProvider_Connect_Error(t *testing.T) {
	wantErr := errors.New("wg-quick failed")
	p := NewWireGuardProvider(
		func() error { return wantErr },
		func() error { return nil },
	)

	err := p.Connect(context.Background())
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, wantErr) {
		t.Errorf("expected %v, got %v", wantErr, err)
	}
}

func TestWireGuardProvider_Status_DisconnectedByDefault(t *testing.T) {
	p := NewWireGuardProvider(
		func() error { return nil },
		func() error { return nil },
	)

	status, err := p.Status(context.Background())
	if err != nil {
		t.Fatalf("Status returned error: %v", err)
	}
	if status.Connected {
		t.Error("expected Connected=false before any Connect call")
	}
}

func TestWireGuardProvider_Status_ConnectedAfterConnect(t *testing.T) {
	p := NewWireGuardProvider(
		func() error { return nil },
		func() error { return nil },
	)

	if err := p.Connect(context.Background()); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	status, err := p.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if !status.Connected {
		t.Error("expected Connected=true after successful Connect")
	}
}

func TestWireGuardProvider_Status_NotConnectedAfterConnectError(t *testing.T) {
	p := NewWireGuardProvider(
		func() error { return errors.New("failed") },
		func() error { return nil },
	)

	_ = p.Connect(context.Background())

	status, err := p.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status.Connected {
		t.Error("expected Connected=false after failed Connect")
	}
}

func TestWireGuardProvider_Disconnect_CallsDisconnectFn(t *testing.T) {
	called := false
	p := NewWireGuardProvider(
		func() error { return nil },
		func() error { called = true; return nil },
	)

	_ = p.Connect(context.Background())

	if err := p.Disconnect(context.Background()); err != nil {
		t.Fatalf("Disconnect returned unexpected error: %v", err)
	}
	if !called {
		t.Error("disconnectFn was not called")
	}
}

func TestWireGuardProvider_Disconnect_SetsDisconnected(t *testing.T) {
	p := NewWireGuardProvider(
		func() error { return nil },
		func() error { return nil },
	)

	_ = p.Connect(context.Background())
	_ = p.Disconnect(context.Background())

	status, err := p.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status.Connected {
		t.Error("expected Connected=false after Disconnect")
	}
}

func TestWireGuardProvider_Disconnect_SetsDisconnectedEvenOnError(t *testing.T) {
	// Even when disconnectFn returns error, connected should be set false.
	p := NewWireGuardProvider(
		func() error { return nil },
		func() error { return errors.New("teardown failed") },
	)

	_ = p.Connect(context.Background())
	err := p.Disconnect(context.Background())
	// Error should propagate
	if err == nil {
		t.Fatal("expected error from failing disconnectFn")
	}

	status, _ := p.Status(context.Background())
	if status.Connected {
		t.Error("expected Connected=false even after Disconnect error")
	}
}

func TestWireGuardProvider_ConnectThenDisconnectThenConnect(t *testing.T) {
	connectCount := 0
	p := NewWireGuardProvider(
		func() error { connectCount++; return nil },
		func() error { return nil },
	)
	ctx := context.Background()

	if err := p.Connect(ctx); err != nil {
		t.Fatalf("first Connect: %v", err)
	}
	if err := p.Disconnect(ctx); err != nil {
		t.Fatalf("Disconnect: %v", err)
	}
	if err := p.Connect(ctx); err != nil {
		t.Fatalf("second Connect: %v", err)
	}

	if connectCount != 2 {
		t.Errorf("expected connectFn called 2 times, got %d", connectCount)
	}

	status, _ := p.Status(ctx)
	if !status.Connected {
		t.Error("expected Connected=true after second Connect")
	}
}

func TestWireGuardProvider_ImplementsOverlayProvider(t *testing.T) {
	// Compile-time check via assignment; if this compiles, the interface is satisfied.
	var _ OverlayProvider = NewWireGuardProvider(
		func() error { return nil },
		func() error { return nil },
	)
}
