// Package config implements configuration management for the SASEWaddle native client.
//
// The config package provides:
// - Hierarchical configuration loading from multiple sources
// - Environment variable and file-based configuration
// - Cross-platform configuration directory management
// - Secure storage of API keys and certificates
// - Configuration validation and defaults
// - Hot reloading of configuration changes
//
// Configuration sources are loaded in priority order:
// 1. Command line flags
// 2. Environment variables
// 3. Configuration files (.yaml, .json, .toml)
// 4. Default values
package config

import (
    "fmt"
    "os"
    "path/filepath"
    "runtime"

    "github.com/spf13/viper"
)

// Config holds the configuration for the SASEWaddle native client
type Config struct {
    // Manager Service configuration
    ManagerURL string `mapstructure:"manager_url" json:"manager_url"`
    APIKey     string `mapstructure:"api_key" json:"api_key"`
    
    // Client configuration
    ClientName string `mapstructure:"client_name" json:"client_name"`
    ClientType string `mapstructure:"client_type" json:"client_type"`
    
    // Connection settings
    AutoConnect       bool `mapstructure:"auto_connect" json:"auto_connect"`
    ReconnectInterval int  `mapstructure:"reconnect_interval" json:"reconnect_interval"`
    
    // Logging and UI
    LogLevel string `mapstructure:"log_level" json:"log_level"`
    Headless bool   `mapstructure:"headless" json:"headless"`
    
    // Platform-specific settings
    ServiceMode bool `mapstructure:"service_mode" json:"service_mode"`
    
    // Advanced settings
    WireGuardInterface string `mapstructure:"wireguard_interface" json:"wireguard_interface"`
    DNSServers         []string `mapstructure:"dns_servers" json:"dns_servers"`
    
    // Authentication settings
    AuthRefreshThreshold int `mapstructure:"auth_refresh_threshold" json:"auth_refresh_threshold"`

    // Squawk DNS settings
    SquawkEnabled   bool   `mapstructure:"squawk_enabled" json:"squawk_enabled"`
    SquawkServerURL string `mapstructure:"squawk_server_url" json:"squawk_server_url"`
    DNSListenAddr   string `mapstructure:"dns_listen_addr" json:"dns_listen_addr"`

    // Performance monitoring (WaddlePerf)
    PerfEnabled  bool `mapstructure:"perf_enabled" json:"perf_enabled"`
    PerfInterval int  `mapstructure:"perf_interval" json:"perf_interval"`

    // Overlay configuration
    // OverlayType selects the network overlay used to reach the hub-router.
    // Valid values: "wireguard" (default) or "openziti" (requires binary
    // compiled with the "openziti" build tag).
    OverlayType string `mapstructure:"overlay_type" json:"overlay_type"`

    // Attestation settings
    AttestationEnabled bool   `mapstructure:"attestation_enabled" json:"attestation_enabled"`
    AttestationTPM     bool   `mapstructure:"attestation_tpm" json:"attestation_tpm"`
    FleetDMHostUUID    string `mapstructure:"fleetdm_host_uuid" json:"fleetdm_host_uuid"`
}

// DefaultConfig returns a configuration with default values
func DefaultConfig() *Config {
    return &Config{
        ClientType:           "client_native",
        AutoConnect:          false,
        ReconnectInterval:    30,
        LogLevel:             "info",
        Headless:             false,
        ServiceMode:          false,
        DNSServers:           []string{"10.200.0.1", "1.1.1.1", "8.8.8.8"},
        AuthRefreshThreshold: 300, // 5 minutes before expiry
        SquawkEnabled:        false,
        SquawkServerURL:      "https://dns.penguintech.io/dns-query",
        DNSListenAddr:        "127.0.0.1:53",
        PerfEnabled:          false,
        PerfInterval:         300,
        OverlayType:          "wireguard",
        AttestationEnabled: true,
        AttestationTPM:     true,
    }
}

// LoadFromFile loads configuration from a file
func LoadFromFile(cfg *Config, configFile string) error {
    viper.SetConfigFile(configFile)
    
    if err := viper.ReadInConfig(); err != nil {
        return fmt.Errorf("failed to read config file: %w", err)
    }
    
    if err := viper.Unmarshal(cfg); err != nil {
        return fmt.Errorf("failed to unmarshal config: %w", err)
    }
    
    return nil
}

// LoadFromDefaults loads configuration from default locations and environment variables
func LoadFromDefaults(cfg *Config) error {
    viper.SetConfigName("sasewaddle")
    viper.SetConfigType("yaml")
    
    // Add config paths
    viper.AddConfigPath(".")
    viper.AddConfigPath("$HOME/.sasewaddle")
    viper.AddConfigPath("/etc/sasewaddle")
    
    // Set environment variable prefix
    viper.SetEnvPrefix("SASEWADDLE")
    viper.AutomaticEnv()
    
    // Set default values
    viper.SetDefault("client_type", "client_native")
    viper.SetDefault("auto_connect", false)
    viper.SetDefault("reconnect_interval", 30)
    viper.SetDefault("log_level", "info")
    viper.SetDefault("headless", false)
    viper.SetDefault("service_mode", false)
    viper.SetDefault("dns_servers", []string{"10.200.0.1", "1.1.1.1", "8.8.8.8"})
    viper.SetDefault("auth_refresh_threshold", 300)
    viper.SetDefault("squawk_enabled", false)
    viper.SetDefault("squawk_server_url", "https://dns.penguintech.io/dns-query")
    viper.SetDefault("dns_listen_addr", "127.0.0.1:53")
    viper.SetDefault("perf_enabled", false)
    viper.SetDefault("perf_interval", 300)
    viper.SetDefault("overlay_type", "wireguard")
    viper.SetDefault("attestation_enabled", true)
    viper.SetDefault("attestation_tpm", true)
    viper.SetDefault("fleetdm_host_uuid", "")

    // Try to read config file (it's ok if it doesn't exist)
    if err := viper.ReadInConfig(); err != nil {
        if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
            return fmt.Errorf("failed to read config file: %w", err)
        }
    }
    
    if err := viper.Unmarshal(cfg); err != nil {
        return fmt.Errorf("failed to unmarshal config: %w", err)
    }
    
    return nil
}

// Save saves the configuration to a file
func (c *Config) Save(configFile string) error {
    viper.SetConfigFile(configFile)
    
    // Set values in viper
    viper.Set("manager_url", c.ManagerURL)
    viper.Set("api_key", c.APIKey)
    viper.Set("client_name", c.ClientName)
    viper.Set("client_type", c.ClientType)
    viper.Set("auto_connect", c.AutoConnect)
    viper.Set("reconnect_interval", c.ReconnectInterval)
    viper.Set("log_level", c.LogLevel)
    viper.Set("headless", c.Headless)
    viper.Set("service_mode", c.ServiceMode)
    viper.Set("wireguard_interface", c.WireGuardInterface)
    viper.Set("dns_servers", c.DNSServers)
    viper.Set("auth_refresh_threshold", c.AuthRefreshThreshold)
    viper.Set("squawk_enabled", c.SquawkEnabled)
    viper.Set("squawk_server_url", c.SquawkServerURL)
    viper.Set("dns_listen_addr", c.DNSListenAddr)
    viper.Set("perf_enabled", c.PerfEnabled)
    viper.Set("perf_interval", c.PerfInterval)
    viper.Set("overlay_type", c.OverlayType)
    viper.Set("attestation_enabled", c.AttestationEnabled)
    viper.Set("attestation_tpm", c.AttestationTPM)
    viper.Set("fleetdm_host_uuid", c.FleetDMHostUUID)

    // Create directory if it doesn't exist
    configDir := filepath.Dir(configFile)
    if err := os.MkdirAll(configDir, 0700); err != nil {
        return fmt.Errorf("failed to create config directory: %w", err)
    }
    
    if err := viper.WriteConfig(); err != nil {
        return fmt.Errorf("failed to write config file: %w", err)
    }
    
    return nil
}

// Validate validates the configuration
func (c *Config) Validate() error {
    if c.ManagerURL == "" {
        return fmt.Errorf("manager_url is required")
    }
    
    if c.APIKey == "" {
        return fmt.Errorf("api_key is required")
    }
    
    if c.ClientType != "client_native" {
        return fmt.Errorf("invalid client_type: %s", c.ClientType)
    }
    
    validLogLevels := map[string]bool{
        "debug": true,
        "info":  true,
        "warn":  true,
        "error": true,
    }
    
    if !validLogLevels[c.LogLevel] {
        return fmt.Errorf("invalid log_level: %s", c.LogLevel)
    }
    
    if c.ReconnectInterval < 10 {
        return fmt.Errorf("reconnect_interval must be at least 10 seconds")
    }
    
    if c.AuthRefreshThreshold < 60 {
        return fmt.Errorf("auth_refresh_threshold must be at least 60 seconds")
    }

    validOverlayTypes := map[string]bool{
        "wireguard": true,
        "openziti":  true,
    }
    if c.OverlayType != "" && !validOverlayTypes[c.OverlayType] {
        return fmt.Errorf("invalid overlay_type %q (valid: wireguard, openziti)", c.OverlayType)
    }

    return nil
}

// GetConfigDir returns the platform-specific configuration directory
func GetConfigDir() string {
    switch runtime.GOOS {
    case "darwin":
        return os.Getenv("HOME") + "/.sasewaddle"
    case "linux":
        configHome := os.Getenv("XDG_CONFIG_HOME")
        if configHome == "" {
            configHome = os.Getenv("HOME") + "/.config"
        }
        return configHome + "/sasewaddle"
    case "windows":
        return os.Getenv("APPDATA") + "\\SASEWaddle"
    default:
        return os.Getenv("HOME") + "/.sasewaddle"
    }
}

// GetDefaultConfigFile returns the default configuration file path
func GetDefaultConfigFile() string {
    return GetConfigDir() + "/config.yaml"
}

// GetWireGuardConfigPath returns the path to the WireGuard configuration file
func (c *Config) GetWireGuardConfigPath() string {
    return GetConfigDir() + "/wireguard.conf"
}

// WriteFile writes data to a file with proper permissions
func (c *Config) WriteFile(path string, data []byte) error {
    // Create directory if it doesn't exist
    configDir := filepath.Dir(path)
    if err := os.MkdirAll(configDir, 0700); err != nil {
        return fmt.Errorf("failed to create directory: %w", err)
    }
    
    // Write file with secure permissions
    if err := os.WriteFile(path, data, 0600); err != nil {
        return fmt.Errorf("failed to write file: %w", err)
    }
    
    return nil
}