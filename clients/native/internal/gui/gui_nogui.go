//go:build nogui

// Package gui provides a stub implementation for headless builds.
package gui

import (
    "context"
)

// App represents a stub GUI application for headless builds
type App struct{}

// NewApp creates a new stub GUI application
func NewApp() *App {
    return &App{}
}

// Start is a no-op for headless builds
func (a *App) Start(ctx context.Context) error {
    return nil
}

// Stop is a no-op for headless builds
func (a *App) Stop() error {
    return nil
}

// ShowWindow is a no-op for headless builds
func (a *App) ShowWindow() {
    // No-op
}

// HideWindow is a no-op for headless builds
func (a *App) HideWindow() {
    // No-op
}