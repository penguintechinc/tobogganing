// Package config implements configuration management for the SASEWaddle headend.
//
// The config manager provides:
// - Centralized configuration retrieval from Manager service
// - Real-time configuration updates and synchronization
// - Configuration caching and validation
// - Environment variable and file-based configuration fallbacks
// - Hot reloading of configuration changes without restart
// - Structured configuration parsing and validation
//
// The manager maintains current headend configuration including
// authentication settings, proxy parameters, firewall rules,
// and operational settings received from the central Manager service.
package config

import (
    "encoding/json"
    "fmt"
    "io/ioutil"
    "net/http"
    "os"
    "time"
    
    log "github.com/sirupsen/logrus"
)

// Manager handles configuration retrieval from SASEWaddle Manager Service
type Manager struct {
    managerURL   string
    apiKey       string
    httpClient   *http.Client
    lastUpdate   time.Time
    config       *HeadendConfig
}

// HeadendConfig represents the complete configuration for a headend server
type HeadendConfig struct {
    // Server configuration
    HTTPPort     string            `json:"http_port"`
    TCPPort      string            `json:"tcp_port"`
    UDPPort      string            `json:"udp_port"`
    MetricsPort  string            `json:"metrics_port"`
    CertFile     string            `json:"cert_file"`
    KeyFile      string            `json:"key_file"`
    
    // Authentication configuration
    Auth         AuthConfig        `json:"auth"`
    
    // WireGuard configuration
    WireGuard    WireGuardConfig   `json:"wireguard"`
    
    // Traffic mirroring configuration
    Mirror       MirrorConfig      `json:"mirror"`
    
    // Proxy configuration
    Proxy        ProxyConfig       `json:"proxy"`
}

// AuthConfig contains authentication provider settings
type AuthConfig struct {
    Type         string            `json:"type"`          // jwt, oauth2, saml2
    ManagerURL   string            `json:"manager_url"`
    JWTPublicKey string            `json:"jwt_public_key"`
    
    // OAuth2 settings
    OAuth2       OAuth2Config      `json:"oauth2,omitempty"`
    
    // SAML2 settings  
    SAML2        SAML2Config       `json:"saml2,omitempty"`
}

type OAuth2Config struct {
    Issuer       string            `json:"issuer"`
    ClientID     string            `json:"client_id"`
    ClientSecret string            `json:"client_secret"`
    RedirectURL  string            `json:"redirect_url"`
}

type SAML2Config struct {
    IDPMetadataURL string          `json:"idp_metadata_url"`
    SPEntityID     string          `json:"sp_entity_id"`
    SSOURL         string          `json:"sso_url"`
    SLOUrl         string          `json:"slo_url"`
}

// WireGuardConfig contains WireGuard interface settings
type WireGuardConfig struct {
    Interface    string            `json:"interface"`
    PrivateKey   string            `json:"private_key"`
    PublicKey    string            `json:"public_key"`
    ListenPort   int               `json:"listen_port"`
    Network      string            `json:"network"`
    IPAddress    string            `json:"ip_address"`
    Peers        []WireGuardPeer   `json:"peers"`
}

type WireGuardPeer struct {
    NodeID       string            `json:"node_id"`
    NodeType     string            `json:"node_type"`
    PublicKey    string            `json:"public_key"`
    AllowedIPs   string            `json:"allowed_ips"`
    Endpoint     string            `json:"endpoint,omitempty"`
}

// MirrorConfig contains traffic mirroring settings
type MirrorConfig struct {
    Enabled      bool              `json:"enabled"`
    Destinations []string          `json:"destinations"`
    Protocol     string            `json:"protocol"`
    BufferSize   int               `json:"buffer_size"`
    SampleRate   int               `json:"sample_rate"`
    Filter       string            `json:"filter,omitempty"`
}

// ProxyConfig contains proxy behavior settings
type ProxyConfig struct {
    SkipTLSVerify bool             `json:"skip_tls_verify"`
    Timeout       int              `json:"timeout_seconds"`
    MaxIdleConns  int              `json:"max_idle_conns"`
}

// NewManager creates a new configuration manager
func NewManager(managerURL, apiKey string) *Manager {
    return &Manager{
        managerURL: managerURL,
        apiKey:     apiKey,
        httpClient: &http.Client{
            Timeout: 30 * time.Second,
        },
    }
}

// FetchConfig retrieves the headend configuration from the Manager Service
func (cm *Manager) FetchConfig() (*HeadendConfig, error) {
    clusterID := os.Getenv("CLUSTER_ID")
    if clusterID == "" {
        return nil, fmt.Errorf("CLUSTER_ID environment variable not set")
    }
    
    url := fmt.Sprintf("%s/api/v1/clusters/%s/headend-config", cm.managerURL, clusterID)
    
    req, err := http.NewRequest("GET", url, nil)
    if err != nil {
        return nil, fmt.Errorf("failed to create request: %w", err)
    }
    
    // Authenticate with cluster API key
    req.Header.Set("Authorization", "Bearer "+cm.apiKey)
    req.Header.Set("Content-Type", "application/json")
    
    resp, err := cm.httpClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("failed to fetch config: %w", err)
    }
    defer resp.Body.Close()
    
    if resp.StatusCode != http.StatusOK {
        body, _ := ioutil.ReadAll(resp.Body)
        return nil, fmt.Errorf("manager returned status %d: %s", resp.StatusCode, string(body))
    }
    
    body, err := ioutil.ReadAll(resp.Body)
    if err != nil {
        return nil, fmt.Errorf("failed to read response: %w", err)
    }
    
    var config HeadendConfig
    if err := json.Unmarshal(body, &config); err != nil {
        return nil, fmt.Errorf("failed to parse config: %w", err)
    }
    
    // Apply environment variable overrides
    cm.applyEnvOverrides(&config)
    
    cm.config = &config
    cm.lastUpdate = time.Now()
    
    log.Infof("Successfully fetched headend configuration from manager")
    return &config, nil
}

// applyEnvOverrides allows environment variables to override config values
func (cm *Manager) applyEnvOverrides(config *HeadendConfig) {
    if val := os.Getenv("HEADEND_HTTP_PORT"); val != "" {
        config.HTTPPort = val
    }
    if val := os.Getenv("HEADEND_TCP_PORT"); val != "" {
        config.TCPPort = val
    }
    if val := os.Getenv("HEADEND_UDP_PORT"); val != "" {
        config.UDPPort = val
    }
    if val := os.Getenv("HEADEND_AUTH_TYPE"); val != "" {
        config.Auth.Type = val
    }
    if val := os.Getenv("HEADEND_MIRROR_ENABLED"); val == "true" {
        config.Mirror.Enabled = true
    } else if val == "false" {
        config.Mirror.Enabled = false
    }
    
    // Add more overrides as needed
    log.Debug("Applied environment variable overrides to configuration")
}

// GetConfig returns the current configuration (fetches if not cached)
func (cm *Manager) GetConfig() (*HeadendConfig, error) {
    if cm.config == nil || time.Since(cm.lastUpdate) > 5*time.Minute {
        return cm.FetchConfig()
    }
    return cm.config, nil
}

// RefreshConfig forces a configuration refresh from the manager
func (cm *Manager) RefreshConfig() (*HeadendConfig, error) {
    log.Info("Refreshing headend configuration from manager")
    return cm.FetchConfig()
}

// WatchConfig starts a background goroutine to periodically refresh configuration
func (cm *Manager) WatchConfig(refreshInterval time.Duration) {
    go func() {
        ticker := time.NewTicker(refreshInterval)
        defer ticker.Stop()
        
        for {
            select {
            case <-ticker.C:
                if _, err := cm.RefreshConfig(); err != nil {
                    log.Errorf("Failed to refresh config: %v", err)
                } else {
                    log.Debug("Configuration refreshed successfully")
                }
            }
        }
    }()
    
    log.Infof("Started configuration watcher with %v refresh interval", refreshInterval)
}

// ValidateConfig performs basic validation on the configuration
func (cm *Manager) ValidateConfig(config *HeadendConfig) error {
    if config.HTTPPort == "" {
        return fmt.Errorf("HTTP port not specified")
    }
    if config.Auth.Type == "" {
        return fmt.Errorf("authentication type not specified")
    }
    if config.Auth.Type == "jwt" && config.Auth.ManagerURL == "" {
        return fmt.Errorf("manager URL required for JWT authentication")
    }
    if config.WireGuard.Interface == "" {
        return fmt.Errorf("WireGuard interface not specified")
    }
    if config.WireGuard.ListenPort == 0 {
        return fmt.Errorf("WireGuard listen port not specified")
    }
    
    return nil
}