// Package svc provides cross-platform system service management.
// It wraps github.com/kardianos/service to provide Install, Uninstall,
// Start, Stop, and Status operations on Linux (systemd), macOS (LaunchAgent),
// and Windows (Service Manager).
package svc

import (
	"fmt"

	"github.com/kardianos/service"
)

// Config holds service registration parameters.
type Config struct {
	Name        string
	DisplayName string
	Description string
	Executable  string
	Arguments   []string
}

// Manager manages lifecycle of the system service.
type Manager struct {
	svc service.Service
}

// program satisfies the kardianos service.Interface.
type program struct{}

func (p *program) Start(_ service.Service) error { return nil }
func (p *program) Stop(_ service.Service) error  { return nil }

// NewManager creates a Manager for the given service config.
func NewManager(cfg Config) (*Manager, error) {
	svcConfig := &service.Config{
		Name:        cfg.Name,
		DisplayName: cfg.DisplayName,
		Description: cfg.Description,
	}
	if cfg.Executable != "" {
		svcConfig.Executable = cfg.Executable
	}
	if len(cfg.Arguments) > 0 {
		svcConfig.Arguments = cfg.Arguments
	}
	s, err := service.New(&program{}, svcConfig)
	if err != nil {
		return nil, fmt.Errorf("create service: %w", err)
	}
	return &Manager{svc: s}, nil
}

// Install registers the service with the OS service manager.
func (m *Manager) Install() error {
	if err := m.svc.Install(); err != nil {
		return fmt.Errorf("install service: %w", err)
	}
	return nil
}

// Uninstall removes the service from the OS service manager.
func (m *Manager) Uninstall() error {
	if err := m.svc.Uninstall(); err != nil {
		return fmt.Errorf("uninstall service: %w", err)
	}
	return nil
}

// Start starts the service via the OS service manager.
func (m *Manager) Start() error {
	if err := m.svc.Start(); err != nil {
		return fmt.Errorf("start service: %w", err)
	}
	return nil
}

// Stop stops the service via the OS service manager.
func (m *Manager) Stop() error {
	if err := m.svc.Stop(); err != nil {
		return fmt.Errorf("stop service: %w", err)
	}
	return nil
}

// Status returns a human-readable status string.
func (m *Manager) Status() (string, error) {
	status, err := m.svc.Status()
	if err != nil {
		return "", fmt.Errorf("service status: %w", err)
	}
	switch status {
	case service.StatusRunning:
		return "running", nil
	case service.StatusStopped:
		return "stopped", nil
	default:
		return "unknown", nil
	}
}
