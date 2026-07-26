package main

import (
	"fmt"

	"github.com/tobogganing/clients/native/internal/config"
)

// parseConfigFlags loads configuration from file or defaults.
// This is extracted to be testable without main() calling os.Exit.
func parseConfigFlags(configFile string) (*config.Config, error) {
	cfg := config.DefaultConfig()

	if configFile != "" {
		if err := config.LoadFromFile(cfg, configFile); err != nil {
			return nil, fmt.Errorf("failed to load config: %w", err)
		}
	} else {
		if err := config.LoadFromDefaults(cfg); err != nil {
			return nil, fmt.Errorf("failed to load default config: %w", err)
		}
	}

	return cfg, nil
}

// validateConfig checks that required configuration is present.
// Returns an error if manager URL is missing.
func validateConfig(cfg *config.Config) error {
	if cfg.ManagerURL == "" {
		return fmt.Errorf("no manager URL configured")
	}
	return nil
}

// printConfigInfo prints configuration details to stdout.
// Exported for testing.
func printConfigInfo(cfg *config.Config) {
	fmt.Printf("Tobogganing Client - Headless Mode\n")
	fmt.Printf("Manager URL: %s\n", cfg.ManagerURL)
	fmt.Printf("Client Type: %s\n", cfg.ClientType)
	fmt.Printf("Auto Connect: %v\n", cfg.AutoConnect)
}
