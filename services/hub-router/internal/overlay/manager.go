package overlay

import (
	"context"
	"fmt"
	"sync"

	log "github.com/sirupsen/logrus"
)

// validPolicyScopes enumerates the scope values that can appear on a
// policy_rules row.  "openziti" is included alongside the pre-existing values
// so that GetProvider can map policy scope → provider without a runtime error.
var validPolicyScopes = map[string]struct{}{
	"wireguard": {},
	"openziti":  {},
	"k8s":       {},
	"both":      {},
	"":          {},
}

// OverlayManager manages one or more overlay providers and routes packets to
// the correct provider based on the policy scope attached to a connection.
// It is safe for concurrent use by multiple goroutines.
type OverlayManager struct {
	providers map[string]OverlayProvider
	// primary is the name of the provider used for "both", "k8s", or unknown scopes.
	primary string
	mu      sync.RWMutex
}

// NewOverlayManager constructs an OverlayManager whose primary (fallback)
// provider is identified by primary (typically "wireguard").
func NewOverlayManager(primary string) *OverlayManager {
	return &OverlayManager{
		providers: make(map[string]OverlayProvider),
		primary:   primary,
	}
}

// RegisterProvider adds provider to the manager.  If a provider with the same
// name was already registered it is replaced.  RegisterProvider may be called
// before or after Initialize / Connect.
func (m *OverlayManager) RegisterProvider(provider OverlayProvider) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.providers[provider.Name()] = provider
	log.WithField("provider", provider.Name()).Info("overlay: provider registered")
}

// Initialize calls Initialize on every registered provider sequentially.
// It returns the first error encountered; successfully initialised providers
// are NOT rolled back on failure.
func (m *OverlayManager) Initialize(ctx context.Context) error {
	m.mu.RLock()
	defer m.mu.RUnlock()

	for name, provider := range m.providers {
		if err := provider.Initialize(ctx); err != nil {
			return fmt.Errorf("overlay: failed to initialize provider %q: %w", name, err)
		}
	}
	return nil
}

// Connect calls Connect on every registered provider sequentially.
// It returns the first error encountered.
func (m *OverlayManager) Connect(ctx context.Context) error {
	m.mu.RLock()
	defer m.mu.RUnlock()

	for name, provider := range m.providers {
		if err := provider.Connect(ctx); err != nil {
			return fmt.Errorf("overlay: failed to connect provider %q: %w", name, err)
		}
	}
	return nil
}

// GetProvider resolves the OverlayProvider that should handle traffic whose
// policy scope is scope.
//
// Scope-to-provider mapping:
//   - "wireguard"  → WireGuard provider
//   - "openziti"   → OpenZiti provider (available only when compiled with the
//     "openziti" build tag and the provider is registered)
//   - "k8s", "both", "" → primary provider (Cilium handles k8s-scoped traffic
//     at the CNI layer; the overlay manager hands it to the primary provider for
//     any application-layer processing)
//   - unrecognised  → primary provider with a warning log
//
// GetProvider always returns a non-nil provider as long as the primary has been
// registered; it never returns nil, nil.
func (m *OverlayManager) GetProvider(scope string) (OverlayProvider, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	// Warn on completely unrecognised scope values so operators can spot
	// misconfigured policy rows without blocking traffic.
	if _, known := validPolicyScopes[scope]; !known {
		log.WithField("scope", scope).Warn("overlay: unknown policy scope, falling back to primary provider")
	}

	switch scope {
	case "wireguard":
		if p, ok := m.providers["wireguard"]; ok {
			return p, nil
		}
	case "openziti":
		if p, ok := m.providers["openziti"]; ok {
			return p, nil
		}
		// OpenZiti may not be compiled in; fall through to primary.
		log.Warn("overlay: openziti provider not registered (binary built without openziti tag?), falling back to primary")
	}

	// "k8s", "both", "", or any unrecognised scope → primary.
	if p, ok := m.providers[m.primary]; ok {
		return p, nil
	}

	return nil, fmt.Errorf("overlay: no provider available for scope %q and primary %q is not registered", scope, m.primary)
}

// Close calls Close on all registered providers.  Errors are logged but do not
// stop the remaining providers from being closed.  The first error is returned.
func (m *OverlayManager) Close() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	var firstErr error
	for name, provider := range m.providers {
		if err := provider.Close(); err != nil {
			log.WithError(err).WithField("provider", name).Warn("overlay: error closing provider")
			if firstErr == nil {
				firstErr = err
			}
		}
	}
	return firstErr
}

// AllMetrics returns a snapshot of metrics from every registered provider,
// keyed by provider name.
func (m *OverlayManager) AllMetrics() map[string]OverlayMetrics {
	m.mu.RLock()
	defer m.mu.RUnlock()

	result := make(map[string]OverlayMetrics, len(m.providers))
	for name, provider := range m.providers {
		result[name] = provider.Metrics()
	}
	return result
}
