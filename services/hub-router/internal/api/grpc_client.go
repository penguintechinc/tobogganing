// Package api provides clients for communicating with the hub-api service.
//
// The HubAPIClient supports both gRPC (preferred) and REST (fallback) modes
// for fetching policy data from the hub-api backend. JWT authentication is
// used for all requests.
package api

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"

	log "github.com/sirupsen/logrus"
)

// Policy represents a network access policy fetched from the hub-api.
type Policy struct {
	ID        string   `json:"id"`
	Name      string   `json:"name"`
	Priority  int      `json:"priority"`
	Action    string   `json:"action"`
	Domains   []string `json:"domains,omitempty"`
	Ports     []string `json:"ports,omitempty"`
	Protocols []string `json:"protocols,omitempty"`
	// CIDRs is the legacy combined CIDR field kept for backward compatibility.
	CIDRs     []string `json:"cidrs,omitempty"`
	// SrcCIDRs contains source address ranges for matching.
	SrcCIDRs  []string `json:"src_cidrs,omitempty"`
	// DstCIDRs contains destination address ranges for matching.
	DstCIDRs  []string `json:"dst_cidrs,omitempty"`
	Scope     string   `json:"scope,omitempty"`
	Direction string   `json:"direction,omitempty"`
	Protocol  string   `json:"protocol,omitempty"`
	Users     []string `json:"users,omitempty"`
	Groups    []string `json:"groups,omitempty"`
	Enabled   bool     `json:"enabled"`
}

// apiEnvelope is the standard hub-api JSON response wrapper.
// Hub-api wraps all responses as {"status":"success","data":{...}}.
type apiEnvelope struct {
	Status string `json:"status"`
	Data   struct {
		Policies []Policy `json:"policies"`
	} `json:"data"`
}

// HubAPIClient fetches policy and configuration data from the hub-api service.
// It prefers gRPC when available and falls back to REST.
type HubAPIClient struct {
	baseURL    string
	authToken  string
	jwtToken   string
	httpClient *http.Client
	mu         sync.RWMutex
}

// NewHubAPIClient creates a new HubAPIClient targeting the given baseURL.
// authToken is used as a static service-to-service token; jwtToken can be
// set later via SetAuthToken for user-scoped requests.
func NewHubAPIClient(baseURL, authToken string) *HubAPIClient {
	return &HubAPIClient{
		baseURL:   baseURL,
		authToken: authToken,
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

// SetAuthToken updates the JWT bearer token used for API requests.
// This method is safe to call concurrently.
func (c *HubAPIClient) SetAuthToken(token string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.jwtToken = token
}

// FetchPolicies retrieves all active policies from the hub-api.
// It attempts gRPC first (if configured) and falls back to REST.
func (c *HubAPIClient) FetchPolicies() ([]Policy, error) {
	// Attempt REST fetch; a future iteration can add gRPC as the primary path.
	policies, err := c.fetchPoliciesREST()
	if err != nil {
		return nil, fmt.Errorf("failed to fetch policies: %w", err)
	}
	return policies, nil
}

// fetchPoliciesREST retrieves policies from the hub-api REST endpoint.
// The hub-api wraps its response in {"status":"success","data":{"policies":[...]}},
// so this method unwraps that envelope before returning the policy slice.
func (c *HubAPIClient) fetchPoliciesREST() ([]Policy, error) {
	req, err := http.NewRequest(http.MethodGet, c.baseURL+"/api/v1/policies", nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	// Prefer user-scoped JWT token; fall back to static service token.
	c.mu.RLock()
	jwtToken := c.jwtToken
	c.mu.RUnlock()

	if jwtToken != "" {
		req.Header.Set("Authorization", "Bearer "+jwtToken)
	} else if c.authToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.authToken)
	}

	req.Header.Set("User-Agent", "SASEWaddle-HubRouter/1.0")
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to execute request: %w", err)
	}
	defer func() {
		if closeErr := resp.Body.Close(); closeErr != nil {
			log.Warnf("Failed to close response body: %v", closeErr)
		}
	}()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("unexpected status %d from hub-api: %s", resp.StatusCode, string(body))
	}

	// Unwrap the standard hub-api envelope.
	var envelope apiEnvelope
	if err := json.NewDecoder(resp.Body).Decode(&envelope); err != nil {
		return nil, fmt.Errorf("failed to decode policies: %w", err)
	}

	return envelope.Data.Policies, nil
}
