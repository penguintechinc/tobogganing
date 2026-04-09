// Package push handles pushing compiled rule sets to MarchProxy.
package push

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"

	"github.com/tobogganing/hub-policy/internal/compiler"
	log "github.com/sirupsen/logrus"
)

// Client pushes compiled rule sets to a MarchProxy levers API endpoint.
// Configure via MARCHPROXY_LEVERS_URL env var.
type Client struct {
	baseURL    string
	httpClient *http.Client
}

// NewClientFromEnv creates a Client from environment variables.
// Returns nil if MARCHPROXY_LEVERS_URL is not set (push disabled).
func NewClientFromEnv() *Client {
	url := os.Getenv("MARCHPROXY_LEVERS_URL")
	if url == "" {
		log.Warn("push: MARCHPROXY_LEVERS_URL not set — rule push disabled")
		return nil
	}
	return &Client{baseURL: url, httpClient: &http.Client{}}
}

// Push sends compiled rules to MarchProxy. Safe to call with nil receiver.
func (c *Client) Push(ctx context.Context, rules compiler.CompiledRuleSet) error {
	if c == nil {
		return nil
	}
	body, err := json.Marshal(rules)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/api/v1/levers/rules", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("push rules: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("marchproxy returned %d", resp.StatusCode)
	}
	return nil
}
