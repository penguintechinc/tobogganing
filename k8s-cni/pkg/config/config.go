// Package config handles configuration parsing and validation for the Tobogganing CNI plugin.
//
// This package provides:
// - CNI network configuration parsing
// - Configuration validation and defaults
// - Integration with Tobogganing Manager settings
// - Support for both IPv4 and IPv6 configurations
// - Performance optimization settings
//
// The configuration follows CNI specification standards while adding
// Tobogganing-specific parameters for WireGuard and SASE integration.
package config

import (
	"encoding/json"
	"fmt"
	"net"
	"time"

	"github.com/containernetworking/cni/pkg/types"
)

// NetworkConfig represents the CNI network configuration for Tobogganing
type NetworkConfig struct {
	// Standard CNI fields
	CNIVersion   string          `json:"cniVersion"`
	Name         string          `json:"name"`
	Type         string          `json:"type"`
	PrevResult   *types.Result   `json:"prevResult,omitempty"`
	Capabilities map[string]bool `json:"capabilities,omitempty"`

	// Tobogganing-specific configuration
	Tobogganing ToboggatingConfig `json:"tobogganing"`

	// Network configuration
	IPAM      IPAMConfig      `json:"ipam"`
	DNS       types.DNS       `json:"dns,omitempty"`
	Routes    []*types.Route  `json:"routes,omitempty"`
}

// ToboggatingConfig contains Tobogganing-specific settings
type ToboggatingConfig struct {
	// Manager service configuration
	ManagerURL    string            `json:"managerURL"`
	APIKey        string            `json:"apiKey"`
	ClusterID     string            `json:"clusterID"`
	
	// WireGuard configuration
	WireGuard     WireGuardConfig   `json:"wireguard"`
	
	// Performance settings
	Performance   PerformanceConfig `json:"performance"`
	
	// Security settings
	Security      SecurityConfig    `json:"security"`
	
	// Logging configuration
	Logging       LoggingConfig     `json:"logging"`
}

// WireGuardConfig contains WireGuard-specific settings
type WireGuardConfig struct {
	// Interface naming
	InterfacePrefix string `json:"interfacePrefix,omitempty"`
	
	// Key management
	KeyPath         string `json:"keyPath,omitempty"`
	
	// Network settings
	ListenPort      int    `json:"listenPort,omitempty"`
	MTU             int    `json:"mtu,omitempty"`
	
	// Keepalive settings
	PersistentKeepalive int `json:"persistentKeepalive,omitempty"`
	
	// Endpoint settings
	AllowedIPs      []string `json:"allowedIPs,omitempty"`
}

// IPAMConfig contains IP address management configuration
type IPAMConfig struct {
	Type    string      `json:"type"`
	Subnet  string      `json:"subnet,omitempty"`
	Gateway string      `json:"gateway,omitempty"`
	Routes  []IPAMRoute `json:"routes,omitempty"`
	
	// Tobogganing-specific IPAM settings
	Pool        string        `json:"pool,omitempty"`
	BlockSize   int           `json:"blockSize,omitempty"`
	Autodetect  bool          `json:"autodetect,omitempty"`
}

// IPAMRoute represents a route in IPAM configuration
type IPAMRoute struct {
	Dst string `json:"dst"`
	GW  string `json:"gw,omitempty"`
}

// PerformanceConfig contains performance optimization settings
type PerformanceConfig struct {
	// Buffer sizes
	ReceiveBufferSize int `json:"receiveBufferSize,omitempty"`
	SendBufferSize    int `json:"sendBufferSize,omitempty"`
	
	// Worker pool settings
	WorkerCount       int `json:"workerCount,omitempty"`
	
	// Timeout settings
	SetupTimeout      time.Duration `json:"setupTimeout,omitempty"`
	HealthCheckTimeout time.Duration `json:"healthCheckTimeout,omitempty"`
	
	// Optimization flags
	EnableFastPath    bool `json:"enableFastPath,omitempty"`
	EnableOffload     bool `json:"enableOffload,omitempty"`
}

// SecurityConfig contains security-related settings
type SecurityConfig struct {
	// Encryption settings
	ForceEncryption   bool `json:"forceEncryption,omitempty"`
	
	// Network policy
	DefaultDeny       bool `json:"defaultDeny,omitempty"`
	
	// Audit settings
	EnableAuditLog    bool `json:"enableAuditLog,omitempty"`
	AuditLogPath      string `json:"auditLogPath,omitempty"`
}

// LoggingConfig contains logging configuration
type LoggingConfig struct {
	Level      string `json:"level,omitempty"`
	Format     string `json:"format,omitempty"`
	Output     string `json:"output,omitempty"`
	MaxSize    int    `json:"maxSize,omitempty"`
	MaxBackups int    `json:"maxBackups,omitempty"`
	MaxAge     int    `json:"maxAge,omitempty"`
}

// ParseNetworkConfig parses CNI network configuration from JSON
func ParseNetworkConfig(data []byte) (*NetworkConfig, error) {
	conf := &NetworkConfig{}
	
	if err := json.Unmarshal(data, conf); err != nil {
		return nil, fmt.Errorf("failed to unmarshal network config: %w", err)
	}
	
	// Validate configuration
	if err := validateConfig(conf); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}
	
	// Apply defaults
	applyDefaults(conf)
	
	return conf, nil
}

// validateConfig validates the network configuration
func validateConfig(conf *NetworkConfig) error {
	if conf.CNIVersion == "" {
		return fmt.Errorf("cniVersion is required")
	}
	
	if conf.Name == "" {
		return fmt.Errorf("network name is required")
	}
	
	if conf.Type != "tobogganing" {
		return fmt.Errorf("invalid plugin type: %s", conf.Type)
	}
	
	if conf.Tobogganing.ManagerURL == "" {
		return fmt.Errorf("managerURL is required")
	}
	
	if conf.Tobogganing.ClusterID == "" {
		return fmt.Errorf("clusterID is required")
	}
	
	// Validate IPAM configuration
	if err := validateIPAM(&conf.IPAM); err != nil {
		return fmt.Errorf("invalid IPAM config: %w", err)
	}
	
	// Validate WireGuard configuration
	if err := validateWireGuard(&conf.Tobogganing.WireGuard); err != nil {
		return fmt.Errorf("invalid WireGuard config: %w", err)
	}
	
	return nil
}

// validateIPAM validates IPAM configuration
func validateIPAM(ipam *IPAMConfig) error {
	if ipam.Type == "" {
		return fmt.Errorf("IPAM type is required")
	}
	
	// Validate subnet if provided
	if ipam.Subnet != "" {
		if _, _, err := net.ParseCIDR(ipam.Subnet); err != nil {
			return fmt.Errorf("invalid subnet: %w", err)
		}
	}
	
	// Validate gateway if provided
	if ipam.Gateway != "" {
		if net.ParseIP(ipam.Gateway) == nil {
			return fmt.Errorf("invalid gateway IP: %s", ipam.Gateway)
		}
	}
	
	// Validate routes
	for i, route := range ipam.Routes {
		if _, _, err := net.ParseCIDR(route.Dst); err != nil {
			return fmt.Errorf("invalid route %d destination: %w", i, err)
		}
		
		if route.GW != "" && net.ParseIP(route.GW) == nil {
			return fmt.Errorf("invalid route %d gateway: %s", i, route.GW)
		}
	}
	
	return nil
}

// validateWireGuard validates WireGuard configuration
func validateWireGuard(wg *WireGuardConfig) error {
	// Validate listen port
	if wg.ListenPort != 0 && (wg.ListenPort < 1024 || wg.ListenPort > 65535) {
		return fmt.Errorf("invalid listen port: %d", wg.ListenPort)
	}
	
	// Validate MTU
	if wg.MTU != 0 && (wg.MTU < 68 || wg.MTU > 9000) {
		return fmt.Errorf("invalid MTU: %d", wg.MTU)
	}
	
	// Validate allowed IPs
	for i, allowedIP := range wg.AllowedIPs {
		if _, _, err := net.ParseCIDR(allowedIP); err != nil {
			return fmt.Errorf("invalid allowed IP %d: %w", i, err)
		}
	}
	
	return nil
}

// applyDefaults applies default values to configuration
func applyDefaults(conf *NetworkConfig) {
	// Default performance settings
	if conf.Tobogganing.Performance.SetupTimeout == 0 {
		conf.Tobogganing.Performance.SetupTimeout = 30 * time.Second
	}
	
	if conf.Tobogganing.Performance.HealthCheckTimeout == 0 {
		conf.Tobogganing.Performance.HealthCheckTimeout = 10 * time.Second
	}
	
	if conf.Tobogganing.Performance.WorkerCount == 0 {
		conf.Tobogganing.Performance.WorkerCount = 4
	}
	
	// Default WireGuard settings
	if conf.Tobogganing.WireGuard.InterfacePrefix == "" {
		conf.Tobogganing.WireGuard.InterfacePrefix = "tob"
	}
	
	if conf.Tobogganing.WireGuard.MTU == 0 {
		conf.Tobogganing.WireGuard.MTU = 1420 // Standard for WireGuard
	}
	
	if conf.Tobogganing.WireGuard.PersistentKeepalive == 0 {
		conf.Tobogganing.WireGuard.PersistentKeepalive = 25 // seconds
	}
	
	// Default logging settings
	if conf.Tobogganing.Logging.Level == "" {
		conf.Tobogganing.Logging.Level = "info"
	}
	
	if conf.Tobogganing.Logging.Format == "" {
		conf.Tobogganing.Logging.Format = "json"
	}
	
	// Default IPAM settings
	if conf.IPAM.Type == "" {
		conf.IPAM.Type = "tobogganing-ipam"
	}
	
	if conf.IPAM.BlockSize == 0 {
		conf.IPAM.BlockSize = 26 // /26 blocks (64 IPs each)
	}
}

// ToJSON converts configuration to JSON string
func (conf *NetworkConfig) ToJSON() (string, error) {
	data, err := json.MarshalIndent(conf, "", "  ")
	if err != nil {
		return "", fmt.Errorf("failed to marshal config: %w", err)
	}
	return string(data), nil
}

// Clone creates a deep copy of the configuration
func (conf *NetworkConfig) Clone() *NetworkConfig {
	data, err := json.Marshal(conf)
	if err != nil {
		return nil
	}
	
	var clone NetworkConfig
	if err := json.Unmarshal(data, &clone); err != nil {
		return nil
	}
	
	return &clone
}