package protocols

import (
	"encoding/json"
	"fmt"
	"math"
	"net/url"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
)

type ICMPTestRequest struct {
	Target         string `json:"target"`
	Protocol       string `json:"protocol"`        // ping, traceroute
	ProtocolDetail string `json:"protocol_detail"` // Alternative field name for compatibility
	Count          int    `json:"count"`
	Timeout        int    `json:"timeout"`
}

type ICMPTestResult struct {
	Target            string   `json:"target"`
	Protocol          string   `json:"protocol"`
	Success           bool     `json:"success"`
	PacketsSent       int      `json:"packets_sent"`
	PacketsReceived   int      `json:"packets_received"`
	PacketLossPercent float64  `json:"packet_loss_percent"`
	LatencyMS         float64  `json:"latency_ms"` // Average
	MinLatencyMS      float64  `json:"min_latency_ms"`
	MaxLatencyMS      float64  `json:"max_latency_ms"`
	JitterMS          float64  `json:"jitter_ms"`
	Error             string   `json:"error,omitempty"`
	Hops              []string `json:"hops,omitempty"` // For traceroute
}

func TestICMP(req ICMPTestRequest) (*ICMPTestResult, error) {
	// Use ProtocolDetail if Protocol is empty (for compatibility)
	protocol := req.Protocol
	if protocol == "" {
		protocol = req.ProtocolDetail
	}
	// Default to ping if still empty
	if protocol == "" {
		protocol = "ping"
	}

	// Extract hostname from target (remove URL scheme if present)
	target := extractHostname(req.Target)

	result := &ICMPTestResult{
		Target:   target,
		Protocol: protocol,
	}

	if req.Count == 0 {
		req.Count = 4
	}
	if req.Timeout == 0 {
		req.Timeout = 10
	}

	switch protocol {
	case "ping":
		return testPing(target, req.Count, req.Timeout, result)
	case "traceroute":
		return testTraceroute(target, req.Timeout, result)
	default:
		result.Error = fmt.Sprintf("unsupported protocol: %s", protocol)
		return result, fmt.Errorf("%s", result.Error)
	}
}

// extractHostname removes URL scheme and port from target
func extractHostname(target string) string {
	// If it's a URL, parse it
	if strings.Contains(target, "://") {
		u, err := url.Parse(target)
		if err == nil {
			return u.Hostname()
		}
	}

	// Remove port if present
	if strings.Contains(target, ":") {
		parts := strings.Split(target, ":")
		return parts[0]
	}

	return target
}

func testPing(target string, count, timeout int, result *ICMPTestResult) (*ICMPTestResult, error) {
	// Use system ping command (requires proper permissions)
	var cmd *exec.Cmd

	switch runtime.GOOS {
	case "linux":
		cmd = exec.Command("ping", "-c", strconv.Itoa(count), "-W", strconv.Itoa(timeout), target)
	case "darwin":
		cmd = exec.Command("ping", "-c", strconv.Itoa(count), "-W", strconv.Itoa(timeout*1000), target)
	case "windows":
		cmd = exec.Command("ping", "-n", strconv.Itoa(count), "-w", strconv.Itoa(timeout*1000), target)
	default:
		result.Error = "unsupported platform for ping"
		return result, fmt.Errorf("%s", result.Error)
	}

	output, err := cmd.CombinedOutput()
	if err != nil {
		result.Success = false
		result.Error = fmt.Sprintf("ping command failed: %v\nOutput: %s", err, string(output))
		return result, err
	}

	// Parse ping output
	lines := strings.Split(string(output), "\n")
	latencies := []float64{}

	for _, line := range lines {
		// Linux/Mac format: "time=12.3 ms"
		if strings.Contains(line, "time=") {
			parts := strings.Split(line, "time=")
			if len(parts) > 1 {
				timeStr := strings.Fields(parts[1])[0]
				if latency, err := strconv.ParseFloat(timeStr, 64); err == nil {
					latencies = append(latencies, latency)
				}
			}
		}
	}

	result.PacketsSent = count
	result.PacketsReceived = len(latencies)
	result.PacketLossPercent = float64(count-len(latencies)) / float64(count) * 100.0

	if len(latencies) > 0 {
		result.Success = true

		// Calculate stats
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

		// Calculate jitter (variance in latency)
		var jitterSum float64
		for i := 1; i < len(latencies); i++ {
			jitterSum += math.Abs(latencies[i] - latencies[i-1])
		}
		if len(latencies) > 1 {
			result.JitterMS = jitterSum / float64(len(latencies)-1)
		}
	} else {
		result.Success = false
		result.Error = "No packets received"
	}

	return result, nil
}

func testTraceroute(target string, timeout int, result *ICMPTestResult) (*ICMPTestResult, error) {
	// Use system traceroute command
	var cmd *exec.Cmd

	switch runtime.GOOS {
	case "linux":
		cmd = exec.Command("traceroute", "-w", strconv.Itoa(timeout), "-m", "30", target)
	case "darwin":
		cmd = exec.Command("traceroute", "-w", strconv.Itoa(timeout), "-m", "30", target)
	case "windows":
		cmd = exec.Command("tracert", "-w", strconv.Itoa(timeout*1000), "-h", "30", target)
	default:
		result.Error = "unsupported platform for traceroute"
		return result, fmt.Errorf("%s", result.Error)
	}

	output, err := cmd.CombinedOutput()
	if err != nil {
		result.Success = false
		result.Error = fmt.Sprintf("traceroute command failed: %v\nOutput: %s", err, string(output))
		return result, err
	}

	// Parse traceroute output
	lines := strings.Split(string(output), "\n")
	hops := []string{}

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "traceroute") || strings.HasPrefix(line, "Tracing") {
			continue
		}
		hops = append(hops, line)
	}

	result.Success = true
	result.Hops = hops

	return result, nil
}

func (r *ICMPTestResult) ToJSON() ([]byte, error) {
	return json.Marshal(r)
}
