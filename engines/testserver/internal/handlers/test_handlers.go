package handlers

import (
	"encoding/json"
	"log"
	"net/http"

	"github.com/penguintechinc/tobogganing/engines/testserver/internal/auth"
	"github.com/penguintechinc/tobogganing/engines/testserver/internal/database"
	"github.com/penguintechinc/tobogganing/engines/testserver/internal/protocols"
	"github.com/penguintechinc/tobogganing/engines/testserver/internal/validation"
)

// TestResultStore is satisfied by *database.DB and allows test injection.
type TestResultStore interface {
	InsertTestResult(result *database.TestResult) (int64, error)
}

type TestHandlers struct {
	db TestResultStore
}

// New creates a TestHandlers backed by a real *database.DB.
func New(db *database.DB) *TestHandlers {
	return &TestHandlers{db: db}
}

// NewWithStore creates a TestHandlers backed by any TestResultStore implementation.
// This is used in tests to inject a mock store.
func NewWithStore(store TestResultStore) *TestHandlers {
	return &TestHandlers{db: store}
}

func (h *TestHandlers) HTTPTestHandler(w http.ResponseWriter, r *http.Request) {
	var req protocols.HTTPTestRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Validate inputs
	if err := validation.ValidateTarget(req.Target); err != nil {
		log.Printf("HTTP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := validation.ValidateHTTPProtocol(req.Protocol); err != nil {
		log.Printf("HTTP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := validation.ValidateHTTPProtocol(req.ProtocolDetail); err != nil {
		log.Printf("HTTP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := validation.ValidateHTTPMethod(req.Method); err != nil {
		log.Printf("HTTP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if req.Timeout > 0 {
		if err := validation.ValidateTimeout(req.Timeout); err != nil {
			log.Printf("HTTP test validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}

	// Sanitize inputs
	req.Target = validation.SanitizeString(req.Target, validation.MaxTargetLength)
	req.Protocol = validation.SanitizeString(req.Protocol, validation.MaxProtocolLength)
	req.ProtocolDetail = validation.SanitizeString(req.ProtocolDetail, validation.MaxProtocolLength)
	req.Method = validation.SanitizeString(req.Method, validation.MaxMethodLength)

	result, err := protocols.TestHTTP(req)
	if err != nil {
		log.Printf("HTTP test failed: %v", err)
		http.Error(w, "Test execution failed", http.StatusInternalServerError)
		return
	}

	if err := h.saveTestResult(r, "http", req.Protocol, req.Target, result); err != nil {
		log.Printf("Failed to save test result: %v", err)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (h *TestHandlers) TCPTestHandler(w http.ResponseWriter, r *http.Request) {
	var req protocols.TCPTestRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Validate inputs
	if err := validation.ValidateTarget(req.Target); err != nil {
		log.Printf("TCP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := validation.ValidateTCPProtocol(req.Protocol); err != nil {
		log.Printf("TCP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := validation.ValidateTCPProtocol(req.ProtocolDetail); err != nil {
		log.Printf("TCP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if req.Port > 0 {
		if err := validation.ValidatePort(req.Port); err != nil {
			log.Printf("TCP test validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}
	if req.Timeout > 0 {
		if err := validation.ValidateTimeout(req.Timeout); err != nil {
			log.Printf("TCP test validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}

	// Sanitize inputs
	req.Target = validation.SanitizeString(req.Target, validation.MaxTargetLength)
	req.Protocol = validation.SanitizeString(req.Protocol, validation.MaxProtocolLength)
	req.ProtocolDetail = validation.SanitizeString(req.ProtocolDetail, validation.MaxProtocolLength)

	result, err := protocols.TestTCP(req)
	if err != nil {
		log.Printf("TCP test failed: %v", err)
		http.Error(w, "Test execution failed", http.StatusInternalServerError)
		return
	}

	if err := h.saveTestResult(r, "tcp", req.Protocol, req.Target, result); err != nil {
		log.Printf("Failed to save test result: %v", err)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (h *TestHandlers) UDPTestHandler(w http.ResponseWriter, r *http.Request) {
	var req protocols.UDPTestRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Validate inputs
	if err := validation.ValidateTarget(req.Target); err != nil {
		log.Printf("UDP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := validation.ValidateUDPProtocol(req.Protocol); err != nil {
		log.Printf("UDP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := validation.ValidateUDPProtocol(req.ProtocolDetail); err != nil {
		log.Printf("UDP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := validation.ValidateDNSQuery(req.Query); err != nil {
		log.Printf("UDP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if req.Port > 0 {
		if err := validation.ValidatePort(req.Port); err != nil {
			log.Printf("UDP test validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}
	if req.Timeout > 0 {
		if err := validation.ValidateTimeout(req.Timeout); err != nil {
			log.Printf("UDP test validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}

	// Sanitize inputs
	req.Target = validation.SanitizeString(req.Target, validation.MaxTargetLength)
	req.Protocol = validation.SanitizeString(req.Protocol, validation.MaxProtocolLength)
	req.ProtocolDetail = validation.SanitizeString(req.ProtocolDetail, validation.MaxProtocolLength)
	req.Query = validation.SanitizeString(req.Query, validation.MaxQueryLength)

	result, err := protocols.TestUDP(req)
	if err != nil {
		log.Printf("UDP test failed: %v", err)
		http.Error(w, "Test execution failed", http.StatusInternalServerError)
		return
	}

	if err := h.saveTestResult(r, "udp", req.Protocol, req.Target, result); err != nil {
		log.Printf("Failed to save test result: %v", err)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (h *TestHandlers) ICMPTestHandler(w http.ResponseWriter, r *http.Request) {
	var req protocols.ICMPTestRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Validate inputs
	if err := validation.ValidateTarget(req.Target); err != nil {
		log.Printf("ICMP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := validation.ValidateICMPProtocol(req.Protocol); err != nil {
		log.Printf("ICMP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := validation.ValidateICMPProtocol(req.ProtocolDetail); err != nil {
		log.Printf("ICMP test validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if req.Count > 0 {
		if err := validation.ValidateCount(req.Count); err != nil {
			log.Printf("ICMP test validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}
	if req.Timeout > 0 {
		if err := validation.ValidateTimeout(req.Timeout); err != nil {
			log.Printf("ICMP test validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}

	// Sanitize inputs
	req.Target = validation.SanitizeString(req.Target, validation.MaxTargetLength)
	req.Protocol = validation.SanitizeString(req.Protocol, validation.MaxProtocolLength)
	req.ProtocolDetail = validation.SanitizeString(req.ProtocolDetail, validation.MaxProtocolLength)

	result, err := protocols.TestICMP(req)
	if err != nil {
		log.Printf("ICMP test failed: %v", err)
		http.Error(w, "Test execution failed", http.StatusInternalServerError)
		return
	}

	if err := h.saveTestResult(r, "icmp", req.Protocol, req.Target, result); err != nil {
		log.Printf("Failed to save test result: %v", err)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (h *TestHandlers) HTTPTraceHandler(w http.ResponseWriter, r *http.Request) {
	var req protocols.HTTPTraceRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Validate inputs
	if err := validation.ValidateTarget(req.Target); err != nil {
		log.Printf("HTTP trace validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if req.Port > 0 {
		if err := validation.ValidatePort(req.Port); err != nil {
			log.Printf("HTTP trace validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}
	if req.Timeout > 0 {
		if err := validation.ValidateTimeout(req.Timeout); err != nil {
			log.Printf("HTTP trace validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}

	// Sanitize inputs
	req.Target = validation.SanitizeString(req.Target, validation.MaxTargetLength)

	result, err := protocols.TestHTTPTrace(req)
	if err != nil {
		log.Printf("HTTP trace failed: %v", err)
		http.Error(w, "Test execution failed", http.StatusInternalServerError)
		return
	}

	if err := h.saveTestResult(r, "http_trace", "http_trace", req.Target, result); err != nil {
		log.Printf("Failed to save test result: %v", err)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (h *TestHandlers) TCPTraceHandler(w http.ResponseWriter, r *http.Request) {
	var req protocols.TCPTraceRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Validate inputs
	if err := validation.ValidateTarget(req.Target); err != nil {
		log.Printf("TCP trace validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if req.Port > 0 {
		if err := validation.ValidatePort(req.Port); err != nil {
			log.Printf("TCP trace validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}
	if req.Timeout > 0 {
		if err := validation.ValidateTimeout(req.Timeout); err != nil {
			log.Printf("TCP trace validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}

	// Sanitize inputs
	req.Target = validation.SanitizeString(req.Target, validation.MaxTargetLength)

	result, err := protocols.TestTCPTrace(req)
	if err != nil {
		log.Printf("TCP trace failed: %v", err)
		http.Error(w, "Test execution failed", http.StatusInternalServerError)
		return
	}

	if err := h.saveTestResult(r, "tcp_trace", "tcp_trace", req.Target, result); err != nil {
		log.Printf("Failed to save test result: %v", err)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (h *TestHandlers) TracerouteHandler(w http.ResponseWriter, r *http.Request) {
	var req protocols.TracerouteRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Validate inputs
	if err := validation.ValidateTarget(req.Target); err != nil {
		log.Printf("Traceroute validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if req.Timeout > 0 {
		if err := validation.ValidateTimeout(req.Timeout); err != nil {
			log.Printf("Traceroute validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}

	// Sanitize inputs
	req.Target = validation.SanitizeString(req.Target, validation.MaxTargetLength)

	result, err := protocols.TestTraceroute(req)
	if err != nil {
		log.Printf("Traceroute failed: %v", err)
		http.Error(w, "Test execution failed", http.StatusInternalServerError)
		return
	}

	if err := h.saveTestResult(r, "traceroute", "icmp", req.Target, result); err != nil {
		log.Printf("Failed to save test result: %v", err)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (h *TestHandlers) UDPTraceHandler(w http.ResponseWriter, r *http.Request) {
	var req protocols.UDPTraceRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Validate inputs
	if err := validation.ValidateTarget(req.Target); err != nil {
		log.Printf("UDP trace validation failed: %v", err)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if req.Port > 0 {
		if err := validation.ValidatePort(req.Port); err != nil {
			log.Printf("UDP trace validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}
	if req.Timeout > 0 {
		if err := validation.ValidateTimeout(req.Timeout); err != nil {
			log.Printf("UDP trace validation failed: %v", err)
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}

	// Sanitize inputs
	req.Target = validation.SanitizeString(req.Target, validation.MaxTargetLength)

	result, err := protocols.TestUDPTrace(req)
	if err != nil {
		log.Printf("UDP trace failed: %v", err)
		http.Error(w, "Test execution failed", http.StatusInternalServerError)
		return
	}

	if err := h.saveTestResult(r, "udp_trace", "udp", req.Target, result); err != nil {
		log.Printf("Failed to save test result: %v", err)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (h *TestHandlers) HealthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"status":  "healthy",
		"version": "1.0.0",
	})
}

func (h *TestHandlers) saveTestResult(r *http.Request, testType, protocolDetail, targetHost string, resultData interface{}) error {
	user := auth.GetUser(r.Context())

	// Get device info from headers
	deviceSerial := r.Header.Get("X-Device-Serial")
	if deviceSerial == "" {
		deviceSerial = "unknown"
	}
	deviceHostname := r.Header.Get("X-Device-Hostname")
	if deviceHostname == "" {
		deviceHostname = "unknown"
	}
	deviceOS := r.Header.Get("X-Device-OS")
	if deviceOS == "" {
		deviceOS = "unknown"
	}
	deviceOSVersion := r.Header.Get("X-Device-OS-Version")
	if deviceOSVersion == "" {
		deviceOSVersion = "unknown"
	}

	// Get client IP
	clientIP := r.RemoteAddr
	if forwarded := r.Header.Get("X-Forwarded-For"); forwarded != "" {
		clientIP = forwarded
	}

	// Extract metrics from result
	var latency, throughput, jitter, packetLoss *float64
	targetIP := targetHost
	rawResults := make(map[string]interface{})

	switch v := resultData.(type) {
	case *protocols.HTTPTestResult:
		latency = &v.LatencyMS
		if v.JitterMS > 0 {
			jitter = &v.JitterMS
		}
		rawResults["status_code"] = v.StatusCode
		rawResults["ttfb_ms"] = v.TTFBMS
		rawResults["total_time_ms"] = v.TotalTimeMS
		rawResults["min_latency_ms"] = v.MinLatencyMS
		rawResults["max_latency_ms"] = v.MaxLatencyMS
	case *protocols.TCPTestResult:
		latency = &v.LatencyMS
		if v.JitterMS > 0 {
			jitter = &v.JitterMS
		}
		if v.HandshakeMS > 0 {
			rawResults["handshake_ms"] = v.HandshakeMS
		}
		rawResults["min_latency_ms"] = v.MinLatencyMS
		rawResults["max_latency_ms"] = v.MaxLatencyMS
		targetIP = v.RemoteAddr
	case *protocols.UDPTestResult:
		latency = &v.LatencyMS
		if v.JitterMS > 0 {
			jitter = &v.JitterMS
		}
		rawResults["min_latency_ms"] = v.MinLatencyMS
		rawResults["max_latency_ms"] = v.MaxLatencyMS
		targetIP = v.RemoteAddr
	case *protocols.ICMPTestResult:
		latency = &v.LatencyMS
		jitter = &v.JitterMS
		packetLoss = &v.PacketLossPercent
		rawResults["packets_sent"] = v.PacketsSent
		rawResults["packets_received"] = v.PacketsReceived
	case *protocols.TraceResult:
		latency = &v.LatencyMS
		if v.Hops != nil && len(v.Hops) > 0 {
			rawResults["hops"] = v.Hops
			rawResults["hop_count"] = len(v.Hops)
		}
		if v.RouteInfo != "" {
			rawResults["route_info"] = v.RouteInfo
		}
	case map[string]interface{}:
		// Handle speedtest results (passed as map)
		if lat, ok := v["latency_ms"].(float64); ok {
			latency = &lat
		}
		if thr, ok := v["throughput"].(float64); ok {
			throughput = &thr
		}
		if jit, ok := v["jitter_ms"].(float64); ok {
			jitter = &jit
		}
		// Copy all values to rawResults
		for k, val := range v {
			rawResults[k] = val
		}
		targetIP = "self" // speedtest is to the server itself
	}

	testResult := &database.TestResult{
		DeviceSerial:      deviceSerial,
		DeviceHostname:    deviceHostname,
		DeviceOS:          deviceOS,
		DeviceOSVersion:   deviceOSVersion,
		TestType:          testType,
		ProtocolDetail:    protocolDetail,
		TargetHost:        targetHost,
		TargetIP:          targetIP,
		ClientIP:          clientIP,
		LatencyMS:         latency,
		ThroughputMbps:    throughput,
		JitterMS:          jitter,
		PacketLossPercent: packetLoss,
		RawResults:        rawResults,
	}

	if user != nil {
		testResult.UserID = &user.ID
	}

	_, err := h.db.InsertTestResult(testResult)
	return err
}
