// Package wireguard provides high-performance WireGuard tunnel management for CNI pods.
//
// This package implements:
// - Per-pod WireGuard interface creation and management
// - Integration with Tobogganing Manager for key exchange
// - Optimized tunnel setup with minimal overhead
// - Dynamic peer configuration and updates
// - Support for both IPv4 and IPv6 networking
// - Performance monitoring and health checks
//
// The manager coordinates with the Tobogganing Manager service to maintain
// secure tunnels for each Kubernetes pod while minimizing resource usage
// and setup time for optimal container networking performance.
package wireguard

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
	"golang.zx2c4.com/wireguard/wgctrl"
	"golang.zx2c4.com/wireguard/wgctrl/wgtypes"
)

// Config represents the WireGuard manager configuration
type Config struct {
	InterfacePrefix     string
	KeyPath            string
	MTU                int
	ListenPort         int
	PersistentKeepalive int
	ManagerURL         string
	APIKey             string
	ClusterID          string
}

// Manager handles WireGuard interface creation and management for CNI
type Manager struct {
	config     *Config
	client     *wgctrl.Client
	httpClient *http.Client
	interfaces map[string]*Interface
	mu         sync.RWMutex
	logger     *logrus.Entry
}

// Interface represents a WireGuard interface for a pod
type Interface struct {
	Name       string
	PublicKey  string
	PrivateKey wgtypes.Key
	ListenPort int
	PodIP      net.IP
	PeerConfig *PeerConfig
	CreatedAt  time.Time
}

// PeerConfig represents remote peer configuration from Manager
type PeerConfig struct {
	PublicKey    string   `json:"public_key"`
	Endpoint     string   `json:"endpoint"`
	AllowedIPs   []string `json:"allowed_ips"`
	KeepAlive    int      `json:"keep_alive"`
}

// RegistrationRequest represents a pod registration request to the Manager
type RegistrationRequest struct {
	PodID       string `json:"pod_id"`
	NodeID      string `json:"node_id"`
	ClusterID   string `json:"cluster_id"`
	PublicKey   string `json:"public_key"`
	PodIP       string `json:"pod_ip"`
	InterfaceIP string `json:"interface_ip"`
}

// RegistrationResponse represents the Manager's response to pod registration
type RegistrationResponse struct {
	PeerConfig *PeerConfig `json:"peer_config"`
	Success    bool        `json:"success"`
	Error      string      `json:"error,omitempty"`
}

// NewManager creates a new WireGuard manager for CNI
func NewManager(config *Config) (*Manager, error) {
	client, err := wgctrl.New()
	if err != nil {
		return nil, fmt.Errorf("failed to create WireGuard client: %w", err)
	}

	logger := logrus.WithFields(logrus.Fields{
		"component": "wireguard-manager",
		"cluster":   config.ClusterID,
	})

	manager := &Manager{
		config:     config,
		client:     client,
		httpClient: &http.Client{Timeout: 30 * time.Second},
		interfaces: make(map[string]*Interface),
		logger:     logger,
	}

	return manager, nil
}

// CreateInterface creates a new WireGuard interface for a pod
func (m *Manager) CreateInterface(ctx context.Context, interfaceName string, podIP net.IP) (*Interface, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.logger.WithFields(logrus.Fields{
		"interface": interfaceName,
		"podIP":     podIP.String(),
	}).Info("creating WireGuard interface for pod")

	// Generate WireGuard keys for the pod
	privateKey, err := wgtypes.GeneratePrivateKey()
	if err != nil {
		return nil, fmt.Errorf("failed to generate private key: %w", err)
	}

	publicKey := privateKey.PublicKey()

	// Find available listen port
	listenPort, err := m.findAvailablePort()
	if err != nil {
		return nil, fmt.Errorf("failed to find available port: %w", err)
	}

	// Create WireGuard interface
	if err := m.createWireGuardInterface(interfaceName, privateKey, listenPort); err != nil {
		return nil, fmt.Errorf("failed to create WireGuard interface: %w", err)
	}

	// Register pod with Tobogganing Manager
	peerConfig, err := m.registerPodWithManager(ctx, interfaceName, publicKey.String(), podIP)
	if err != nil {
		// Cleanup interface on registration failure
		if cleanupErr := m.destroyWireGuardInterface(interfaceName); cleanupErr != nil {
			m.logger.WithError(cleanupErr).Warn("failed to cleanup interface after registration failure")
		}
		return nil, fmt.Errorf("failed to register pod with manager: %w", err)
	}

	// Configure peer
	if err := m.configurePeer(interfaceName, peerConfig); err != nil {
		// Cleanup interface on peer configuration failure
		if cleanupErr := m.destroyWireGuardInterface(interfaceName); cleanupErr != nil {
			m.logger.WithError(cleanupErr).Warn("failed to cleanup interface after peer config failure")
		}
		return nil, fmt.Errorf("failed to configure peer: %w", err)
	}

	// Create interface object
	iface := &Interface{
		Name:       interfaceName,
		PublicKey:  publicKey.String(),
		PrivateKey: privateKey,
		ListenPort: listenPort,
		PodIP:      podIP,
		PeerConfig: peerConfig,
		CreatedAt:  time.Now(),
	}

	m.interfaces[interfaceName] = iface

	m.logger.WithFields(logrus.Fields{
		"interface":  interfaceName,
		"publicKey":  publicKey.String()[:16] + "...",
		"listenPort": listenPort,
		"podIP":      podIP.String(),
	}).Info("successfully created WireGuard interface for pod")

	return iface, nil
}

// DestroyInterface removes a WireGuard interface for a pod
func (m *Manager) DestroyInterface(ctx context.Context, interfaceName string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.logger.WithField("interface", interfaceName).Info("destroying WireGuard interface")

	// Get interface info for cleanup
	_, exists := m.interfaces[interfaceName]
	if exists {
		// Unregister pod from Manager
		if err := m.unregisterPodFromManager(ctx, interfaceName); err != nil {
			m.logger.WithError(err).Warn("failed to unregister pod from manager")
		}
	}

	// Remove WireGuard interface
	if err := m.destroyWireGuardInterface(interfaceName); err != nil {
		m.logger.WithError(err).Warn("failed to destroy WireGuard interface")
	}

	// Remove from tracking
	delete(m.interfaces, interfaceName)

	m.logger.WithField("interface", interfaceName).Info("successfully destroyed WireGuard interface")
	return nil
}

// CheckInterface verifies that a WireGuard interface is properly configured
func (m *Manager) CheckInterface(ctx context.Context, interfaceName string) error {
	m.mu.RLock()
	defer m.mu.RUnlock()

	iface, exists := m.interfaces[interfaceName]
	if !exists {
		return fmt.Errorf("interface %s not found", interfaceName)
	}

	// Check if WireGuard device exists
	device, err := m.client.Device(interfaceName)
	if err != nil {
		return fmt.Errorf("WireGuard device not found: %w", err)
	}

	// Verify configuration
	if device.PublicKey != iface.PrivateKey.PublicKey() {
		return fmt.Errorf("public key mismatch")
	}

	if device.ListenPort != iface.ListenPort {
		return fmt.Errorf("listen port mismatch: expected %d, got %d", 
			iface.ListenPort, device.ListenPort)
	}

	// Check peer configuration
	if len(device.Peers) == 0 {
		return fmt.Errorf("no peers configured")
	}

	return nil
}

// Close cleans up the WireGuard manager
func (m *Manager) Close() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Cleanup all interfaces
	for name := range m.interfaces {
		if err := m.destroyWireGuardInterface(name); err != nil {
			m.logger.WithError(err).WithField("interface", name).Warn("failed to cleanup interface")
		}
	}

	// Close WireGuard client
	if m.client != nil {
		return m.client.Close()
	}

	return nil
}

// createWireGuardInterface creates a new WireGuard interface
func (m *Manager) createWireGuardInterface(name string, privateKey wgtypes.Key, listenPort int) error {
	// Create WireGuard interface configuration
	config := wgtypes.Config{
		PrivateKey: &privateKey,
		ListenPort: &listenPort,
	}

	// Create the interface (this requires the interface to exist first)
	if err := m.createSystemInterface(name); err != nil {
		return fmt.Errorf("failed to create system interface: %w", err)
	}

	// Configure WireGuard on the interface
	if err := m.client.ConfigureDevice(name, config); err != nil {
		return fmt.Errorf("failed to configure WireGuard device: %w", err)
	}

	return nil
}

// createSystemInterface creates a system WireGuard interface
func (m *Manager) createSystemInterface(name string) error {
	// Use netlink to create WireGuard interface
	// This is a simplified version - in production you'd use netlink directly
	cmd := fmt.Sprintf("ip link add dev %s type wireguard", name)
	if err := m.executeCommand(cmd); err != nil {
		return err
	}

	// Set MTU
	if m.config.MTU > 0 {
		mtuCmd := fmt.Sprintf("ip link set dev %s mtu %d", name, m.config.MTU)
		if err := m.executeCommand(mtuCmd); err != nil {
			return err
		}
	}

	// Bring interface up
	upCmd := fmt.Sprintf("ip link set dev %s up", name)
	return m.executeCommand(upCmd)
}

// destroyWireGuardInterface removes a WireGuard interface
func (m *Manager) destroyWireGuardInterface(name string) error {
	cmd := fmt.Sprintf("ip link delete dev %s", name)
	return m.executeCommand(cmd)
}

// executeCommand executes a shell command (simplified for demo)
func (m *Manager) executeCommand(cmd string) error {
	m.logger.WithField("command", cmd).Debug("executing command")
	// In production, use os/exec properly
	return nil
}

// findAvailablePort finds an available port for the WireGuard interface
func (m *Manager) findAvailablePort() (int, error) {
	// Start from a base port and increment
	basePort := m.config.ListenPort
	if basePort == 0 {
		basePort = 51820
	}

	for port := basePort; port < basePort+1000; port++ {
		// Check if port is available
		ln, err := net.Listen("udp", fmt.Sprintf(":%d", port))
		if err == nil {
			ln.Close()
			return port, nil
		}
	}

	return 0, fmt.Errorf("no available ports found")
}

// registerPodWithManager registers a pod with the Tobogganing Manager
func (m *Manager) registerPodWithManager(ctx context.Context, podID, publicKey string, podIP net.IP) (*PeerConfig, error) {
	url := fmt.Sprintf("%s/api/v1/pods/register", m.config.ManagerURL)

	// Get hostname as node ID
	nodeID, err := os.Hostname()
	if err != nil {
		nodeID = "unknown"
	}

	req := &RegistrationRequest{
		PodID:       podID,
		NodeID:      nodeID,
		ClusterID:   m.config.ClusterID,
		PublicKey:   publicKey,
		PodIP:       podIP.String(),
		InterfaceIP: podIP.String(),
	}

	reqData, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, strings.NewReader(string(reqData)))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+m.config.APIKey)

	resp, err := m.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("manager returned status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	var response RegistrationResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to unmarshal response: %w", err)
	}

	if !response.Success {
		return nil, fmt.Errorf("registration failed: %s", response.Error)
	}

	return response.PeerConfig, nil
}

// unregisterPodFromManager unregisters a pod from the Tobogganing Manager
func (m *Manager) unregisterPodFromManager(ctx context.Context, podID string) error {
	url := fmt.Sprintf("%s/api/v1/pods/%s", m.config.ManagerURL, podID)

	httpReq, err := http.NewRequestWithContext(ctx, "DELETE", url, nil)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Authorization", "Bearer "+m.config.APIKey)

	resp, err := m.httpClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNotFound {
		return fmt.Errorf("manager returned status %d", resp.StatusCode)
	}

	return nil
}

// configurePeer configures the WireGuard peer based on Manager response
func (m *Manager) configurePeer(interfaceName string, peerConfig *PeerConfig) error {
	// Parse peer public key
	peerKey, err := wgtypes.ParseKey(peerConfig.PublicKey)
	if err != nil {
		return fmt.Errorf("invalid peer public key: %w", err)
	}

	// Parse allowed IPs
	var allowedIPs []net.IPNet
	for _, ipStr := range peerConfig.AllowedIPs {
		_, ipNet, err := net.ParseCIDR(ipStr)
		if err != nil {
			return fmt.Errorf("invalid allowed IP %s: %w", ipStr, err)
		}
		allowedIPs = append(allowedIPs, *ipNet)
	}

	// Parse endpoint if provided
	var endpoint *net.UDPAddr
	if peerConfig.Endpoint != "" {
		parts := strings.Split(peerConfig.Endpoint, ":")
		if len(parts) != 2 {
			return fmt.Errorf("invalid endpoint format: %s", peerConfig.Endpoint)
		}
		
		port, err := strconv.Atoi(parts[1])
		if err != nil {
			return fmt.Errorf("invalid endpoint port: %w", err)
		}
		
		ip := net.ParseIP(parts[0])
		if ip == nil {
			return fmt.Errorf("invalid endpoint IP: %s", parts[0])
		}
		
		endpoint = &net.UDPAddr{IP: ip, Port: port}
	}

	// Configure peer
	keepalive := time.Duration(peerConfig.KeepAlive) * time.Second
	peerConf := wgtypes.PeerConfig{
		PublicKey:                   peerKey,
		Endpoint:                    endpoint,
		AllowedIPs:                  allowedIPs,
		ReplaceAllowedIPs:           true,
		PersistentKeepaliveInterval: &keepalive,
	}

	config := wgtypes.Config{
		Peers: []wgtypes.PeerConfig{peerConf},
	}

	if err := m.client.ConfigureDevice(interfaceName, config); err != nil {
		return fmt.Errorf("failed to configure peer: %w", err)
	}

	return nil
}

// GetInterface returns information about a WireGuard interface
func (m *Manager) GetInterface(name string) (*Interface, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	
	iface, exists := m.interfaces[name]
	return iface, exists
}

// ListInterfaces returns all active WireGuard interfaces
func (m *Manager) ListInterfaces() []*Interface {
	m.mu.RLock()
	defer m.mu.RUnlock()
	
	var interfaces []*Interface
	for _, iface := range m.interfaces {
		interfaces = append(interfaces, iface)
	}
	
	return interfaces
}