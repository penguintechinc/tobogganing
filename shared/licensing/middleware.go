package licensing

import (
	"errors"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
)

// FeatureGate manages feature access based on license
type FeatureGate struct {
	client       *Client
	features     map[string]bool
	lastUpdate   time.Time
	cacheTTL     time.Duration
	mutex        sync.RWMutex
}

// NewFeatureGate creates a new feature gate
func NewFeatureGate(client *Client) *FeatureGate {
	fg := &FeatureGate{
		client:   client,
		features: make(map[string]bool),
		cacheTTL: 5 * time.Minute,
	}

	// Initialize features cache
	fg.refreshFeatures()

	return fg
}

// RequireFeature is a Gin middleware that requires a specific feature
func (fg *FeatureGate) RequireFeature(featureName string) gin.HandlerFunc {
	return func(c *gin.Context) {
		if !fg.HasFeature(featureName) {
			c.JSON(http.StatusForbidden, gin.H{
				"error":   "feature_not_available",
				"message": "This feature requires a license upgrade",
				"feature": featureName,
			})
			c.Abort()
			return
		}
		c.Next()
	}
}

// HasFeature checks if a feature is available
func (fg *FeatureGate) HasFeature(featureName string) bool {
	fg.mutex.RLock()

	// Check if cache is stale
	if time.Since(fg.lastUpdate) > fg.cacheTTL {
		fg.mutex.RUnlock()
		fg.refreshFeatures()
		fg.mutex.RLock()
	}

	enabled, exists := fg.features[featureName]
	fg.mutex.RUnlock()

	if !exists {
		// Feature not in cache, check directly
		enabled, err := fg.client.CheckFeature(featureName)
		if err != nil {
			log.Printf("Failed to check feature %s: %v", featureName, err)
			return false
		}

		// Update cache
		fg.mutex.Lock()
		fg.features[featureName] = enabled
		fg.mutex.Unlock()

		return enabled
	}

	return enabled
}

// refreshFeatures refreshes the features cache
func (fg *FeatureGate) refreshFeatures() {
	validation, err := fg.client.Validate()
	if err != nil {
		log.Printf("Failed to refresh license features: %v", err)
		return
	}

	if !validation.Valid {
		log.Printf("License validation failed: %s", validation.Message)
		return
	}

	fg.mutex.Lock()
	defer fg.mutex.Unlock()

	// Clear existing features
	fg.features = make(map[string]bool)

	// Update with current features
	for _, feature := range validation.Features {
		fg.features[feature.Name] = feature.Entitled
	}

	fg.lastUpdate = time.Now()
}

// GetAllFeatures returns all available features
func (fg *FeatureGate) GetAllFeatures() map[string]bool {
	fg.mutex.RLock()
	defer fg.mutex.RUnlock()

	// Return a copy to prevent external modification
	features := make(map[string]bool)
	for k, v := range fg.features {
		features[k] = v
	}

	return features
}

// FeatureNotAvailableError represents a feature not available error
type FeatureNotAvailableError struct {
	Feature string
}

func (e FeatureNotAvailableError) Error() string {
	return "feature '" + e.Feature + "' requires license upgrade"
}

// RequireFeatureFunc returns a function that checks for a feature
func RequireFeatureFunc(fg *FeatureGate, featureName string) func() error {
	return func() error {
		if !fg.HasFeature(featureName) {
			return FeatureNotAvailableError{Feature: featureName}
		}
		return nil
	}
}

// LicenseMiddleware provides license validation middleware
func LicenseMiddleware(client *Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Add license client to context
		c.Set("license_client", client)

		// Add feature gate to context
		fg := NewFeatureGate(client)
		c.Set("feature_gate", fg)

		c.Next()
	}
}

// GetFeatureGate extracts feature gate from Gin context
func GetFeatureGate(c *gin.Context) (*FeatureGate, error) {
	fg, exists := c.Get("feature_gate")
	if !exists {
		return nil, errors.New("feature gate not found in context")
	}

	featureGate, ok := fg.(*FeatureGate)
	if !ok {
		return nil, errors.New("invalid feature gate type in context")
	}

	return featureGate, nil
}

// GetLicenseClient extracts license client from Gin context
func GetLicenseClient(c *gin.Context) (*Client, error) {
	client, exists := c.Get("license_client")
	if !exists {
		return nil, errors.New("license client not found in context")
	}

	licenseClient, ok := client.(*Client)
	if !ok {
		return nil, errors.New("invalid license client type in context")
	}

	return licenseClient, nil
}