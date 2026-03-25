package protocols

import (
	"net"
	"time"
)

// TCPTestResult holds the outcome of a single TCP dial probe.
type TCPTestResult struct {
	Target    string  `json:"target"`
	LatencyMs float64 `json:"latency_ms"`
	Success   bool    `json:"success"`
	Error     string  `json:"error,omitempty"`
}

// RunTCPTest attempts a TCP connection to target (host:port) and measures
// the time to establish the connection.
func RunTCPTest(target string, timeout time.Duration) TCPTestResult {
	result := TCPTestResult{Target: target}

	start := time.Now()
	conn, err := net.DialTimeout("tcp", target, timeout)
	elapsed := time.Since(start)

	result.LatencyMs = elapsed.Seconds() * 1000

	if err != nil {
		result.Error = err.Error()
		return result
	}
	defer conn.Close()

	result.Success = true
	return result
}
