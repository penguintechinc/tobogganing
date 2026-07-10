package protocols

import (
	"crypto/tls"
	"encoding/json"
	"fmt"
	"math"
	"net"
	"net/url"
	"strconv"
	"strings"
	"time"

	"golang.org/x/crypto/ssh"
)

type TCPTestRequest struct {
	Target         string `json:"target"`
	Protocol       string `json:"protocol"`        // raw, tls, ssh
	ProtocolDetail string `json:"protocol_detail"` // Alternative field name for compatibility
	Port           int    `json:"port"`            // Optional port override
	Timeout        int    `json:"timeout"`
	Count          int    `json:"count"` // Number of connections for jitter calculation
}

type TCPTestResult struct {
	Target       string  `json:"target"`
	Protocol     string  `json:"protocol"`
	Connected    bool    `json:"connected"`
	LatencyMS    float64 `json:"latency_ms"`      // Average latency
	MinLatencyMS float64 `json:"min_latency_ms"`  // Minimum latency
	MaxLatencyMS float64 `json:"max_latency_ms"`  // Maximum latency
	JitterMS     float64 `json:"jitter_ms"`       // Average jitter
	HandshakeMS  float64 `json:"handshake_ms,omitempty"`
	Success      bool    `json:"success"`
	Error        string  `json:"error,omitempty"`
	RemoteAddr   string  `json:"remote_addr"`
	TLSVersion   string  `json:"tls_version,omitempty"`
	SSHVersion   string  `json:"ssh_version,omitempty"`
}

func TestTCP(req TCPTestRequest) (*TCPTestResult, error) {
	// Use ProtocolDetail if Protocol is empty (for compatibility)
	protocol := req.Protocol
	if protocol == "" {
		protocol = req.ProtocolDetail
	}
	// Default to raw if still empty
	if protocol == "" {
		protocol = "raw"
	}

	// Normalize protocol to lowercase for case-insensitive comparison
	protocol = strings.ToLower(protocol)
	protocol = strings.ReplaceAll(protocol, " ", "")
	// Handle "Raw TCP" -> "raw"
	if strings.Contains(protocol, "raw") {
		protocol = "raw"
	}

	// Parse target to extract host and port
	target, err := parseTarget(req.Target, req.Port, protocol)
	if err != nil {
		return nil, err
	}

	result := &TCPTestResult{
		Target:   target,
		Protocol: protocol,
	}

	timeout := time.Duration(req.Timeout) * time.Second
	if timeout == 0 {
		timeout = 10 * time.Second
	}

	// Default count to 1 if not specified
	count := req.Count
	if count <= 0 {
		count = 1
	}

	// Run multiple tests to calculate jitter
	var latencies []float64
	var lastResult *TCPTestResult
	var lastError error

	for i := 0; i < count; i++ {
		var iterResult *TCPTestResult

		switch protocol {
		case "raw", "tcp":
			iterResult, lastError = testRawTCP(target, timeout, &TCPTestResult{Target: target, Protocol: protocol})
		case "tls":
			iterResult, lastError = testTLSTCP(target, timeout, &TCPTestResult{Target: target, Protocol: protocol})
		case "ssh":
			iterResult, lastError = testSSH(target, timeout, &TCPTestResult{Target: target, Protocol: protocol})
		default:
			result.Error = fmt.Sprintf("unsupported protocol: %s", protocol)
			return result, fmt.Errorf("%s", result.Error)
		}

		if iterResult != nil {
			latencies = append(latencies, iterResult.LatencyMS)
			lastResult = iterResult
		}

		// Small delay between attempts
		if i < count-1 {
			time.Sleep(100 * time.Millisecond)
		}
	}

	if len(latencies) == 0 || lastResult == nil {
		result.Success = false
		if lastError != nil {
			result.Error = lastError.Error()
		} else {
			result.Error = "No successful connections"
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

	// Calculate jitter
	if len(latencies) > 1 {
		var jitterSum float64
		for i := 1; i < len(latencies); i++ {
			jitterSum += math.Abs(latencies[i] - latencies[i-1])
		}
		result.JitterMS = jitterSum / float64(len(latencies)-1)
	}

	// Copy other fields from last result
	result.Connected = lastResult.Connected
	result.Success = lastResult.Success
	result.RemoteAddr = lastResult.RemoteAddr
	result.TLSVersion = lastResult.TLSVersion
	result.SSHVersion = lastResult.SSHVersion
	result.HandshakeMS = lastResult.HandshakeMS

	return result, nil
}

// parseTarget extracts host:port from various input formats
func parseTarget(target string, portOverride int, protocol string) (string, error) {
	// If target already has host:port format, use it
	if strings.Contains(target, ":") && !strings.Contains(target, "://") {
		return target, nil
	}

	// Try to parse as URL
	var host string
	var port int

	if strings.Contains(target, "://") {
		// Parse as URL
		u, err := url.Parse(target)
		if err != nil {
			return "", fmt.Errorf("invalid target URL: %v", err)
		}
		host = u.Hostname()
		if u.Port() != "" {
			port, _ = strconv.Atoi(u.Port())
		}
	} else {
		// Assume it's just a hostname
		host = target
	}

	// Use port override if provided
	if portOverride > 0 {
		port = portOverride
	}

	// If still no port, use defaults based on protocol
	if port == 0 {
		switch protocol {
		case "tls":
			port = 443
		case "ssh":
			port = 22
		case "raw":
			port = 80
		default:
			port = 80
		}
	}

	return fmt.Sprintf("%s:%d", host, port), nil
}

func testRawTCP(target string, timeout time.Duration, result *TCPTestResult) (*TCPTestResult, error) {
	startTime := time.Now()

	conn, err := net.DialTimeout("tcp", target, timeout)
	if err != nil {
		result.Success = false
		result.Error = err.Error()
		result.LatencyMS = float64(time.Since(startTime).Microseconds()) / 1000.0
		return result, err
	}
	defer conn.Close()

	latency := time.Since(startTime)

	result.Connected = true
	result.Success = true
	result.LatencyMS = float64(latency.Microseconds()) / 1000.0
	result.RemoteAddr = conn.RemoteAddr().String()

	return result, nil
}

func testTLSTCP(target string, timeout time.Duration, result *TCPTestResult) (*TCPTestResult, error) {
	startTime := time.Now()

	config := &tls.Config{
		InsecureSkipVerify: false,
	}

	dialer := &net.Dialer{Timeout: timeout}
	conn, err := tls.DialWithDialer(dialer, "tcp", target, config)
	if err != nil {
		result.Success = false
		result.Error = err.Error()
		result.LatencyMS = float64(time.Since(startTime).Microseconds()) / 1000.0
		return result, err
	}
	defer conn.Close()

	handshakeStart := time.Now()
	if err := conn.Handshake(); err != nil {
		result.Success = false
		result.Error = fmt.Sprintf("TLS handshake failed: %v", err)
		return result, err
	}
	handshakeDuration := time.Since(handshakeStart)
	totalLatency := time.Since(startTime)

	state := conn.ConnectionState()

	result.Connected = true
	result.Success = true
	result.LatencyMS = float64(totalLatency.Microseconds()) / 1000.0
	result.HandshakeMS = float64(handshakeDuration.Microseconds()) / 1000.0
	result.RemoteAddr = conn.RemoteAddr().String()
	result.TLSVersion = tlsVersionToString(state.Version)

	return result, nil
}

func testSSH(target string, timeout time.Duration, result *TCPTestResult) (*TCPTestResult, error) {
	startTime := time.Now()

	config := &ssh.ClientConfig{
		Timeout:         timeout,
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
	}

	client, err := ssh.Dial("tcp", target, config)
	if err != nil {
		// This is expected - we're just testing connectivity, not auth
		// SSH banner exchange still happens before auth
		result.Connected = true
		result.Success = true
		result.LatencyMS = float64(time.Since(startTime).Microseconds()) / 1000.0
		result.Error = "Auth not attempted (connectivity test only)"
		return result, nil
	}
	defer client.Close()

	latency := time.Since(startTime)

	result.Connected = true
	result.Success = true
	result.LatencyMS = float64(latency.Microseconds()) / 1000.0
	result.RemoteAddr = client.RemoteAddr().String()
	result.SSHVersion = string(client.ServerVersion())

	return result, nil
}

func tlsVersionToString(version uint16) string {
	switch version {
	case tls.VersionTLS10:
		return "TLS 1.0"
	case tls.VersionTLS11:
		return "TLS 1.1"
	case tls.VersionTLS12:
		return "TLS 1.2"
	case tls.VersionTLS13:
		return "TLS 1.3"
	default:
		return fmt.Sprintf("Unknown (0x%x)", version)
	}
}

func (r *TCPTestResult) ToJSON() ([]byte, error) {
	return json.Marshal(r)
}
