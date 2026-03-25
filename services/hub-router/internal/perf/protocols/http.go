// Package protocols provides lightweight protocol-level probe functions adapted
// from WaddlePerf for fabric health measurement inside hub-router nodes.
package protocols

import (
	"net/http"
	"time"
)

// HTTPTestResult holds the outcome of a single HTTP probe.
type HTTPTestResult struct {
	Target     string  `json:"target"`
	StatusCode int     `json:"status_code"`
	LatencyMs  float64 `json:"latency_ms"`
	Success    bool    `json:"success"`
	Error      string  `json:"error,omitempty"`
}

// RunHTTPTest performs a GET request to target and returns latency and status.
// A response with a 2xx or 3xx status code is considered successful.
func RunHTTPTest(target string, timeout time.Duration) HTTPTestResult {
	result := HTTPTestResult{Target: target}

	client := &http.Client{Timeout: timeout}
	start := time.Now()

	resp, err := client.Get(target) //nolint:noctx // timeout controlled via http.Client
	elapsed := time.Since(start)

	if err != nil {
		result.Error = err.Error()
		result.LatencyMs = elapsed.Seconds() * 1000
		return result
	}
	defer resp.Body.Close()

	result.StatusCode = resp.StatusCode
	result.LatencyMs = elapsed.Seconds() * 1000
	result.Success = resp.StatusCode >= 200 && resp.StatusCode < 400
	return result
}
