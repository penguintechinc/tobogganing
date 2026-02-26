package dns

import (
	"context"

	log "github.com/sirupsen/logrus"
)

// Module manages the lifecycle of the native-client DNS integration.
//
// When started it:
//  1. Records that DNS forwarding is active.
//  2. Logs the listener address so operators know where stub DNS is bound.
//
// System DNS configuration (resolv.conf / networksetup / netsh) is handled
// by the platform-specific functions ConfigureSystemDNS and RestoreSystemDNS
// defined in the platform_*.go build-tag files.
type Module struct {
	config  Config
	running bool
}

// NewModule creates a Module from the supplied Config.
func NewModule(cfg Config) *Module {
	return &Module{config: cfg}
}

// Start activates the DNS module.  When Enabled is false the method returns
// immediately without changing any system state.
func (m *Module) Start(_ context.Context) error {
	if !m.config.Enabled {
		return nil
	}
	m.running = true
	log.WithFields(log.Fields{
		"listen":   m.config.ListenAddr,
		"upstream": m.config.UpstreamAddr,
	}).Info("DNS module started — forwarding to hub-router Squawk endpoint")
	return nil
}

// Stop deactivates the DNS module.  It is safe to call Stop when the module
// was never started or was already stopped.
func (m *Module) Stop() error {
	if !m.running {
		return nil
	}
	m.running = false
	log.Info("DNS module stopped")
	return nil
}

// IsRunning reports whether the DNS module is currently active.
func (m *Module) IsRunning() bool {
	return m.running
}
