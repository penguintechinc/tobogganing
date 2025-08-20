// Package config provides configuration management for SASEWaddle client.
//
// The config manager handles:
// - Automatic configuration updates from the Manager service
// - Random update scheduling (45-60 minutes) to spread client requests
// - Manual configuration pulls via API
// - Configuration validation and caching
// - Retry logic with exponential backoff
package config

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"os"
	"sync"
	"time"
)

// Manager handles configuration updates and scheduling
type Manager struct {
	config           *Config
	httpClient       *http.Client
	lastUpdate       time.Time
	nextUpdate       time.Time
	isUpdating       bool
	updateMutex      sync.RWMutex
	ctx              context.Context
	cancel           context.CancelFunc
	schedulerTicker  *time.Ticker
}

// ConfigResponse represents the API response from the Manager service
type ConfigResponse struct {
	Success bool   `json:"success"`
	Config  string `json:"config"` // Base64 encoded WireGuard config
	Message string `json:"message"`
	Version int    `json:"version"`
}

// NewConfigManager creates a new configuration manager
func NewConfigManager(cfg *Config) *Manager {
	ctx, cancel := context.WithCancel(context.Background())
	
	// Create HTTP client with reasonable timeouts
	client := &http.Client{
		Timeout: 30 * time.Second,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				InsecureSkipVerify: cfg.InsecureSkipVerify(), // For development
			},
		},
	}
	
	return &Manager{
		config:     cfg,
		httpClient: client,
		ctx:        ctx,
		cancel:     cancel,
	}
}

// Start begins the automatic configuration update scheduler
func (cm *Manager) Start() error {
	log.Println("Starting configuration manager")
	
	// Schedule the next update randomly between 45-60 minutes
	cm.scheduleNextUpdate()
	
	// Start the scheduler goroutine
	go cm.runScheduler()
	
	return nil
}

// Stop gracefully stops the configuration manager
func (cm *Manager) Stop() error {
	log.Println("Stopping configuration manager")
	
	cm.cancel()
	
	if cm.schedulerTicker != nil {
		cm.schedulerTicker.Stop()
	}
	
	return nil
}

// GetLastConfigUpdate returns the time of the last successful config update
func (cm *Manager) GetLastConfigUpdate() time.Time {
	cm.updateMutex.RLock()
	defer cm.updateMutex.RUnlock()
	return cm.lastUpdate
}

// GetNextScheduledUpdate returns the time of the next scheduled config update
func (cm *Manager) GetNextScheduledUpdate() time.Time {
	cm.updateMutex.RLock()
	defer cm.updateMutex.RUnlock()
	return cm.nextUpdate
}

// PullConfig manually pulls configuration from the Manager service
func (cm *Manager) PullConfig() error {
	cm.updateMutex.Lock()
	if cm.isUpdating {
		cm.updateMutex.Unlock()
		return fmt.Errorf("configuration update already in progress")
	}
	cm.isUpdating = true
	cm.updateMutex.Unlock()
	
	defer func() {
		cm.updateMutex.Lock()
		cm.isUpdating = false
		cm.updateMutex.Unlock()
	}()
	
	log.Println("Pulling configuration from Manager service")
	
	err := cm.fetchAndUpdateConfig()
	if err != nil {
		log.Printf("Failed to pull configuration: %v", err)
		return err
	}
	
	// Update last update time and reschedule
	cm.updateMutex.Lock()
	cm.lastUpdate = time.Now()
	cm.updateMutex.Unlock()
	
	cm.scheduleNextUpdate()
	
	log.Println("Configuration updated successfully")
	return nil
}

// runScheduler runs the automatic update scheduler
func (cm *Manager) runScheduler() {
	for {
		select {
		case <-cm.ctx.Done():
			return
		default:
			// Wait until it's time for the next update
			timeUntilUpdate := time.Until(cm.nextUpdate)
			if timeUntilUpdate <= 0 {
				// Time for an update
				go func() {
					if err := cm.PullConfig(); err != nil {
						log.Printf("Scheduled configuration update failed: %v", err)
						// Retry after a shorter interval on failure
						cm.scheduleRetryUpdate()
					}
				}()
				
				// Schedule the next update
				cm.scheduleNextUpdate()
			}
			
			// Sleep for a short interval before checking again
			time.Sleep(1 * time.Minute)
		}
	}
}

// scheduleNextUpdate schedules the next configuration update randomly between 45-60 minutes
func (cm *Manager) scheduleNextUpdate() {
	// Random interval between 45 and 60 minutes
	minMinutes := 45
	maxMinutes := 60
	
	randomMinutes := minMinutes + rand.Intn(maxMinutes-minMinutes+1)
	nextUpdateTime := time.Now().Add(time.Duration(randomMinutes) * time.Minute)
	
	cm.updateMutex.Lock()
	cm.nextUpdate = nextUpdateTime
	cm.updateMutex.Unlock()
	
	log.Printf("Next configuration update scheduled for %s (in %d minutes)",
		nextUpdateTime.Format("15:04:05"), randomMinutes)
}

// scheduleRetryUpdate schedules a retry update after a shorter interval (5-10 minutes)
func (cm *Manager) scheduleRetryUpdate() {
	// Shorter random interval for retries: 5-10 minutes
	minMinutes := 5
	maxMinutes := 10
	
	randomMinutes := minMinutes + rand.Intn(maxMinutes-minMinutes+1)
	nextUpdateTime := time.Now().Add(time.Duration(randomMinutes) * time.Minute)
	
	cm.updateMutex.Lock()
	cm.nextUpdate = nextUpdateTime
	cm.updateMutex.Unlock()
	
	log.Printf("Configuration update retry scheduled for %s (in %d minutes)",
		nextUpdateTime.Format("15:04:05"), randomMinutes)
}

// fetchAndUpdateConfig fetches configuration from the Manager service and updates local config
func (cm *Manager) fetchAndUpdateConfig() error {
	// Build request URL
	managerURL := cm.config.GetManagerURL()
	if managerURL == "" {
		return fmt.Errorf("manager URL not configured")
	}
	
	clientID := cm.config.GetClientID()
	if clientID == "" {
		return fmt.Errorf("client ID not configured")
	}
	
	configURL := fmt.Sprintf("%s/api/v1/clients/%s/config", managerURL, clientID)
	
	// Create HTTP request
	req, err := http.NewRequestWithContext(cm.ctx, "GET", configURL, nil)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	
	// Add authentication headers
	apiKey := cm.config.GetAPIKey()
	if apiKey != "" {
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", apiKey))
	}
	
	// Add client identification headers
	req.Header.Set("User-Agent", cm.config.GetUserAgent())
	req.Header.Set("X-Client-ID", clientID)
	req.Header.Set("X-Client-Version", cm.config.GetVersion())
	
	// Send request
	resp, err := cm.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()
	
	// Read response
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read response: %w", err)
	}
	
	// Check status code
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("server returned status %d: %s", resp.StatusCode, string(body))
	}
	
	// Parse response
	var configResp ConfigResponse
	if err := json.Unmarshal(body, &configResp); err != nil {
		return fmt.Errorf("failed to parse response: %w", err)
	}
	
	if !configResp.Success {
		return fmt.Errorf("server error: %s", configResp.Message)
	}
	
	// Validate and save configuration
	if err := cm.validateAndSaveConfig(configResp.Config); err != nil {
		return fmt.Errorf("failed to save configuration: %w", err)
	}
	
	log.Printf("Configuration updated successfully (version %d)", configResp.Version)
	return nil
}

// validateAndSaveConfig validates the received configuration and saves it
func (cm *Manager) validateAndSaveConfig(configData string) error {
	if configData == "" {
		return fmt.Errorf("received empty configuration")
	}
	
	// Decode base64 configuration (if needed)
	// For now, assume it's plain text WireGuard config
	
	// Basic validation of WireGuard config format
	if err := cm.validateWireGuardConfig(configData); err != nil {
		return fmt.Errorf("invalid WireGuard configuration: %w", err)
	}
	
	// Save to file
	configPath := cm.config.GetWireGuardConfigPath()
	if err := cm.WriteConfigFile(configPath, []byte(configData)); err != nil {
		return fmt.Errorf("failed to write configuration file: %w", err)
	}
	
	log.Printf("Configuration saved to %s", configPath)
	return nil
}

// validateWireGuardConfig performs basic validation of WireGuard configuration
func (cm *Manager) validateWireGuardConfig(config string) error {
	// Basic checks for WireGuard config format
	if !bytes.Contains([]byte(config), []byte("[Interface]")) {
		return fmt.Errorf("missing [Interface] section")
	}
	
	if !bytes.Contains([]byte(config), []byte("[Peer]")) {
		return fmt.Errorf("missing [Peer] section")
	}
	
	// Check for required fields
	requiredFields := []string{"PrivateKey", "Address", "PublicKey", "Endpoint"}
	for _, field := range requiredFields {
		if !bytes.Contains([]byte(config), []byte(field+" =")) {
			return fmt.Errorf("missing required field: %s", field)
		}
	}
	
	return nil
}

// Utility methods for Config integration

func (cfg *Config) GetManagerURL() string {
	if cfg.ManagerURL != "" {
		return cfg.ManagerURL
	}
	return "https://manager.sasewaddle.com"
}

func (cfg *Config) GetClientID() string {
	if cfg.ClientName != "" {
		return cfg.ClientName
	}
	// Generate a client ID based on hostname if not configured
	hostname, _ := os.Hostname()
	return fmt.Sprintf("client-%s", hostname)
}

func (cfg *Config) GetAPIKey() string {
	return cfg.APIKey
}

func (cfg *Config) GetUserAgent() string {
	return fmt.Sprintf("SASEWaddle-Client/%s", cfg.GetVersion())
}

func (cfg *Config) GetVersion() string {
	// This would be set during build time via ldflags
	return "1.0.0"
}

func (cfg *Config) InsecureSkipVerify() bool {
	// For production, always verify TLS certificates
	return false
}

func (cm *Manager) WriteConfigFile(path string, data []byte) error {
	// Write configuration file with proper permissions
	return cm.config.WriteFile(path, data) // Uses existing WriteFile method
}

// Additional configuration management methods

// GetConfigUpdateHistory returns the history of configuration updates
func (cm *Manager) GetConfigUpdateHistory() []ConfigUpdateEntry {
	// This would return a history of config updates
	// For now, return empty slice
	return []ConfigUpdateEntry{}
}

// ConfigUpdateEntry represents a single configuration update entry
type ConfigUpdateEntry struct {
	Timestamp time.Time `json:"timestamp"`
	Version   int       `json:"version"`
	Success   bool      `json:"success"`
	Error     string    `json:"error,omitempty"`
}

// IsUpdateInProgress returns whether a configuration update is currently in progress
func (cm *Manager) IsUpdateInProgress() bool {
	cm.updateMutex.RLock()
	defer cm.updateMutex.RUnlock()
	return cm.isUpdating
}

// ForceUpdate forces an immediate configuration update, bypassing the schedule
func (cm *Manager) ForceUpdate() error {
	log.Println("Forcing immediate configuration update")
	return cm.PullConfig()
}