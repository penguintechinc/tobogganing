package ports

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	log "github.com/sirupsen/logrus"
)

// PortConfig represents the port configuration received from the Manager
type PortConfig struct {
	HeadendID        string    `json:"headend_id"`
	ClusterID        string    `json:"cluster_id"`
	TCPRanges        string    `json:"tcp_ranges"`
	UDPRanges        string    `json:"udp_ranges"`
	TCPRangesDetail  []PortRange `json:"tcp_ranges_detail"`
	UDPRangesDetail  []PortRange `json:"udp_ranges_detail"`
	UpdatedAt        string    `json:"updated_at"`
}

// PortRange represents a detailed port range from the Manager
type PortRange struct {
	ID          string `json:"id"`
	StartPort   int    `json:"start_port"`
	EndPort     int    `json:"end_port"`
	Protocol    string `json:"protocol"`
	Description string `json:"description"`
	Enabled     bool   `json:"enabled"`
	CreatedAt   string `json:"created_at"`
	UpdatedAt   string `json:"updated_at"`
}

// ConfigClient fetches port configuration from the Manager service
type ConfigClient struct {
	managerURL  string
	authToken   string
	headendID   string
	clusterID   string
	httpClient  *http.Client
}

// NewConfigClient creates a new configuration client
func NewConfigClient(managerURL, authToken, headendID, clusterID string) *ConfigClient {
	return &ConfigClient{
		managerURL: managerURL,
		authToken:  authToken,
		headendID:  headendID,
		clusterID:  clusterID,
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

// FetchConfig retrieves the current port configuration from the Manager
func (c *ConfigClient) FetchConfig() (*PortConfig, error) {
	url := fmt.Sprintf("%s/api/v1/headend/%s/ports?cluster_id=%s", c.managerURL, c.headendID, c.clusterID)
	
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	
	req.Header.Set("Authorization", "Bearer "+c.authToken)
	req.Header.Set("User-Agent", "SASEWaddle-Headend/1.0")
	
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch config: %w", err)
	}
	defer func() {
		if err := resp.Body.Close(); err != nil {
			log.Debugf("Error closing response body: %v", err)
		}
	}()
	
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("failed to fetch config: status %d, body: %s", resp.StatusCode, string(body))
	}
	
	var config PortConfig
	if err := json.NewDecoder(resp.Body).Decode(&config); err != nil {
		return nil, fmt.Errorf("failed to decode config response: %w", err)
	}
	
	log.Debugf("Fetched port configuration: TCP=%s, UDP=%s", config.TCPRanges, config.UDPRanges)
	return &config, nil
}

// ValidateConfig checks if the configuration is valid
func (c *ConfigClient) ValidateConfig(config *PortConfig) error {
	if config.HeadendID != c.headendID {
		return fmt.Errorf("headend ID mismatch: expected %s, got %s", c.headendID, config.HeadendID)
	}
	
	// Basic validation
	if config.TCPRanges == "" && config.UDPRanges == "" {
		return fmt.Errorf("no port ranges configured")
	}
	
	return nil
}