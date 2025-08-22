// Example application demonstrating SASEWaddle tray icon functionality
package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/sasewaddle/clients/native/internal/config"
	"github.com/sasewaddle/clients/native/internal/tray"
	"github.com/sasewaddle/clients/native/internal/vpn"
)

func main() {
	var configPath = flag.String("config", "config.yaml", "Path to configuration file")
	flag.Parse()

	log.Println("Starting SASEWaddle Client with System Tray...")

	// Load configuration
	cfg := config.DefaultConfig()
	if *configPath != "" {
		if err := config.LoadFromFile(cfg, *configPath); err != nil {
			log.Fatalf("Failed to load configuration from %s: %v", *configPath, err)
		}
	}

	// Create VPN manager
	vpnManager := vpn.NewManager(cfg)

	// Create configuration manager
	configManager := config.NewConfigManager(cfg)
	
	// Start configuration manager
	if err := configManager.Start(); err != nil {
		log.Fatalf("Failed to start configuration manager: %v", err)
	}
	defer configManager.Stop()

	// Create tray manager
	trayManager := tray.NewTrayManager(vpnManager, configManager)

	// Handle graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-sigChan
		log.Println("Received shutdown signal, cleaning up...")
		
		// Stop managers
		configManager.Stop()
		vpnManager.Stop()
		trayManager.Stop()
		
		os.Exit(0)
	}()

	// Run tray (this blocks until the application exits)
	log.Println("System tray started. Right-click the tray icon to access options.")
	if err := trayManager.Run(); err != nil {
		log.Fatalf("Tray manager failed: %v", err)
	}
}