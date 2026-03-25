package overlay

import (
	"context"
	"net"
	"sync/atomic"

	log "github.com/sirupsen/logrus"
)

// WireGuardProvider wraps existing WireGuard setup for the client.
// Traffic routes through the kernel tun interface, so Dial returns (nil, nil).
type WireGuardProvider struct {
	connected atomic.Bool

	// setupFn is called during Connect to set up the WireGuard tunnel.
	// This allows injecting the existing client's setupWireGuard+startWireGuard logic.
	setupFn func() error

	// teardownFn is called during Disconnect to tear down the tunnel.
	teardownFn func() error
}

// NewWireGuardProvider creates a new client-side WireGuard overlay provider.
// The setup/teardown functions should wrap the existing wg-quick up/down logic.
func NewWireGuardProvider(setupFn, teardownFn func() error) *WireGuardProvider {
	return &WireGuardProvider{
		setupFn:    setupFn,
		teardownFn: teardownFn,
	}
}

// Name returns "wireguard".
func (w *WireGuardProvider) Name() string {
	return "wireguard"
}

// Connect establishes the WireGuard tunnel via the injected setup function.
func (w *WireGuardProvider) Connect(_ context.Context) error {
	if w.setupFn != nil {
		if err := w.setupFn(); err != nil {
			return err
		}
	}
	w.connected.Store(true)
	log.Info("WireGuard overlay connected (kernel tunnel active)")
	return nil
}

// Disconnect tears down the WireGuard tunnel.
func (w *WireGuardProvider) Disconnect() error {
	if w.teardownFn != nil {
		if err := w.teardownFn(); err != nil {
			return err
		}
	}
	w.connected.Store(false)
	log.Info("WireGuard overlay disconnected")
	return nil
}

// IsConnected returns whether the WireGuard tunnel is active.
func (w *WireGuardProvider) IsConnected() bool {
	return w.connected.Load()
}

// Dial returns (nil, nil) for WireGuard — all traffic routes through the
// kernel tun interface transparently. The caller should fall through to
// normal network operations when Dial returns (nil, nil).
func (w *WireGuardProvider) Dial(_ context.Context, _ string) (net.Conn, error) {
	return nil, nil
}
