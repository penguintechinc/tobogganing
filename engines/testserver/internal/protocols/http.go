package protocols

import (
	"crypto/tls"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"strings"
	"time"

	"golang.org/x/net/http2"
)

type HTTPTestRequest struct {
	Target         string `json:"target"`
	Protocol       string `json:"protocol"`        // http1, http2, http3
	ProtocolDetail string `json:"protocol_detail"` // Alternative field name for compatibility
	Method         string `json:"method"`
	Timeout        int    `json:"timeout"` // seconds
	Count          int    `json:"count"`   // Number of requests for jitter calculation
}

type HTTPTestResult struct {
	Target         string  `json:"target"`
	Protocol       string  `json:"protocol"`
	StatusCode     int     `json:"status_code"`
	LatencyMS      float64 `json:"latency_ms"`      // Average latency
	MinLatencyMS   float64 `json:"min_latency_ms"`  // Minimum latency
	MaxLatencyMS   float64 `json:"max_latency_ms"`  // Maximum latency
	JitterMS       float64 `json:"jitter_ms"`       // Average jitter
	TTFBMS         float64 `json:"ttfb_ms"`
	TotalTimeMS    float64 `json:"total_time_ms"`
	Success        bool    `json:"success"`
	Error          string  `json:"error,omitempty"`
	ConnectedProto string  `json:"connected_proto"`
}

func TestHTTP(req HTTPTestRequest) (*HTTPTestResult, error) {
	// Use ProtocolDetail if Protocol is empty (for compatibility)
	protocol := req.Protocol
	if protocol == "" {
		protocol = req.ProtocolDetail
	}
	// Default to http2 if still empty
	if protocol == "" {
		protocol = "http2"
	}

	// Normalize protocol to lowercase and handle various formats
	protocol = strings.ToLower(protocol)
	protocol = strings.ReplaceAll(protocol, "/", "")
	protocol = strings.ReplaceAll(protocol, ".", "")
	protocol = strings.ReplaceAll(protocol, " ", "")

	// Ensure target has scheme
	target := req.Target
	if !strings.HasPrefix(target, "http://") && !strings.HasPrefix(target, "https://") {
		target = "https://" + target
	}

	result := &HTTPTestResult{
		Target:   target,
		Protocol: protocol,
	}

	timeout := time.Duration(req.Timeout) * time.Second
	if timeout == 0 {
		timeout = 30 * time.Second
	}

	var client *http.Client

	switch protocol {
	case "http1", "http11":
		client = &http.Client{
			Timeout: timeout,
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{InsecureSkipVerify: false},
			},
		}
	case "http2", "http20":
		client = &http.Client{
			Timeout: timeout,
			Transport: &http2.Transport{
				TLSClientConfig: &tls.Config{InsecureSkipVerify: false},
			},
		}
	case "http3", "http30":
		// TODO: Implement HTTP/3 when quic-go is stable
		return nil, fmt.Errorf("HTTP/3 not yet implemented")
	default:
		return nil, fmt.Errorf("unsupported protocol: %s", protocol)
	}

	method := req.Method
	if method == "" {
		method = "GET"
	}

	// Default count to 1 if not specified
	count := req.Count
	if count <= 0 {
		count = 1
	}

	// Run multiple requests to calculate jitter
	var latencies []float64
	var lastStatusCode int
	var lastProto string
	var lastError error

	for i := 0; i < count; i++ {
		startTime := time.Now()

		httpReq, err := http.NewRequest(method, target, nil)
		if err != nil {
			result.Success = false
			result.Error = err.Error()
			return result, err
		}

		httpReq.Header.Set("User-Agent", "WaddlePerf-TestServer/1.0")

		resp, err := client.Do(httpReq)
		if err != nil {
			lastError = err
			// Record failed attempt but continue
			latencies = append(latencies, float64(time.Since(startTime).Microseconds())/1000.0)
			continue
		}

		totalTime := time.Since(startTime)
		latencyMS := float64(totalTime.Microseconds()) / 1000.0
		latencies = append(latencies, latencyMS)

		lastStatusCode = resp.StatusCode
		lastProto = resp.Proto
		resp.Body.Close()

		// Small delay between requests to avoid overwhelming the server
		if i < count-1 {
			time.Sleep(100 * time.Millisecond)
		}
	}

	if len(latencies) == 0 {
		result.Success = false
		if lastError != nil {
			result.Error = lastError.Error()
		} else {
			result.Error = "No successful requests"
		}
		return result, lastError
	}

	// Calculate statistics
	var sum, min, max float64
	min = latencies[0]
	max = latencies[0]

	for _, lat := range latencies {
		sum += lat
		if lat < min {
			min = lat
		}
		if lat > max {
			max = lat
		}
	}

	result.LatencyMS = sum / float64(len(latencies))
	result.MinLatencyMS = min
	result.MaxLatencyMS = max
	result.TTFBMS = result.LatencyMS
	result.TotalTimeMS = result.LatencyMS

	// Calculate jitter (average absolute difference between consecutive latencies)
	if len(latencies) > 1 {
		var jitterSum float64
		for i := 1; i < len(latencies); i++ {
			jitterSum += math.Abs(latencies[i] - latencies[i-1])
		}
		result.JitterMS = jitterSum / float64(len(latencies)-1)
	}

	result.StatusCode = lastStatusCode
	result.Success = lastStatusCode >= 200 && lastStatusCode < 400
	result.ConnectedProto = lastProto

	return result, nil
}

func (r *HTTPTestResult) ToJSON() ([]byte, error) {
	return json.Marshal(r)
}
