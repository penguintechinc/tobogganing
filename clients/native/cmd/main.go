package main

import (
    "context"
    "fmt"
    "os"
    "os/signal"
    "runtime"
    "syscall"

    "github.com/spf13/cobra"
    "github.com/sasewaddle/clients/native/internal/client"
    "github.com/sasewaddle/clients/native/internal/config"
    "github.com/sasewaddle/clients/native/internal/gui"
    "github.com/sasewaddle/clients/native/internal/tray"
)

var (
    version   = "1.0.0"
    buildTime = "unknown"
    gitCommit = "unknown"
)

func main() {
    var rootCmd = &cobra.Command{
        Use:   "sasewaddle-client",
        Short: "SASEWaddle Native Client",
        Long: `SASEWaddle Native Client provides secure SASE connectivity
with WireGuard VPN and dual authentication (Certificate + JWT/SSO).

Supports:
- macOS Universal (Intel + Apple Silicon)
- Windows (x64)  
- Linux (x64, ARM64)`,
        Version: fmt.Sprintf("%s (build %s, commit %s)", version, buildTime, gitCommit),
    }

    // Global flags
    rootCmd.PersistentFlags().StringP("config", "c", "", "Configuration file path")
    rootCmd.PersistentFlags().StringP("manager-url", "m", "", "Manager Service URL")
    rootCmd.PersistentFlags().StringP("log-level", "l", "info", "Log level (debug, info, warn, error)")
    rootCmd.PersistentFlags().Bool("headless", false, "Run in headless mode (no GUI)")

    // Connect command
    var connectCmd = &cobra.Command{
        Use:   "connect",
        Short: "Connect to SASEWaddle network",
        Long:  "Establish VPN connection to the SASEWaddle SASE network with dual authentication",
        RunE:  runConnect,
    }
    
    connectCmd.Flags().StringP("api-key", "k", "", "Client API key for authentication")
    connectCmd.Flags().StringP("client-name", "n", "", "Client name (defaults to hostname)")
    connectCmd.Flags().Bool("auto-connect", false, "Automatically connect on startup")

    // Disconnect command
    var disconnectCmd = &cobra.Command{
        Use:   "disconnect",
        Short: "Disconnect from SASEWaddle network",
        Long:  "Safely disconnect from the SASEWaddle SASE network",
        RunE:  runDisconnect,
    }

    // Status command
    var statusCmd = &cobra.Command{
        Use:   "status",
        Short: "Show connection status",
        Long:  "Display current VPN connection status and authentication info",
        RunE:  runStatus,
    }

    // GUI command
    var guiCmd = &cobra.Command{
        Use:   "gui",
        Short: "Launch GUI interface",
        Long:  "Start the graphical user interface for SASEWaddle client",
        RunE:  runGUI,
    }

    // Service command (Windows/macOS/Linux service)
    var serviceCmd = &cobra.Command{
        Use:   "service",
        Short: "Service management commands",
        Long:  "Install, uninstall, start, stop the SASEWaddle client service",
    }

    var installServiceCmd = &cobra.Command{
        Use:   "install",
        Short: "Install system service",
        RunE:  runServiceInstall,
    }

    var uninstallServiceCmd = &cobra.Command{
        Use:   "uninstall", 
        Short: "Uninstall system service",
        RunE:  runServiceUninstall,
    }

    var startServiceCmd = &cobra.Command{
        Use:   "start",
        Short: "Start system service",
        RunE:  runServiceStart,
    }

    var stopServiceCmd = &cobra.Command{
        Use:   "stop",
        Short: "Stop system service", 
        RunE:  runServiceStop,
    }

    // Add service subcommands
    serviceCmd.AddCommand(installServiceCmd, uninstallServiceCmd, startServiceCmd, stopServiceCmd)

    // Add all commands
    rootCmd.AddCommand(connectCmd, disconnectCmd, statusCmd, guiCmd, serviceCmd)

    if err := rootCmd.Execute(); err != nil {
        fmt.Fprintf(os.Stderr, "Error: %v\n", err)
        os.Exit(1)
    }
}

func runConnect(cmd *cobra.Command, args []string) error {
    cfg, err := loadConfig(cmd)
    if err != nil {
        return fmt.Errorf("failed to load config: %w", err)
    }

    client, err := client.New(cfg)
    if err != nil {
        return fmt.Errorf("failed to create client: %w", err)
    }

    ctx, cancel := context.WithCancel(context.Background())
    defer cancel()

    // Handle interrupt signals
    sigChan := make(chan os.Signal, 1)
    signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
    
    go func() {
        <-sigChan
        fmt.Println("\nReceived interrupt signal, disconnecting...")
        cancel()
    }()

    return client.Connect(ctx)
}

func runDisconnect(cmd *cobra.Command, args []string) error {
    cfg, err := loadConfig(cmd)
    if err != nil {
        return fmt.Errorf("failed to load config: %w", err)
    }

    client, err := client.New(cfg)
    if err != nil {
        return fmt.Errorf("failed to create client: %w", err)
    }

    return client.Disconnect()
}

func runStatus(cmd *cobra.Command, args []string) error {
    cfg, err := loadConfig(cmd)
    if err != nil {
        return fmt.Errorf("failed to load config: %w", err)
    }

    client, err := client.New(cfg)
    if err != nil {
        return fmt.Errorf("failed to create client: %w", err)
    }

    status, err := client.Status()
    if err != nil {
        return fmt.Errorf("failed to get status: %w", err)
    }

    // Pretty print status
    fmt.Printf("SASEWaddle Client Status\n")
    fmt.Printf("========================\n")
    fmt.Printf("State: %s\n", status.State)
    fmt.Printf("Client ID: %s\n", status.ClientID)
    fmt.Printf("WireGuard IP: %s\n", status.WireGuardIP)
    fmt.Printf("Headend URL: %s\n", status.HeadendURL)
    fmt.Printf("Connected Since: %s\n", status.ConnectedSince.Format("2006-01-02 15:04:05"))
    fmt.Printf("Bytes Sent: %d\n", status.BytesSent)
    fmt.Printf("Bytes Received: %d\n", status.BytesReceived)
    fmt.Printf("Last Handshake: %s\n", status.LastHandshake.Format("2006-01-02 15:04:05"))

    return nil
}

func runGUI(cmd *cobra.Command, args []string) error {
    cfg, err := loadConfig(cmd)
    if err != nil {
        return fmt.Errorf("failed to load config: %w", err)
    }

    headless, _ := cmd.Flags().GetBool("headless")
    
    if headless || runtime.GOOS == "linux" {
        // Use system tray for headless or Linux
        return tray.Run(cfg)
    } else {
        // Use full GUI for Windows/macOS
        return gui.Run(cfg)
    }
}

func runServiceInstall(cmd *cobra.Command, args []string) error {
    // Implementation depends on platform
    switch runtime.GOOS {
    case "windows":
        return installWindowsService()
    case "darwin":
        return installMacOSService()
    case "linux":
        return installLinuxService()
    default:
        return fmt.Errorf("service installation not supported on %s", runtime.GOOS)
    }
}

func runServiceUninstall(cmd *cobra.Command, args []string) error {
    switch runtime.GOOS {
    case "windows":
        return uninstallWindowsService()
    case "darwin":
        return uninstallMacOSService()
    case "linux":
        return uninstallLinuxService()
    default:
        return fmt.Errorf("service uninstallation not supported on %s", runtime.GOOS)
    }
}

func runServiceStart(cmd *cobra.Command, args []string) error {
    switch runtime.GOOS {
    case "windows":
        return startWindowsService()
    case "darwin":
        return startMacOSService()
    case "linux":
        return startLinuxService()
    default:
        return fmt.Errorf("service control not supported on %s", runtime.GOOS)
    }
}

func runServiceStop(cmd *cobra.Command, args []string) error {
    switch runtime.GOOS {
    case "windows":
        return stopWindowsService()
    case "darwin":
        return stopMacOSService()
    case "linux":
        return stopLinuxService()
    default:
        return fmt.Errorf("service control not supported on %s", runtime.GOOS)
    }
}

func loadConfig(cmd *cobra.Command) (*config.Config, error) {
    configFile, _ := cmd.Flags().GetString("config")
    managerURL, _ := cmd.Flags().GetString("manager-url")
    logLevel, _ := cmd.Flags().GetString("log-level")
    
    cfg := &config.Config{
        ManagerURL: managerURL,
        LogLevel:   logLevel,
    }
    
    if configFile != "" {
        if err := config.LoadFromFile(cfg, configFile); err != nil {
            return nil, err
        }
    }
    
    return cfg, cfg.Validate()
}

// Platform-specific service implementations would go here
// For brevity, these are placeholder functions

func installWindowsService() error {
    fmt.Println("Installing Windows service...")
    return fmt.Errorf("Windows service installation not implemented yet")
}

func uninstallWindowsService() error {
    fmt.Println("Uninstalling Windows service...")  
    return fmt.Errorf("Windows service uninstallation not implemented yet")
}

func startWindowsService() error {
    fmt.Println("Starting Windows service...")
    return fmt.Errorf("Windows service control not implemented yet")
}

func stopWindowsService() error {
    fmt.Println("Stopping Windows service...")
    return fmt.Errorf("Windows service control not implemented yet")
}

func installMacOSService() error {
    fmt.Println("Installing macOS service...")
    return fmt.Errorf("macOS service installation not implemented yet")
}

func uninstallMacOSService() error {
    fmt.Println("Uninstalling macOS service...")
    return fmt.Errorf("macOS service uninstallation not implemented yet")
}

func startMacOSService() error {
    fmt.Println("Starting macOS service...")
    return fmt.Errorf("macOS service control not implemented yet")
}

func stopMacOSService() error {
    fmt.Println("Stopping macOS service...")
    return fmt.Errorf("macOS service control not implemented yet")
}

func installLinuxService() error {
    fmt.Println("Installing Linux systemd service...")
    return fmt.Errorf("Linux service installation not implemented yet")
}

func uninstallLinuxService() error {
    fmt.Println("Uninstalling Linux systemd service...")
    return fmt.Errorf("Linux service uninstallation not implemented yet")
}

func startLinuxService() error {
    fmt.Println("Starting Linux systemd service...")
    return fmt.Errorf("Linux service control not implemented yet")
}

func stopLinuxService() error {
    fmt.Println("Stopping Linux systemd service...")
    return fmt.Errorf("Linux service control not implemented yet")
}