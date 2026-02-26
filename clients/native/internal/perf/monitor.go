// Package perf implements lightweight performance monitoring for the native client.
//
// The monitor periodically probes hub-api reachability via HTTP and ships
// the resulting latency sample to the hub-api perf metrics endpoint so that
// client-to-hub round-trip health is visible alongside fabric metrics.
package perf

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// Config holds configuration for the native-client performance monitor.
type Config struct {
	Enabled   bool   `mapstructure:"enabled"`
	Interval  int    `mapstructure:"interval"`    // seconds between probes
	HubAPIURL string `mapstructure:"hub_api_url"` // base URL of hub-api service
	ClientID  string // set at runtime from the registered client ID
}

// Monitor probes hub-api reachability and reports latency.
type Monitor struct {
	config     Config
	httpClient *http.Client
	cancelFunc context.CancelFunc
}

// NewMonitor creates a Monitor from the given Config.
func NewMonitor(cfg Config) *Monitor {
	return &Monitor{
		config:     cfg,
		httpClient: &http.Client{Timeout: 15 * time.Second},
	}
}

// Start launches the background probe loop. It is a no-op when disabled.
func (m *Monitor) Start(ctx context.Context) error {
	if !m.config.Enabled {
		return nil
	}

	ctx, cancel := context.WithCancel(ctx)
	m.cancelFunc = cancel

	interval := time.Duration(m.config.Interval) * time.Second

	go func() {
		ticker := time.NewTicker(interval)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				m.runProbe()
			}
		}
	}()

	fmt.Printf("Performance monitor started (interval: %v)\n", interval)
	return nil
}

// Stop cancels the background probe loop.
func (m *Monitor) Stop() {
	if m.cancelFunc != nil {
		m.cancelFunc()
	}
}

// runProbe measures HTTP latency to hub-api and submits the result.
func (m *Monitor) runProbe() {
	start := time.Now()
	resp, err := m.httpClient.Get(m.config.HubAPIURL + "/healthz")
	latency := time.Since(start).Seconds() * 1000

	if err != nil || resp.StatusCode != http.StatusOK {
		// Log but do not surface errors to the user — perf is best-effort.
		if resp != nil {
			resp.Body.Close()
		}
		return
	}
	resp.Body.Close()

	metric := map[string]interface{}{
		"source_id":   m.config.ClientID,
		"source_type": "client",
		"target_id":   "hub-api",
		"protocol":    "http",
		"latency_ms":  latency,
	}

	body, err := json.Marshal(map[string]interface{}{"metrics": []interface{}{metric}})
	if err != nil {
		return
	}

	submitResp, err := m.httpClient.Post(
		m.config.HubAPIURL+"/api/v1/perf/metrics",
		"application/json",
		bytes.NewReader(body),
	)
	if err == nil {
		submitResp.Body.Close()
	}
}
