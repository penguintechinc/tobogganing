// Example application demonstrating Tobogganing tray icon functionality
package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/tobogganing/clients/native/internal/config"
	"github.com/tobogganing/clients/native/internal/tray"
	"github.com/tobogganing/clients/native/internal/vpn"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	if err := run(ctx, "config.yaml"); err != nil {
		fmt.Fprintf(os.Stderr, "tray-example: %v\n", err)
		os.Exit(1)
	}
}

// run starts the tray example with the given context. configPath may be empty to use defaults.
func run(ctx context.Context, configPath string) error {
	// Load configuration
	cfg := config.DefaultConfig()
	if configPath != "" {
		if err := config.LoadFromFile(cfg, configPath); err != nil {
			return fmt.Errorf("failed to load configuration from %s: %w", configPath, err)
		}
	}

	// Create managers
	vpnManager := vpn.NewManager(cfg)
	configManager := config.NewConfigManager(cfg)

	if err := configManager.Start(); err != nil {
		return fmt.Errorf("failed to start configuration manager: %w", err)
	}
	defer func() { _ = configManager.Stop() }()

	trayManager := tray.NewTrayManager(vpnManager, configManager)
	defer trayManager.Stop()

	// Context cancellation stops the tray manager
	go func() {
		<-ctx.Done()
		trayManager.Stop()
	}()

	return trayManager.Run()
}
