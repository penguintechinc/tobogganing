package overlay

import (
	"context"
	"net"
	"sync/atomic"

	log "github.com/sirupsen/logrus"
)

// DualProvider runs WireGuard (L3) and OpenZiti (L7) simultaneously.
//
// This works because WireGuard operates at L3 (kernel tun interface) and
// OpenZiti at L7 (userspace net.Conn). There are no port conflicts — they
// operate at complementary layers. The client decides per-connection:
// Ziti dark services for sensitive targets, WireGuard for general traffic.
type DualProvider struct {
	wg        *WireGuardProvider
	ziti      *OpenZitiProvider
	connected atomic.Bool
}

// NewDualProvider creates a provider that manages both WireGuard and OpenZiti.
func NewDualProvider(wg *WireGuardProvider, ziti *OpenZitiProvider) *DualProvider {
	return &DualProvider{
		wg:   wg,
		ziti: ziti,
	}
}

// Name returns "dual".
func (d *DualProvider) Name() string {
	return "dual"
}

// Connect starts both WireGuard (L3 kernel tunnel) and OpenZiti (L7 userspace).
func (d *DualProvider) Connect(ctx context.Context) error {
	// Start WireGuard first (L3 — general traffic)
	if err := d.wg.Connect(ctx); err != nil {
		return err
	}

	// Start OpenZiti (L7 — dark services)
	if err := d.ziti.Connect(ctx); err != nil {
		// WireGuard is still active, log warning but don't fail
		log.WithError(err).Warn("Dual-mode: OpenZiti failed to connect, WireGuard still active")
		d.connected.Store(true)
		return nil
	}

	d.connected.Store(true)
	log.Info("Dual-mode overlay active: WireGuard (L3) + OpenZiti (L7)")
	return nil
}

// Disconnect tears down both overlays.
func (d *DualProvider) Disconnect() error {
	var firstErr error

	if err := d.ziti.Disconnect(); err != nil {
		log.WithError(err).Warn("Dual-mode: error disconnecting OpenZiti")
		firstErr = err
	}

	if err := d.wg.Disconnect(); err != nil {
		log.WithError(err).Warn("Dual-mode: error disconnecting WireGuard")
		if firstErr == nil {
			firstErr = err
		}
	}

	d.connected.Store(false)
	return firstErr
}

// IsConnected returns true if either overlay is connected.
func (d *DualProvider) IsConnected() bool {
	return d.wg.IsConnected() || d.ziti.IsConnected()
}

// Dial routes via OpenZiti if it's connected, otherwise returns (nil, nil)
// to fall through to the WireGuard kernel tunnel path.
func (d *DualProvider) Dial(ctx context.Context, service string) (net.Conn, error) {
	if d.ziti.IsConnected() {
		conn, err := d.ziti.Dial(ctx, service)
		if err != nil {
			log.WithError(err).WithField("service", service).Debug("Dual-mode: Ziti dial failed, falling through to WireGuard")
			return nil, nil
		}
		return conn, nil
	}

	// OpenZiti not connected — fall through to WireGuard kernel path
	return nil, nil
}
