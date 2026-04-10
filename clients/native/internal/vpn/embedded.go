// Package vpn provides embedded WireGuard implementation using wireguard-go
// This eliminates the need for separate WireGuard installation

package vpn

import (
	"context"
	"fmt"
	"net"
	"strings"
	"sync"

	"golang.zx2c4.com/wireguard/conn"
	"golang.zx2c4.com/wireguard/device"
	"golang.zx2c4.com/wireguard/tun"
)

// TunnelBackend abstracts TUN/device creation so it can be mocked in tests.
type TunnelBackend interface {
	// CreateTUN creates a new TUN device with the given name and MTU.
	CreateTUN(name string, mtu int) (tun.Device, error)
	// NewDevice creates a new WireGuard device on the given TUN device.
	NewDevice(tunDev tun.Device, bind conn.Bind, logger *device.Logger) *device.Device
}

// realTunnelBackend is the production implementation that calls wireguard-go
// functions that require kernel access.
type realTunnelBackend struct{}

func (r *realTunnelBackend) CreateTUN(name string, mtu int) (tun.Device, error) {
	return tun.CreateTUN(name, mtu)
}

func (r *realTunnelBackend) NewDevice(tunDev tun.Device, bind conn.Bind, logger *device.Logger) *device.Device {
	return device.NewDevice(tunDev, bind, logger)
}

// DefaultTunnelBackend returns the production TunnelBackend.
func DefaultTunnelBackend() TunnelBackend {
	return &realTunnelBackend{}
}

// EmbeddedWireGuard manages a WireGuard interface using wireguard-go
type EmbeddedWireGuard struct {
	device        *device.Device
	tun           tun.Device
	interfaceName string
	config        string
	isRunning     bool
	mutex         sync.RWMutex
	ctx           context.Context
	cancel        context.CancelFunc
	backend       TunnelBackend
}

// NewEmbeddedWireGuard creates a new embedded WireGuard instance using the
// production (kernel-backed) TunnelBackend.
func NewEmbeddedWireGuard(interfaceName string) *EmbeddedWireGuard {
	return NewEmbeddedWireGuardWithBackend(interfaceName, DefaultTunnelBackend())
}

// NewEmbeddedWireGuardWithBackend creates a new EmbeddedWireGuard that delegates
// TUN/device creation to the supplied backend. Use this in tests to inject a mock.
func NewEmbeddedWireGuardWithBackend(interfaceName string, backend TunnelBackend) *EmbeddedWireGuard {
	ctx, cancel := context.WithCancel(context.Background())
	return &EmbeddedWireGuard{
		interfaceName: interfaceName,
		ctx:           ctx,
		cancel:        cancel,
		backend:       backend,
	}
}

// Start initializes and starts the embedded WireGuard tunnel
func (ew *EmbeddedWireGuard) Start(config string) error {
	ew.mutex.Lock()
	defer ew.mutex.Unlock()

	if ew.isRunning {
		return fmt.Errorf("WireGuard is already running")
	}

	// Create TUN interface via the injected backend.
	tunDevice, err := ew.backend.CreateTUN(ew.interfaceName, device.DefaultMTU)
	if err != nil {
		return fmt.Errorf("failed to create TUN interface: %w", err)
	}
	ew.tun = tunDevice

	// Create WireGuard device via the injected backend.
	logger := device.NewLogger(device.LogLevelVerbose, fmt.Sprintf("(%s) ", ew.interfaceName))
	bind := conn.NewDefaultBind()
	wgDevice := ew.backend.NewDevice(ew.tun, bind, logger)
	ew.device = wgDevice

	// Configure WireGuard device
	if err := ew.configureDevice(config); err != nil {
		ew.cleanup()
		return fmt.Errorf("failed to configure device: %w", err)
	}

	// Bring the device up
	if err := wgDevice.Up(); err != nil {
		ew.cleanup()
		return fmt.Errorf("failed to bring device up: %w", err)
	}

	ew.config = config
	ew.isRunning = true

	return nil
}

// Stop shuts down the embedded WireGuard tunnel
func (ew *EmbeddedWireGuard) Stop() error {
	ew.mutex.Lock()
	defer ew.mutex.Unlock()

	if !ew.isRunning {
		return nil
	}

	ew.cleanup()
	ew.isRunning = false
	ew.cancel()

	return nil
}

// IsRunning returns whether the WireGuard tunnel is active
func (ew *EmbeddedWireGuard) IsRunning() bool {
	ew.mutex.RLock()
	defer ew.mutex.RUnlock()
	return ew.isRunning
}

// GetConfig returns the current WireGuard configuration
func (ew *EmbeddedWireGuard) GetConfig() string {
	ew.mutex.RLock()
	defer ew.mutex.RUnlock()
	return ew.config
}

// GetInterfaceName returns the interface name
func (ew *EmbeddedWireGuard) GetInterfaceName() string {
	return ew.interfaceName
}

// configureDevice applies WireGuard configuration to the device
func (ew *EmbeddedWireGuard) configureDevice(config string) error {
	// Parse and apply the WireGuard configuration
	if err := ew.device.IpcSetOperation(strings.NewReader(ew.parseConfig(config))); err != nil {
		return fmt.Errorf("failed to set device configuration: %w", err)
	}

	// Configure IP address and routes from the config
	if err := ew.configureNetworking(config); err != nil {
		return fmt.Errorf("failed to configure networking: %w", err)
	}

	return nil
}

// parseConfig converts WireGuard .conf format to IPC format
func (ew *EmbeddedWireGuard) parseConfig(config string) string {
	// This is a simplified parser - in production, would use a proper parser
	lines := strings.Split(config, "\n")
	var ipcConfig strings.Builder

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		if strings.HasPrefix(line, "[") {
			continue // Skip section headers
		}

		if strings.Contains(line, "=") {
			parts := strings.SplitN(line, "=", 2)
			key := strings.TrimSpace(strings.ToLower(parts[0]))
			value := strings.TrimSpace(parts[1])

			switch key {
			case "privatekey":
				ipcConfig.WriteString(fmt.Sprintf("private_key=%s\n", value))
			case "publickey":
				ipcConfig.WriteString(fmt.Sprintf("public_key=%s\n", value))
			case "endpoint":
				ipcConfig.WriteString(fmt.Sprintf("endpoint=%s\n", value))
			case "allowedips":
				ipcConfig.WriteString(fmt.Sprintf("allowed_ip=%s\n", value))
			case "persistentkeepalive":
				ipcConfig.WriteString(fmt.Sprintf("persistent_keepalive_interval=%s\n", value))
			}
		}
	}

	return ipcConfig.String()
}

// configureNetworking sets up IP addresses and routes
func (ew *EmbeddedWireGuard) configureNetworking(config string) error {
	// Extract Address from config
	address := ew.extractConfigValue(config, "Address")
	if address == "" {
		return fmt.Errorf("no Address specified in configuration")
	}

	// Configure the TUN interface with the IP address
	if err := ew.configureInterfaceIP(address); err != nil {
		return fmt.Errorf("failed to configure interface IP: %w", err)
	}

	// Extract and configure DNS if specified
	dns := ew.extractConfigValue(config, "DNS")
	if dns != "" {
		if err := ew.configureDNS(dns); err != nil {
			// DNS configuration is not critical, log but continue
			fmt.Printf("Warning: failed to configure DNS: %v\n", err)
		}
	}

	return nil
}

// extractConfigValue extracts a value from WireGuard config.
// Handles both "Key=Value" and "Key = Value" (with optional spaces around =).
func (ew *EmbeddedWireGuard) extractConfigValue(config, key string) string {
	lines := strings.Split(config, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if !strings.Contains(line, "=") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		lineKey := strings.TrimSpace(strings.ToLower(parts[0]))
		if lineKey == strings.ToLower(key) {
			return strings.TrimSpace(parts[1])
		}
	}
	return ""
}

// configureInterfaceIP configures the IP address on the TUN interface
func (ew *EmbeddedWireGuard) configureInterfaceIP(address string) error {
	// Parse the CIDR address
	ip, ipNet, err := net.ParseCIDR(address)
	if err != nil {
		return fmt.Errorf("invalid address format: %w", err)
	}

	// For embedded implementation, we would configure the TUN interface
	// This is platform-specific and would require different implementations
	// for Windows, macOS, and Linux

	fmt.Printf("Configuring interface %s with IP %s (network %s)\n",
		ew.interfaceName, ip.String(), ipNet.String())

	// In a full implementation, this would call platform-specific functions
	// to configure the interface IP address and routing table

	return nil
}

// configureDNS configures DNS settings
func (ew *EmbeddedWireGuard) configureDNS(dns string) error {
	dnsServers := strings.Split(dns, ",")
	for i, server := range dnsServers {
		dnsServers[i] = strings.TrimSpace(server)
	}

	fmt.Printf("Configuring DNS servers: %v\n", dnsServers)

	// In a full implementation, this would configure system DNS settings
	// This is platform-specific and requires elevated privileges

	return nil
}

// cleanup releases resources.
// device.Close() internally closes the underlying TUN, so we must not call
// ew.tun.Close() again to avoid a double-close panic.
func (ew *EmbeddedWireGuard) cleanup() {
	if ew.device != nil {
		ew.device.Close() // also closes ew.tun internally
		ew.device = nil
		ew.tun = nil // already closed by device.Close()
		return
	}
	// Device was never created but tun might still be open.
	if ew.tun != nil {
		_ = ew.tun.Close()
		ew.tun = nil
	}
}
