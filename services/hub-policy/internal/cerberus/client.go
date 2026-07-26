// Package cerberus provides optional integration with Cerberus NGFW for threat enrichment.
package cerberus

import (
	"context"
	"net/http"
	"os"
)

// Client is an optional integration with Cerberus NGFW for threat enrichment.
// Returns nil from NewClientFromEnv() if CERBERUS_URL is not configured.
type Client struct {
	baseURL    string
	httpClient *http.Client
}

// NewClientFromEnv returns nil if CERBERUS_URL is not set (module disabled).
func NewClientFromEnv() *Client {
	url := os.Getenv("CERBERUS_URL")
	if url == "" {
		return nil
	}
	return &Client{baseURL: url, httpClient: &http.Client{}}
}

// GetCurrentBlocklists fetches current threat IP and domain blocklists from Cerberus.
// Safe to call with nil receiver — returns empty slices.
func (c *Client) GetCurrentBlocklists(ctx context.Context) (threatIPs []string, threatDomains []string) {
	if c == nil {
		return nil, nil
	}
	// TODO: implement REST call to Cerberus /api/v1/threats/blocklists
	return nil, nil
}
