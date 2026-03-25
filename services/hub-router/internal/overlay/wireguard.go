package overlay

import (
	"context"
	"sync"

	log "github.com/sirupsen/logrus"
)

// WireGuardProvider wraps the existing WireGuard manager as an OverlayProvider.
// It delegates packet accounting to in-memory counters; actual kernel-level
// WireGuard operations remain owned by the wireguard.Manager in the sibling
// package.  This thin adapter allows the OverlayManager to treat WireGuard
// polymorphically alongside OpenZiti without altering the manager's API.
type WireGuardProvider struct {
	config  WireGuardConfig
	running bool
	mu      sync.RWMutex
	metrics OverlayMetrics
}

// NewWireGuardProvider constructs a WireGuardProvider from the given config.
func NewWireGuardProvider(cfg WireGuardConfig) *WireGuardProvider {
	return &WireGuardProvider{
		config: cfg,
	}
}

// Name implements OverlayProvider.
func (w *WireGuardProvider) Name() string {
	return "wireguard"
}

// Initialize implements OverlayProvider.  For WireGuard the kernel interface
// is brought up by the wireguard.Manager; this method only logs intent.
func (w *WireGuardProvider) Initialize(ctx context.Context) error {
	log.WithFields(log.Fields{
		"interface":   w.config.Interface,
		"listen_port": w.config.ListenPort,
	}).Info("overlay: initializing WireGuard provider")
	return nil
}

// Connect implements OverlayProvider.
func (w *WireGuardProvider) Connect(ctx context.Context) error {
	w.mu.Lock()
	defer w.mu.Unlock()

	w.running = true
	log.Info("overlay: WireGuard provider connected")
	return nil
}

// Disconnect implements OverlayProvider.
func (w *WireGuardProvider) Disconnect() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	w.running = false
	log.Info("overlay: WireGuard provider disconnected")
	return nil
}

// HandlePacket implements OverlayProvider.  It updates byte counters and
// passes the packet through unchanged; the kernel WireGuard module performs
// the actual encryption.
func (w *WireGuardProvider) HandlePacket(data []byte, direction string) ([]byte, error) {
	w.mu.Lock()
	if direction == "send" {
		w.metrics.BytesSent += int64(len(data))
	} else {
		w.metrics.BytesReceived += int64(len(data))
	}
	w.mu.Unlock()

	// Actual tunnel processing is performed by the kernel WireGuard module;
	// this adapter is a pass-through at the application layer.
	return data, nil
}

// Metrics implements OverlayProvider.
func (w *WireGuardProvider) Metrics() OverlayMetrics {
	w.mu.RLock()
	defer w.mu.RUnlock()
	return w.metrics
}

// Close implements OverlayProvider.
func (w *WireGuardProvider) Close() error {
	return w.Disconnect()
}
