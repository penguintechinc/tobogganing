package handlers

import (
	"crypto/rand"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strconv"
	"time"
)

// SpeedTestDownloadHandler serves random data for download speed testing
// Query parameters:
//   - size: chunk size in MB (default 10, max 100)
//   - duration: test duration hint in seconds (not enforced server-side)
func (h *TestHandlers) SpeedTestDownloadHandler(w http.ResponseWriter, r *http.Request) {
	// Parse size parameter (in megabytes)
	sizeStr := r.URL.Query().Get("size")
	sizeMB := 10 // Default 10MB chunks
	if sizeStr != "" {
		if parsed, err := strconv.Atoi(sizeStr); err == nil && parsed > 0 && parsed <= 100 {
			sizeMB = parsed
		}
	}

	sizeBytes := int64(sizeMB) * 1024 * 1024

	// Set headers for download
	w.Header().Set("Content-Type", "application/octet-stream")
	w.Header().Set("Content-Length", fmt.Sprintf("%d", sizeBytes))
	w.Header().Set("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
	w.Header().Set("Pragma", "no-cache")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Expose-Headers", "Content-Length")

	// Generate and stream random data
	// Using a buffer to improve performance
	bufferSize := 64 * 1024 // 64KB buffer
	buffer := make([]byte, bufferSize)
	remaining := sizeBytes

	for remaining > 0 {
		chunkSize := int64(bufferSize)
		if remaining < chunkSize {
			chunkSize = remaining
		}

		// Generate random data
		if _, err := rand.Read(buffer[:chunkSize]); err != nil {
			log.Printf("Error generating random data: %v", err)
			return
		}

		// Write to response
		if _, err := w.Write(buffer[:chunkSize]); err != nil {
			// Client disconnected
			return
		}

		remaining -= chunkSize
	}
}

// SpeedTestUploadHandler receives data for upload speed testing
// Simply reads and discards the data
func (h *TestHandlers) SpeedTestUploadHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Read and discard body
	startTime := time.Now()
	bytesReceived, err := io.Copy(io.Discard, r.Body)
	duration := time.Since(startTime)

	if err != nil {
		http.Error(w, "Error reading upload data", http.StatusInternalServerError)
		return
	}

	// Calculate throughput
	throughputMbps := 0.0
	if duration.Seconds() > 0 {
		throughputMbps = (float64(bytesReceived) * 8) / (duration.Seconds() * 1_000_000)
	}

	// Return success with stats
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"success":         true,
		"bytes_received":  bytesReceived,
		"duration_ms":     duration.Milliseconds(),
		"throughput_mbps": throughputMbps,
	})
}

// SpeedTestPingHandler provides low-latency ping endpoint for latency measurement
func (h *TestHandlers) SpeedTestPingHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
	w.Header().Set("Pragma", "no-cache")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	json.NewEncoder(w).Encode(map[string]interface{}{
		"pong":      true,
		"timestamp": time.Now().UnixMilli(),
	})
}

// SpeedTestInfoHandler returns server capabilities and configuration
func (h *TestHandlers) SpeedTestInfoHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	json.NewEncoder(w).Encode(map[string]interface{}{
		"name":                  "WaddlePerf SpeedTest",
		"version":               "1.0.0",
		"max_chunk_size_mb":     100,
		"default_chunk_size_mb": 10,
		"recommended_streams":   6,
		"max_streams":           32,
	})
}

// SpeedTestResultRequest represents a completed speedtest result from the client
type SpeedTestResultRequest struct {
	DownloadMbps float64 `json:"download_mbps"`
	UploadMbps   float64 `json:"upload_mbps"`
	LatencyMS    float64 `json:"latency_ms"`
	JitterMS     float64 `json:"jitter_ms"`
	ServerURL    string  `json:"server_url"`
}

// SpeedTestResultHandler saves speedtest results to the database
func (h *TestHandlers) SpeedTestResultHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req SpeedTestResultRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Save to database using saveTestResult helper
	// For speedtest, we'll use download as throughput and set appropriate metrics
	if err := h.saveSpeedTestResult(r, req); err != nil {
		log.Printf("Failed to save speedtest result: %v", err)
		http.Error(w, "Failed to save result", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"success": true,
		"message": "Speedtest result saved successfully",
	})
}

// saveSpeedTestResult is a helper to save speedtest results
func (h *TestHandlers) saveSpeedTestResult(r *http.Request, req SpeedTestResultRequest) error {
	// Build result data that matches the generic saveTestResult expectations
	resultData := map[string]interface{}{
		"latency_ms":    req.LatencyMS,
		"throughput":    req.DownloadMbps,
		"download_mbps": req.DownloadMbps,
		"upload_mbps":   req.UploadMbps,
		"jitter_ms":     req.JitterMS,
	}

	return h.saveTestResult(r, "speedtest", "download_upload", req.ServerURL, resultData)
}
