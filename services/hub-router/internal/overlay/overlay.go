// Package overlay manages VPN overlay providers for the hub-router.
//
// It supports multiple overlay technologies (WireGuard, OpenZiti) and allows
// the active provider to be selected at runtime via configuration.
package overlay

import (
	"context"
	"fmt"
	"net"
)

// Provider is the interface all overlay implementations must satisfy.
type Provider interface {
	// Name returns a stable identifier for this provider (e.g. "wireguard", "openziti").
	Name() string
	// Initialize prepares the provider for use without establishing a connection.
	Initialize(ctx context.Context) error
	// Connect establishes the overlay network connection.
	Connect(ctx context.Context) error
	// Disconnect tears down the overlay connection.
	Disconnect(ctx context.Context) error
	// Listener returns a net.Listener for inbound connections through this overlay.
	// May return nil for providers that do not accept inbound connections directly.
	Listener() net.Listener
}

// WireGuardConfig holds configuration for the WireGuard overlay provider.
type WireGuardConfig struct {
	Interface string
	Network   string
}

// OpenZitiConfig holds configuration for the OpenZiti overlay provider.
type OpenZitiConfig struct {
	IdentityFile string
	ServiceName  string
}

// Manager coordinates one or more overlay providers and routes traffic
// through the active (primary) provider.
type Manager struct {
	providers map[string]Provider
	primary   string
}

// NewManager creates a new overlay Manager with no registered providers.
func NewManager() *Manager {
	return &Manager{
		providers: make(map[string]Provider),
	}
}

// RegisterProvider registers a provider under its Name().
func (m *Manager) RegisterProvider(p Provider) {
	m.providers[p.Name()] = p
}

// SetPrimary designates the named provider as the active overlay.
func (m *Manager) SetPrimary(name string) error {
	if _, ok := m.providers[name]; !ok {
		return fmt.Errorf("overlay provider %q not registered", name)
	}
	m.primary = name
	return nil
}

// CloseAll disconnects all registered providers.
func (m *Manager) CloseAll() {
	ctx := context.Background()
	for _, p := range m.providers {
		_ = p.Disconnect(ctx)
	}
}

// Primary returns the active provider, or nil if none has been set.
func (m *Manager) Primary() Provider {
	if m.primary == "" {
		return nil
	}
	return m.providers[m.primary]
}

// --- WireGuard provider ---

type wireGuardProvider struct {
	cfg WireGuardConfig
}

// NewWireGuardProvider creates a Provider backed by WireGuard.
func NewWireGuardProvider(cfg WireGuardConfig) Provider {
	return &wireGuardProvider{cfg: cfg}
}

func (w *wireGuardProvider) Name() string { return "wireguard" }

func (w *wireGuardProvider) Initialize(_ context.Context) error { return nil }

func (w *wireGuardProvider) Connect(_ context.Context) error { return nil }

func (w *wireGuardProvider) Disconnect(_ context.Context) error { return nil }

func (w *wireGuardProvider) Listener() net.Listener { return nil }

// --- OpenZiti provider ---

type openZitiProvider struct {
	cfg      OpenZitiConfig
	listener net.Listener
}

// NewOpenZitiProvider creates a Provider backed by OpenZiti.
func NewOpenZitiProvider(cfg OpenZitiConfig) *openZitiProvider { //nolint:revive
	return &openZitiProvider{cfg: cfg}
}

func (o *openZitiProvider) Name() string { return "openziti" }

func (o *openZitiProvider) Initialize(_ context.Context) error { return nil }

func (o *openZitiProvider) Connect(_ context.Context) error { return nil }

func (o *openZitiProvider) Disconnect(_ context.Context) error { return nil }

func (o *openZitiProvider) Listener() net.Listener { return o.listener }
