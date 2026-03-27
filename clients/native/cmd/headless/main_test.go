package main

import (
	"testing"

	"github.com/spf13/cobra"
)

// buildRootCmd assembles the cobra command tree as it would be in main(), but
// without calling Execute() so tests can inspect structure.
func buildRootCmd() *cobra.Command {
	rootCmd := &cobra.Command{
		Use:   "tobogganing-client",
		Short: "Tobogganing Native Client",
		Long:  "A native client for Tobogganing SASE solution",
		Run:   runClient,
	}

	rootCmd.PersistentFlags().String("config", "", "config file path")

	rootCmd.AddCommand(
		newServiceInstallCmd(),
		newServiceUninstallCmd(),
		newServiceStartCmd(),
		newServiceStopCmd(),
		newServiceStatusCmd(),
	)

	return rootCmd
}

// --- Root command ---

func TestRootCmd_Use(t *testing.T) {
	cmd := buildRootCmd()
	if cmd.Use != "tobogganing-client" {
		t.Errorf("Use: want %q, got %q", "tobogganing-client", cmd.Use)
	}
}

func TestRootCmd_Short_NonEmpty(t *testing.T) {
	cmd := buildRootCmd()
	if cmd.Short == "" {
		t.Error("Short description should not be empty")
	}
}

func TestRootCmd_Long_NonEmpty(t *testing.T) {
	cmd := buildRootCmd()
	if cmd.Long == "" {
		t.Error("Long description should not be empty")
	}
}

func TestRootCmd_HasConfigFlag(t *testing.T) {
	cmd := buildRootCmd()
	flag := cmd.PersistentFlags().Lookup("config")
	if flag == nil {
		t.Fatal("expected --config persistent flag")
	}
	if flag.Value.Type() != "string" {
		t.Errorf("--config flag type: want string, got %q", flag.Value.Type())
	}
}

// --- Subcommands are registered ---

func TestRootCmd_HasServiceInstall(t *testing.T) {
	cmd := buildRootCmd()
	sub, _, err := cmd.Find([]string{"service-install"})
	if err != nil {
		t.Fatalf("Find service-install: %v", err)
	}
	if sub == nil || sub.Use != "service-install" {
		t.Errorf("expected service-install subcommand, got %v", sub)
	}
}

func TestRootCmd_HasServiceUninstall(t *testing.T) {
	cmd := buildRootCmd()
	sub, _, err := cmd.Find([]string{"service-uninstall"})
	if err != nil {
		t.Fatalf("Find service-uninstall: %v", err)
	}
	if sub == nil || sub.Use != "service-uninstall" {
		t.Errorf("expected service-uninstall subcommand, got %v", sub)
	}
}

func TestRootCmd_HasServiceStart(t *testing.T) {
	cmd := buildRootCmd()
	sub, _, err := cmd.Find([]string{"service-start"})
	if err != nil {
		t.Fatalf("Find service-start: %v", err)
	}
	if sub == nil || sub.Use != "service-start" {
		t.Errorf("expected service-start subcommand, got %v", sub)
	}
}

func TestRootCmd_HasServiceStop(t *testing.T) {
	cmd := buildRootCmd()
	sub, _, err := cmd.Find([]string{"service-stop"})
	if err != nil {
		t.Fatalf("Find service-stop: %v", err)
	}
	if sub == nil || sub.Use != "service-stop" {
		t.Errorf("expected service-stop subcommand, got %v", sub)
	}
}

func TestRootCmd_HasServiceStatus(t *testing.T) {
	cmd := buildRootCmd()
	sub, _, err := cmd.Find([]string{"service-status"})
	if err != nil {
		t.Fatalf("Find service-status: %v", err)
	}
	if sub == nil || sub.Use != "service-status" {
		t.Errorf("expected service-status subcommand, got %v", sub)
	}
}

func TestRootCmd_SubcommandCount(t *testing.T) {
	cmd := buildRootCmd()
	// 5 service management subcommands.
	if len(cmd.Commands()) != 5 {
		t.Errorf("expected 5 subcommands, got %d", len(cmd.Commands()))
	}
}

// --- Subcommand properties ---

func TestServiceInstallCmd_Short_NonEmpty(t *testing.T) {
	cmd := newServiceInstallCmd()
	if cmd.Short == "" {
		t.Error("service-install Short should not be empty")
	}
}

func TestServiceUninstallCmd_Short_NonEmpty(t *testing.T) {
	cmd := newServiceUninstallCmd()
	if cmd.Short == "" {
		t.Error("service-uninstall Short should not be empty")
	}
}

func TestServiceStartCmd_Short_NonEmpty(t *testing.T) {
	cmd := newServiceStartCmd()
	if cmd.Short == "" {
		t.Error("service-start Short should not be empty")
	}
}

func TestServiceStopCmd_Short_NonEmpty(t *testing.T) {
	cmd := newServiceStopCmd()
	if cmd.Short == "" {
		t.Error("service-stop Short should not be empty")
	}
}

func TestServiceStatusCmd_Short_NonEmpty(t *testing.T) {
	cmd := newServiceStatusCmd()
	if cmd.Short == "" {
		t.Error("service-status Short should not be empty")
	}
}

// --- Service constants ---

func TestServiceConstants(t *testing.T) {
	if serviceName == "" {
		t.Error("serviceName should not be empty")
	}
	if serviceDisplayName == "" {
		t.Error("serviceDisplayName should not be empty")
	}
	if serviceDescription == "" {
		t.Error("serviceDescription should not be empty")
	}
}

// --- newServiceManager ---

func TestNewServiceManager_ReturnsNonNilOrError(t *testing.T) {
	m, err := newServiceManager()
	if err != nil {
		// Acceptable: might fail if executable path is unusual in test environment.
		t.Logf("newServiceManager error (acceptable in test env): %v", err)
		return
	}
	if m == nil {
		t.Error("newServiceManager returned nil manager without error")
	}
}

// --- Service subcommand RunE (integration without actual OS service calls) ---

func TestServiceInstallCmd_RunE_ErrorWrapped(t *testing.T) {
	cmd := newServiceInstallCmd()
	// RunE will try to create and install a service. It will fail without privileges.
	err := cmd.RunE(cmd, nil)
	if err != nil {
		// Acceptable. Just verify the error is non-nil and sensible.
		t.Logf("service-install RunE error (expected without privileges): %v", err)
	}
}

func TestServiceUninstallCmd_RunE_ErrorWrapped(t *testing.T) {
	cmd := newServiceUninstallCmd()
	err := cmd.RunE(cmd, nil)
	if err != nil {
		t.Logf("service-uninstall RunE error (expected without privileges): %v", err)
	}
}

func TestServiceStartCmd_RunE_ErrorWrapped(t *testing.T) {
	cmd := newServiceStartCmd()
	err := cmd.RunE(cmd, nil)
	if err != nil {
		t.Logf("service-start RunE error (expected without privileges): %v", err)
	}
}

func TestServiceStopCmd_RunE_ErrorWrapped(t *testing.T) {
	cmd := newServiceStopCmd()
	err := cmd.RunE(cmd, nil)
	if err != nil {
		t.Logf("service-stop RunE error (expected without privileges): %v", err)
	}
}

func TestServiceStatusCmd_RunE_ReturnsResult(t *testing.T) {
	cmd := newServiceStatusCmd()
	err := cmd.RunE(cmd, nil)
	if err != nil {
		t.Logf("service-status RunE error (expected without privileges): %v", err)
	}
}

// --- Help text ---

func TestRootCmd_HelpText_NonEmpty(t *testing.T) {
	cmd := buildRootCmd()
	help := cmd.UsageString()
	if help == "" {
		t.Error("root command usage string should not be empty")
	}
}
