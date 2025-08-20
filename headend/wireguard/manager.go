// Package wireguard implements WireGuard VPN management for the SASEWaddle headend.
//
// The WireGuard manager provides:
// - VPN interface creation and lifecycle management
// - Peer configuration and key management
// - Dynamic peer addition and removal
// - Integration with Manager service for configuration sync
// - Real-time monitoring of tunnel status and metrics
// - Support for multiple concurrent tunnels
// - Automatic peer cleanup and garbage collection
//
// The manager coordinates with the Manager service to maintain up-to-date
// peer configurations and handles the underlying WireGuard interface
// operations for secure tunnel termination.
package wireguard

import (
    "context"
    "encoding/json"
    "fmt"
    "io/ioutil"
    "net/http"
    "os"
    "os/exec"
    "strings"
    "time"
    
    log "github.com/sirupsen/logrus"
    "golang.zx2c4.com/wireguard/wgctrl"
    "golang.zx2c4.com/wireguard/wgctrl/wgtypes"
)

// Manager handles WireGuard interface configuration and peer management
type Manager struct {
    interfaceName string
    managerURL    string
    client        *wgctrl.Client
    httpClient    *http.Client
    privateKey    wgtypes.Key
    publicKey     wgtypes.Key
    listenPort    int
    network       string
}

// Peer represents a WireGuard peer configuration
type Peer struct {
    NodeID      string `json:"node_id"`
    NodeType    string `json:"node_type"`
    PublicKey   string `json:"public_key"`
    AllowedIPs  string `json:"allowed_ips"`
    Endpoint    string `json:"endpoint,omitempty"`
}

// NewManager creates a new WireGuard manager
func NewManager(interfaceName, managerURL string, listenPort int, network string) (*Manager, error) {
    client, err := wgctrl.New()
    if err != nil {
        return nil, fmt.Errorf("failed to create WireGuard client: %w", err)
    }
    
    manager := &Manager{
        interfaceName: interfaceName,
        managerURL:    managerURL,
        client:        client,
        httpClient: &http.Client{
            Timeout: 30 * time.Second,
        },
        listenPort: listenPort,
        network:    network,
    }
    
    // Generate or load WireGuard keys
    if err := manager.initializeKeys(); err != nil {
        return nil, fmt.Errorf("failed to initialize WireGuard keys: %w", err)
    }
    
    return manager, nil
}

func (m *Manager) initializeKeys() error {
    keyPath := fmt.Sprintf("/etc/wireguard/%s.key", m.interfaceName)
    
    // Try to load existing private key
    if data, err := ioutil.ReadFile(keyPath); err == nil {
        key, err := wgtypes.ParseKey(strings.TrimSpace(string(data)))
        if err == nil {
            m.privateKey = key
            m.publicKey = key.PublicKey()
            log.Infof("Loaded existing WireGuard key for interface %s", m.interfaceName)
            return nil
        }
    }
    
    // Generate new private key
    privateKey, err := wgtypes.GeneratePrivateKey()
    if err != nil {
        return fmt.Errorf("failed to generate private key: %w", err)
    }
    
    m.privateKey = privateKey
    m.publicKey = privateKey.PublicKey()
    
    // Save private key
    if err := os.MkdirAll("/etc/wireguard", 0700); err != nil {
        return fmt.Errorf("failed to create /etc/wireguard directory: %w", err)
    }
    
    if err := ioutil.WriteFile(keyPath, []byte(privateKey.String()), 0600); err != nil {
        return fmt.Errorf("failed to save private key: %w", err)
    }
    
    log.Infof("Generated new WireGuard key for interface %s", m.interfaceName)
    return nil
}

// Initialize sets up the WireGuard interface
func (m *Manager) Initialize() error {
    // Create WireGuard interface if it doesn't exist
    if err := m.createInterface(); err != nil {
        return fmt.Errorf("failed to create WireGuard interface: %w", err)
    }
    
    // Configure the interface
    if err := m.configureInterface(); err != nil {
        return fmt.Errorf("failed to configure WireGuard interface: %w", err)
    }
    
    // Fetch and configure peers from manager
    if err := m.syncPeers(); err != nil {
        log.Warnf("Failed to sync peers: %v", err)
    }
    
    log.Infof("WireGuard interface %s initialized successfully", m.interfaceName)
    return nil
}

func (m *Manager) createInterface() error {
    // Check if interface already exists
    _, err := m.client.Device(m.interfaceName)
    if err == nil {
        return nil // Interface already exists
    }
    
    // Create interface using ip link
    cmd := exec.Command("ip", "link", "add", "dev", m.interfaceName, "type", "wireguard")
    if output, err := cmd.CombinedOutput(); err != nil {
        return fmt.Errorf("failed to create interface: %v, output: %s", err, output)
    }
    
    log.Infof("Created WireGuard interface: %s", m.interfaceName)
    return nil
}

func (m *Manager) configureInterface() error {
    // Set IP address - headend gets the first IP
    // Parse network to get first IP
    // For simplicity, assuming 10.200.0.1 for headend
    headendIP := "10.200.0.1/16"
    
    cmd := exec.Command("ip", "addr", "add", headendIP, "dev", m.interfaceName)
    if output, err := cmd.CombinedOutput(); err != nil {
        // Ignore if address already exists
        if !strings.Contains(string(output), "File exists") {
            return fmt.Errorf("failed to set IP address: %v, output: %s", err, output)
        }
    }
    
    // Bring interface up
    cmd = exec.Command("ip", "link", "set", "up", "dev", m.interfaceName)
    if output, err := cmd.CombinedOutput(); err != nil {
        return fmt.Errorf("failed to bring interface up: %v, output: %s", err, output)
    }
    
    // Configure WireGuard
    config := wgtypes.Config{
        PrivateKey: &m.privateKey,
        ListenPort: &m.listenPort,
    }
    
    if err := m.client.ConfigureDevice(m.interfaceName, config); err != nil {
        return fmt.Errorf("failed to configure WireGuard device: %w", err)
    }
    
    log.Infof("Configured WireGuard interface %s with IP %s", m.interfaceName, headendIP)
    return nil
}

// syncPeers fetches peer configurations from the manager and applies them
func (m *Manager) syncPeers() error {
    peers, err := m.fetchPeersFromManager()
    if err != nil {
        return fmt.Errorf("failed to fetch peers from manager: %w", err)
    }
    
    // Convert peers to WireGuard peer configs
    var wgPeers []wgtypes.PeerConfig
    
    for _, peer := range peers {
        publicKey, err := wgtypes.ParseKey(peer.PublicKey)
        if err != nil {
            log.Errorf("Invalid public key for peer %s: %v", peer.NodeID, err)
            continue
        }
        
        // Parse allowed IPs
        allowedIPs, err := m.parseAllowedIPs(peer.AllowedIPs)
        if err != nil {
            log.Errorf("Invalid allowed IPs for peer %s: %v", peer.NodeID, err)
            continue
        }
        
        peerConfig := wgtypes.PeerConfig{
            PublicKey:  publicKey,
            AllowedIPs: allowedIPs,
            ReplaceAllowedIPs: true,
        }
        
        // Set endpoint if provided
        if peer.Endpoint != "" {
            endpoint, err := wgtypes.ParseEndpoint(peer.Endpoint)
            if err != nil {
                log.Errorf("Invalid endpoint for peer %s: %v", peer.NodeID, err)
            } else {
                peerConfig.Endpoint = &endpoint
            }
        }
        
        wgPeers = append(wgPeers, peerConfig)
    }
    
    // Apply peer configuration
    config := wgtypes.Config{
        Peers: wgPeers,
        ReplacePeers: true,
    }
    
    if err := m.client.ConfigureDevice(m.interfaceName, config); err != nil {
        return fmt.Errorf("failed to configure peers: %w", err)
    }
    
    log.Infof("Synchronized %d WireGuard peers", len(wgPeers))
    return nil
}

func (m *Manager) fetchPeersFromManager() ([]Peer, error) {
    url := m.managerURL + "/api/v1/wireguard/peers"
    
    req, err := http.NewRequest("GET", url, nil)
    if err != nil {
        return nil, fmt.Errorf("failed to create request: %w", err)
    }
    
    // Add authentication header (would be cluster API key in practice)
    req.Header.Set("Authorization", "Bearer "+os.Getenv("CLUSTER_API_KEY"))
    
    resp, err := m.httpClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("failed to fetch peers: %w", err)
    }
    defer resp.Body.Close()
    
    if resp.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("manager returned status %d", resp.StatusCode)
    }
    
    body, err := ioutil.ReadAll(resp.Body)
    if err != nil {
        return nil, fmt.Errorf("failed to read response: %w", err)
    }
    
    var response struct {
        Peers []Peer `json:"peers"`
        Total int    `json:"total"`
    }
    
    if err := json.Unmarshal(body, &response); err != nil {
        return nil, fmt.Errorf("failed to parse response: %w", err)
    }
    
    return response.Peers, nil
}

func (m *Manager) parseAllowedIPs(allowedIPsStr string) ([]wgtypes.IPNet, error) {
    var allowedIPs []wgtypes.IPNet
    
    for _, ipStr := range strings.Split(allowedIPsStr, ",") {
        ipStr = strings.TrimSpace(ipStr)
        if ipStr == "" {
            continue
        }
        
        ipNet, err := wgtypes.ParseIPNet(ipStr)
        if err != nil {
            return nil, fmt.Errorf("invalid IP network %s: %w", ipStr, err)
        }
        
        allowedIPs = append(allowedIPs, ipNet)
    }
    
    return allowedIPs, nil
}

// StartPeriodicSync starts a background goroutine to periodically sync peers
func (m *Manager) StartPeriodicSync(ctx context.Context) {
    go func() {
        ticker := time.NewTicker(5 * time.Minute)
        defer ticker.Stop()
        
        for {
            select {
            case <-ctx.Done():
                log.Info("Stopping WireGuard peer sync")
                return
            case <-ticker.C:
                if err := m.syncPeers(); err != nil {
                    log.Errorf("Failed to sync WireGuard peers: %v", err)
                }
            }
        }
    }()
}

// GetStats returns WireGuard interface statistics
func (m *Manager) GetStats() (*wgtypes.Device, error) {
    return m.client.Device(m.interfaceName)
}

// Close closes the WireGuard client
func (m *Manager) Close() error {
    if m.client != nil {
        return m.client.Close()
    }
    return nil
}

// GetPublicKey returns the headend's public key
func (m *Manager) GetPublicKey() string {
    return m.publicKey.String()
}