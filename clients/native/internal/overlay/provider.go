// Package overlay provides VPN overlay provider abstractions.
package overlay

import "context"

// Provider is the interface all overlay implementations satisfy.
type Provider interface {
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

// WireGuardConfig holds configuration for the WireGuard provider.
type WireGuardConfig struct {
	Interface  string
	PrivateKey string
	Address    string
	DNS        []string
	Peers      []PeerConfig
}

// PeerConfig holds a single WireGuard peer's configuration.
type PeerConfig struct {
	PublicKey           string
	Endpoint            string
	AllowedIPs          []string
	PersistentKeepalive int
}

// OpenZitiConfig holds configuration for the OpenZiti provider.
type OpenZitiConfig struct {
	IdentityFile string
	ServiceName  string
}

// NewWireGuardProvider creates a Provider backed by WireGuard.
func NewWireGuardProvider(cfg WireGuardConfig) Provider {
	return &wireguardProvider{cfg: cfg}
}

// NewOpenZitiProvider creates a Provider backed by OpenZiti (stub).
func NewOpenZitiProvider(cfg OpenZitiConfig) Provider {
	return &openZitiProvider{cfg: cfg}
}

// NewDualProvider creates a Provider that uses primary, falling back to secondary on failure.
func NewDualProvider(primary, secondary Provider) Provider {
	return &dualProvider{primary: primary, secondary: secondary}
}
