package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/spf13/cobra"

	"github.com/tobogganing/clients/native/internal/svc"
)

const (
	serviceName        = "sasewaddle-client"
	serviceDisplayName = "SASEWaddle Client"
	serviceDescription = "SASEWaddle native headless client — manages WireGuard VPN tunnels"
)

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	if err := run(ctx, os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

// run executes the client with the given arguments and context.
// All real logic is extracted here so it can be tested without os.Exit.
func run(ctx context.Context, args []string) error {
	var rootCmd = &cobra.Command{
		Use:   "tobogganing-client",
		Short: "Tobogganing Native Client",
		Long:  "A native client for Tobogganing SASE solution",
		RunE:  runClient,
	}

	var configFile string
	rootCmd.PersistentFlags().StringVar(&configFile, "config", "", "config file path")

	// Service management subcommands — default factory creates a real OS manager.
	mgr := defaultManagerFactory
	rootCmd.AddCommand(
		newServiceInstallCmd(mgr),
		newServiceUninstallCmd(mgr),
		newServiceStartCmd(mgr),
		newServiceStopCmd(mgr),
		newServiceStatusCmd(mgr),
	)

	rootCmd.SetArgs(args)
	rootCmd.SetContext(ctx)

	return rootCmd.Execute()
}

// runClient is the cobra RunE handler for the root command.
func runClient(cmd *cobra.Command, args []string) error {
	configFile, _ := cmd.Flags().GetString("config")

	cfg, err := parseConfigFlags(configFile)
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}

	printConfigInfo(cfg)

	if err := validateConfig(cfg); err != nil {
		return fmt.Errorf("no manager URL configured. Please set TOBOGGANING_MANAGER_URL environment variable or config file")
	}

	fmt.Println("Client would start here...")
	return nil
}

// managerFactory is a function that creates a ServiceManagerIface.
// The default uses the real OS service manager; tests inject a mock.
type managerFactory func() (svc.ServiceManagerIface, error)

// defaultManagerFactory creates a real OS service manager.
func defaultManagerFactory() (svc.ServiceManagerIface, error) {
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

func newServiceInstallCmd(factory managerFactory) *cobra.Command {
	return &cobra.Command{
		Use:   "service-install",
		Short: "Register sasewaddle-client as a system service",
		RunE: func(cmd *cobra.Command, args []string) error {
			m, err := factory()
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

func newServiceUninstallCmd(factory managerFactory) *cobra.Command {
	return &cobra.Command{
		Use:   "service-uninstall",
		Short: "Remove the sasewaddle-client system service",
		RunE: func(cmd *cobra.Command, args []string) error {
			m, err := factory()
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

func newServiceStartCmd(factory managerFactory) *cobra.Command {
	return &cobra.Command{
		Use:   "service-start",
		Short: "Start the sasewaddle-client system service",
		RunE: func(cmd *cobra.Command, args []string) error {
			m, err := factory()
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

func newServiceStopCmd(factory managerFactory) *cobra.Command {
	return &cobra.Command{
		Use:   "service-stop",
		Short: "Stop the sasewaddle-client system service",
		RunE: func(cmd *cobra.Command, args []string) error {
			m, err := factory()
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

func newServiceStatusCmd(factory managerFactory) *cobra.Command {
	return &cobra.Command{
		Use:   "service-status",
		Short: "Show the sasewaddle-client system service status",
		RunE: func(cmd *cobra.Command, args []string) error {
			m, err := factory()
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
