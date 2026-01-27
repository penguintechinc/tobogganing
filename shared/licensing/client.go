package licensing

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"time"
)

// Client represents a PenguinTech License Server client
type Client struct {
	LicenseKey string
	Product    string
	BaseURL    string
	ServerID   string
	HTTPClient *http.Client
}

// ValidationResponse represents the license validation response
type ValidationResponse struct {
	Valid        bool      `json:"valid"`
	Message      string    `json:"message,omitempty"`
	Customer     string    `json:"customer"`
	Product      string    `json:"product"`
	LicenseKey   string    `json:"license_key"`
	ExpiresAt    time.Time `json:"expires_at"`
	IssuedAt     time.Time `json:"issued_at"`
	Tier         string    `json:"tier"`
	Features     []Feature `json:"features"`
	Limits       Limits    `json:"limits"`
	Metadata     Metadata  `json:"metadata"`
}

// Feature represents a license feature
type Feature struct {
	Name        string      `json:"name"`
	Entitled    bool        `json:"entitled"`
	Units       int         `json:"units"`
	Description string      `json:"description"`
	Metadata    interface{} `json:"metadata"`
}

// Limits represents license limits
type Limits struct {
	MaxServers         int `json:"max_servers"`
	MaxUsers           int `json:"max_users"`
	DataRetentionDays  int `json:"data_retention_days"`
}

// Metadata represents license metadata
type Metadata struct {
	ServerID     string                 `json:"server_id"`
	SupportTier  string                 `json:"support_tier"`
	CustomFields map[string]interface{} `json:"custom_fields"`
}

// FeatureResponse represents the feature check response
type FeatureResponse struct {
	Valid    bool      `json:"valid"`
	Customer string    `json:"customer"`
	Product  string    `json:"product"`
	Features []Feature `json:"features"`
	Metadata Metadata  `json:"metadata"`
}

// NewClient creates a new license client
func NewClient(licenseKey, product string) *Client {
	baseURL := os.Getenv("LICENSE_SERVER_URL")
	if baseURL == "" {
		baseURL = "https://license.penguintech.io"
	}

	return &Client{
		LicenseKey: licenseKey,
		Product:    product,
		BaseURL:    baseURL,
		HTTPClient: &http.Client{Timeout: 30 * time.Second},
	}
}

// NewClientFromEnv creates a new license client from environment variables
func NewClientFromEnv() *Client {
	licenseKey := os.Getenv("LICENSE_KEY")
	product := os.Getenv("PRODUCT_NAME")

	if licenseKey == "" || product == "" {
		return nil
	}

	return NewClient(licenseKey, product)
}

// Validate validates the license and stores server ID for keepalives
func (c *Client) Validate() (*ValidationResponse, error) {
	payload := map[string]string{"product": c.Product}

	resp, err := c.makeRequest("POST", "/api/v2/validate", payload)
	if err != nil {
		return nil, fmt.Errorf("license validation request failed: %w", err)
	}

	var validation ValidationResponse
	if err := json.Unmarshal(resp, &validation); err != nil {
		return nil, fmt.Errorf("failed to parse validation response: %w", err)
	}

	if validation.Valid {
		c.ServerID = validation.Metadata.ServerID
	}

	return &validation, nil
}

// CheckFeature checks if a specific feature is enabled
func (c *Client) CheckFeature(feature string) (bool, error) {
	payload := map[string]string{
		"product": c.Product,
		"feature": feature,
	}

	resp, err := c.makeRequest("POST", "/api/v2/features", payload)
	if err != nil {
		return false, fmt.Errorf("feature check request failed: %w", err)
	}

	var response FeatureResponse
	if err := json.Unmarshal(resp, &response); err != nil {
		return false, fmt.Errorf("failed to parse feature response: %w", err)
	}

	if len(response.Features) > 0 {
		return response.Features[0].Entitled, nil
	}

	return false, nil
}

// Keepalive sends keepalive with optional usage statistics
func (c *Client) Keepalive(usageData map[string]interface{}) error {
	if c.ServerID == "" {
		// Validate first to get server ID
		_, err := c.Validate()
		if err != nil {
			return fmt.Errorf("failed to validate license for keepalive: %w", err)
		}
	}

	payload := map[string]interface{}{
		"product":   c.Product,
		"server_id": c.ServerID,
	}

	// Add usage data if provided
	for key, value := range usageData {
		payload[key] = value
	}

	_, err := c.makeRequest("POST", "/api/v2/keepalive", payload)
	if err != nil {
		return fmt.Errorf("keepalive request failed: %w", err)
	}

	return nil
}

// makeRequest makes an HTTP request to the license server
func (c *Client) makeRequest(method, endpoint string, payload interface{}) ([]byte, error) {
	jsonData, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal payload: %w", err)
	}

	req, err := http.NewRequest(method, c.BaseURL+endpoint, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", "Bearer "+c.LicenseKey)
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	var buf bytes.Buffer
	_, err = buf.ReadFrom(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API request failed with status %d: %s", resp.StatusCode, buf.String())
	}

	return buf.Bytes(), nil
}

// IsValidLicenseKey validates the license key format
func IsValidLicenseKey(key string) bool {
	// Basic format validation: PENG-XXXX-XXXX-XXXX-XXXX-ABCD
	if len(key) != 29 {
		return false
	}

	if key[:5] != "PENG-" {
		return false
	}

	// Count dashes - should be 5 total
	dashCount := 0
	for _, char := range key {
		if char == '-' {
			dashCount++
		}
	}

	return dashCount == 5
}