// Package overlay provides VPN overlay provider abstractions.
package overlay

import "context"

// OverlayProvider is the interface all overlay implementations satisfy.
type OverlayProvider interface {
	Connect(ctx context.Context) error
	Disconnect(ctx context.Context) error
	Status(ctx context.Context) (ProviderStatus, error)
}

// ProviderStatus holds the current connection state.
type ProviderStatus struct {
	Connected bool
	Endpoint  string
	BytesIn   uint64
	BytesOut  uint64
}

// OpenZitiConfig holds configuration for the OpenZiti provider.
type OpenZitiConfig struct {
	// IdentityFile is the path to the OpenZiti identity JSON file.
	IdentityFile string
	// ServiceName is the OpenZiti service to connect to.
	ServiceName string
}

// NewWireGuardProvider creates an OverlayProvider that delegates connect and disconnect
// to the provided callbacks. This allows the caller to use its own WireGuard management
// logic (key exchange, interface setup, etc.) while participating in the overlay abstraction.
func NewWireGuardProvider(connectFn, disconnectFn func() error) OverlayProvider {
	return &wireguardProvider{connectFn: connectFn, disconnectFn: disconnectFn}
}

// NewDualProvider creates an OverlayProvider that tries primary first, falling back to
// secondary on Connect failure.
func NewDualProvider(primary, secondary OverlayProvider) OverlayProvider {
	return &dualProvider{primary: primary, secondary: secondary}
}
