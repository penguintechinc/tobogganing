package main

import (
	"fmt"
	"log"
	"os"

	"github.com/spf13/cobra"

	"github.com/tobogganing/clients/native/internal/config"
	"github.com/tobogganing/clients/native/internal/svc"
)

const (
	serviceName        = "sasewaddle-client"
	serviceDisplayName = "SASEWaddle Client"
	serviceDescription = "SASEWaddle native headless client — manages WireGuard VPN tunnels"
)

func main() {
	var rootCmd = &cobra.Command{
		Use:   "tobogganing-client",
		Short: "Tobogganing Native Client",
		Long:  "A native client for Tobogganing SASE solution",
		Run:   runClient,
	}

	var configFile string
	rootCmd.PersistentFlags().StringVar(&configFile, "config", "", "config file path")

	// Service management subcommands
	rootCmd.AddCommand(
		newServiceInstallCmd(),
		newServiceUninstallCmd(),
		newServiceStartCmd(),
		newServiceStopCmd(),
		newServiceStatusCmd(),
	)

	if err := rootCmd.Execute(); err != nil {
		log.Fatal(err)
	}
}

func runClient(cmd *cobra.Command, args []string) {
	cfg := config.DefaultConfig()

	configFile, _ := cmd.Flags().GetString("config")
	if configFile != "" {
		if err := config.LoadFromFile(cfg, configFile); err != nil {
			log.Fatalf("Failed to load config: %v", err)
		}
	} else {
		if err := config.LoadFromDefaults(cfg); err != nil {
			log.Fatalf("Failed to load default config: %v", err)
		}
	}

	fmt.Printf("Tobogganing Client - Headless Mode\n")
	fmt.Printf("Manager URL: %s\n", cfg.ManagerURL)
	fmt.Printf("Client Type: %s\n", cfg.ClientType)
	fmt.Printf("Auto Connect: %v\n", cfg.AutoConnect)

	if cfg.ManagerURL == "" {
		fmt.Println("No manager URL configured. Please set TOBOGGANING_MANAGER_URL environment variable or config file.")
		os.Exit(1)
	}

	fmt.Println("Client would start here...")
}

// newServiceManager constructs a svc.Manager with standard config.
func newServiceManager() (*svc.Manager, error) {
	executable, err := os.Executable()
	if err != nil {
		return nil, fmt.Errorf("resolve executable path: %w", err)
	}
	return svc.NewManager(svc.Config{
		Name:        serviceName,
		DisplayName: serviceDisplayName,
		Description: serviceDescription,
		Executable:  executable,
	})
}

func newServiceInstallCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "service-install",
		Short: "Register sasewaddle-client as a system service",
		RunE: func(cmd *cobra.Command, args []string) error {
			m, err := newServiceManager()
			if err != nil {
				return err
			}
			if err := m.Install(); err != nil {
				return fmt.Errorf("install failed: %w", err)
			}
			fmt.Println("Service installed successfully")
			return nil
		},
	}
}

func newServiceUninstallCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "service-uninstall",
		Short: "Remove the sasewaddle-client system service",
		RunE: func(cmd *cobra.Command, args []string) error {
			m, err := newServiceManager()
			if err != nil {
				return err
			}
			if err := m.Uninstall(); err != nil {
				return fmt.Errorf("uninstall failed: %w", err)
			}
			fmt.Println("Service uninstalled successfully")
			return nil
		},
	}
}

func newServiceStartCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "service-start",
		Short: "Start the sasewaddle-client system service",
		RunE: func(cmd *cobra.Command, args []string) error {
			m, err := newServiceManager()
			if err != nil {
				return err
			}
			if err := m.Start(); err != nil {
				return fmt.Errorf("start failed: %w", err)
			}
			fmt.Println("Service started successfully")
			return nil
		},
	}
}

func newServiceStopCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "service-stop",
		Short: "Stop the sasewaddle-client system service",
		RunE: func(cmd *cobra.Command, args []string) error {
			m, err := newServiceManager()
			if err != nil {
				return err
			}
			if err := m.Stop(); err != nil {
				return fmt.Errorf("stop failed: %w", err)
			}
			fmt.Println("Service stopped successfully")
			return nil
		},
	}
}

func newServiceStatusCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "service-status",
		Short: "Show the sasewaddle-client system service status",
		RunE: func(cmd *cobra.Command, args []string) error {
			m, err := newServiceManager()
			if err != nil {
				return err
			}
			status, err := m.Status()
			if err != nil {
				return fmt.Errorf("status failed: %w", err)
			}
			fmt.Printf("Service status: %s\n", status)
			return nil
		},
	}
}
