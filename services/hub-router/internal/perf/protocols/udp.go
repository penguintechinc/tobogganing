package protocols

import (
	"net"
	"time"
)

// UDPTestResult holds the outcome of a single UDP probe.
type UDPTestResult struct {
	Target    string  `json:"target"`
	LatencyMs float64 `json:"latency_ms"`
	Success   bool    `json:"success"`
	Error     string  `json:"error,omitempty"`
}

// RunUDPTest sends a small probe payload to a UDP target (host:port).
// Because UDP is connectionless, the probe is considered successful if the
// write completes; an echo response is accepted if one arrives within timeout.
func RunUDPTest(target string, timeout time.Duration) UDPTestResult {
	result := UDPTestResult{Target: target}

	addr, err := net.ResolveUDPAddr("udp", target)
	if err != nil {
		result.Error = err.Error()
		return result
	}

	conn, err := net.DialUDP("udp", nil, addr)
	if err != nil {
		result.Error = err.Error()
		return result
	}
	defer conn.Close()

	_ = conn.SetDeadline(time.Now().Add(timeout))

	payload := []byte("TOBOGGANING_PERF_PROBE")
	start := time.Now()

	if _, err := conn.Write(payload); err != nil {
		result.Error = err.Error()
		return result
	}

	buf := make([]byte, 1024)
	if _, err := conn.Read(buf); err != nil {
		// UDP may not return a response; a successful write is sufficient.
		result.LatencyMs = time.Since(start).Seconds() * 1000
		result.Success = true
		return result
	}

	result.LatencyMs = time.Since(start).Seconds() * 1000
	result.Success = true
	return result
}
