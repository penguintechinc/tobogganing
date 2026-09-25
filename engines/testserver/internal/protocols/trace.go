package protocols

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os/exec"
	"regexp"
	"strings"
	"time"
)

type HTTPTraceRequest struct {
	Target  string `json:"target"`
	Port    int    `json:"port"`
	Timeout int    `json:"timeout"`
}

type TCPTraceRequest struct {
	Target  string `json:"target"`
	Port    int    `json:"port"`
	Timeout int    `json:"timeout"`
}

type TracerouteRequest struct {
	Target  string `json:"target"`
	Timeout int    `json:"timeout"`
}

type UDPTraceRequest struct {
	Target  string `json:"target"`
	Port    int    `json:"port"`
	Timeout int    `json:"timeout"`
}

type HopDetail struct {
	HopNumber int     `json:"hop_number"`
	IPAddress string  `json:"ip_address,omitempty"`
	Hostname  string  `json:"hostname,omitempty"`
	Latency   string  `json:"latency,omitempty"`
	RawOutput string  `json:"raw_output"`
	Timeout   bool    `json:"timeout,omitempty"`
}

type TraceResult struct {
	Target     string                 `json:"target"`
	Protocol   string                 `json:"protocol"`
	Success    bool                   `json:"success"`
	LatencyMS  float64                `json:"latency_ms"`
	Hops       []string               `json:"hops,omitempty"`
	Error      string                 `json:"error,omitempty"`
	RouteInfo  string                 `json:"route_info,omitempty"`
	RawResults map[string]interface{} `json:"raw_results,omitempty"`
}

// TestHTTPTrace performs a TCP traceroute followed by HTTP requests to trace the network path
func TestHTTPTrace(req HTTPTraceRequest) (*TraceResult, error) {
	result := &TraceResult{
		Target:   req.Target,
		Protocol: "http_trace",
	}

	// Ensure target has scheme
	target := req.Target
	scheme := "https"
	if strings.HasPrefix(target, "http://") {
		scheme = "http"
		target = strings.TrimPrefix(target, "http://")
	} else if strings.HasPrefix(target, "https://") {
		target = strings.TrimPrefix(target, "https://")
	}

	// Determine port
	port := req.Port
	if port == 0 {
		if scheme == "https" {
			port = 443
		} else {
			port = 80
		}
	}

	// Extract hostname (remove path)
	hostname := target
	if idx := strings.Index(target, "/"); idx > 0 {
		hostname = target[:idx]
	}

	// Remove port from hostname if present
	if strings.Contains(hostname, ":") {
		hostname, _, _ = net.SplitHostPort(hostname)
	}

	startTime := time.Now()

	// First, try TCP traceroute to the actual port we're testing
	portStr := fmt.Sprintf("%d", port)
	var cmd *exec.Cmd
	var usedTCPTrace bool

	if _, err := exec.LookPath("tcptraceroute"); err == nil {
		cmd = exec.Command("tcptraceroute", "-n", "-q", "1", "-w", "3", "-m", "30", hostname, portStr)
		usedTCPTrace = true
	} else {
		cmd = exec.Command("traceroute", "-T", "-n", "-q", "1", "-w", "3", "-p", portStr, "-m", "30", hostname)
		usedTCPTrace = true
	}

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	_ = cmd.Run()

	tracerouteOutput := stdout.String()
	if tracerouteOutput == "" {
		tracerouteOutput = stderr.String()
	}

	// Parse network hops
	networkHops := parseTracerouteDetailed(tracerouteOutput)

	// If TCP traceroute failed or gave poor results (less than 2 hops), fall back to ICMP
	if len(networkHops) < 2 && usedTCPTrace {
		// Fall back to ICMP traceroute
		cmd = exec.Command("traceroute", "-n", "-q", "1", "-w", "3", "-m", "30", hostname)

		stdout.Reset()
		stderr.Reset()
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		_ = cmd.Run()

		tracerouteOutput = stdout.String()
		if tracerouteOutput == "" {
			tracerouteOutput = stderr.String()
		}

		networkHops = parseTracerouteDetailed(tracerouteOutput)
	}

	// Now make the actual HTTP request to the final destination
	fullURL := fmt.Sprintf("%s://%s", scheme, target)
	timeout := time.Duration(req.Timeout) * time.Second
	if timeout == 0 {
		timeout = 30 * time.Second
	}

	// Force HTTP/1.1 by creating a custom transport (prevents HTTP/2)
	transport := &http.Transport{
		DisableKeepAlives: true, // Close connection after each request
		// By not setting TLSClientConfig.NextProtos, we prevent HTTP/2 negotiation
	}

	client := &http.Client{
		Timeout:   timeout,
		Transport: transport,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse // Don't follow redirects
		},
	}

	httpStartTime := time.Now()
	httpReq, err := http.NewRequest("GET", fullURL, nil)
	if err != nil {
		result.Success = false
		result.Error = err.Error()
		result.LatencyMS = float64(time.Since(startTime).Microseconds()) / 1000.0
		return result, err
	}

	// Force HTTP/1.1 (prevents HTTP/2)
	httpReq.Proto = "HTTP/1.1"
	httpReq.ProtoMajor = 1
	httpReq.ProtoMinor = 1
	httpReq.Header.Set("User-Agent", "WaddlePerf-TestServer/1.0")
	httpReq.Header.Set("Connection", "close")

	resp, err := client.Do(httpReq)
	if err != nil {
		result.Success = false
		result.Error = err.Error()
		result.LatencyMS = float64(time.Since(startTime).Microseconds()) / 1000.0
		return result, err
	}
	defer resp.Body.Close()

	httpLatency := float64(time.Since(httpStartTime).Microseconds()) / 1000.0
	result.LatencyMS = float64(time.Since(startTime).Microseconds()) / 1000.0
	result.Success = true

	// Build hops combining network path and HTTP info
	var hops []string

	// Add network hops
	for _, netHop := range networkHops {
		hops = append(hops, fmt.Sprintf("Hop %d: %s", netHop.HopNumber, netHop.RawOutput))
	}

	// Add final HTTP destination hop
	hops = append(hops, fmt.Sprintf("HTTP Destination: %s %s (%s)", resp.Proto, resp.Status, fullURL))

	result.Hops = hops
	result.RouteInfo = fmt.Sprintf("HTTP trace completed with %d network hops", len(networkHops))

	// Populate raw results with detailed information
	result.RawResults = make(map[string]interface{})
	result.RawResults["status_code"] = resp.StatusCode
	result.RawResults["status"] = resp.Status
	result.RawResults["proto"] = resp.Proto
	result.RawResults["content_length"] = resp.ContentLength

	// Add all response headers
	headers := make(map[string]string)
	for key, values := range resp.Header {
		if len(values) > 0 {
			headers[key] = values[0]
		}
	}
	result.RawResults["headers"] = headers

	// Add TLS info if available
	if resp.TLS != nil {
		tlsInfo := make(map[string]interface{})
		tlsInfo["version"] = getTLSVersion(resp.TLS.Version)
		tlsInfo["cipher_suite"] = getCipherSuite(resp.TLS.CipherSuite)
		tlsInfo["server_name"] = resp.TLS.ServerName
		tlsInfo["negotiated_protocol"] = resp.TLS.NegotiatedProtocol
		result.RawResults["tls"] = tlsInfo
	}

	result.RawResults["latency_ms"] = result.LatencyMS
	result.RawResults["http_latency_ms"] = httpLatency
	result.RawResults["hop_count"] = len(networkHops)
	result.RawResults["total_hops"] = len(hops)
	result.RawResults["traceroute_output"] = tracerouteOutput
	result.RawResults["url"] = fullURL

	// Add which traceroute method was used
	if usedTCPTrace {
		if len(networkHops) < 2 {
			result.RawResults["traceroute_method"] = "ICMP (TCP fallback)"
		} else {
			result.RawResults["traceroute_method"] = "TCP"
		}
	} else {
		result.RawResults["traceroute_method"] = "ICMP"
	}

	// Create detailed hops for HTTP trace - include network hops + final HTTP destination
	var detailedHops []HopDetail

	// Add network hops from traceroute
	detailedHops = append(detailedHops, networkHops...)

	// Add final HTTP destination hop with full details
	finalHop := HopDetail{
		HopNumber: len(networkHops) + 1,
		IPAddress: hostname,
		Latency:   fmt.Sprintf("%.2f ms", httpLatency),
		RawOutput: fmt.Sprintf("HTTP/%s %s - %s (%s)", resp.Proto, resp.Status, fullURL, fmt.Sprintf("%.2f ms", httpLatency)),
	}

	// Add server hostname if available
	if server := resp.Header.Get("Server"); server != "" {
		finalHop.Hostname = server
	}

	detailedHops = append(detailedHops, finalHop)

	result.RawResults["detailed_hops"] = detailedHops

	// Add HTTP-specific details
	httpDetails := make(map[string]interface{})
	httpDetails["http_version"] = resp.Proto
	httpDetails["status"] = resp.Status
	httpDetails["status_code"] = resp.StatusCode
	httpDetails["url"] = fullURL
	httpDetails["latency_ms"] = httpLatency

	if server := resp.Header.Get("Server"); server != "" {
		httpDetails["server"] = server
	}
	if via := resp.Header.Get("Via"); via != "" {
		httpDetails["via"] = via
	}
	if xForwardedFor := resp.Header.Get("X-Forwarded-For"); xForwardedFor != "" {
		httpDetails["x_forwarded_for"] = xForwardedFor
	}

	if resp.TLS != nil {
		httpDetails["tls_version"] = getTLSVersion(resp.TLS.Version)
		httpDetails["cipher_suite"] = getCipherSuite(resp.TLS.CipherSuite)
		httpDetails["server_name"] = resp.TLS.ServerName
	}

	result.RawResults["http_details"] = httpDetails

	return result, nil
}

// TestTCPTrace performs a TCP trace using traceroute-like functionality
func TestTCPTrace(req TCPTraceRequest) (*TraceResult, error) {
	result := &TraceResult{
		Target:   req.Target,
		Protocol: "tcp_trace",
	}

	// Default port to 22 (SSH) if not specified
	port := req.Port
	if port == 0 {
		port = 22
	}

	target := req.Target
	if !strings.Contains(target, ":") {
		target = fmt.Sprintf("%s:%d", target, port)
	}

	startTime := time.Now()

	// Try to resolve the target
	host, portStr, err := net.SplitHostPort(target)
	if err != nil {
		result.Success = false
		result.Error = fmt.Sprintf("Invalid target: %v", err)
		return result, err
	}

	ips, err := net.LookupIP(host)
	if err != nil {
		result.Success = false
		result.Error = fmt.Sprintf("DNS resolution failed: %v", err)
		return result, err
	}

	if len(ips) == 0 {
		result.Success = false
		result.Error = "No IP addresses found for target"
		return result, fmt.Errorf("%s", result.Error)
	}

	targetIP := ips[0].String()

	// Use tcptraceroute if available, otherwise use traceroute with TCP
	var cmd *exec.Cmd
	if _, err := exec.LookPath("tcptraceroute"); err == nil {
		cmd = exec.Command("tcptraceroute", "-n", "-q", "1", "-w", "3", "-m", "30", host, portStr)
	} else {
		// Fallback to traceroute with TCP (requires root on some systems)
		cmd = exec.Command("traceroute", "-T", "-n", "-q", "1", "-w", "3", "-p", portStr, "-m", "30", host)
	}

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err = cmd.Run()

	result.LatencyMS = float64(time.Since(startTime).Microseconds()) / 1000.0

	output := stdout.String()
	if output == "" {
		output = stderr.String()
	}

	// Parse traceroute output
	hops := parseTracerouteOutput(output)

	if len(hops) == 0 && err != nil {
		// If traceroute failed, try a simple TCP connection to show at least the final hop
		conn, dialErr := net.DialTimeout("tcp", target, 5*time.Second)
		if dialErr == nil {
			conn.Close()
			hops = append(hops, fmt.Sprintf("Direct connection to %s:%s successful", targetIP, portStr))
			result.Success = true
		} else {
			result.Success = false
			result.Error = fmt.Sprintf("Connection failed: %v", dialErr)
			return result, dialErr
		}
	} else {
		result.Success = true
	}

	result.Hops = hops
	result.RouteInfo = fmt.Sprintf("TCP trace to %s completed with %d hops", target, len(hops))

	// Populate raw results with detailed information
	result.RawResults = make(map[string]interface{})
	result.RawResults["target_host"] = host
	result.RawResults["target_port"] = portStr
	result.RawResults["target_ip"] = targetIP
	result.RawResults["resolved_ips"] = ips
	result.RawResults["latency_ms"] = result.LatencyMS
	result.RawResults["hop_count"] = len(hops)
	result.RawResults["traceroute_output"] = output

	// Add command used
	if _, err := exec.LookPath("tcptraceroute"); err == nil {
		result.RawResults["command"] = "tcptraceroute"
	} else {
		result.RawResults["command"] = "traceroute -T"
	}

	// Add individual hop details
	if len(hops) > 0 {
		result.RawResults["hops"] = hops
		result.RawResults["detailed_hops"] = parseTracerouteDetailed(output)
	}

	return result, nil
}

// TestTraceroute performs an ICMP traceroute
func TestTraceroute(req TracerouteRequest) (*TraceResult, error) {
	result := &TraceResult{
		Target:   req.Target,
		Protocol: "traceroute",
	}

	timeout := req.Timeout
	if timeout == 0 {
		timeout = 30
	}

	startTime := time.Now()

	// Run traceroute command
	cmd := exec.Command("traceroute", "-n", "-q", "1", "-w", "2", "-m", "30", req.Target)

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()

	result.LatencyMS = float64(time.Since(startTime).Microseconds()) / 1000.0

	output := stdout.String()
	if output == "" {
		output = stderr.String()
	}

	// Parse traceroute output
	hops := parseTracerouteOutput(output)

	if len(hops) == 0 && err != nil {
		result.Success = false
		result.Error = fmt.Sprintf("Traceroute failed: %v", err)
		if output != "" {
			result.Error += fmt.Sprintf(" - Output: %s", strings.TrimSpace(output))
		}
		return result, err
	}

	result.Success = true
	result.Hops = hops
	result.RouteInfo = fmt.Sprintf("Traceroute completed with %d hops", len(hops))

	// Populate raw results with detailed information
	result.RawResults = make(map[string]interface{})
	result.RawResults["target"] = req.Target
	result.RawResults["latency_ms"] = result.LatencyMS
	result.RawResults["hop_count"] = len(hops)
	result.RawResults["traceroute_output"] = output
	result.RawResults["command"] = "traceroute -n -q 1 -w 2 -m 30"
	result.RawResults["timeout"] = timeout
	result.RawResults["max_hops"] = 30

	// Try to resolve target IP for additional info
	if ips, err := net.LookupIP(req.Target); err == nil && len(ips) > 0 {
		result.RawResults["target_ip"] = ips[0].String()
		result.RawResults["resolved_ips"] = ips
	}

	// Add individual hop details
	if len(hops) > 0 {
		result.RawResults["hops"] = hops
		result.RawResults["detailed_hops"] = parseTracerouteDetailed(output)
	}

	return result, nil
}

// TestUDPTrace performs a UDP traceroute using traceroute with UDP mode
func TestUDPTrace(req UDPTraceRequest) (*TraceResult, error) {
	result := &TraceResult{
		Target:   req.Target,
		Protocol: "udp_trace",
	}

	// Default port to 53 (DNS) if not specified
	port := req.Port
	if port == 0 {
		port = 53
	}

	timeout := req.Timeout
	if timeout == 0 {
		timeout = 30
	}

	target := req.Target
	portStr := fmt.Sprintf("%d", port)

	startTime := time.Now()

	// Try to resolve the target
	ips, err := net.LookupIP(target)
	if err != nil {
		result.Success = false
		result.Error = fmt.Sprintf("DNS resolution failed: %v", err)
		return result, err
	}

	if len(ips) == 0 {
		result.Success = false
		result.Error = "No IP addresses found for target"
		return result, fmt.Errorf("%s", result.Error)
	}

	// Run traceroute in UDP mode (default mode for traceroute)
	// -n: numeric output (no DNS lookups)
	// -q 1: send only 1 query per hop
	// -w 2: wait 2 seconds for response
	// -m 30: max 30 hops
	// -p: port to use
	cmd := exec.Command("traceroute", "-n", "-q", "1", "-w", "2", "-m", "30", "-p", portStr, target)

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err = cmd.Run()

	result.LatencyMS = float64(time.Since(startTime).Microseconds()) / 1000.0

	output := stdout.String()
	if output == "" {
		output = stderr.String()
	}

	// Parse traceroute output
	hops := parseTracerouteOutput(output)

	if len(hops) == 0 && err != nil {
		// If traceroute failed, try a simple UDP connection to show at least the final hop
		conn, dialErr := net.DialTimeout("udp", fmt.Sprintf("%s:%d", target, port), 5*time.Second)
		if dialErr == nil {
			conn.Close()
			hops = append(hops, fmt.Sprintf("Direct UDP connection to %s:%d successful", ips[0].String(), port))
			result.Success = true
		} else {
			result.Success = false
			result.Error = fmt.Sprintf("UDP trace failed: %v", dialErr)
			if output != "" {
				result.Error += fmt.Sprintf(" - Output: %s", strings.TrimSpace(output))
			}
			return result, dialErr
		}
	} else {
		result.Success = true
	}

	result.Hops = hops
	result.RouteInfo = fmt.Sprintf("UDP trace to %s:%d completed with %d hops", target, port, len(hops))

	// Populate raw results with detailed information
	result.RawResults = make(map[string]interface{})
	result.RawResults["target"] = target
	result.RawResults["target_port"] = port
	result.RawResults["target_ip"] = ips[0].String()
	result.RawResults["resolved_ips"] = ips
	result.RawResults["latency_ms"] = result.LatencyMS
	result.RawResults["hop_count"] = len(hops)
	result.RawResults["traceroute_output"] = output
	result.RawResults["command"] = fmt.Sprintf("traceroute -n -q 1 -w 2 -m 30 -p %s", portStr)
	result.RawResults["timeout"] = timeout
	result.RawResults["max_hops"] = 30

	// Add individual hop details
	if len(hops) > 0 {
		result.RawResults["hops"] = hops
		result.RawResults["detailed_hops"] = parseTracerouteDetailed(output)
	}

	return result, nil
}

// parseTracerouteOutput parses traceroute command output into hop strings
func parseTracerouteOutput(output string) []string {
	var hops []string
	lines := strings.Split(output, "\n")

	// Regex to match traceroute lines
	hopRegex := regexp.MustCompile(`^\s*(\d+)\s+(.+)$`)

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "traceroute") {
			continue
		}

		matches := hopRegex.FindStringSubmatch(line)
		if len(matches) >= 3 {
			hopNum := matches[1]
			hopInfo := strings.TrimSpace(matches[2])

			// Clean up the hop info
			hopInfo = strings.ReplaceAll(hopInfo, "  ", " ")

			hops = append(hops, fmt.Sprintf("Hop %s: %s", hopNum, hopInfo))
		}
	}

	return hops
}

// parseTracerouteDetailed parses traceroute command output into detailed hop objects
func parseTracerouteDetailed(output string) []HopDetail {
	var hops []HopDetail
	lines := strings.Split(output, "\n")

	// Regex patterns for parsing
	hopRegex := regexp.MustCompile(`^\s*(\d+)\s+(.+)$`)
	ipRegex := regexp.MustCompile(`(\d+\.\d+\.\d+\.\d+)`)
	latencyRegex := regexp.MustCompile(`(\d+\.?\d*)\s*ms`)

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "traceroute") {
			continue
		}

		matches := hopRegex.FindStringSubmatch(line)
		if len(matches) >= 3 {
			hopNum := matches[1]
			hopInfo := strings.TrimSpace(matches[2])

			hop := HopDetail{
				HopNumber: 0,
				RawOutput: hopInfo,
			}

			// Parse hop number
			if num, err := fmt.Sscanf(hopNum, "%d", &hop.HopNumber); err == nil && num > 0 {
				// Successfully parsed hop number
			}

			// Check for timeout
			if strings.Contains(hopInfo, "*") || strings.Contains(hopInfo, "!") {
				hop.Timeout = true
			}

			// Extract IP address
			if ipMatch := ipRegex.FindString(hopInfo); ipMatch != "" {
				hop.IPAddress = ipMatch
			}

			// Extract latency
			if latencyMatch := latencyRegex.FindString(hopInfo); latencyMatch != "" {
				hop.Latency = latencyMatch
			}

			hops = append(hops, hop)
		}
	}

	return hops
}

// Helper function to get TLS version string
func getTLSVersion(version uint16) string {
	switch version {
	case 0x0300:
		return "SSL 3.0"
	case 0x0301:
		return "TLS 1.0"
	case 0x0302:
		return "TLS 1.1"
	case 0x0303:
		return "TLS 1.2"
	case 0x0304:
		return "TLS 1.3"
	default:
		return fmt.Sprintf("Unknown (0x%04x)", version)
	}
}

// Helper function to get cipher suite name
func getCipherSuite(suite uint16) string {
	// Add common cipher suites
	suites := map[uint16]string{
		0x1301: "TLS_AES_128_GCM_SHA256",
		0x1302: "TLS_AES_256_GCM_SHA384",
		0x1303: "TLS_CHACHA20_POLY1305_SHA256",
		0xc02f: "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
		0xc030: "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
		0xcca8: "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256",
	}

	if name, ok := suites[suite]; ok {
		return name
	}
	return fmt.Sprintf("Unknown (0x%04x)", suite)
}

func (r *TraceResult) ToJSON() ([]byte, error) {
	return json.Marshal(r)
}
