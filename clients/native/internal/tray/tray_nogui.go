//go:build nogui || !(linux || darwin || windows)

// Package tray provides system tray icon functionality for Tobogganing client.
// This is the no-GUI stub implementation.
package tray

import (
	"context"
	"time"

	"github.com/tobogganing/clients/native/internal/logger"
)

var log = logger.Get()

// VPNManager interface defines the methods needed to control VPN connections
type VPNManager interface {
	Connect() error
	Disconnect() error
	IsConnected() bool
	GetStatusString() string
	GetStatistics() map[string]interface{}
}

// ConfigManager interface defines methods for configuration management
type ConfigManager interface {
	GetServerURL() string
	UpdateConfiguration() error
	GetUpdateSchedule() time.Duration
}

// TrayManager manages the system tray icon and interactions (stub implementation)
type TrayManager struct {
	vpn    VPNManager
	config ConfigManager
	ctx    context.Context
	cancel context.CancelFunc
}

// NewTrayManager creates a new system tray manager (stub implementation)
func NewTrayManager(vpn VPNManager, config ConfigManager) *TrayManager {
	ctx, cancel := context.WithCancel(context.Background())
	return &TrayManager{
		vpn:    vpn,
		config: config,
		ctx:    ctx,
		cancel: cancel,
	}
}

// Run starts the system tray and blocks until the context is canceled (stub implementation)
func (t *TrayManager) Run() error {
	log.Info("system tray not available in this build (no GUI support)")
	<-t.ctx.Done()
	return nil
}

// Stop gracefully shuts down the tray manager (stub implementation)
func (t *TrayManager) Stop() {
	t.cancel()
}

// Run starts the system tray manager with the given configuration (stub implementation)
func Run(cfg interface{}) error {
	log.Info("system tray not available in this build (no GUI support)")
	return nil
}