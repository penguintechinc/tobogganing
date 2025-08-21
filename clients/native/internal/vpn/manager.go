// Package vpn provides WireGuard VPN management functionality for SASEWaddle client.
//
// The vpn package implements a cross-platform WireGuard VPN manager that handles:
// - Connection establishment and termination
// - Configuration management
// - Status monitoring and statistics
// - Automatic reconnection and failover
// - Integration with system networking
package vpn

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/sasewaddle/clients/native/internal/config"
	"golang.zx2c4.com/wireguard/wgctrl"
	"golang.zx2c4.com/wireguard/wgctrl/wgtypes"
)

// Manager handles WireGuard VPN connections and implements the tray.VPNManager interface
type Manager struct {
	config         *config.Config
	isConnected    bool
	currentStatus  tray.ConnectionStatus
	ctx            context.Context
	cancel         context.CancelFunc
	mutex          sync.RWMutex
	
	// WireGuard interface management
	interfaceName  string
	configPath     string
	
	// Connection monitoring
	monitorTicker  *time.Ticker
	
	// Embedded WireGuard
	embeddedWG     *EmbeddedWireGuard
	useEmbedded    bool
	monitorStop    chan struct{}
}

// NewManager creates a new VPN manager instance
func NewManager(cfg *config.Config) *Manager {
	ctx, cancel := context.WithCancel(context.Background())
	
	// Determine interface name based on platform
	interfaceName := "wg0"
	if runtime.GOOS == "windows" {
		interfaceName = "SASEWaddle"
	}
	
	manager := &Manager{
		config:        cfg,
		ctx:           ctx,
		cancel:        cancel,
		interfaceName: interfaceName,
		configPath:    cfg.GetWireGuardConfigPath(),
		monitorStop:   make(chan struct{}),
		useEmbedded:   true, // Use embedded WireGuard by default
	}
	
	// Initialize embedded WireGuard
	manager.embeddedWG = NewEmbeddedWireGuard(interfaceName)
	
	return manager
}

// Connect establishes a VPN connection
func (m *Manager) Connect() error {
	m.mutex.Lock()
	defer m.mutex.Unlock()
	
	if m.isConnected {
		return fmt.Errorf("already connected")
	}
	
	log.Println("Initiating VPN connection...")
	
	// Validate configuration
	if err := m.validateConfig(); err != nil {
		return fmt.Errorf("invalid configuration: %w", err)
	}
	
	// Establish WireGuard connection
	if err := m.connectWireGuard(); err != nil {
		return fmt.Errorf("failed to establish WireGuard connection: %w", err)
	}
	
	// Update status
	m.isConnected = true
	m.currentStatus = tray.ConnectionStatus{
		Connected:      true,
		ServerName:     m.config.GetServerName(),
		ConnectedSince: time.Now(),
		LocalIP:        m.getLocalIP(),
		ServerIP:       m.config.GetServerIP(),
		PublicKey:      m.config.GetPublicKey(),
	}
	
	// Start monitoring
	m.startMonitoring()
	
	log.Printf("VPN connected successfully to %s", m.currentStatus.ServerName)
	return nil
}

// Disconnect terminates the VPN connection
func (m *Manager) Disconnect() error {
	m.mutex.Lock()
	defer m.mutex.Unlock()
	
	if !m.isConnected {
		return fmt.Errorf("not connected")
	}
	
	log.Println("Disconnecting VPN...")
	
	// Stop monitoring
	m.stopMonitoring()
	
	// Platform-specific disconnection logic
	if err := m.disconnectWireGuard(); err != nil {
		log.Printf("Warning: error during disconnection: %v", err)
	}
	
	// Update status
	m.isConnected = false
	m.currentStatus = tray.ConnectionStatus{
		Connected: false,
	}
	
	log.Println("VPN disconnected successfully")
	return nil
}

// IsConnected returns the current connection status
func (m *Manager) IsConnected() bool {
	m.mutex.RLock()
	defer m.mutex.RUnlock()
	return m.isConnected
}

// GetStatus returns detailed connection status
func (m *Manager) GetStatus() tray.ConnectionStatus {
	m.mutex.RLock()
	defer m.mutex.RUnlock()
	
	if m.isConnected {
		// Update statistics if connected
		stats := m.getInterfaceStatistics()
		m.currentStatus.BytesSent = stats.BytesSent
		m.currentStatus.BytesReceived = stats.BytesReceived
		m.currentStatus.LastHandshake = stats.LastHandshake
	}
	
	return m.currentStatus
}

// Stop gracefully stops the VPN manager
func (m *Manager) Stop() error {
	if m.isConnected {
		if err := m.Disconnect(); err != nil {
			log.Printf("Error disconnecting during stop: %v", err)
		}
	}
	
	m.cancel()
	return nil
}

// Platform-specific WireGuard operations

// connectWireGuard establishes the WireGuard connection
func (m *Manager) connectWireGuard() error {
	if m.useEmbedded {
		return m.connectEmbedded()
	}
	
	// Fallback to platform-specific methods
	switch runtime.GOOS {
	case "linux":
		return m.connectLinux()
	case "darwin":
		return m.connectMacOS()
	case "windows":
		return m.connectWindows()
	default:
		return fmt.Errorf("unsupported platform: %s", runtime.GOOS)
	}
}

// disconnectWireGuard terminates the WireGuard connection
func (m *Manager) disconnectWireGuard() error {
	if m.useEmbedded {
		return m.disconnectEmbedded()
	}
	
	// Fallback to platform-specific methods
	switch runtime.GOOS {
	case "linux":
		return m.disconnectLinux()
	case "darwin":
		return m.disconnectMacOS()
	case "windows":
		return m.disconnectWindows()
	default:
		return fmt.Errorf("unsupported platform: %s", runtime.GOOS)
	}
}

// Embedded WireGuard implementations

func (m *Manager) connectEmbedded() error {
	log.Println("Starting embedded WireGuard tunnel...")

	// Read configuration from file
	configData, err := readWireGuardConfig(m.configPath)
	if err != nil {
		return fmt.Errorf("failed to read WireGuard config: %w", err)
	}

	// Start embedded WireGuard
	if err := m.embeddedWG.Start(string(configData)); err != nil {
		return fmt.Errorf("failed to start embedded WireGuard: %w", err)
	}

	log.Printf("Embedded WireGuard tunnel '%s' started successfully", m.interfaceName)
	return nil
}

func (m *Manager) disconnectEmbedded() error {
	log.Println("Stopping embedded WireGuard tunnel...")

	if err := m.embeddedWG.Stop(); err != nil {
		return fmt.Errorf("failed to stop embedded WireGuard: %w", err)
	}

	log.Printf("Embedded WireGuard tunnel '%s' stopped successfully", m.interfaceName)
	return nil
}

// Linux-specific implementations

func (m *Manager) connectLinux() error {
	// Bring up WireGuard interface
	cmd := exec.Command("sudo", "wg-quick", "up", m.configPath)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("wg-quick up failed: %w, output: %s", err, output)
	}
	
	log.Printf("WireGuard interface brought up: %s", string(output))
	return nil
}

func (m *Manager) disconnectLinux() error {
	// Bring down WireGuard interface
	cmd := exec.Command("sudo", "wg-quick", "down", m.configPath)
	output, err := cmd.CombinedOutput()
	if err != nil {
		// Try alternative method if wg-quick fails
		log.Printf("wg-quick down failed, trying ip link delete: %v", err)
		cmd = exec.Command("sudo", "ip", "link", "delete", m.interfaceName)
		if err2 := cmd.Run(); err2 != nil {
			return fmt.Errorf("both wg-quick down and ip link delete failed: %w, %v", err, err2)
		}
	}
	
	log.Printf("WireGuard interface brought down: %s", string(output))
	return nil
}

// macOS-specific implementations

func (m *Manager) connectMacOS() error {
	// On macOS, we can use wg-quick or integrate with the WireGuard app
	cmd := exec.Command("sudo", "wg-quick", "up", m.configPath)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("wg-quick up failed: %w, output: %s", err, output)
	}
	
	log.Printf("WireGuard interface brought up on macOS: %s", string(output))
	return nil
}

func (m *Manager) disconnectMacOS() error {
	cmd := exec.Command("sudo", "wg-quick", "down", m.configPath)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("wg-quick down failed: %w, output: %s", err, output)
	}
	
	log.Printf("WireGuard interface brought down on macOS: %s", string(output))
	return nil
}

// Windows-specific implementations

func (m *Manager) connectWindows() error {
	// On Windows, we need to use the WireGuard service or wg.exe
	// This is a simplified implementation - production would use the WireGuard Windows API
	cmd := exec.Command("wg-quick", "up", m.configPath)
	output, err := cmd.CombinedOutput()
	if err != nil {
		// Try alternative method using wireguard-go
		return m.connectWindowsFallback()
	}
	
	log.Printf("WireGuard interface brought up on Windows: %s", string(output))
	return nil
}

func (m *Manager) connectWindowsFallback() error {
	// Fallback method for Windows using wireguard-go
	log.Println("Using wireguard-go fallback for Windows connection")
	
	// This would implement wireguard-go integration
	// For now, return an error indicating the limitation
	// Use WireGuard for Windows service
	cmd := exec.Command("wg-quick", "up", configPath)
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to start WireGuard on Windows: %w", err)
	}
	return nil
}

func (m *Manager) disconnectWindows() error {
	cmd := exec.Command("wg-quick", "down", m.configPath)
	output, err := cmd.CombinedOutput()
	if err != nil {
		log.Printf("wg-quick down failed on Windows: %v, output: %s", err, output)
		// Don't return error - Windows connection might not have been established via wg-quick
	}
	
	log.Printf("WireGuard interface brought down on Windows: %s", string(output))
	return nil
}

// Configuration validation

func (m *Manager) validateConfig() error {
	if m.configPath == "" {
		return fmt.Errorf("no WireGuard configuration path specified")
	}
	
	// Check if config file exists and is readable
	if !m.config.FileExists(m.configPath) {
		return fmt.Errorf("WireGuard configuration file not found: %s", m.configPath)
	}
	
	// Validate config content (basic check)
	content, err := m.config.ReadFile(m.configPath)
	if err != nil {
		return fmt.Errorf("cannot read configuration file: %w", err)
	}
	
	configStr := string(content)
	if !strings.Contains(configStr, "[Interface]") || !strings.Contains(configStr, "[Peer]") {
		return fmt.Errorf("invalid WireGuard configuration format")
	}
	
	return nil
}

// Network utilities

func (m *Manager) getLocalIP() string {
	// Try to get the IP address of the WireGuard interface
	iface, err := net.InterfaceByName(m.interfaceName)
	if err != nil {
		return "unknown"
	}
	
	addrs, err := iface.Addrs()
	if err != nil {
		return "unknown"
	}
	
	for _, addr := range addrs {
		if ipnet, ok := addr.(*net.IPNet); ok && !ipnet.IP.IsLoopback() {
			if ipnet.IP.To4() != nil {
				return ipnet.IP.String()
			}
		}
	}
	
	return "unknown"
}

// Statistics and monitoring

type InterfaceStatistics struct {
	BytesSent     uint64
	BytesReceived uint64
	LastHandshake time.Time
}

func (m *Manager) getInterfaceStatistics() InterfaceStatistics {
	stats := InterfaceStatistics{}
	
	// Get statistics using wg command
	cmd := exec.Command("wg", "show", m.interfaceName)
	output, err := cmd.Output()
	if err != nil {
		log.Printf("Failed to get WireGuard statistics: %v", err)
		return stats
	}
	
	// Parse wg output for statistics
	lines := strings.Split(string(output), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if strings.Contains(line, "transfer:") {
			// Parse transfer line: "transfer: 1.23 MiB received, 456.78 KiB sent"
			parts := strings.Fields(line)
			if len(parts) >= 6 {
				// This is a simplified parser - production would be more robust
				if strings.Contains(line, "received") {
					stats.BytesReceived = m.parseTransferAmount(parts[1] + " " + parts[2])
				}
				if strings.Contains(line, "sent") {
					stats.BytesSent = m.parseTransferAmount(parts[4] + " " + parts[5])
				}
			}
		}
		if strings.Contains(line, "latest handshake:") {
			// Parse handshake time
			parts := strings.SplitN(line, ":", 2)
			if len(parts) == 2 {
				timeStr := strings.TrimSpace(parts[1])
				if t, err := time.Parse("2006-01-02 15:04:05", timeStr); err == nil {
					stats.LastHandshake = t
				}
			}
		}
	}
	
	return stats
}

func (m *Manager) parseTransferAmount(amountStr string) uint64 {
	// Parse amounts like "1.23 MiB", "456.78 KiB", etc.
	parts := strings.Fields(amountStr)
	if len(parts) != 2 {
		return 0
	}
	
	var multiplier uint64 = 1
	switch parts[1] {
	case "KiB":
		multiplier = 1024
	case "MiB":
		multiplier = 1024 * 1024
	case "GiB":
		multiplier = 1024 * 1024 * 1024
	}
	
	// Simple parsing - would use proper float parsing in production
	var amount float64
	fmt.Sscanf(parts[0], "%f", &amount)
	
	return uint64(amount * float64(multiplier))
}

// Connection monitoring

func (m *Manager) startMonitoring() {
	m.monitorTicker = time.NewTicker(5 * time.Second)
	
	go func() {
		for {
			select {
			case <-m.ctx.Done():
				return
			case <-m.monitorStop:
				return
			case <-m.monitorTicker.C:
				m.checkConnection()
			}
		}
	}()
}

func (m *Manager) stopMonitoring() {
	if m.monitorTicker != nil {
		m.monitorTicker.Stop()
	}
	
	select {
	case m.monitorStop <- struct{}{}:
	default:
	}
}

func (m *Manager) checkConnection() {
	// Check if the WireGuard interface is still up
	_, err := net.InterfaceByName(m.interfaceName)
	if err != nil {
		log.Printf("WireGuard interface %s not found, marking as disconnected", m.interfaceName)
		m.mutex.Lock()
		m.isConnected = false
		m.currentStatus.Connected = false
		m.mutex.Unlock()
		return
	}
	
	// Additional health checks could be added here:
	// - Ping the server
	// - Check recent handshake time
	// - Verify routing table
	
	// Update last handshake time
	stats := m.getInterfaceStatistics()
	m.mutex.Lock()
	m.currentStatus.LastHandshake = stats.LastHandshake
	m.mutex.Unlock()
}

// Utility functions for VPN management

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func readWireGuardConfig(path string) ([]byte, error) {
	return os.ReadFile(path)
}